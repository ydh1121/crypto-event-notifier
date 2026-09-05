from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
DB_PATH = REPO_ROOT / "b3_trader/data/auto_demo.sqlite3"
STATUS_PATH = REPO_ROOT / "b3_trader/data/research-platform/status.json"
DEPLOY_PATH = REPO_ROOT / "b3_trader/data/research-platform/cloudflare-pages-deploy-state.json"
LOCAL_INDEX = REPO_ROOT / "dashboard/index.html"
VIEWER_INDEX = REPO_ROOT / "cloudflare-pages/public/index.html"


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
from b3_trader.strategy_lab_market import read_strategy_lab_market


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


def main() -> None:
    local = git("rev-parse", "--short", "HEAD")
    remote = git("rev-parse", "--short", "origin/b3-auto-trader-phase1")
    print(f"python={sys.executable}")
    print(f"git_local={local or '-'}")
    print(f"git_remote={remote or '-'}")

    errors: list[str] = []
    pending: list[str] = []
    status = read_json(STATUS_PATH)
    components = status.get("components") if isinstance(status.get("components"), dict) else {}
    lab = components.get("strategy-lab-shadow") if isinstance(components.get("strategy-lab-shadow"), dict) else {}
    detail = components.get("cloudflare-market-detail-publish") if isinstance(components.get("cloudflare-market-detail-publish"), dict) else {}
    lab_result = lab.get("last_result") if isinstance(lab.get("last_result"), dict) else {}
    detail_result = detail.get("last_result") if isinstance(detail.get("last_result"), dict) else {}

    print("\n=== LIVE COMPONENTS ===")
    print(json.dumps({
        "strategy_lab": {
            "status": lab.get("status"), "runs": int(lab.get("runs") or 0),
            "last_error": str(lab.get("last_error") or ""),
            "experiment_count": int(lab_result.get("experiment_count") or 0),
            "custom_experiment_count": lab_result.get("custom_experiment_count"),
        },
        "detail_publisher": {
            "status": detail.get("status"), "runs": int(detail.get("runs") or 0),
            "last_error": str(detail.get("last_error") or ""),
            "strategy_lab_detail": detail_result.get("strategy_lab_detail"),
            "detail_payload_version": detail_result.get("detail_payload_version"),
            "published_by_exchange": detail_result.get("published_by_exchange") or {},
        },
    }, ensure_ascii=False, indent=2))

    db_summary = {"custom_table": False, "custom_experiments": 0, "market_probe": 0}
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH), timeout=20)
        try:
            db_summary["custom_table"] = bool(conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='strategy_lab_custom_specs'"
            ).fetchone())
            if db_summary["custom_table"]:
                db_summary["custom_experiments"] = int(conn.execute(
                    "SELECT COUNT(*) FROM strategy_lab_custom_specs"
                ).fetchone()[0])
        finally:
            conn.close()
        probe = read_strategy_lab_market("bithumb", "KRW-BTC", DB_PATH)
        db_summary["market_probe"] = len(probe.get("experiments") or [])
    else:
        errors.append("authoritative PAPER SQLite database is missing")
    print("\n=== STRATEGY LAB DB ===")
    print(json.dumps(db_summary, ensure_ascii=False, indent=2))

    snapshot = CloudflareSnapshotPublisher().build_snapshot()
    public = snapshot.get("public") if isinstance(snapshot.get("public"), dict) else {}
    lab_public = public.get("strategy_lab") if isinstance(public.get("strategy_lab"), dict) else {}
    global_count = len(lab_public.get("experiments") or []) if isinstance(lab_public.get("experiments"), list) else 0
    print("\n=== READ-ONLY CONTRACT ===")
    print(json.dumps({
        "global_strategy_experiments": global_count,
        "public_version": int(public.get("version") or 0),
        "paper_only": bool(lab_public.get("paper_only")),
        "cloudflare_to_pc_control": False,
        "custom_write_scope": "local_pc_only",
    }, ensure_ascii=False, indent=2))

    local_index = LOCAL_INDEX.read_text(encoding="utf-8", errors="replace") if LOCAL_INDEX.exists() else ""
    viewer_index = VIEWER_INDEX.read_text(encoding="utf-8", errors="replace") if VIEWER_INDEX.exists() else ""
    ui = {
        "local_custom_builder_js": "strategy-lab-local.js?v=1" in local_index,
        "local_custom_builder_css": "strategy-lab-local.css?v=1" in local_index,
        "viewer_strategy_v2": "strategy-lab-v1.js?v=2" in viewer_index,
        "viewer_strategy_css_v2": "strategy-lab-v1.css?v=2" in viewer_index,
    }
    print("\n=== UI CONTRACT ===")
    print(json.dumps(ui, ensure_ascii=False, indent=2))

    deploy = read_json(DEPLOY_PATH)
    deployed_head = str(deploy.get("deployed_head") or "")
    print("\n=== PAGES ===")
    print(json.dumps({
        "deployed_head": deployed_head[:7],
        "health_ok": bool(deploy.get("health_ok")),
        "viewer_url": deploy.get("viewer_url"),
    }, ensure_ascii=False, indent=2))

    if not local or not remote or local != remote:
        pending.append("Git local/remote HEAD is not synchronized yet")
    if lab.get("last_error"):
        errors.append(f"Strategy Lab error: {lab.get('last_error')}")
    if detail.get("last_error"):
        errors.append(f"detail publisher error: {detail.get('last_error')}")
    if lab.get("status") not in {"healthy", "running"}:
        pending.append("new Strategy Lab runner has not completed a healthy run")
    if "custom_experiment_count" not in lab_result:
        pending.append("supervisor is still using the pre-custom Strategy Lab runner")
    if detail_result.get("strategy_lab_detail") is not True or int(detail_result.get("detail_payload_version") or 0) < 3:
        pending.append("per-market Strategy Lab detail publisher has not completed a new cycle")
    if not db_summary["custom_table"]:
        pending.append("custom Strategy Lab schema has not been initialized")
    if db_summary["market_probe"] < 6:
        pending.append("per-market Strategy Lab probe is not ready")
    if global_count < 12:
        pending.append("global Strategy Lab snapshot is not ready")
    if not all(ui.values()):
        errors.append("Strategy Lab local/viewer UI assets are not linked correctly")
    if not deployed_head or (local and not deployed_head.startswith(local)):
        pending.append("Pages has not deployed the current Git HEAD")
    if not deploy.get("health_ok"):
        pending.append("Pages health check is not green")

    print("\n=== RESULT ===")
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        print("PHASE4_CUSTOM_READY=FAIL")
        raise SystemExit(1)
    if pending:
        for item in pending:
            print(f"PENDING: {item}")
        print("PHASE4_CUSTOM_READY=WARMING")
        return
    print("PHASE4_CUSTOM_READY=PASS")


if __name__ == "__main__":
    main()
