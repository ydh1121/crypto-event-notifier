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
PUBLIC = ROOT / "cloudflare-pages/public"
INDEX = PUBLIC / "index.html"
MAIN = PUBLIC / "modules/main.js"
CHECKLIST = ROOT / "docs/VIEWER_REBUILD_CHECKLIST.md"
REFERENCE = ROOT / "docs/TRADING_UI_REFERENCE.md"
DEPLOY = ROOT / "b3_trader/data/research-platform/cloudflare-pages-deploy-state.json"
REQUIRED = [
    "modules/core/http.js", "modules/core/store.js", "modules/core/router.js", "modules/core/auth.js",
    "modules/core/snapshot.js", "modules/shared/format.js", "modules/shared/selectors.js",
    "modules/shared/components.js", "modules/shared/charts.js", "modules/services/market-detail.js",
    "modules/pages/dashboard.js", "modules/pages/research.js", "modules/pages/assets.js", "modules/pages/paper.js",
    "modules/pages/strategy.js", "modules/pages/records.js", "modules/pages/system.js", "modules/main.js",
    "modules/styles/charts.css",
]


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


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


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

    index = text(INDEX)
    main_js = text(MAIN)
    checklist = text(CHECKLIST)
    reference = text(REFERENCE)
    dashboard_js = text(PUBLIC / "modules/pages/dashboard.js")
    assets_js = text(PUBLIC / "modules/pages/assets.js")
    research_js = text(PUBLIC / "modules/pages/research.js")
    paper_js = text(PUBLIC / "modules/pages/paper.js")
    records_js = text(PUBLIC / "modules/pages/records.js")
    charts_js = text(PUBLIC / "modules/shared/charts.js")
    store_js = text(PUBLIC / "modules/core/store.js")

    static = {
        "build_26": 'crypto-viewer-build" content="2026.08.26-26' in index,
        "module_entry_v3": 'type="module" src="/modules/main.js?v=3"' in index,
        "all_required_modules": all((PUBLIC / path).exists() for path in REQUIRED),
        "charts_css_linked": '/modules/styles/charts.css?v=1' in index,
        "legacy_app_unlinked": '/app.js' not in index,
        "legacy_canonical_unlinked": 'viewer-canonical-' not in index,
        "legacy_exchange_unlinked": 'exchange-phase3.js' not in index,
        "legacy_records_unlinked": 'records-port.js' not in index,
        "legacy_strategy_unlinked": 'strategy-lab-v2.js' not in index,
        "six_main_nav": all(f'data-route="{x}"' in index for x in ("dashboard", "research", "assets", "paper", "strategy", "records")),
        "system_utility": 'id="systemStatusBtn"' in index,
        "single_store": "from'./core/store.js'" in main_js,
        "page_modules": all(f"create{x}Page" in main_js for x in ("Dashboard", "Research", "Assets", "Paper", "Strategy", "Records", "System")),
        "asset_same_page_detail": "data-asset-market" in assets_js and "asset-workspace" in assets_js,
        "asset_allocation_in_master": "allocation-panel compact" in assets_js and "asset-master" in assets_js,
        "dashboard_recent_activity": "최근 중요 변화" in dashboard_js and "recordsData" in dashboard_js,
        "research_filtered_selection": "filteredRows" in research_js and "현재 조건에서 선택할 코인이 없습니다." in research_js,
        "research_history": all(x in research_js for x in ("data-research-range", "priceFillChart", "scoreHistoryChart", "BTC 시장참고", "ETH 시장참고")),
        "paper_price_fill_history": "data-paper-range" in paper_js and "priceFillChart" in paper_js,
        "shared_chart_module": all(x in charts_js for x in ("rangeControl", "priceFillChart", "scoreHistoryChart", "simpleLineChart")),
        "records_period_coin_filters": "data-records-period" in records_js and "data-records-search" in records_js,
        "paper_compare_search_sort": "data-compare-search" in paper_js and "data-compare-sort" in paper_js,
        "independent_filter_state": all(x in store_js for x in ("researchExchange", "paperExchange", "strategyExchange", "recordsExchange", "researchRange", "paperRange")),
        "checklist_present": "## 0. 모듈 아키텍처" in checklist and "[x] PC 우측 선택 종목 상세" in checklist,
        "reference_contract": all(x in reference for x in ("freqtrade/frequi", "hummingbot/dashboard", "marketcalls/openalgo", "OpenBB-finance/OpenBB")),
    }
    print("\n=== MODULAR VIEWER V6 CONTRACT ===")
    print(json.dumps(static, ensure_ascii=False, indent=2))
    errors: list[str] = []
    pending: list[str] = []
    if not all(static.values()):
        errors.append("modular source contract is incomplete")
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
        "index_status": 0, "main_status": 0, "assets_status": 0, "research_status": 0, "paper_status": 0, "charts_status": 0,
        "build_26": False, "module_entry_v3": False, "legacy_absent": False,
        "asset_master_detail": False, "asset_allocation_in_master": False, "research_filter_fix": False,
        "research_history": False, "paper_history": False, "shared_charts": False,
    }
    if url:
        nonce = str(time.time_ns())
        si, ri = fetch(f"{url}/?modular={nonce}")
        sm, rm = fetch(f"{url}/modules/main.js?v=3&modular={nonce}")
        sa, ra = fetch(f"{url}/modules/pages/assets.js?modular={nonce}")
        sr, rr = fetch(f"{url}/modules/pages/research.js?modular={nonce}")
        sp, rp = fetch(f"{url}/modules/pages/paper.js?modular={nonce}")
        sc, rc = fetch(f"{url}/modules/shared/charts.js?modular={nonce}")
        remote_contract.update({
            "index_status": si,
            "main_status": sm,
            "assets_status": sa,
            "research_status": sr,
            "paper_status": sp,
            "charts_status": sc,
            "build_26": 'crypto-viewer-build" content="2026.08.26-26' in ri,
            "module_entry_v3": 'type="module" src="/modules/main.js?v=3"' in ri and "createAssetsPage" in rm,
            "legacy_absent": all(x not in ri for x in ("/app.js", "viewer-canonical-", "exchange-phase3.js", "records-port.js", "strategy-lab-v2.js")),
            "asset_master_detail": "asset-workspace" in ra and "data-asset-market" in ra,
            "asset_allocation_in_master": "allocation-panel compact" in ra,
            "research_filter_fix": "filteredRows" in rr and "현재 조건에서 선택할 코인이 없습니다." in rr,
            "research_history": "data-research-range" in rr and "scoreHistoryChart" in rr,
            "paper_history": "data-paper-range" in rp and "priceFillChart" in rp,
            "shared_charts": all(x in rc for x in ("priceFillChart", "scoreHistoryChart", "rangeControl")),
        })
        if any(code != 200 for code in (si, sm, sa, sr, sp, sc)):
            pending.append("modular viewer assets are not reachable yet")
        elif not all(v for k, v in remote_contract.items() if k.endswith(("_v3", "_26")) or k in ("legacy_absent", "asset_master_detail", "asset_allocation_in_master", "research_filter_fix", "research_history", "paper_history", "shared_charts")):
            pending.append("Pages is still serving the previous viewer build")
    else:
        pending.append("viewer URL is not available in deploy state")

    print("\n=== REMOTE VIEWER CONTRACT ===")
    print(json.dumps(remote_contract, ensure_ascii=False, indent=2))
    print("\n=== RESULT ===")
    if errors:
        for x in errors:
            print(f"ERROR: {x}")
        print("VIEWER_MODULAR_V6=FAIL")
        raise SystemExit(1)
    if pending:
        for x in pending:
            print(f"PENDING: {x}")
        print("VIEWER_MODULAR_V6=WARMING")
        return
    print("BROWSER_JOURNEY_QA_REQUIRED=true")
    print("VIEWER_MODULAR_V6=PASS")


if __name__ == "__main__":
    main()
