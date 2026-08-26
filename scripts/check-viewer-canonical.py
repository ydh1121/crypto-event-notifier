from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv" / "Scripts" / "python.exe"
INDEX = ROOT / "cloudflare-pages/public/index.html"
JS = ROOT / "cloudflare-pages/public/viewer-canonical-v1.js"
CSS = ROOT / "cloudflare-pages/public/viewer-canonical-v1.css"
DEPLOY = ROOT / "b3_trader/data/research-platform/cloudflare-pages-deploy-state.json"


def same(a: str, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except OSError:
        return False


if os.name == "nt" and VENV.exists() and not same(sys.executable, VENV):
    os.execv(str(VENV), [str(VENV), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]])


def git(*args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def read_json(path: Path) -> dict:
    try:
        x = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return x if isinstance(x, dict) else {}


def fetch(url: str) -> tuple[int, str]:
    try:
        r = requests.get(url, timeout=20, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
        return r.status_code, r.text
    except requests.RequestException:
        return 0, ""


def main() -> None:
    local = git("rev-parse", "--short", "HEAD")
    remote = git("rev-parse", "--short", "origin/b3-auto-trader-phase1")
    print(f"python={sys.executable}")
    print(f"git_local={local or '-'}")
    print(f"git_remote={remote or '-'}")

    index = INDEX.read_text(encoding="utf-8", errors="replace") if INDEX.exists() else ""
    js = JS.read_text(encoding="utf-8", errors="replace") if JS.exists() else ""
    css = CSS.read_text(encoding="utf-8", errors="replace") if CSS.exists() else ""
    static = {
        "build_20": 'crypto-viewer-build" content="2026.08.26-20' in index,
        "canonical_js": "viewer-canonical-v1.js?v=1" in index,
        "canonical_css": "viewer-canonical-v1.css?v=1" in index,
        "legacy_ux_unlinked": "viewer-ux-v4.js" not in index and "viewer-ux-v4.css" not in index,
        "legacy_ia_unlinked": "viewer-ia-v5.js" not in index and "viewer-ia-v5.css" not in index,
        "four_main_nav": all(f'>{x}</button>' in index for x in ("개요", "자산", "리서치", "PAPER")),
        "assets_panel": "ensureAssetsPanel" in js,
        "overview_priority": "먼저 확인할 것" in js and "canonical-alerts" in css,
        "research_priority": "canonical-market-pulse" in js and "canonical-research-find" in css,
        "paper_subnav": all(x in js for x in ("성과", "거래기록", "전략비교", "거래소비교")),
        "system_utility": "canonicalSystemBtn" in js,
    }
    print("\n=== CANONICAL JOURNEY CONTRACT ===")
    print(json.dumps(static, ensure_ascii=False, indent=2))

    pending: list[str] = []
    errors: list[str] = []
    if not all(static.values()):
        errors.append("canonical viewer source contract is incomplete")
    if not local or not remote or local != remote:
        pending.append("Git local/remote HEAD has not synchronized yet")

    deploy = read_json(DEPLOY)
    url = str(deploy.get("viewer_url") or "").rstrip("/")
    head = str(deploy.get("deployed_head") or "")
    print("\n=== LOCAL DEPLOY STATE ===")
    print(json.dumps({"deployed_head": head[:7], "health_ok": bool(deploy.get("health_ok")), "viewer_url": url}, ensure_ascii=False, indent=2))
    if not head or (local and not head.startswith(local)):
        pending.append("Pages has not deployed the current Git HEAD")
    if not deploy.get("health_ok"):
        pending.append("Pages health check is not green")

    remote_contract = {"index_status": 0, "js_status": 0, "css_status": 0, "build_20": False, "canonical_loaded": False, "legacy_layers_absent": False}
    if url:
        nonce = str(time.time_ns())
        si, ri = fetch(f"{url}/?canonical={nonce}")
        sj, rj = fetch(f"{url}/viewer-canonical-v1.js?v=1&canonical={nonce}")
        sc, rc = fetch(f"{url}/viewer-canonical-v1.css?v=1&canonical={nonce}")
        remote_contract.update({
            "index_status": si,
            "js_status": sj,
            "css_status": sc,
            "build_20": 'crypto-viewer-build" content="2026.08.26-20' in ri,
            "canonical_loaded": "__viewerCanonicalV1Loaded" in rj and ".canonical-overview" in rc,
            "legacy_layers_absent": "viewer-ux-v4.js" not in ri and "viewer-ia-v5.js" not in ri,
        })
        if any(x != 200 for x in (si, sj, sc)):
            pending.append("canonical viewer assets are not reachable yet")
        elif not all((remote_contract["build_20"], remote_contract["canonical_loaded"], remote_contract["legacy_layers_absent"])):
            pending.append("Pages is still serving the previous viewer build")
    else:
        pending.append("viewer URL is not available in deploy state")

    print("\n=== REMOTE VIEWER CONTRACT ===")
    print(json.dumps(remote_contract, ensure_ascii=False, indent=2))
    print("\n=== RESULT ===")
    if errors:
        for x in errors:
            print(f"ERROR: {x}")
        print("VIEWER_CANONICAL=FAIL")
        raise SystemExit(1)
    if pending:
        for x in pending:
            print(f"PENDING: {x}")
        print("VIEWER_CANONICAL=WARMING")
        return
    print("VIEWER_CANONICAL=PASS")


if __name__ == "__main__":
    main()
