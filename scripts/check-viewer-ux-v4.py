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
PERF2_PATH = REPO_ROOT / "cloudflare-pages/public/viewer-performance-v2.js"
UX_JS_PATH = REPO_ROOT / "cloudflare-pages/public/viewer-ux-v4.js"
UX_CSS_PATH = REPO_ROOT / "cloudflare-pages/public/viewer-ux-v4.css"
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
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20, check=False,
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
        response = requests.get(url, timeout=20, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
        return response.status_code, response.text
    except requests.RequestException:
        return 0, ""


def main() -> None:
    local = git("rev-parse", "--short", "HEAD")
    remote = git("rev-parse", "--short", "origin/b3-auto-trader-phase1")
    print(f"python={sys.executable}")
    print(f"git_local={local or '-'}")
    print(f"git_remote={remote or '-'}")

    index = INDEX_PATH.read_text(encoding="utf-8", errors="replace") if INDEX_PATH.exists() else ""
    perf2 = PERF2_PATH.read_text(encoding="utf-8", errors="replace") if PERF2_PATH.exists() else ""
    uxjs = UX_JS_PATH.read_text(encoding="utf-8", errors="replace") if UX_JS_PATH.exists() else ""
    uxcss = UX_CSS_PATH.read_text(encoding="utf-8", errors="replace") if UX_CSS_PATH.exists() else ""

    static = {
        "build_17": 'crypto-viewer-build" content="2026.08.26-17' in index,
        "performance_v2_linked": "viewer-performance-v2.js?v=1" in index,
        "ux_js_linked": "viewer-ux-v4.js?v=1" in index,
        "ux_css_linked": "viewer-ux-v4.css?v=1" in index,
        "result_page_size_80": "const STEP=80" in perf2 and "data-viewer-more-results" in perf2,
        "coin_search": "uxCoinSearch" in uxjs and "uxCoinOptions" in uxjs,
        "legacy_chip_rail_pruned": "uxPruned" in uxjs,
        "strategy_lab_collapsible": "uxStrategyToggle" in uxjs and "ux-collapsed" in uxcss,
        "settings_components_collapsible": "uxComponentsToggle" in uxjs and "ux-components-expanded" in uxcss,
        "compare_internal_scroll": "phase3-compare-workspace" in uxcss and "max-height:calc(100vh - 190px)" in uxcss,
    }
    print("\n=== STATIC UX/PERFORMANCE CONTRACT ===")
    print(json.dumps(static, ensure_ascii=False, indent=2))

    pending: list[str] = []
    errors: list[str] = []
    if not all(static.values()):
        errors.append("viewer UX/performance source contract is incomplete")
    if not local or not remote or local != remote:
        pending.append("Git local/remote HEAD has not synchronized yet")

    deploy = read_json(DEPLOY_PATH)
    viewer_url = str(deploy.get("viewer_url") or "").rstrip("/")
    deployed_head = str(deploy.get("deployed_head") or "")
    print("\n=== LOCAL DEPLOY STATE ===")
    print(json.dumps({
        "deployed_head": deployed_head[:7],
        "health_ok": bool(deploy.get("health_ok")),
        "viewer_url": viewer_url,
    }, ensure_ascii=False, indent=2))
    if not deployed_head or (local and not deployed_head.startswith(local)):
        pending.append("Pages has not deployed the current Git HEAD")
    if not deploy.get("health_ok"):
        pending.append("Pages health check is not green")

    remote_contract = {
        "index_status": 0,
        "performance_v2_status": 0,
        "ux_js_status": 0,
        "ux_css_status": 0,
        "build_17": False,
        "assets_loaded": False,
    }
    if viewer_url:
        nonce = str(time.time_ns())
        i_status, r_index = fetch_text(f"{viewer_url}/?ux_check={nonce}")
        p_status, r_perf = fetch_text(f"{viewer_url}/viewer-performance-v2.js?v=1&ux_check={nonce}")
        j_status, r_js = fetch_text(f"{viewer_url}/viewer-ux-v4.js?v=1&ux_check={nonce}")
        c_status, r_css = fetch_text(f"{viewer_url}/viewer-ux-v4.css?v=1&ux_check={nonce}")
        remote_contract.update({
            "index_status": i_status,
            "performance_v2_status": p_status,
            "ux_js_status": j_status,
            "ux_css_status": c_status,
            "build_17": 'crypto-viewer-build" content="2026.08.26-17' in r_index,
            "assets_loaded": "__viewerPerformanceV2Loaded" in r_perf and "__viewerUxV4Loaded" in r_js and ".ux-coin-finder" in r_css,
        })
        if any(status != 200 for status in (i_status, p_status, j_status, c_status)):
            pending.append("new viewer assets are not reachable yet")
        elif not remote_contract["build_17"] or not remote_contract["assets_loaded"]:
            pending.append("Pages is still serving the previous viewer build")
    else:
        pending.append("viewer URL is not available in deploy state")

    print("\n=== REMOTE VIEWER CONTRACT ===")
    print(json.dumps(remote_contract, ensure_ascii=False, indent=2))

    print("\n=== RESULT ===")
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        print("VIEWER_UX_V4=FAIL")
        raise SystemExit(1)
    if pending:
        for item in pending:
            print(f"PENDING: {item}")
        print("VIEWER_UX_V4=WARMING")
        return
    print("VIEWER_UX_V4=PASS")


if __name__ == "__main__":
    main()
