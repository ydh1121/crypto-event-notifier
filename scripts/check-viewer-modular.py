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
DEPLOY = ROOT / "b3_trader/data/research-platform/cloudflare-pages-deploy-state.json"
PRIVATE_STORAGE = ROOT / "docs/PRIVATE_PORTFOLIO_STORAGE.md"
BUILD29_PLAN = ROOT / "docs/VIEWER_BUILD29_PLAN.md"
BUILD30_PLAN = ROOT / "docs/VIEWER_BUILD30_PLAN.md"
BUILD31_PLAN = ROOT / "docs/VIEWER_BUILD31_PLAN.md"
TASTES = ROOT / "TASTES.md"
REQUIRED = [
    "modules/core/http.js", "modules/core/store.js", "modules/core/router.js", "modules/core/auth.js",
    "modules/core/snapshot.js", "modules/shared/format.js", "modules/shared/selectors.js",
    "modules/shared/components.js", "modules/shared/charts.js", "modules/shared/decision.js",
    "modules/shared/averaging.js", "modules/services/market-detail.js", "modules/services/sectors.js",
    "modules/services/coin-profile.js", "modules/pages/dashboard.js", "modules/pages/research.js",
    "modules/pages/assets.js", "modules/pages/paper.js", "modules/pages/strategy.js", "modules/pages/sectors.js",
    "modules/pages/records.js", "modules/pages/system.js", "modules/main.js", "modules/styles/charts.css",
    "modules/styles/sectors.css", "modules/styles/build29.css", "modules/styles/exchange-ui.css",
]
LEGACY_ROOT_PATTERNS = (
    "app.js", "asset-local-port.*", "asset-parity-shell.*", "exchange-phase3.*", "local-parity.*",
    "market-detail.*", "records-port.*", "strategy-lab-v1.*", "strategy-lab-v2.js", "viewer-best-port.*",
    "viewer-canonical-v1.*", "viewer-canonical-v2.*", "viewer-canonical-v3.*", "viewer-canonical-v4.*",
    "viewer-ia-v5.*", "viewer-performance-v1.*", "viewer-performance-v2.*", "viewer-shell-v2.*",
    "viewer-shell-v3.*", "viewer-ux-v4.*", "styles.css", "workspaces.css",
)
REMOTE_LEGACY_PATHS = (
    "app.js", "asset-local-port.js", "exchange-phase3.js", "local-parity.js", "records-port.js",
    "strategy-lab-v2.js", "viewer-canonical-v4.js", "viewer-ia-v5.js", "styles.css", "workspaces.css",
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
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
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
        response = requests.get(url, timeout=20, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
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
    main_js = text(PUBLIC / "modules/main.js")
    router_js = text(PUBLIC / "modules/core/router.js")
    store_js = text(PUBLIC / "modules/core/store.js")
    dashboard_js = text(PUBLIC / "modules/pages/dashboard.js")
    research_js = text(PUBLIC / "modules/pages/research.js")
    assets_js = text(PUBLIC / "modules/pages/assets.js")
    paper_js = text(PUBLIC / "modules/pages/paper.js")
    records_js = text(PUBLIC / "modules/pages/records.js")
    sectors_js = text(PUBLIC / "modules/pages/sectors.js")
    coin_profile_service = text(PUBLIC / "modules/services/coin-profile.js")
    sector_service_js = text(PUBLIC / "modules/services/sectors.js")
    build29_css = text(PUBLIC / "modules/styles/build29.css")
    exchange_css = text(PUBLIC / "modules/styles/exchange-ui.css")
    sector_css = text(PUBLIC / "modules/styles/sectors.css")
    tokens_css = text(PUBLIC / "modules/styles/tokens.css")
    paper_css = text(PUBLIC / "modules/styles/paper.css")
    sector_api = text(ROOT / "cloudflare-pages/functions/api/sector-summary.ts")
    profile_api = text(ROOT / "cloudflare-pages/functions/api/coin-profile.ts")
    taxonomy = text(ROOT / "cloudflare-pages/functions/lib/coin-taxonomy.ts")
    exchange_names = text(ROOT / "cloudflare-pages/functions/lib/exchange-market-names.ts")
    sector_migration = text(ROOT / "cloudflare-pages/migrations/0003_sector_history.sql")
    profile_migration = text(ROOT / "cloudflare-pages/migrations/0004_coin_profile_cache.sql")
    repair_script = text(ROOT / "scripts/repair-local-sync.ps1")
    gitignore = text(ROOT / ".gitignore")

    static = {
        "build_31": 'crypto-viewer-build" content="2026.08.26-31' in index,
        "module_entry_v8": 'type="module" src="/modules/main.js?v=8"' in index,
        "all_required_modules": all((PUBLIC / path).exists() for path in REQUIRED),
        "apple_finance_tokens": all(token in tokens_css for token in ("#f5f5f7", "#1d1d1f", "#0066cc", "tabular-nums")),
        "quiet_filter_chips": ".chip-row button.active" in build29_css,
        "financial_values_no_wrap": "white-space:nowrap" in paper_css,
        "legacy_files_physically_absent": legacy_files_absent(),
        "seven_main_nav": all(f'data-route="{route}"' in index for route in ("dashboard", "research", "assets", "paper", "strategy", "sectors", "records")),
        "router_sector_route": "'sectors'" in router_js and "ROUTES" in router_js,
        "single_store": "from'./core/store.js'" in main_js and "createSectorsPage" in main_js,
        "research_filtered_selection": "filteredRows" in research_js and "현재 조건에서 선택할 코인이 없습니다." in research_js,
        "paper_primary_hierarchy": ".paper-detail-kpis>span:nth-child(3)" in build29_css and ".trade-plan-panel>div>span:nth-child(6)" in build29_css,
        "asset_direct_average": "추천 타점 · 즉시 평단" in assets_js and "calculateDirectAverage" in assets_js,
        "dashboard_live_patch": "function patchDashboard" in dashboard_js and "if(m.type==='snapshot')patchDashboard()" in dashboard_js,
        "dashboard_no_snapshot_full_render": "if(m.type==='snapshot')render()" not in dashboard_js,
        "dashboard_coin_jump": all(token in dashboard_js for token in ("data-watch-market", "researchMarket:watch.dataset.watchMarket", "navigate('research')")),
        "dashboard_sector_jump": all(token in dashboard_js for token in ("data-sector-jump", "sectorSelected:sector.dataset.sectorJump", "navigate('sectors')")),
        "dashboard_incremental_sector": "function reconcileSectorFlow" in dashboard_js and "data-sector-key" in dashboard_js,
        "dashboard_incremental_activity": "function patchActivity" in dashboard_js and "data-activity-key" in dashboard_js,
        "dashboard_bottom_aligned": "max-width:1320px" in exchange_css and "minmax(350px,.82fr)" in exchange_css,
        "dashboard_strategy_nowrap": ".section-panel>header button{white-space:nowrap" in exchange_css,
        "dashboard_pulse_explained": all(token in dashboard_js for token in ("실시간 관제", "data-pulse-market", "이 영역은 무엇을 보나")) and "pulse-guide" in exchange_css,
        "dashboard_value_tick": "value-tick" in dashboard_js and "@keyframes valueTick" in exchange_css,
        "records_live_insert": all(token in records_js for token in ("refreshLive", "feed.prepend", "seenKeys")),
        "sector_full_coin_list": "slice(0, 14)" not in sector_api and "coins: item.coins.sort" in sector_api,
        "sector_bilingual_names": all(token in sector_api for token in ("name_ko", "name_en", "exchangeMarketNames")) and all(token in exchange_names for token in ("korean_name", "english_name", "api.bithumb.com", "api.upbit.com")),
        "sector_taxonomy": all(token in taxonomy for token in ("미분류 검토", "sectorFor", "TAXONOMY_SOURCE_NOTE", "RWA", "AI·데이터")) and "taxonomy_source" in sector_api,
        "sector_descriptions": all(token in sectors_js for token in ("이 섹터는 무엇을 하나", "sector_description", "sector_business")),
        "sector_sortable_columns": all(token in sectors_js for token in ("data-sector-sort", "turnover_desc", "change_desc", "opportunity_desc")) and "sectorCoinSort" in store_js,
        "sector_bilingual_ui": all(token in sectors_js for token in ("name_ko", "name_en", "sector-coin-name")) and ".sector-coin-name b" in sector_css,
        "sector_project_profile": all(token in sectors_js for token in ("getCoinProfile", "무슨 사업을 하나", "coin-profile-tags")) and "getCoinProfile" in coin_profile_service,
        "sector_coin_profile_cache": all(token in profile_api for token in ("CoinGecko", "coin_profile_cache", "description_ko", "canonical_sector")) and "CREATE TABLE IF NOT EXISTS coin_profile_cache" in profile_migration,
        "sector_coin_research_jump": "data-sector-research" in sectors_js and "navigate?.('research')" in sectors_js,
        "sector_range_shared": all(token in sectors_js for token in ("'1h'", "'6h'", "'24h'", "'7d'", "rangeControl('data-sector-range',range)")),
        "sector_d1_history": "sector_history" in sector_api and "CREATE TABLE IF NOT EXISTS sector_history" in sector_migration,
        "runtime_tmp_safe": "dashboard/runtime-demo-upbit.json.tmp" in gitignore and "dashboard/runtime-demo*.tmp" in repair_script,
        "privacy_contract": "AES-256-GCM" in text(PRIVATE_STORAGE),
        "taste_contract": "Do not change the approved information architecture" in text(TASTES),
        "build29_plan": "strategy equity curve" in text(BUILD29_PLAN),
        "build30_plan": all(token in text(BUILD30_PLAN) for token in ("sector route", "in-place", "watchlist", "activity")),
        "build31_plan": all(token in text(BUILD31_PLAN) for token in ("14-coin cap", "CoinGecko", "CoinMarketCap", "strategy equity curve")),
    }
    print("\n=== MODULAR VIEWER V6 CONTRACT ===")
    print(json.dumps(static, ensure_ascii=False, indent=2))

    errors: list[str] = []
    pending: list[str] = []
    if not all(static.values()):
        errors.append("build 31 source contract is incomplete")
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
        "index_status": 0, "main_status": 0, "dashboard_status": 0, "sectors_status": 0,
        "coin_profile_service_status": 0, "sector_css_status": 0, "exchange_css_status": 0,
        "build_31": False, "module_entry_v8": False, "legacy_files_absent": False,
        "dashboard_pulse_explained": False, "dashboard_strategy_nowrap": False,
        "sector_full_list_ui": False, "sector_sortable": False, "sector_bilingual": False,
        "sector_project_profile": False,
    }
    if url:
        nonce = str(time.time_ns())
        si, ri = fetch(f"{url}/?modular={nonce}")
        sm, rm = fetch(f"{url}/modules/main.js?v=8&modular={nonce}")
        sd, rd = fetch(f"{url}/modules/pages/dashboard.js?modular={nonce}")
        ss, rs = fetch(f"{url}/modules/pages/sectors.js?modular={nonce}")
        sp, rp = fetch(f"{url}/modules/services/coin-profile.js?modular={nonce}")
        sc, rc = fetch(f"{url}/modules/styles/sectors.css?v=2&modular={nonce}")
        se, re = fetch(f"{url}/modules/styles/exchange-ui.css?v=2&modular={nonce}")
        legacy_statuses = {path: fetch(f"{url}/{path}?retired={nonce}")[0] for path in REMOTE_LEGACY_PATHS}
        remote_contract.update({
            "index_status": si, "main_status": sm, "dashboard_status": sd, "sectors_status": ss,
            "coin_profile_service_status": sp, "sector_css_status": sc, "exchange_css_status": se,
            "build_31": 'crypto-viewer-build" content="2026.08.26-31' in ri,
            "module_entry_v8": 'type="module" src="/modules/main.js?v=8"' in ri and "createSectorsPage" in rm,
            "legacy_files_absent": all(status == 404 for status in legacy_statuses.values()),
            "dashboard_pulse_explained": "실시간 관제" in rd and "data-pulse-market" in rd and "pulse-guide" in re,
            "dashboard_strategy_nowrap": ".section-panel>header button{white-space:nowrap" in re,
            "sector_full_list_ui": "종목 전체" in rs and "sector-coin-list" in rs,
            "sector_sortable": "data-sector-sort" in rs and "turnover_desc" in rs,
            "sector_bilingual": "name_ko" in rs and "name_en" in rs and ".sector-coin-name b" in rc,
            "sector_project_profile": "getCoinProfile" in rs and "getCoinProfile" in rp and "무슨 사업을 하나" in rs,
        })
        print("remote_legacy_statuses=" + json.dumps(legacy_statuses, ensure_ascii=False, sort_keys=True))
        if any(code != 200 for code in (si, sm, sd, ss, sp, sc, se)):
            pending.append("build 31 viewer assets are not reachable yet")
        elif not all(value for key, value in remote_contract.items() if not key.endswith("_status")):
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
