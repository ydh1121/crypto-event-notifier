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
JS = ROOT / "cloudflare-pages/public/viewer-canonical-v2.js"
CSS = ROOT / "cloudflare-pages/public/viewer-canonical-v2.css"
STRATEGY = ROOT / "cloudflare-pages/public/strategy-lab-v2.js"
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
    static = {
        "build_21": 'crypto-viewer-build" content="2026.08.26-21' in index,
        "canonical_v2_js": "viewer-canonical-v2.js?v=1" in index,
        "canonical_v2_css": "viewer-canonical-v2.css?v=1" in index,
        "strategy_v2": "strategy-lab-v2.js?v=1" in index,
        "legacy_canonical_unlinked": "viewer-canonical-v1.js" not in index and "viewer-canonical-v1.css" not in index,
        "legacy_strategy_unlinked": "strategy-lab-v1.js" not in index and "strategy-lab-v1.css" not in index,
        "four_main_nav": all(f'>{x}</button>' in index for x in ("개요", "자산", "리서치", "PAPER")),
        "nav_reassertion": "navSignature" in js and "ensureNavigation" in js,
        "user_chip_preserved": "ensureUserChip" in js and "viewer-intro" not in js.split("ensureUserChip", 1)[0],
        "loading_state_model": "canonical-state loading" in js and "PAPER 코인 결과를 불러오는 중" in js,
        "assets_states": "자산정보를 볼 권한이 없습니다" in js and "등록된 보유자산이 없습니다" in js,
        "research_paper_separation": "paperResearchExtra" in js and "strategyLabMarketCard" in js and "canonical-hidden" in css,
        "paper_subnav": all(x in js for x in ("성과", "거래기록", "전략비교", "거래소비교")),
        "paper_priority_kpis": all(x in js for x in ("전체 수익률", "최대 낙폭", "완료 거래", "승률")),
        "strategy_table": "strategy-table-row" in strategy and "strategy-lab-grid" not in strategy,
        "compare_sticky_header": "phase3-compare-header" in css and "position:sticky" in css,
    }
    print("\n=== CANONICAL V2 CONTRACT ===")
    print(json.dumps(static, ensure_ascii=False, indent=2))

    pending: list[str] = []
    errors: list[str] = []
    if not all(static.values()):
        errors.append("canonical v2 source contract is incomplete")
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

    remote_contract = {
        "index_status": 0,
        "js_status": 0,
        "css_status": 0,
        "strategy_status": 0,
        "build_21": False,
        "canonical_v2_loaded": False,
        "legacy_v1_absent": False,
    }
    if url:
        nonce = str(time.time_ns())
        si, ri = fetch(f"{url}/?canonical={nonce}")
        sj, rj = fetch(f"{url}/viewer-canonical-v2.js?v=1&canonical={nonce}")
        sc, rc = fetch(f"{url}/viewer-canonical-v2.css?v=1&canonical={nonce}")
        ss, rs = fetch(f"{url}/strategy-lab-v2.js?v=1&canonical={nonce}")
        remote_contract.update({
            "index_status": si,
            "js_status": sj,
            "css_status": sc,
            "strategy_status": ss,
            "build_21": 'crypto-viewer-build" content="2026.08.26-21' in ri,
            "canonical_v2_loaded": "__viewerCanonicalV2Loaded" in rj and ".canonical-overview" in rc and "__strategyLabViewerV2Loaded" in rs,
            "legacy_v1_absent": "viewer-canonical-v1.js" not in ri and "strategy-lab-v1.js" not in ri,
        })
        if any(x != 200 for x in (si, sj, sc, ss)):
            pending.append("canonical v2 viewer assets are not reachable yet")
        elif not all((remote_contract["build_21"], remote_contract["canonical_v2_loaded"], remote_contract["legacy_v1_absent"])):
            pending.append("Pages is still serving the previous viewer build")
    else:
        pending.append("viewer URL is not available in deploy state")

    print("\n=== REMOTE VIEWER CONTRACT ===")
    print(json.dumps(remote_contract, ensure_ascii=False, indent=2))
    print("\n=== RESULT ===")
    if errors:
        for x in errors:
            print(f"ERROR: {x}")
        print("VIEWER_CANONICAL_V2=FAIL")
        raise SystemExit(1)
    if pending:
        for x in pending:
            print(f"PENDING: {x}")
        print("VIEWER_CANONICAL_V2=WARMING")
        return
    print("BROWSER_JOURNEY_QA_REQUIRED=true")
    print("VIEWER_CANONICAL_V2=PASS")


if __name__ == "__main__":
    main()
