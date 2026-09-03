from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles

from .assets import AssetProfile, AssetRegistry, default_profile, normalize_market
from .auto_demo import AutoPaperDemo, SCAN_INTERVAL_SECONDS, STATUS_PATH
from .config import Settings
from .journal import TradeJournal
from .local_engine import MultiAssetEngine
from .network_access import network_status
from .paper_runtime_liveness import external_status_owner_is_alive, status_is_fresh
from .research_routes import install_research_routes
from .runtime_config import RuntimeConfigStore
from .runtime_state import RuntimeState
from .sync_manager import BackupManager, GitAutoSync
from .telegram_notify import TelegramNotifier
from .telegram_settings import TelegramSettingsStore
from .user_tools import UserToolsStore, calculate_averaging

RESTART_EXIT_CODE = 75
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
RANGE_SECONDS = {
    "1h": 3_600.0,
    "6h": 21_600.0,
    "24h": 86_400.0,
    "7d": 604_800.0,
}


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


def _range_seconds(value: str) -> float:
    key = str(value or "24h").strip().lower()
    if key not in RANGE_SECONDS:
        raise HTTPException(status_code=422, detail="range must be one of 1h, 6h, 24h, 7d")
    return RANGE_SECONDS[key]


def _downsample(rows: list[dict[str, Any]], target: int = 420) -> list[dict[str, Any]]:
    if len(rows) <= target:
        return rows
    step = max(1, len(rows) // target)
    sampled = rows[::step]
    if sampled[-1] is not rows[-1]:
        sampled.append(rows[-1])
    return sampled[: target + 1]


def _env_enabled(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "off", "no"}


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        text = completed.stdout.strip()
        return completed.returncode == 0 and str(pid) in text and not text.startswith("INFO:")
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _read_demo_status() -> dict[str, Any]:
    if not STATUS_PATH.exists():
        return {}
    try:
        raw = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def create_app() -> FastAPI:
    load_dotenv()
    settings = Settings()
    state = RuntimeState()
    registry = AssetRegistry(settings.asset_registry_path)
    runtime_config = RuntimeConfigStore(settings.runtime_config_path)
    journal = TradeJournal(settings.journal_db)
    user_tools = UserToolsStore(settings.journal_db)

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

    demo_enabled = _env_enabled("AUTO_DEMO_ENABLED", True)
    demo_worker_enabled = _env_enabled("AUTO_DEMO_EMBEDDED_WORKER", True)
    demo_stop = threading.Event()
    demo_thread: threading.Thread | None = None

    def demo_snapshot() -> dict[str, Any]:
        payload = _read_demo_status()
        fresh = status_is_fresh(
            payload,
            scan_interval_seconds=SCAN_INTERVAL_SECONDS,
        )
        if not payload:
            return {
                "enabled": demo_enabled,
                "worker_mode": "embedded" if demo_worker_enabled else "external_supervisor",
                "running": False,
                "paper_only": True,
                "start_krw": 10_000_000.0,
                "cash_krw": 10_000_000.0,
                "equity_krw": 10_000_000.0,
                "positions": [],
                "candidates": [],
                "recent_fills": [],
                "updated_at": 0.0,
                "state": "starting" if demo_enabled else "disabled",
            }
        return {
            **payload,
            "enabled": demo_enabled,
            "worker_mode": "embedded" if demo_worker_enabled else "external_supervisor",
            "fresh": fresh,
            "running": bool(payload.get("running")) and fresh,
            "state": "running" if bool(payload.get("running")) and fresh else "waiting",
        }

    def external_demo_is_alive() -> bool:
        return external_status_owner_is_alive(
            _read_demo_status(),
            scan_interval_seconds=SCAN_INTERVAL_SECONDS,
            pid_alive=_pid_alive,
            current_pid=os.getpid(),
        )

    def demo_worker() -> None:
        while not demo_stop.is_set():
            if external_demo_is_alive():
                if demo_stop.wait(20.0):
                    return
                continue
            try:
                AutoPaperDemo().run(stop_event=demo_stop)
            except Exception as exc:
                state.set_error(exc, scope="auto_demo")
            else:
                if demo_stop.is_set():
                    return
                state.set_error("AutoPaperDemo.run returned without a stop request", scope="auto_demo")
            if demo_stop.wait(15.0):
                return

    def start_demo() -> None:
        nonlocal demo_thread
        if (
            not demo_enabled
            or not demo_worker_enabled
            or (demo_thread and demo_thread.is_alive())
        ):
            return
        demo_thread = threading.Thread(target=demo_worker, name="bithumb-auto-paper-demo", daemon=True)
        demo_thread.start()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        print(
            f"Dashboard: http://127.0.0.1:{settings.service_port}\n"
            "Local browser: automatic loopback authentication enabled.\n"
            "Phone connection code: available from the local Settings screen."
        )
        engine.start()
        git_sync.start()
        backup.start()
        start_demo()
        try:
            yield
        finally:
            demo_stop.set()
            git_sync.stop()
            backup.stop()
            engine.stop()
            user_tools.close()
            journal.close()

    app = FastAPI(title="Crypto Auto Trader", version="0.7.0", lifespan=lifespan)

    def auth(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> None:
        client_host = request.client.host if request.client else ""
        if client_host in LOOPBACK_HOSTS:
            return
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid dashboard token")

    def require_loopback(request: Request) -> None:
        client_host = request.client.host if request.client else ""
        if client_host not in LOOPBACK_HOSTS:
            raise HTTPException(status_code=403, detail="available only on the local PC")

    def publish_control(message: str) -> None:
        try:
            git_sync.publish_control(message)
        except Exception as exc:
            state.set_error(exc, scope="git_publish")

    def holding_with_market_value(market: str) -> dict[str, Any]:
        holding = user_tools.get_holding(market)
        asset = (state.snapshot().get("assets") or {}).get(market) or {}
        price = float(asset.get("price") or 0.0)
        volume = float(holding.get("volume") or 0.0)
        avg_price = float(holding.get("avg_price") or 0.0)
        invested = volume * avg_price
        value = volume * price
        pnl = value - invested
        pnl_pct = pnl / invested * 100.0 if invested > 0 else 0.0
        return {
            **holding,
            "current_price": round(price, 12),
            "invested_krw": round(invested, 2),
            "value_krw": round(value, 2),
            "unrealized_pnl_krw": round(pnl, 2),
            "unrealized_pnl_pct": round(pnl_pct, 4),
        }

    install_research_routes(app, auth=auth, require_loopback=require_loopback, journal=journal)

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
            "auto_demo": demo_snapshot().get("state"),
        }

    @app.get("/api/state", dependencies=[Depends(auth)])
    def api_state() -> dict[str, Any]:
        return {"mode": "PAPER", **state.snapshot()}

    @app.get("/api/demo", dependencies=[Depends(auth)])
    def api_demo() -> dict[str, Any]:
        return demo_snapshot()

    @app.get("/api/analytics", dependencies=[Depends(auth)])
    def analytics() -> dict[str, Any]:
        snapshot = state.snapshot()
        portfolio = snapshot.get("portfolio") or {}
        stats = journal.paper_trade_stats()
        start_krw = float(portfolio.get("start_krw") or settings.paper_start_krw)
        equity = float(portfolio.get("equity_krw") or start_krw)
        positions = portfolio.get("positions") or {}
        unrealized = 0.0
        for item in positions.values():
            volume = float(item.get("volume") or 0.0)
            avg_price = float(item.get("avg_price") or 0.0)
            value = float(item.get("value_krw") or 0.0)
            unrealized += value - volume * avg_price
        total_pnl = equity - start_krw
        return {
            **stats,
            "start_krw": round(start_krw, 2),
            "equity_krw": round(equity, 2),
            "total_pnl_krw": round(total_pnl, 2),
            "unrealized_pnl_krw": round(unrealized, 2),
            "return_pct": round(total_pnl / start_krw * 100.0, 4) if start_krw > 0 else 0.0,
            "exposure_krw": float(portfolio.get("exposure_krw") or 0.0),
            "current_daily_drawdown_pct": float(portfolio.get("daily_drawdown_pct") or 0.0),
        }

    @app.get("/api/history", dependencies=[Depends(auth)])
    def history(
        market: str = Query(...),
        range: str = Query(default="24h"),
    ) -> dict[str, Any]:
        normalized = normalize_market(market)
        seconds = _range_seconds(range)
        rows = journal.snapshot_history(
            normalized,
            since_seconds=seconds,
            limit=20_000,
        )
        fills = journal.fills_for_market(
            normalized,
            since_seconds=seconds,
            limit=2_000,
        )
        return {
            "market": normalized,
            "range": range,
            "points": _downsample(rows),
            "fills": fills,
        }

    @app.get("/api/portfolio/history", dependencies=[Depends(auth)])
    def portfolio_history(range: str = Query(default="7d")) -> dict[str, Any]:
        seconds = _range_seconds(range)
        rows = journal.portfolio_history(
            since_seconds=seconds,
            limit=20_000,
        )
        return {"range": range, "points": _downsample(rows)}

    @app.get("/api/network", dependencies=[Depends(auth)])
    def network() -> dict[str, Any]:
        return network_status(settings.service_port)

    @app.get("/api/local/phone-code")
    def local_phone_code(request: Request) -> dict[str, str]:
        require_loopback(request)
        return {
            "code": token,
            "file": "b3_trader/data/dashboard-token.txt",
        }

    @app.post("/api/local/phone-code/rotate")
    def rotate_phone_code(request: Request) -> dict[str, str]:
        nonlocal token
        require_loopback(request)
        if settings.dashboard_token:
            raise HTTPException(
                status_code=409,
                detail="DASHBOARD_TOKEN is fixed in .env; change it there and restart instead",
            )
        token = secrets.token_urlsafe(32)
        token_file = Path("b3_trader/data/dashboard-token.txt")
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(token + "\n", encoding="utf-8")
        app.state.dashboard_token = token
        journal.record_event("dashboard_token_rotated", {"local_only": True})
        return {"code": token}

    @app.get("/api/holdings", dependencies=[Depends(auth)])
    def list_manual_holdings() -> list[dict[str, Any]]:
        return [holding_with_market_value(row["market"]) for row in user_tools.list_holdings()]

    @app.get("/api/holdings/{market:path}", dependencies=[Depends(auth)])
    def get_manual_holding(market: str) -> dict[str, Any]:
        return holding_with_market_value(normalize_market(market))

    @app.put("/api/holdings/{market:path}", dependencies=[Depends(auth)])
    def save_manual_holding(
        market: str,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        normalized = normalize_market(market)
        try:
            volume = float(payload.get("volume") or 0.0)
            avg_price = float(payload.get("avg_price") or 0.0)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="volume and avg_price must be numbers") from exc
        if volume < 0 or avg_price < 0:
            raise HTTPException(status_code=422, detail="volume and avg_price must be zero or greater")
        holding_kwargs: dict[str, Any] = {}
        if "exchange" in payload:
            holding_kwargs["exchange"] = payload.get("exchange")
        try:
            saved = user_tools.set_holding(
                normalized,
                volume=volume,
                avg_price=avg_price,
                **holding_kwargs,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        journal.record_event(
            "manual_holding_updated",
            {
                "market": normalized,
                "volume": volume,
                "avg_price": avg_price,
                "exchange": saved.get("exchange"),
            },
        )
        return holding_with_market_value(normalized)

    @app.delete("/api/holdings/{market:path}", dependencies=[Depends(auth)])
    def delete_manual_holding(market: str) -> dict[str, Any]:
        normalized = normalize_market(market)
        removed = user_tools.delete_holding(normalized)
        journal.record_event("manual_holding_deleted", {"market": normalized})
        return {"ok": True, "removed": removed, "market": normalized}

    @app.get("/api/averaging/{market:path}", dependencies=[Depends(auth)])
    def get_averaging_plan(market: str) -> dict[str, Any]:
        normalized = normalize_market(market)
        holding = user_tools.get_holding(normalized)
        plan = user_tools.get_plan(normalized)
        calculation = calculate_averaging(
            volume=float(holding.get("volume") or 0.0),
            avg_price=float(holding.get("avg_price") or 0.0),
            rows=list(plan.get("rows") or []),
        )
        return {"market": normalized, "holding": holding, "plan": plan, "calculation": calculation}

    @app.put("/api/averaging/{market:path}", dependencies=[Depends(auth)])
    def save_averaging_plan(
        market: str,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        normalized = normalize_market(market)
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            raise HTTPException(status_code=422, detail="rows must be a list")
        plan = user_tools.set_plan(normalized, rows)
        holding = user_tools.get_holding(normalized)
        calculation = calculate_averaging(
            volume=float(holding.get("volume") or 0.0),
            avg_price=float(holding.get("avg_price") or 0.0),
            rows=list(plan.get("rows") or []),
        )
        journal.record_event(
            "averaging_plan_updated",
            {"market": normalized, "rows": len(plan.get("rows") or [])},
        )
        return {"market": normalized, "holding": holding, "plan": plan, "calculation": calculation}

    @app.delete("/api/averaging/{market:path}", dependencies=[Depends(auth)])
    def delete_averaging_plan(market: str) -> dict[str, Any]:
        normalized = normalize_market(market)
        removed = user_tools.delete_plan(normalized)
        journal.record_event("averaging_plan_deleted", {"market": normalized})
        return {"ok": True, "removed": removed, "market": normalized}

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
        notifier.safe_send("자동매매 모니터: 새 매수를 잠시 멈췄습니다")
        return {"ok": True, "paused": True}

    @app.post("/api/control/resume", dependencies=[Depends(auth)])
    def resume() -> dict[str, Any]:
        if state.kill_switch:
            raise HTTPException(status_code=409, detail="reset kill switch first")
        state.paused = False
        journal.record_event("manual_resume", {})
        notifier.safe_send("자동매매 모니터: 새 매수 감시를 다시 시작했습니다")
        return {"ok": True, "paused": False}

    @app.post("/api/control/kill", dependencies=[Depends(auth)])
    def kill() -> dict[str, Any]:
        state.kill_switch = True
        state.paused = True
        journal.record_event("manual_kill_switch", {})
        notifier.safe_send("자동매매 모니터: 긴급 정지를 켰습니다")
        return {"ok": True, "kill_switch": True}

    @app.post("/api/control/reset-kill", dependencies=[Depends(auth)])
    def reset_kill() -> dict[str, Any]:
        state.kill_switch = False
        state.paused = True
        journal.record_event("manual_kill_switch_reset", {})
        notifier.safe_send("자동매매 모니터: 긴급 정지를 해제했습니다. 새 매수는 아직 멈춘 상태입니다")
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
            ok = notifier.send("코인 자동매매 모니터 텔레그램 연결 테스트")
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
    app.state.user_tools = user_tools
    app.state.engine = engine
    app.state.git_sync = git_sync
    app.state.backup = backup
    app.state.telegram_store = telegram_store
    app.state.dashboard_token = token
    app.state.demo_enabled = demo_enabled
    app.state.demo_worker_enabled = demo_worker_enabled
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
