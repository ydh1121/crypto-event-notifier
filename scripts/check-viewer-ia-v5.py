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
IA_JS_PATH = REPO_ROOT / "cloudflare-pages/public/viewer-ia-v5.js"
IA_CSS_PATH = REPO_ROOT / "cloudflare-pages/public/viewer-ia-v5.css"
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
    js = IA_JS_PATH.read_text(encoding="utf-8", errors="replace") if IA_JS_PATH.exists() else ""
    css = IA_CSS_PATH.read_text(encoding="utf-8", errors="replace") if IA_CSS_PATH.exists() else ""

    static = {
        "build_18": 'crypto-viewer-build" content="2026.08.26-18' in index,
        "ia_js_linked": "viewer-ia-v5.js?v=1" in index,
        "ia_css_linked": "viewer-ia-v5.css?v=1" in index,
        "purpose_nav": all(label in index for label in ("대시보드", "성과분석", "거래기록", "시스템")) and "coin:'코인분석'" in js,
        "exchange_bar_demoted": "#phase3ExchangeBar{display:none!important}" in css,
        "page_exchange_filter": "ia-exchange-filter" in js and "PAPER 거래소" in js and "거래소'" in js,
        "compare_results_only": "view==='results'" in js and "거래소 비교" in js,
        "dashboard_assets_separated": "iaAssetHeading" in js and "iaPaperHeading" in js,
        "native_datalist_removed": "removeAttribute('list')" in js and "iaCoinSuggestions" in js,
        "coin_suggestions_bounded": ".slice(0,8)" in js,
        "view_scroll_reset": "window.scrollTo({top:0" in js,
        "strategy_after_results": "layout.insertAdjacentElement('afterend',toggle)" in js,
    }
    print("\n=== INFORMATION ARCHITECTURE CONTRACT ===")
    print(json.dumps(static, ensure_ascii=False, indent=2))

    errors: list[str] = []
    pending: list[str] = []
    if not all(static.values()):
        errors.append("viewer IA v5 source contract is incomplete")
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
        "ia_js_status": 0,
        "ia_css_status": 0,
        "build_18": False,
        "assets_loaded": False,
    }
    if viewer_url:
        nonce = str(time.time_ns())
        i_status, r_index = fetch_text(f"{viewer_url}/?ia_check={nonce}")
        j_status, r_js = fetch_text(f"{viewer_url}/viewer-ia-v5.js?v=1&ia_check={nonce}")
        c_status, r_css = fetch_text(f"{viewer_url}/viewer-ia-v5.css?v=1&ia_check={nonce}")
        remote_contract.update({
            "index_status": i_status,
            "ia_js_status": j_status,
            "ia_css_status": c_status,
            "build_18": 'crypto-viewer-build" content="2026.08.26-18' in r_index,
            "assets_loaded": "__viewerIaV5Loaded" in r_js and ".ia-exchange-filter" in r_css,
        })
        if any(status != 200 for status in (i_status, j_status, c_status)):
            pending.append("viewer IA v5 assets are not reachable yet")
        elif not remote_contract["build_18"] or not remote_contract["assets_loaded"]:
            pending.append("Pages is still serving the previous viewer build")
    else:
        pending.append("viewer URL is not available in deploy state")

    print("\n=== REMOTE VIEWER CONTRACT ===")
    print(json.dumps(remote_contract, ensure_ascii=False, indent=2))

    print("\n=== RESULT ===")
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        print("VIEWER_IA_V5=FAIL")
        raise SystemExit(1)
    if pending:
        for item in pending:
            print(f"PENDING: {item}")
        print("VIEWER_IA_V5=WARMING")
        return
    print("VIEWER_IA_V5=PASS")


if __name__ == "__main__":
    main()
