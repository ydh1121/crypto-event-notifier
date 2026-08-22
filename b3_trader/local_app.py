from __future__ import annotations

import os
import secrets
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .assets import AssetProfile, AssetRegistry, default_profile, normalize_market
from .config import Settings
from .journal import TradeJournal
from .local_engine import MultiAssetEngine
from .runtime_config import RuntimeConfigStore
from .runtime_state import RuntimeState
from .sync_manager import BackupManager, GitAutoSync
from .telegram_notify import TelegramNotifier

RESTART_EXIT_CODE = 75


def _dashboard_token(settings: Settings) -> str:
    if settings.dashboard_token:
        return settings.dashboard_token
    token_file = Path("b3_trader/data/dashboard-token.txt")
    token_file.parent.mkdir(parents=True, exist_ok=True)
    if token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token: return token
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
    notifier = TelegramNotifier(settings.telegram_token, settings.telegram_chat_id, enabled=settings.telegram_enabled)
    token = _dashboard_token(settings)
    engine = MultiAssetEngine(settings=settings, registry=registry, runtime_config=runtime_config, journal=journal, state=state, notifier=notifier)
    restart_lock = threading.Lock()
    restart_scheduled = False

    def request_restart() -> None:
        nonlocal restart_scheduled
        with restart_lock:
            if restart_scheduled: return
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

    app = FastAPI(title="Crypto Auto Trader", version="0.4.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

    def auth(authorization: str | None = Header(default=None)) -> None:
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid dashboard token")

    def publish_control(message: str) -> None:
        try: git_sync.publish_control(message)
        except Exception as exc: state.set_error(exc, scope="git_publish")

    @app.on_event("startup")
    def on_startup() -> None:
        print(f"Dashboard: http://127.0.0.1:{settings.service_port}\nDashboard token: {token}\nPhone on same Wi-Fi: use this PC's LAN IP with the same port.")
        engine.start(); git_sync.start(); backup.start()

    @app.on_event("shutdown")
    def on_shutdown() -> None:
        git_sync.stop(); backup.stop(); engine.stop(); journal.close()

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        snapshot = state.snapshot()
        return {"ok": True, "mode": "PAPER", "uptime_seconds": snapshot["uptime_seconds"], "assets": len(snapshot["assets"]), "paused": snapshot["paused"], "kill_switch": snapshot["kill_switch"]}

    @app.get("/api/state", dependencies=[Depends(auth)])
    def api_state() -> dict[str, Any]: return {"mode": "PAPER", **state.snapshot()}

    @app.get("/api/assets", dependencies=[Depends(auth)])
    def api_assets() -> list[dict[str, Any]]: return [profile.to_dict() for profile in registry.list()]

    @app.post("/api/assets", dependencies=[Depends(auth)])
    def add_asset(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        ticker = str(payload.get("ticker") or payload.get("market") or "")
        profile = default_profile(ticker)
        if payload.get("context_mode"): profile = AssetProfile.from_dict({**profile.to_dict(), **payload})
        registry.upsert(profile)
        journal.record_event("asset_added", profile.to_dict())
        notifier.safe_send(f"[{profile.symbol}] 감시 자산 추가\n컨텍스트: {profile.context_mode}", event_key=f"asset-added-{profile.market}")
        publish_control(f"Add {profile.market} trader profile")
        return profile.to_dict()

    @app.put("/api/assets/{market:path}", dependencies=[Depends(auth)])
    def update_asset(market: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        market = normalize_market(market)
        current = registry.get(market)
        if current is None: raise HTTPException(status_code=404, detail="asset not found")
        profile = AssetProfile.from_dict({**current.to_dict(), **payload, "market": market})
        registry.upsert(profile); journal.record_event("asset_updated", profile.to_dict())
        publish_control(f"Update {profile.market} trader profile")
        return profile.to_dict()

    @app.delete("/api/assets/{market:path}", dependencies=[Depends(auth)])
    def remove_asset(market: str) -> dict[str, Any]:
        market = normalize_market(market)
        if not registry.remove(market): raise HTTPException(status_code=404, detail="asset not found")
        journal.record_event("asset_removed", {"market": market}); publish_control(f"Remove {market} trader profile")
        return {"ok": True, "market": market}

    @app.get("/api/config", dependencies=[Depends(auth)])
    def get_runtime_config() -> dict[str, Any]: return asdict(runtime_config.get())

    @app.patch("/api/config", dependencies=[Depends(auth)])
    def patch_runtime_config(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        config = runtime_config.patch(payload)
        journal.record_event("runtime_config_updated", payload); publish_control("Update trader runtime config")
        return asdict(config)

    @app.post("/api/control/pause", dependencies=[Depends(auth)])
    def pause() -> dict[str, Any]:
        state.paused = True; journal.record_event("manual_pause", {}); notifier.safe_send("Crypto Auto Trader: 신규 진입 일시정지")
        return {"ok": True, "paused": True}

    @app.post("/api/control/resume", dependencies=[Depends(auth)])
    def resume() -> dict[str, Any]:
        if state.kill_switch: raise HTTPException(status_code=409, detail="reset kill switch first")
        state.paused = False; journal.record_event("manual_resume", {}); notifier.safe_send("Crypto Auto Trader: 신규 진입 재개")
        return {"ok": True, "paused": False}

    @app.post("/api/control/kill", dependencies=[Depends(auth)])
    def kill() -> dict[str, Any]:
        state.kill_switch = True; state.paused = True; journal.record_event("manual_kill_switch", {}); notifier.safe_send("Crypto Auto Trader: KILL SWITCH 활성")
        return {"ok": True, "kill_switch": True}

    @app.post("/api/control/reset-kill", dependencies=[Depends(auth)])
    def reset_kill() -> dict[str, Any]:
        state.kill_switch = False; state.paused = True; journal.record_event("manual_kill_switch_reset", {}); notifier.safe_send("Crypto Auto Trader: KILL SWITCH 해제 (진입은 아직 일시정지)")
        return {"ok": True, "kill_switch": False, "paused": True}

    @app.get("/api/fills", dependencies=[Depends(auth)])
    def fills(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]: return journal.recent_fills(limit)

    @app.get("/api/events", dependencies=[Depends(auth)])
    def events(limit: int = Query(default=100, ge=1, le=1000)) -> list[dict[str, Any]]: return journal.recent_events(limit)

    @app.post("/api/telegram/test", dependencies=[Depends(auth)])
    def telegram_test() -> dict[str, Any]:
        if not notifier.enabled: raise HTTPException(status_code=409, detail="Telegram is not configured")
        return {"ok": notifier.safe_send("Crypto Auto Trader 텔레그램 연결 테스트")}

    @app.post("/api/backup", dependencies=[Depends(auth)])
    def backup_now() -> dict[str, Any]: return backup.backup_once()

    @app.post("/api/sync", dependencies=[Depends(auth)])
    def sync_now() -> dict[str, Any]: return git_sync.check_once()

    dashboard = Path(settings.dashboard_dir)
    if dashboard.exists(): app.mount("/", StaticFiles(directory=str(dashboard), html=True), name="dashboard")

    app.state.trader_state = state; app.state.registry = registry; app.state.runtime_config = runtime_config
    app.state.journal = journal; app.state.engine = engine; app.state.git_sync = git_sync; app.state.backup = backup; app.state.dashboard_token = token
    return app


app = create_app()


def run() -> None:
    load_dotenv(); settings = Settings()
    uvicorn.run(app, host=settings.service_host, port=settings.service_port, reload=False, access_log=False)


if __name__ == "__main__": run()
