from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def _same_path(a: str, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except OSError:
        return False


if os.name == "nt" and VENV_PYTHON.exists() and not _same_path(sys.executable, VENV_PYTHON):
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]])

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from b3_trader.cloudflare_snapshot_publisher import CloudflareSnapshotPublisher

STATUS_PATH = REPO_ROOT / "b3_trader/data/research-platform/status.json"
UPBIT_PATH = REPO_ROOT / "dashboard/runtime-demo-upbit.json"
DETAIL_STATE_PATH = REPO_ROOT / "b3_trader/data/research-platform/cloudflare-market-detail-state.json"
DEPLOY_STATE_PATH = REPO_ROOT / "b3_trader/data/research-platform/cloudflare-pages-deploy-state.json"


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def component(status: dict, name: str) -> dict:
    rows = status.get("components") if isinstance(status.get("components"), dict) else {}
    value = rows.get(name)
    return value if isinstance(value, dict) else {}


def compact_component(row: dict) -> dict:
    result = row.get("last_result") if isinstance(row.get("last_result"), dict) else {}
    return {
        "enabled": bool(row.get("enabled")),
        "status": row.get("status"),
        "runs": int(row.get("runs") or 0),
        "last_error": str(row.get("last_error") or ""),
        "last_result": result,
    }


def main() -> None:
    local = git("rev-parse", "--short", "HEAD")
    remote = git("rev-parse", "--short", "origin/b3-auto-trader-phase1")
    print(f"python={sys.executable}")
    print(f"git_local={local or '-'}")
    print(f"git_remote={remote or '-'}")

    upbit = read_json(UPBIT_PATH)
    print("\n=== UPBIT PAPER ===")
    print(json.dumps({
        "exchange": upbit.get("exchange"),
        "strategy": upbit.get("strategy"),
        "market_count": int(upbit.get("market_count") or 0),
        "scanned_count": int(upbit.get("scanned_count") or 0),
        "scan_total": int(upbit.get("scan_total") or 0),
        "active_positions": int(upbit.get("active_positions") or 0),
        "warning_markets": int(upbit.get("warning_markets") or 0),
        "scan_number": int(upbit.get("scan_number") or 0),
        "error": str(upbit.get("error") or ""),
    }, ensure_ascii=False, indent=2))

    status = read_json(STATUS_PATH)
    print("\n=== SUPERVISOR ===")
    for name in (
        "upbit-paper-research",
        "cloudflare-snapshot-publish",
        "cloudflare-market-detail-publish",
        "cloudflare-pages-deploy",
    ):
        print(name)
        print(json.dumps(compact_component(component(status, name)), ensure_ascii=False, indent=2))

    print("\n=== MULTI-EXCHANGE SNAPSHOT CONTRACT ===")
    snapshot = CloudflareSnapshotPublisher().build_snapshot()
    public = snapshot.get("public") if isinstance(snapshot.get("public"), dict) else {}
    exchanges = public.get("exchanges") if isinstance(public.get("exchanges"), dict) else {}
    exchange_summary: dict[str, dict] = {}
    for name in ("bithumb", "upbit"):
        payload = exchanges.get(name) if isinstance(exchanges.get(name), dict) else {}
        exchange_summary[name] = {
            "market_count": int(payload.get("market_count") or 0),
            "leaderboard": len(payload.get("leaderboard") or []),
            "scanned_count": int(payload.get("scanned_count") or 0),
            "scan_total": int(payload.get("scan_total") or 0),
            "active_positions": int(payload.get("active_positions") or 0),
            "return_pct": float(payload.get("return_pct") or 0.0),
        }
    body_bytes = len(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    print(json.dumps({"bytes": body_bytes, "exchanges": exchange_summary}, ensure_ascii=False, indent=2))

    print("\n=== DETAIL BRIDGE ===")
    detail = read_json(DETAIL_STATE_PATH)
    print(json.dumps({
        "version": int(detail.get("version") or 0),
        "cursors": detail.get("cursors") if isinstance(detail.get("cursors"), dict) else {},
        "published": int(detail.get("published") or 0),
        "published_by_exchange": detail.get("published_by_exchange") if isinstance(detail.get("published_by_exchange"), dict) else {},
        "stored": int(detail.get("stored") or 0),
        "stored_by_exchange": detail.get("stored_by_exchange") if isinstance(detail.get("stored_by_exchange"), dict) else {},
        "requests": int(detail.get("requests") or 0),
        "retries": int(detail.get("retries") or 0),
    }, ensure_ascii=False, indent=2))

    deploy = read_json(DEPLOY_STATE_PATH)
    deployed_head = str(deploy.get("deployed_head") or "")
    print("\n=== PAGES ===")
    print(json.dumps({
        "deployed_head": deployed_head[:7],
        "health_ok": bool(deploy.get("health_ok")),
        "viewer_url": deploy.get("viewer_url"),
    }, ensure_ascii=False, indent=2))

    errors: list[str] = []
    pending: list[str] = []
    if not local or not remote or local != remote:
        pending.append("Git local/remote HEAD가 아직 일치하지 않음")
    if int(upbit.get("market_count") or 0) < 200 or int(upbit.get("scanned_count") or 0) != int(upbit.get("scan_total") or 0):
        errors.append("Upbit 전체 PAPER 순회 미완료")
    if upbit.get("error"):
        errors.append(f"Upbit runtime error: {upbit.get('error')}")
    upbit_component = component(status, "upbit-paper-research")
    if not upbit_component.get("enabled") or upbit_component.get("status") not in {"healthy", "running"}:
        errors.append("Upbit Supervisor component 비정상")
    if exchange_summary["bithumb"]["leaderboard"] < 400 or exchange_summary["upbit"]["leaderboard"] < 200:
        errors.append("다중거래소 snapshot 계약에 전체 leaderboard가 없음")
    if body_bytes >= 1_800_000:
        errors.append("다중거래소 snapshot이 전송 안전 한도를 초과함")
    if int(detail.get("version") or 0) < 3:
        pending.append("상세 publisher가 아직 v3 state를 한 번도 기록하지 않음")
    elif int((detail.get("stored_by_exchange") or {}).get("upbit") or 0) <= 0:
        pending.append("Upbit 상세 D1 순환이 아직 도착하지 않음")
    if not deployed_head or (local and not deployed_head.startswith(local)):
        pending.append("Pages가 현재 Git HEAD 배포를 아직 완료하지 않음")
    if not deploy.get("health_ok"):
        pending.append("Pages health 확인 대기")

    print("\n=== RESULT ===")
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        print("PHASE3_LIVE=FAIL")
        raise SystemExit(1)
    if pending:
        for item in pending:
            print(f"PENDING: {item}")
        print("PHASE3_LIVE=WARMING")
        return
    print("PHASE3_LIVE=PASS")


if __name__ == "__main__":
    main()
