from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
INDEX_PATH = REPO_ROOT / "cloudflare-pages/public/index.html"
PERF_PATH = REPO_ROOT / "cloudflare-pages/public/viewer-performance-v1.js"
DEPLOY_PATH = REPO_ROOT / "b3_trader/data/research-platform/cloudflare-pages-deploy-state.json"


def _same_path(a: str, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except OSError:
        return False


if os.name == "nt" and VENV_PYTHON.exists() and not _same_path(sys.executable, VENV_PYTHON):
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]])


def git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def fetch_text(url: str) -> tuple[int, str]:
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
        )
        return response.status_code, response.text
    except requests.RequestException:
        return 0, ""


def main() -> None:
    local = git("rev-parse", "--short", "HEAD")
    remote = git("rev-parse", "--short", "origin/b3-auto-trader-phase1")
    print(f"python={sys.executable}")
    print(f"git_local={local or '-'}")
    print(f"git_remote={remote or '-'}")

    errors: list[str] = []
    pending: list[str] = []

    index = INDEX_PATH.read_text(encoding="utf-8", errors="replace") if INDEX_PATH.exists() else ""
    perf = PERF_PATH.read_text(encoding="utf-8", errors="replace") if PERF_PATH.exists() else ""
    order = [
        index.find("viewer-performance-v1.js?v=1"),
        index.find("exchange-phase3.js?v=1"),
        index.find("app.js?v=3"),
    ]
    markers = {
        "performance_script_first": min(order) >= 0 and order == sorted(order),
        "active_view_rendering": "const renderActive=()=>" in perf,
        "keyed_market_rows": "marketRenderSignature" in perf and "existing=new Map" in perf,
        "snapshot_coalescing": "snapshotInFlight" in perf,
        "single_snapshot_parse": "url.pathname==='/api/snapshot')return nativeFetch" in perf,
        "hidden_coin_guard": "activeView()==='coin'" in perf,
        "hidden_records_guard": "activeView()==='records'" in perf,
        "hidden_results_guard": "activeView()==='results'" in perf,
        "observer_attribute_guard": "target?.id==='marketList'" in perf and "next.attributes=false" in perf,
        "offscreen_row_containment": "content-visibility:auto" in perf,
        "performance_telemetry": "window.__viewerPerformance=" in perf,
    }
    print("\n=== STATIC PERFORMANCE CONTRACT ===")
    print(json.dumps(markers, ensure_ascii=False, indent=2))
    if not all(markers.values()):
        errors.append("viewer performance source contract is incomplete")

    deploy = read_json(DEPLOY_PATH)
    viewer_url = str(deploy.get("viewer_url") or "").rstrip("/")
    deployed_head = str(deploy.get("deployed_head") or "")
    deployment = {
        "deployed_head": deployed_head[:7],
        "health_ok": bool(deploy.get("health_ok")),
        "viewer_url": viewer_url,
    }
    print("\n=== LOCAL DEPLOY STATE ===")
    print(json.dumps(deployment, ensure_ascii=False, indent=2))

    if not local or not remote or local != remote:
        pending.append("Git local/remote HEAD has not synchronized yet")
    if not deployed_head or (local and not deployed_head.startswith(local)):
        pending.append("Pages has not deployed the current Git HEAD")
    if not deploy.get("health_ok"):
        pending.append("Pages health check is not green")

    remote_contract = {
        "index_status": 0,
        "performance_js_status": 0,
        "build_15": False,
        "performance_asset_linked": False,
        "performance_asset_loaded": False,
    }
    if viewer_url:
        nonce = str(time.time_ns())
        index_status, remote_index = fetch_text(f"{viewer_url}/?performance_check={nonce}")
        js_status, remote_js = fetch_text(f"{viewer_url}/viewer-performance-v1.js?v=1&performance_check={nonce}")
        remote_contract.update(
            {
                "index_status": index_status,
                "performance_js_status": js_status,
                "build_15": "crypto-viewer-build\" content=\"2026.08.26-15" in remote_index,
                "performance_asset_linked": "viewer-performance-v1.js?v=1" in remote_index,
                "performance_asset_loaded": "__viewerPerformanceV1Loaded" in remote_js and "marketRenderSignature" in remote_js,
            }
        )
        if index_status != 200 or js_status != 200:
            pending.append("deployed viewer assets are not reachable yet")
        elif not all((remote_contract["build_15"], remote_contract["performance_asset_linked"], remote_contract["performance_asset_loaded"])):
            pending.append("Pages is still serving the pre-performance viewer build")
    else:
        pending.append("viewer URL is not available in deploy state")

    print("\n=== REMOTE VIEWER CONTRACT ===")
    print(json.dumps(remote_contract, ensure_ascii=False, indent=2))

    print("\n=== RESULT ===")
    print("BROWSER_ENDURANCE_REQUIRED=true")
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        print("VIEWER_PERFORMANCE_READY=FAIL")
        raise SystemExit(1)
    if pending:
        for item in pending:
            print(f"PENDING: {item}")
        print("VIEWER_PERFORMANCE_READY=WARMING")
        return
    print("VIEWER_PERFORMANCE_READY=PASS")


if __name__ == "__main__":
    main()
