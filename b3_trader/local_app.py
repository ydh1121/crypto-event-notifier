from __future__ import annotations

import os
import secrets
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles

from .assets import AssetProfile, AssetRegistry, default_profile, normalize_market
from .config import Settings
from .journal import TradeJournal
from .local_engine import MultiAssetEngine
from .runtime_config import RuntimeConfigStore
from .runtime_state import RuntimeState
from .sync_manager import BackupManager, GitAutoSync
from .telegram_notify import TelegramNotifier
from .telegram_settings import TelegramSettingsStore

RESTART_EXIT_CODE = 75
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def _dashboard_token(settings: Settings) -> str:
    if settings.dashboard_token:
        return settings.dashboard_token
    token_file = Path("b3_trader/data/dashboard-token.txt")
    token_file.parent.mkdir(parents=True, exist_ok=True)
    if token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    token_file.write_text(token + "\n", encoding="utf-8")
    return token


def create_app() -> FastAPI:
    load_dotenv()
    settings = Settings()
    state = RuntimeState()
    registry = AssetRegistry(settings.asset_registry_path)
    runtime_config = RuntimeConfigStore(settings.runtime_config_path)
    journal = TradeJournal(settings.journal_db)

    telegram_store = TelegramSettingsStore(
        default_enabled=settings.telegram_enabled,
        default_token=settings.telegram_token,
        default_chat_id=settings.telegram_chat_id,
    )
    telegram_settings = telegram_store.load()
    notifier = TelegramNotifier(
        telegram_settings.token,
        telegram_settings.chat_id,
        enabled=telegram_settings.enabled,
    )

    token = _dashboard_token(settings)
    engine = MultiAssetEngine(
        settings=settings,
        registry=registry,
        runtime_config=runtime_config,
        journal=journal,
        state=state,
        notifier=notifier,
    )
    restart_lock = threading.Lock()
    restart_scheduled = False

    def request_restart() -> None:
        nonlocal restart_scheduled
        with restart_lock:
            if restart_scheduled:
                return
            restart_scheduled = True
            state.restart_required = True
        threading.Timer(3.0, lambda: os._exit(RESTART_EXIT_CODE)).start()

    git_sync = GitAutoSync(
        repo_dir=settings.git_repo_dir,
        branch=settings.git_sync_branch,
        enabled=settings.auto_git_sync,
        interval_seconds=settings.git_sync_interval_seconds,
        state=state,
        notifier=notifier,
        on_restart_required=request_restart,
        block_code_updates=settings.live_trading_armed,
        push_control_changes=settings.auto_git_push_control,
    )
    backup = BackupManager(
        sqlite_path=settings.journal_db,
        local_dir=settings.local_backup_dir,
        interval_seconds=settings.backup_interval_seconds,
        state=state,
        rclone_remote=settings.rclone_remote,
        repo_dir=settings.git_repo_dir,
        notifier=notifier,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        print(
            f"Dashboard: http://127.0.0.1:{settings.service_port}\n"
            "Local browser: automatic loopback authentication enabled.\n"
            f"Dashboard token for phone/LAN/Tailscale: {token}\n"
            "Phone on same Wi-Fi: use this PC's LAN IP with the same port."
        )
        engine.start()
        git_sync.start()
        backup.start()
        try:
            yield
        finally:
            git_sync.stop()
            backup.stop()
            engine.stop()
            journal.close()

    app = FastAPI(title="Crypto Auto Trader", version="0.4.2", lifespan=lifespan)

    def auth(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> None:
        client_host = request.client.host if request.client else ""
        if client_host in LOOPBACK_HOSTS:
            return
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid dashboard token")

    def publish_control(message: str) -> None:
        try:
            git_sync.publish_control(message)
        except Exception as exc:
            state.set_error(exc, scope="git_publish")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        snapshot = state.snapshot()
        return {
            "ok": True,
            "mode": "PAPER",
            "uptime_seconds": snapshot["uptime_seconds"],
            "assets": len(snapshot["assets"]),
            "paused": snapshot["paused"],
            "kill_switch": snapshot["kill_switch"],
        }

    @app.get("/api/state", dependencies=[Depends(auth)])
    def api_state() -> dict[str, Any]:
        return {"mode": "PAPER", **state.snapshot()}

    @app.get("/api/assets", dependencies=[Depends(auth)])
    def api_assets() -> list[dict[str, Any]]:
        return [profile.to_dict() for profile in registry.list()]

    @app.post("/api/assets", dependencies=[Depends(auth)])
    def add_asset(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        ticker = str(payload.get("ticker") or payload.get("market") or "")
        profile = default_profile(ticker)
        if payload.get("context_mode"):
            profile = AssetProfile.from_dict({**profile.to_dict(), **payload})
        registry.upsert(profile)
        journal.record_event("asset_added", profile.to_dict())
        notifier.safe_send(
            f"[{profile.symbol}] 감시 자산 추가\n컨텍스트: {profile.context_mode}",
            event_key=f"asset-added-{profile.market}",
        )
        publish_control(f"Add {profile.market} trader profile")
        return profile.to_dict()

    @app.put("/api/assets/{market:path}", dependencies=[Depends(auth)])
    def update_asset(
        market: str,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        market = normalize_market(market)
        current = registry.get(market)
        if current is None:
            raise HTTPException(status_code=404, detail="asset not found")
        profile = AssetProfile.from_dict({**current.to_dict(), **payload, "market": market})
        registry.upsert(profile)
        journal.record_event("asset_updated", profile.to_dict())
        publish_control(f"Update {profile.market} trader profile")
        return profile.to_dict()

    @app.delete("/api/assets/{market:path}", dependencies=[Depends(auth)])
    def remove_asset(market: str) -> dict[str, Any]:
        market = normalize_market(market)
        if not registry.remove(market):
            raise HTTPException(status_code=404, detail="asset not found")
        journal.record_event("asset_removed", {"market": market})
        publish_control(f"Remove {market} trader profile")
        return {"ok": True, "market": market}

    @app.get("/api/config", dependencies=[Depends(auth)])
    def get_runtime_config() -> dict[str, Any]:
        return asdict(runtime_config.get())

    @app.patch("/api/config", dependencies=[Depends(auth)])
    def patch_runtime_config(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        config = runtime_config.patch(payload)
        journal.record_event("runtime_config_updated", payload)
        publish_control("Update trader runtime config")
        return asdict(config)

    @app.post("/api/control/pause", dependencies=[Depends(auth)])
    def pause() -> dict[str, Any]:
        state.paused = True
        journal.record_event("manual_pause", {})
        notifier.safe_send("Crypto Auto Trader: 신규 진입 일시정지")
        return {"ok": True, "paused": True}

    @app.post("/api/control/resume", dependencies=[Depends(auth)])
    def resume() -> dict[str, Any]:
        if state.kill_switch:
            raise HTTPException(status_code=409, detail="reset kill switch first")
        state.paused = False
        journal.record_event("manual_resume", {})
        notifier.safe_send("Crypto Auto Trader: 신규 진입 재개")
        return {"ok": True, "paused": False}

    @app.post("/api/control/kill", dependencies=[Depends(auth)])
    def kill() -> dict[str, Any]:
        state.kill_switch = True
        state.paused = True
        journal.record_event("manual_kill_switch", {})
        notifier.safe_send("Crypto Auto Trader: KILL SWITCH 활성")
        return {"ok": True, "kill_switch": True}

    @app.post("/api/control/reset-kill", dependencies=[Depends(auth)])
    def reset_kill() -> dict[str, Any]:
        state.kill_switch = False
        state.paused = True
        journal.record_event("manual_kill_switch_reset", {})
        notifier.safe_send("Crypto Auto Trader: KILL SWITCH 해제 (진입은 아직 일시정지)")
        return {"ok": True, "kill_switch": False, "paused": True}

    @app.get("/api/fills", dependencies=[Depends(auth)])
    def fills(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
        return journal.recent_fills(limit)

    @app.get("/api/events", dependencies=[Depends(auth)])
    def events(limit: int = Query(default=100, ge=1, le=1000)) -> list[dict[str, Any]]:
        return journal.recent_events(limit)

    @app.get("/api/telegram/status", dependencies=[Depends(auth)])
    def telegram_status() -> dict[str, Any]:
        return notifier.status()

    @app.put("/api/telegram/config", dependencies=[Depends(auth)])
    def telegram_config(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        current = telegram_store.load()
        enabled = bool(payload.get("enabled", current.enabled))
        supplied_token = str(payload.get("token") or "").strip()
        supplied_chat_id = str(payload.get("chat_id") or "").strip()
        next_token = supplied_token or current.token
        next_chat_id = supplied_chat_id or current.chat_id

        if enabled and (not next_token or not next_chat_id):
            raise HTTPException(
                status_code=422,
                detail="Telegram bot token and chat ID are required",
            )

        updated = telegram_store.patch(
            enabled=enabled,
            token=supplied_token if supplied_token else None,
            chat_id=supplied_chat_id if supplied_chat_id else None,
        )
        notifier.configure(
            token=updated.token,
            chat_id=updated.chat_id,
            enabled=updated.enabled,
        )
        journal.record_event(
            "telegram_config_updated",
            {
                "enabled": notifier.enabled,
                "configured": bool(updated.token and updated.chat_id),
                "chat_id": updated.chat_id,
            },
        )
        return notifier.status()

    @app.post("/api/telegram/test", dependencies=[Depends(auth)])
    def telegram_test() -> dict[str, Any]:
        if not notifier.enabled:
            raise HTTPException(
                status_code=409,
                detail="Telegram is not configured or enabled",
            )
        try:
            ok = notifier.send("Crypto Auto Trader 텔레그램 연결 테스트")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"ok": ok}

    @app.post("/api/backup", dependencies=[Depends(auth)])
    def backup_now() -> dict[str, Any]:
        return backup.backup_once()

    @app.post("/api/sync", dependencies=[Depends(auth)])
    def sync_now() -> dict[str, Any]:
        return git_sync.check_once()

    dashboard = Path(settings.dashboard_dir)
    if dashboard.exists():
        app.mount("/", StaticFiles(directory=str(dashboard), html=True), name="dashboard")

    app.state.trader_state = state
    app.state.registry = registry
    app.state.runtime_config = runtime_config
    app.state.journal = journal
    app.state.engine = engine
    app.state.git_sync = git_sync
    app.state.backup = backup
    app.state.telegram_store = telegram_store
    app.state.dashboard_token = token
    return app


app = create_app()


def run() -> None:
    load_dotenv()
    settings = Settings()
    uvicorn.run(
        app,
        host=settings.service_host,
        port=settings.service_port,
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    run()
