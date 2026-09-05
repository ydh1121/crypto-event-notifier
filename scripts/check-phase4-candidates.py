from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
DB_PATH = REPO_ROOT / "b3_trader/data/auto_demo.sqlite3"
STATUS_PATH = REPO_ROOT / "b3_trader/data/research-platform/status.json"
DEPLOY_PATH = REPO_ROOT / "b3_trader/data/research-platform/cloudflare-pages-deploy-state.json"
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
from b3_trader.strategy_lab_candidates import read_strategy_lab_candidates


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
    commit_epoch = int(git("show", "-s", "--format=%ct", "HEAD") or 0)
    print(f"python={sys.executable}")
    print(f"git_local={local or '-'}")
    print(f"git_remote={remote or '-'}")

    errors: list[str] = []
    pending: list[str] = []

    status = read_json(STATUS_PATH)
    components = status.get("components") if isinstance(status.get("components"), dict) else {}
    lab_component = components.get("strategy-lab-shadow") if isinstance(components.get("strategy-lab-shadow"), dict) else {}
    snapshot_component = components.get("cloudflare-snapshot-publish") if isinstance(components.get("cloudflare-snapshot-publish"), dict) else {}
    print("\n=== LIVE COMPONENTS ===")
    print(json.dumps({
        "supervisor_started_at": status.get("started_at"),
        "strategy_lab": {
            "status": lab_component.get("status"),
            "runs": int(lab_component.get("runs") or 0),
            "last_error": str(lab_component.get("last_error") or ""),
            "last_success_at": lab_component.get("last_success_at"),
        },
        "snapshot_publisher": {
            "status": snapshot_component.get("status"),
            "runs": int(snapshot_component.get("runs") or 0),
            "last_error": str(snapshot_component.get("last_error") or ""),
            "last_success_at": snapshot_component.get("last_success_at"),
        },
    }, ensure_ascii=False, indent=2))

    candidate_state = read_strategy_lab_candidates(DB_PATH)
    evaluations = candidate_state.get("evaluations") if isinstance(candidate_state.get("evaluations"), dict) else {}
    criteria = candidate_state.get("criteria") if isinstance(candidate_state.get("criteria"), dict) else {}
    summary = candidate_state.get("summary") if isinstance(candidate_state.get("summary"), dict) else {}
    gate_lengths = sorted({len(row.get("gates") or []) for row in evaluations.values() if isinstance(row, dict)})
    statuses: dict[str, int] = {}
    for row in evaluations.values():
        if not isinstance(row, dict):
            continue
        key = str(row.get("status") or "unknown")
        statuses[key] = statuses.get(key, 0) + 1
    print("\n=== CANDIDATE GATES ===")
    print(json.dumps({
        "criteria": criteria,
        "summary": summary,
        "evaluation_count": len(evaluations),
        "statuses": statuses,
        "gate_lengths": gate_lengths,
    }, ensure_ascii=False, indent=2))

    snapshot = CloudflareSnapshotPublisher().build_snapshot()
    public = snapshot.get("public") if isinstance(snapshot.get("public"), dict) else {}
    lab_public = public.get("strategy_lab") if isinstance(public.get("strategy_lab"), dict) else {}
    experiments = lab_public.get("experiments") if isinstance(lab_public.get("experiments"), list) else []
    with_candidate = sum(1 for row in experiments if isinstance(row, dict) and isinstance(row.get("candidate"), dict))
    print("\n=== READ-ONLY SNAPSHOT CONTRACT ===")
    print(json.dumps({
        "public_version": int(public.get("version") or 0),
        "strategy_lab_version": int(lab_public.get("version") or 0),
        "experiments": len(experiments),
        "experiments_with_candidate": with_candidate,
        "candidate_summary": lab_public.get("candidate_summary") or {},
        "paper_only": bool(lab_public.get("paper_only")),
        "auto_promote": (lab_public.get("candidate_criteria") or {}).get("auto_promote"),
        "cloudflare_to_pc_control": False,
    }, ensure_ascii=False, indent=2))

    viewer_index = VIEWER_INDEX.read_text(encoding="utf-8", errors="replace") if VIEWER_INDEX.exists() else ""
    ui = {
        "viewer_candidate_js_v3": "strategy-lab-v1.js?v=3" in viewer_index,
        "viewer_candidate_css_v3": "strategy-lab-v1.css?v=3" in viewer_index,
        "read_only_mode": "READ ONLY PAPER" in viewer_index,
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
    if lab_component.get("last_error"):
        errors.append(f"Strategy Lab error: {lab_component.get('last_error')}")
    if snapshot_component.get("last_error"):
        errors.append(f"snapshot publisher error: {snapshot_component.get('last_error')}")
    if lab_component.get("status") not in {"healthy", "running"}:
        pending.append("Strategy Lab has not completed a healthy cycle")
    if snapshot_component.get("status") not in {"healthy", "running"}:
        pending.append("snapshot publisher has not completed a healthy cycle")
    supervisor_started = float(status.get("started_at") or 0.0)
    if commit_epoch and supervisor_started + 5 < commit_epoch:
        pending.append("research supervisor has not restarted onto the candidate-gate Python code")
    if len(evaluations) < 12:
        pending.append("candidate evaluations have not reached all base Strategy Lab experiments")
    if gate_lengths != [8]:
        errors.append(f"candidate gate shape is unexpected: {gate_lengths}")
    if criteria.get("auto_promote") is not False:
        errors.append("candidate gate must not auto-promote strategies")
    if int(criteria.get("min_closed_trades") or 0) != 30 or int(criteria.get("min_traded_markets") or 0) != 5:
        errors.append("candidate minimum sample contract changed unexpectedly")
    if int(lab_public.get("version") or 0) < 2:
        errors.append("Strategy Lab snapshot candidate contract is missing")
    if len(experiments) and with_candidate != len(experiments):
        errors.append("not every published Strategy Lab experiment has a candidate evaluation")
    if not all(ui.values()):
        errors.append("candidate gate viewer assets are not linked correctly")
    if not deployed_head or (local and not deployed_head.startswith(local)):
        pending.append("Pages has not deployed the current Git HEAD")
    if not deploy.get("health_ok"):
        pending.append("Pages health check is not green")

    print("\n=== RESULT ===")
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        print("PHASE4_CANDIDATE_GATE=FAIL")
        raise SystemExit(1)
    if pending:
        for item in pending:
            print(f"PENDING: {item}")
        print("PHASE4_CANDIDATE_GATE=WARMING")
        return
    print("PHASE4_CANDIDATE_GATE=PASS")


if __name__ == "__main__":
    main()
