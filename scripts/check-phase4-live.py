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
DEPLOY_STATE_PATH = REPO_ROOT / "b3_trader/data/research-platform/cloudflare-pages-deploy-state.json"
VIEWER_SHELL = REPO_ROOT / "cloudflare-pages/public/viewer-shell-v3.js"
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


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


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
    lab_component = components.get("strategy-lab-shadow") if isinstance(components.get("strategy-lab-shadow"), dict) else {}
    print("\n=== STRATEGY LAB SUPERVISOR ===")
    print(json.dumps({
        "enabled": bool(lab_component.get("enabled")),
        "status": lab_component.get("status"),
        "runs": int(lab_component.get("runs") or 0),
        "last_error": str(lab_component.get("last_error") or ""),
        "last_result": lab_component.get("last_result") if isinstance(lab_component.get("last_result"), dict) else {},
    }, ensure_ascii=False, indent=2))

    lab_summary = {
        "experiments": 0,
        "bithumb_experiments": 0,
        "upbit_experiments": 0,
        "metrics": 0,
        "accounts": 0,
        "trades": 0,
        "learning_rows": 0,
        "bithumb_account_markets_min": 0,
        "upbit_account_markets_min": 0,
    }
    leaders: dict[str, dict] = {}
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH), timeout=20)
        conn.row_factory = sqlite3.Row
        try:
            required = {
                "strategy_lab_experiments", "strategy_lab_accounts", "strategy_lab_learning",
                "strategy_lab_trades", "strategy_lab_metrics", "strategy_lab_ingest_state",
            }
            existing = {name for name in required if table_exists(conn, name)}
            if existing == required:
                lab_summary["experiments"] = int(conn.execute("SELECT COUNT(*) FROM strategy_lab_experiments").fetchone()[0])
                lab_summary["bithumb_experiments"] = int(conn.execute("SELECT COUNT(*) FROM strategy_lab_experiments WHERE exchange='bithumb'").fetchone()[0])
                lab_summary["upbit_experiments"] = int(conn.execute("SELECT COUNT(*) FROM strategy_lab_experiments WHERE exchange='upbit'").fetchone()[0])
                lab_summary["metrics"] = int(conn.execute("SELECT COUNT(*) FROM strategy_lab_metrics").fetchone()[0])
                lab_summary["accounts"] = int(conn.execute("SELECT COUNT(*) FROM strategy_lab_accounts").fetchone()[0])
                lab_summary["trades"] = int(conn.execute("SELECT COUNT(*) FROM strategy_lab_trades").fetchone()[0])
                lab_summary["learning_rows"] = int(conn.execute("SELECT COUNT(*) FROM strategy_lab_learning").fetchone()[0])
                for exchange in ("bithumb", "upbit"):
                    counts = [int(row[0]) for row in conn.execute(
                        """SELECT COUNT(*) FROM strategy_lab_accounts a
                           JOIN strategy_lab_experiments e ON e.experiment_id=a.experiment_id
                           WHERE e.exchange=? GROUP BY a.experiment_id""", (exchange,)
                    ).fetchall()]
                    lab_summary[f"{exchange}_account_markets_min"] = min(counts) if counts else 0
                    row = conn.execute(
                        """SELECT m.*,e.label FROM strategy_lab_metrics m
                           JOIN strategy_lab_experiments e USING(experiment_id)
                           WHERE m.exchange=? ORDER BY m.return_pct DESC LIMIT 1""", (exchange,)
                    ).fetchone()
                    if row:
                        leaders[exchange] = dict(row)
            else:
                pending.append("Strategy Lab tables have not been created by the restarted supervisor yet")
        finally:
            conn.close()
    else:
        errors.append("authoritative PAPER SQLite database is missing")

    print("\n=== STRATEGY LAB SQLITE ===")
    print(json.dumps({**lab_summary, "leaders": leaders}, ensure_ascii=False, indent=2, default=str))

    snapshot = CloudflareSnapshotPublisher().build_snapshot()
    public = snapshot.get("public") if isinstance(snapshot.get("public"), dict) else {}
    lab = public.get("strategy_lab") if isinstance(public.get("strategy_lab"), dict) else {}
    snapshot_experiments = lab.get("experiments") if isinstance(lab.get("experiments"), list) else []
    body_bytes = len(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    print("\n=== CLOUDFLARE STRATEGY LAB CONTRACT ===")
    print(json.dumps({
        "public_version": int(public.get("version") or 0),
        "strategy_lab_experiments": len(snapshot_experiments),
        "snapshot_bytes": body_bytes,
        "paper_only": bool(lab.get("paper_only")),
        "source": lab.get("source"),
    }, ensure_ascii=False, indent=2))

    shell_text = VIEWER_SHELL.read_text(encoding="utf-8", errors="replace") if VIEWER_SHELL.exists() else ""
    index_text = VIEWER_INDEX.read_text(encoding="utf-8", errors="replace") if VIEWER_INDEX.exists() else ""
    old_detail_loop = "new MutationObserver(()=>requestAnimationFrame(detailBar))" in shell_text
    guarded_detail = "if(detailFrame)return" in shell_text and "detailFrame=requestAnimationFrame" in shell_text
    guarded_row_text = "if(meta.textContent!==next)meta.textContent=next" in shell_text
    cache_busted = "viewer-shell-v3.js?v=2" in index_text
    lab_viewer_loaded = "strategy-lab-v1.js?v=1" in index_text
    print("\n=== VIEWER CHROME SAFETY ===")
    print(json.dumps({
        "old_detail_feedback_loop_present": old_detail_loop,
        "detail_observer_frame_guard": guarded_detail,
        "result_row_write_guard": guarded_row_text,
        "viewer_shell_cache_bust_v2": cache_busted,
        "strategy_lab_viewer_loaded": lab_viewer_loaded,
    }, ensure_ascii=False, indent=2))

    deploy = read_json(DEPLOY_STATE_PATH)
    deployed_head = str(deploy.get("deployed_head") or "")
    print("\n=== PAGES DEPLOY ===")
    print(json.dumps({
        "deployed_head": deployed_head[:7],
        "health_ok": bool(deploy.get("health_ok")),
        "viewer_url": deploy.get("viewer_url"),
    }, ensure_ascii=False, indent=2))

    if not local or not remote or local != remote:
        pending.append("Git local/remote HEAD is not synchronized yet")
    if lab_component.get("last_error"):
        errors.append(f"Strategy Lab supervisor error: {lab_component.get('last_error')}")
    if lab_component.get("status") not in {"healthy", "running"}:
        pending.append("Strategy Lab supervisor has not completed a healthy run yet")
    if lab_summary["experiments"] not in {0, 12}:
        errors.append(f"Strategy Lab experiment count is unexpected: {lab_summary['experiments']}")
    if lab_summary["experiments"] == 12 and (lab_summary["bithumb_experiments"] != 6 or lab_summary["upbit_experiments"] != 6):
        errors.append("Strategy Lab does not have six styles per exchange")
    if lab_summary["metrics"] not in {0, 12}:
        errors.append(f"Strategy Lab metric count is unexpected: {lab_summary['metrics']}")
    if lab_summary["metrics"] < 12:
        pending.append("Strategy Lab metrics are still warming up")
    if lab_summary["accounts"] <= 0:
        pending.append("Strategy Lab has not replayed market-memory rows into isolated accounts yet")
    if len(snapshot_experiments) < 12:
        pending.append("Strategy Lab summary has not reached the Cloudflare snapshot contract yet")
    if body_bytes >= 1_800_000:
        errors.append(f"Cloudflare snapshot exceeds safety limit: {body_bytes} bytes")
    if old_detail_loop or not guarded_detail or not guarded_row_text:
        errors.append("viewer-shell Chrome MutationObserver feedback-loop guard is missing")
    if not cache_busted:
        errors.append("viewer-shell cache-bust version is not active")
    if not lab_viewer_loaded:
        errors.append("Strategy Lab viewer script is not loaded")
    if not deployed_head or (local and not deployed_head.startswith(local)):
        pending.append("Pages has not deployed the current Git HEAD yet")
    if not deploy.get("health_ok"):
        pending.append("Pages health check is not green yet")

    print("\n=== RESULT ===")
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        print("VIEWER_BROWSER_SAFE=FAIL")
        print("PHASE4_LIVE=FAIL")
        raise SystemExit(1)
    browser_pending = any("Pages" in item or "Git" in item for item in pending)
    if browser_pending:
        print("VIEWER_BROWSER_SAFE=WARMING")
    else:
        print("VIEWER_BROWSER_SAFE=PASS")
    if pending:
        for item in pending:
            print(f"PENDING: {item}")
        print("PHASE4_LIVE=WARMING")
        return
    print("PHASE4_LIVE=PASS")


if __name__ == "__main__":
    main()
