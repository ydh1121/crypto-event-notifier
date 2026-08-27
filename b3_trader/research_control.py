from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import requests

from .config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PATH = Path("b3_trader/data/research-platform/components.json")
STATUS_PATH = Path("b3_trader/data/research-platform/status.json")
REFERENCE_STATE_PATH = Path("b3_trader/data/research-platform/reference-components-state.json")
WAREHOUSE_STATE_PATH = Path("b3_trader/data/research-warehouse/warehouse-state.json")
PAGES_DEPLOY_STATE_PATH = Path("b3_trader/data/research-platform/cloudflare-pages-deploy-state.json")

# Cloudflare D1 Free is row-write metered. Keep the Viewer useful while leaving
# enough daily headroom for profile/evidence writes and other operational data.
# These minima also clamp older local components.json files that still contain
# the original 20s/30s publish cadence after the supervisor restarts.
COMPONENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "warehouse-export": {"label":"AI 분석 데이터 저장","description":"가상매매·시장 기억 데이터를 Parquet 분석 창고에 추가 저장합니다.","default_enabled":True,"default_interval_seconds":300,"min_interval_seconds":60},
    "reference-version-watch": {"label":"외부 레포 버전 확인","description":"참고 GitHub 프로젝트의 새 버전만 확인합니다. 코드는 자동 적용하지 않습니다.","default_enabled":True,"default_interval_seconds":21600,"min_interval_seconds":300},
    "cloudflare-snapshot-publish": {"label":"웹 상태판 데이터 보내기","description":"24시간 PC의 가상매매 결과를 Cloudflare Pages 조회용 스냅샷으로 보냅니다.","default_enabled":False,"default_interval_seconds":60,"min_interval_seconds":60},
    "cloudflare-market-detail-publish": {"label":"웹 코인 상세 데이터 보내기","description":"코인별 체결·매매계획·학습·자산곡선을 작게 나눠 Cloudflare 조회판으로 보냅니다.","default_enabled":True,"default_interval_seconds":300,"min_interval_seconds":300},
    "coin-profile-enrichment": {"label":"전체 코인 사업·섹터 전수조사","description":"빗썸·업비트 KRW 전체 종목을 공식 설명서·홈페이지·백서·Docs/GitHub와 CoinMarketCap·CoinGecko로 교차검증해 사업 설명과 섹터를 누적합니다. 커뮤니티는 보조 근거로만 사용합니다.","default_enabled":True,"default_interval_seconds":90,"min_interval_seconds":60},
    "market-notice-watch": {"label":"상장·유의·거래종료 공지 감시","description":"빗썸·업비트 공식 공지와 공개 market warning을 별도 DB에 누적해 신규상장·유의·거래종료 상태를 자동 갱신합니다. PAPER 점수에는 아직 반영하지 않습니다.","default_enabled":True,"default_interval_seconds":60,"min_interval_seconds":30},
    "upbit-paper-research": {"label":"업비트 전체 PAPER 연구","description":"업비트 KRW 전체 종목을 독립 1,000만원 PAPER 계좌로 연구합니다. 공개 시세 API만 사용합니다.","default_enabled":False,"default_interval_seconds":60,"min_interval_seconds":30},
    "strategy-lab-shadow": {"label":"전략 연구실","description":"동일한 시장 기억 데이터를 보수적·균형·공격적·분할매수·역추세·스윙 전략이 독립 PAPER 계좌로 비교합니다.","default_enabled":True,"default_interval_seconds":60,"min_interval_seconds":30},
    "cloudflare-pages-deploy": {"label":"웹 화면 자동 배포","description":"GitHub에서 새 웹 화면을 받은 뒤 Pages 코드가 바뀐 경우에만 pages.dev로 자동 배포합니다.","default_enabled":False,"default_interval_seconds":30,"min_interval_seconds":15},
}

_LOCK = threading.RLock()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    temp.write_text(text, encoding="utf-8")
    try:
        last_error: OSError | None = None
        for attempt in range(6):
            try:
                os.replace(temp, path)
                return
            except OSError as exc:
                last_error = exc
                if attempt >= 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
        if last_error is not None:
            raise last_error
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _git_text(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_summary(settings: Settings) -> dict[str, Any]:
    branch = _git_text("branch", "--show-current") or settings.git_sync_branch
    local_head = _git_text("rev-parse", "--short", "HEAD")
    origin_ref = f"refs/remotes/origin/{settings.git_sync_branch}"
    origin_head = _git_text("rev-parse", "--short", origin_ref)
    return {
        "branch": branch,
        "configured_branch": settings.git_sync_branch,
        "local_head": local_head,
        "origin_head": origin_head,
        "aligned": bool(local_head and origin_head and local_head == origin_head),
        "auto_sync_enabled": bool(settings.auto_git_sync),
        "mutates_from_viewer": False,
    }


def _local_api_json(settings: Settings, path: str) -> dict[str, Any]:
    """Read the local dashboard over loopback and keep the public snapshot sanitized."""
    try:
        response = requests.get(
            f"http://127.0.0.1:{int(settings.service_port)}{path}",
            timeout=1.2,
            headers={"User-Agent": "crypto-research-operations-status/1.0"},
        )
        if not response.ok:
            return {}
        value = response.json()
        return value if isinstance(value, dict) else {}
    except (requests.RequestException, ValueError):
        return {}


def _component_last_result(status_components: dict[str, Any], name: str) -> dict[str, Any]:
    source = status_components.get(name)
    if not isinstance(source, dict):
        return {}
    result = source.get("last_result")
    return result if isinstance(result, dict) else {}


def _cloudflare_summary(status_components: dict[str, Any]) -> dict[str, Any]:
    snapshot = _component_last_result(status_components, "cloudflare-snapshot-publish")
    details = _component_last_result(status_components, "cloudflare-market-detail-publish")
    deploy = _component_last_result(status_components, "cloudflare-pages-deploy")
    deploy_state = _read_json(PAGES_DEPLOY_STATE_PATH)
    return {
        "snapshot": {
            "status": str(snapshot.get("status") or "unknown"),
            "bytes": int(snapshot.get("bytes") or 0),
            "retries": int(snapshot.get("retries") or 0),
            "markets": int(snapshot.get("markets") or 0),
            "strategy_lab_experiments": int(snapshot.get("strategy_lab_experiments") or 0),
            "private_holdings_enabled": bool(snapshot.get("private_holdings_enabled")),
        },
        "market_details": {
            "status": str(details.get("status") or "unknown"),
            "published": int(details.get("published") or details.get("stored") or 0),
            "requests": int(details.get("requests") or 0),
            "bytes": int(details.get("bytes") or details.get("total_bytes") or 0),
            "retries": int(details.get("retries") or 0),
        },
        "pages": {
            "status": str(deploy.get("status") or deploy_state.get("status") or "unknown"),
            "head": str(deploy.get("head") or deploy_state.get("deployed_head") or "")[:12],
            "health_ok": bool(deploy.get("health_ok", deploy_state.get("health_ok", False))),
            "viewer_url": str(deploy.get("viewer_url") or deploy_state.get("viewer_url") or ""),
            "changed_files": int(deploy.get("changed_files") or 0),
            "elapsed_seconds": float(deploy.get("elapsed_seconds") or 0.0),
        },
    }


def _warehouse_summary(status_components: dict[str, Any]) -> dict[str, Any]:
    result = _component_last_result(status_components, "warehouse-export")
    state = _read_json(WAREHOUSE_STATE_PATH)
    tables = state.get("tables") if isinstance(state.get("tables"), dict) else {}
    total_rows = 0
    latest_export = 0.0
    for value in tables.values():
        if not isinstance(value, dict):
            continue
        total_rows += int(value.get("rows_exported_total") or 0)
        latest_export = max(latest_export, float(value.get("last_export_at") or 0.0))
    files = result.get("files") if isinstance(result.get("files"), list) else []
    return {
        "status": str(result.get("status") or ("ready" if tables else "waiting")),
        "tracked_tables": len(tables),
        "rows_exported_total": total_rows,
        "last_export_at": latest_export or float(state.get("updated_at") or 0.0),
        "last_run_rows": int(result.get("exported_rows") or 0),
        "last_run_files": len(files),
        "elapsed_seconds": float(result.get("elapsed_seconds") or 0.0),
        "format": "Parquet/ZSTD",
        "authoritative_store": "SQLite",
    }


def _backup_summary(settings: Settings) -> dict[str, Any]:
    runtime = _local_api_json(settings, "/api/state")
    backup = runtime.get("backup") if isinstance(runtime.get("backup"), dict) else {}
    local_dir = Path(settings.local_backup_dir)
    if not local_dir.is_absolute():
        local_dir = REPO_ROOT / local_dir
    files = sorted(local_dir.glob("crypto-trader-*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True) if local_dir.exists() else []
    latest = files[0] if files else None
    latest_mtime = float(latest.stat().st_mtime) if latest else 0.0
    latest_bytes = int(latest.stat().st_size) if latest else 0
    drive_status = str(backup.get("drive") or ("configured" if settings.rclone_remote else "disabled"))
    return {
        "status": str(backup.get("status") or ("ready" if latest else "waiting")),
        "last_backup_at": float(backup.get("ts") or latest_mtime),
        "local_backup_count": len(files),
        "latest_local_bytes": latest_bytes,
        "drive_configured": bool(settings.rclone_remote.strip()),
        "rclone_installed": shutil.which("rclone") is not None,
        "drive_status": drive_status,
        "drive_uploaded": drive_status == "uploaded_and_mirrored",
        "local_path_exposed": False,
        "remote_path_exposed": False,
    }


def _telegram_summary(settings: Settings) -> dict[str, Any]:
    local = _local_api_json(settings, "/api/telegram/status")
    enabled = bool(local.get("enabled", settings.telegram_enabled))
    token_configured = bool(local.get("token_configured", bool(settings.telegram_token.strip())))
    chat_configured = bool(local.get("chat_configured", bool(local.get("chat_id") or settings.telegram_chat_id.strip())))
    automatic_alerts = str(local.get("automatic_alerts") or "buy_candidate_only")
    return {
        "enabled": enabled,
        "token_configured": token_configured,
        "chat_configured": chat_configured,
        "ready": bool(enabled and token_configured and chat_configured),
        "automatic_alerts": automatic_alerts,
        "buy_candidate_only": automatic_alerts == "buy_candidate_only",
        "buy_candidate_sent_count": int(local.get("buy_candidate_sent_count") or 0),
        "last_buy_candidate_sent_at": float(local.get("last_buy_candidate_sent_at") or 0.0),
    }


def _remote_access_summary(settings: Settings) -> dict[str, Any]:
    state = _read_json(Path("b3_trader/data/research-platform/remote-access-state.json"))
    return {
        "status": str(state.get("status") or "unknown"),
        "mode": str(state.get("mode") or "cloudflare_https"),
        "public_direct_port": False,
        "loopback_bind": str(settings.service_host) in {"127.0.0.1", "localhost"},
        "address_values_exposed": False,
    }


def platform_snapshot() -> dict[str, Any]:
    settings = Settings()
    control = load_control()
    status = _read_json(STATUS_PATH)
    status_components = status.get("components") if isinstance(status.get("components"), dict) else {}
    return {
        "version": 3,
        "paper_only": True,
        "updated_at": time.time(),
        "git": _git_summary(settings),
        "cloudflare": _cloudflare_summary(status_components),
        "warehouse": _warehouse_summary(status_components),
        "backup": _backup_summary(settings),
        "telegram": _telegram_summary(settings),
        "remote_access": _remote_access_summary(settings),
        "components": status_components,
        "control": control,
    }


def _default_control() -> dict[str, Any]:
    return {
        "version": 3,
        "revision": 1,
        "enabled": True,
        "components": {
            name: {
                "enabled": bool(definition.get("default_enabled", True)),
                "interval_seconds": float(definition["default_interval_seconds"]),
                "run_nonce": 0,
            }
            for name, definition in COMPONENT_DEFINITIONS.items()
        },
    }


def load_control() -> dict[str, Any]:
    with _LOCK:
        current = _read_json(CONTROL_PATH)
        if not current:
            current = _default_control()
            atomic_json(CONTROL_PATH, current)
            return current
        changed = False
        components = current.get("components")
        if not isinstance(components, dict):
            components = {}
            current["components"] = components
            changed = True
        for name, definition in COMPONENT_DEFINITIONS.items():
            cfg = components.get(name)
            if not isinstance(cfg, dict):
                components[name] = {
                    "enabled": bool(definition.get("default_enabled", True)),
                    "interval_seconds": float(definition["default_interval_seconds"]),
                    "run_nonce": 0,
                }
                changed = True
                continue
            minimum = float(definition["min_interval_seconds"])
            try:
                interval = float(cfg.get("interval_seconds") or definition["default_interval_seconds"])
            except (TypeError, ValueError):
                interval = float(definition["default_interval_seconds"])
            clamped = max(minimum, interval)
            if clamped != interval:
                cfg["interval_seconds"] = clamped
                changed = True
            if "run_nonce" not in cfg:
                cfg["run_nonce"] = 0
                changed = True
        if changed:
            current["revision"] = max(1, int(current.get("revision") or 1)) + 1
            atomic_json(CONTROL_PATH, current)
        return current


def update_component(name: str, *, enabled: bool | None = None, interval_seconds: float | None = None, force_run: bool = False) -> dict[str, Any]:
    if name not in COMPONENT_DEFINITIONS:
        raise KeyError(name)
    with _LOCK:
        control = load_control()
        components = control.setdefault("components", {})
        cfg = components.setdefault(name, {})
        definition = COMPONENT_DEFINITIONS[name]
        if enabled is not None:
            cfg["enabled"] = bool(enabled)
        if interval_seconds is not None:
            minimum = float(definition["min_interval_seconds"])
            cfg["interval_seconds"] = max(minimum, float(interval_seconds))
        if force_run:
            cfg["run_nonce"] = int(cfg.get("run_nonce") or 0) + 1
        control["revision"] = max(1, int(control.get("revision") or 1)) + 1
        atomic_json(CONTROL_PATH, control)
        return control
