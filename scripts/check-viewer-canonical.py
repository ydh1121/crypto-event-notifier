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
JS = ROOT / "cloudflare-pages/public/viewer-canonical-v4.js"
CSS = ROOT / "cloudflare-pages/public/viewer-canonical-v4.css"
STRATEGY = ROOT / "cloudflare-pages/public/strategy-lab-v2.js"
RECORDS = ROOT / "cloudflare-pages/public/records-port.js"
SITEMAP = ROOT / "docs/workstreams/viewer-sitemap-v4.md"
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
    strategy = STRATEGY.read_text(encoding="utf-8", errors="replace") if STRATEGY.exists() else ""
    records = RECORDS.read_text(encoding="utf-8", errors="replace") if RECORDS.exists() else ""
    sitemap = SITEMAP.read_text(encoding="utf-8", errors="replace") if SITEMAP.exists() else ""
    static = {
        "build_23": 'crypto-viewer-build" content="2026.08.26-23' in index,
        "canonical_v4_js": "viewer-canonical-v4.js?v=1" in index,
        "canonical_v4_css": "viewer-canonical-v4.css?v=1" in index,
        "old_canonical_unlinked": "viewer-canonical-v3.js" not in index and "viewer-canonical-v3.css" not in index,
        "sitemap_documented": all(x in sitemap for x in ("Dashboard", "Research", "PAPER", "Assets")),
        "four_main_nav": all(f'>{x}</button>' in index for x in ("대시보드", "리서치", "PAPER", "자산")),
        "dashboard_zones": all(x in js for x in ("먼저 확인할 것", "전체 PAPER 증감", "지금 볼 코인", "PAPER 거래소별 상태")),
        "research_split": "v4-research-shell" in css and "v4ResearchSide" in js and "v4ResearchMain" in js,
        "research_inline_paper": "PAPER 참고" in js and "PAPER에서 보기" in js,
        "paper_default_summary": "let paperMode='summary'" in js and "data-paper-mode=\"summary\"" in js,
        "paper_sections": all(x in js for x in ("코인별 성과", "전략 비교", "거래 기록", "거래소 비교")),
        "combined_paper_pnl": "전체 PAPER 증감" in js and "빗썸+업비트 통합" in js,
        "assets_no_forced_navigation": "누르면 리서치로 이동" not in js,
        "records_no_forced_navigation": "switchView('coin')" not in records,
        "strategy_table": "strategy-table-row" in strategy,
        "compare_sticky_header": "phase3-compare-header" in css and "position:sticky" in css,
    }
    print("\n=== CANONICAL V4 SITEMAP CONTRACT ===")
    print(json.dumps(static, ensure_ascii=False, indent=2))

    pending: list[str] = []
    errors: list[str] = []
    if not all(static.values()):
        errors.append("canonical v4 sitemap contract is incomplete")
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

    remote_contract = {"index_status":0,"js_status":0,"css_status":0,"build_23":False,"canonical_v4_loaded":False,"old_v3_absent":False}
    if url:
        nonce = str(time.time_ns())
        si, ri = fetch(f"{url}/?canonical={nonce}")
        sj, rj = fetch(f"{url}/viewer-canonical-v4.js?v=1&canonical={nonce}")
        sc, rc = fetch(f"{url}/viewer-canonical-v4.css?v=1&canonical={nonce}")
        remote_contract.update({
            "index_status":si,
            "js_status":sj,
            "css_status":sc,
            "build_23":'crypto-viewer-build" content="2026.08.26-23' in ri,
            "canonical_v4_loaded":"__viewerCanonicalV4Loaded" in rj and "canonical-v4" in rc,
            "old_v3_absent":"viewer-canonical-v3.js" not in ri,
        })
        if any(x != 200 for x in (si,sj,sc)):
            pending.append("canonical v4 viewer assets are not reachable yet")
        elif not all((remote_contract["build_23"],remote_contract["canonical_v4_loaded"],remote_contract["old_v3_absent"])):
            pending.append("Pages is still serving the previous viewer build")
    else:
        pending.append("viewer URL is not available in deploy state")

    print("\n=== REMOTE VIEWER CONTRACT ===")
    print(json.dumps(remote_contract, ensure_ascii=False, indent=2))
    print("\n=== RESULT ===")
    if errors:
        for x in errors: print(f"ERROR: {x}")
        print("VIEWER_CANONICAL_V4=FAIL")
        raise SystemExit(1)
    if pending:
        for x in pending: print(f"PENDING: {x}")
        print("VIEWER_CANONICAL_V4=WARMING")
        return
    print("BROWSER_JOURNEY_QA_REQUIRED=true")
    print("VIEWER_CANONICAL_V4=PASS")


if __name__ == "__main__":
    main()
