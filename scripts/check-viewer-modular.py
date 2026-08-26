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
    "modules/shared/components.js", "modules/shared/charts.js", "modules/shared/decision.js",
    "modules/services/market-detail.js", "modules/pages/dashboard.js", "modules/pages/research.js",
    "modules/pages/assets.js", "modules/pages/paper.js", "modules/pages/strategy.js",
    "modules/pages/records.js", "modules/pages/system.js", "modules/main.js",
    "modules/styles/charts.css",
]
LEGACY_ROOT_PATTERNS = (
    "app.js",
    "asset-local-port.*",
    "asset-parity-shell.*",
    "exchange-phase3.*",
    "local-parity.*",
    "market-detail.*",
    "records-port.*",
    "strategy-lab-v1.*",
    "strategy-lab-v2.js",
    "viewer-best-port.*",
    "viewer-canonical-v1.*",
    "viewer-canonical-v2.*",
    "viewer-canonical-v3.*",
    "viewer-canonical-v4.*",
    "viewer-ia-v5.*",
    "viewer-performance-v1.*",
    "viewer-performance-v2.*",
    "viewer-shell-v2.*",
    "viewer-shell-v3.*",
    "viewer-ux-v4.*",
    "styles.css",
    "workspaces.css",
)
REMOTE_LEGACY_PATHS = (
    "app.js",
    "asset-local-port.js",
    "exchange-phase3.js",
    "local-parity.js",
    "records-port.js",
    "strategy-lab-v2.js",
    "viewer-canonical-v4.js",
    "viewer-ia-v5.js",
    "styles.css",
    "workspaces.css",
)


def same(a: str, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except OSError:
        return False


if os.name == "nt" and VENV.exists() and not same(sys.executable, VENV):
    os.execv(str(VENV), [str(VENV), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]])


def git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def fetch(url: str) -> tuple[int, str]:
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
        )
        return response.status_code, response.text
    except requests.RequestException:
        return 0, ""


def legacy_files_absent() -> bool:
    return all(not any(PUBLIC.glob(pattern)) for pattern in LEGACY_ROOT_PATTERNS)


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
    decision_js = text(PUBLIC / "modules/shared/decision.js")
    store_js = text(PUBLIC / "modules/core/store.js")

    static = {
        "build_27": 'crypto-viewer-build" content="2026.08.26-27' in index,
        "module_entry_v4": 'type="module" src="/modules/main.js?v=4"' in index,
        "all_required_modules": all((PUBLIC / path).exists() for path in REQUIRED),
        "charts_css_linked": '/modules/styles/charts.css?v=2' in index,
        "legacy_files_physically_absent": legacy_files_absent(),
        "six_main_nav": all(f'data-route="{route}"' in index for route in ("dashboard", "research", "assets", "paper", "strategy", "records")),
        "system_utility": 'id="systemStatusBtn"' in index,
        "single_store": "from'./core/store.js'" in main_js,
        "page_modules": all(f"create{name}Page" in main_js for name in ("Dashboard", "Research", "Assets", "Paper", "Strategy", "Records", "System")),
        "asset_same_page_detail": "data-asset-market" in assets_js and "asset-workspace" in assets_js,
        "asset_allocation_in_master": "allocation-panel compact" in assets_js and "asset-master" in assets_js,
        "dashboard_recent_activity": "최근 중요 변화" in dashboard_js and "recordsData" in dashboard_js,
        "research_filtered_selection": "filteredRows" in research_js and "현재 조건에서 선택할 코인이 없습니다." in research_js,
        "research_decision_filter": (
            "../shared/decision.js" in research_js
            and all(token in decision_js for token in (
                "DECISION_FILTERS", "decisionCounts", "decisionMatches", "decisionEmptyMessage",
                "regime>=65&&entry>=68", "regime>=70&&entry<50", "regime<50",
            ))
        ),
        "research_history": all(token in research_js for token in (
            "data-research-range", "priceFillChart", "scoreHistoryChart", "BTC 시장참고", "ETH 시장참고",
        )),
        "paper_price_fill_history": "data-paper-range" in paper_js and "priceFillChart" in paper_js,
        "shared_chart_module": all(token in charts_js for token in (
            "rangeControl", "priceFillChart", "scoreHistoryChart", "simpleLineChart",
        )),
        "records_period_coin_filters": "data-records-period" in records_js and "data-records-search" in records_js,
        "paper_compare_search_sort": "data-compare-search" in paper_js and "data-compare-sort" in paper_js,
        "independent_filter_state": all(token in store_js for token in (
            "researchExchange", "paperExchange", "strategyExchange", "recordsExchange", "researchRange", "paperRange",
        )),
        "checklist_present": "## 0. 모듈 아키텍처" in checklist and "[x] PC 우측 선택 종목 상세" in checklist,
        "reference_contract": all(token in reference for token in (
            "freqtrade/frequi", "hummingbot/dashboard", "marketcalls/openalgo", "OpenBB-finance/OpenBB",
        )),
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
    print(json.dumps({
        "deployed_head": head[:7],
        "health_ok": bool(deploy.get("health_ok")),
        "viewer_url": url,
    }, ensure_ascii=False, indent=2))
    if not head or (local and not head.startswith(local)):
        pending.append("Pages has not deployed the current Git HEAD")
    if not deploy.get("health_ok"):
        pending.append("Pages health check is not green")

    remote_contract = {
        "index_status": 0,
        "main_status": 0,
        "assets_status": 0,
        "research_status": 0,
        "paper_status": 0,
        "charts_status": 0,
        "decision_status": 0,
        "build_27": False,
        "module_entry_v4": False,
        "legacy_files_absent": False,
        "asset_master_detail": False,
        "asset_allocation_in_master": False,
        "research_filter_fix": False,
        "research_decision_filter": False,
        "research_history": False,
        "paper_history": False,
        "shared_charts": False,
    }
    if url:
        nonce = str(time.time_ns())
        si, ri = fetch(f"{url}/?modular={nonce}")
        sm, rm = fetch(f"{url}/modules/main.js?v=4&modular={nonce}")
        sa, ra = fetch(f"{url}/modules/pages/assets.js?modular={nonce}")
        sr, rr = fetch(f"{url}/modules/pages/research.js?modular={nonce}")
        sp, rp = fetch(f"{url}/modules/pages/paper.js?modular={nonce}")
        sc, rc = fetch(f"{url}/modules/shared/charts.js?modular={nonce}")
        sd, rd = fetch(f"{url}/modules/shared/decision.js?modular={nonce}")
        legacy_statuses = {path: fetch(f"{url}/{path}?retired={nonce}")[0] for path in REMOTE_LEGACY_PATHS}
        remote_contract.update({
            "index_status": si,
            "main_status": sm,
            "assets_status": sa,
            "research_status": sr,
            "paper_status": sp,
            "charts_status": sc,
            "decision_status": sd,
            "build_27": 'crypto-viewer-build" content="2026.08.26-27' in ri,
            "module_entry_v4": 'type="module" src="/modules/main.js?v=4"' in ri and "createAssetsPage" in rm,
            "legacy_files_absent": all(status == 404 for status in legacy_statuses.values()),
            "asset_master_detail": "asset-workspace" in ra and "data-asset-market" in ra,
            "asset_allocation_in_master": "allocation-panel compact" in ra,
            "research_filter_fix": "filteredRows" in rr and "현재 조건에서 선택할 코인이 없습니다." in rr,
            "research_decision_filter": "../shared/decision.js" in rr and "DECISION_FILTERS" in rd and "decisionMatches" in rd,
            "research_history": "data-research-range" in rr and "scoreHistoryChart" in rr,
            "paper_history": "data-paper-range" in rp and "priceFillChart" in rp,
            "shared_charts": all(token in rc for token in ("priceFillChart", "scoreHistoryChart", "rangeControl")),
        })
        print("remote_legacy_statuses=" + json.dumps(legacy_statuses, ensure_ascii=False, sort_keys=True))
        required_codes = (si, sm, sa, sr, sp, sc, sd)
        if any(code != 200 for code in required_codes):
            pending.append("modular viewer assets are not reachable yet")
        elif not all(
            remote_contract[key]
            for key in (
                "build_27", "module_entry_v4", "legacy_files_absent", "asset_master_detail",
                "asset_allocation_in_master", "research_filter_fix", "research_decision_filter",
                "research_history", "paper_history", "shared_charts",
            )
        ):
            pending.append("Pages is still serving the previous viewer build")
    else:
        pending.append("viewer URL is not available in deploy state")

    print("\n=== REMOTE VIEWER CONTRACT ===")
    print(json.dumps(remote_contract, ensure_ascii=False, indent=2))
    print("\n=== RESULT ===")
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        print("VIEWER_MODULAR_V6=FAIL")
        raise SystemExit(1)
    if pending:
        for item in pending:
            print(f"PENDING: {item}")
        print("VIEWER_MODULAR_V6=WARMING")
        return
    print("BROWSER_JOURNEY_QA_REQUIRED=true")
    print("VIEWER_MODULAR_V6=PASS")


if __name__ == "__main__":
    main()
