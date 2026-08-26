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
TASTES = ROOT / "TASTES.md"
CHECKLIST = ROOT / "docs/VIEWER_REBUILD_CHECKLIST.md"
BUILD29_PLAN = ROOT / "docs/VIEWER_BUILD29_PLAN.md"
BUILD30_PLAN = ROOT / "docs/VIEWER_BUILD30_PLAN.md"
BUILD31_PLAN = ROOT / "docs/VIEWER_BUILD31_PLAN.md"
BUILD32_PLAN = ROOT / "docs/VIEWER_BUILD32_PLAN.md"
BUILD33_PLAN = ROOT / "docs/VIEWER_BUILD33_PLAN.md"
BUILD34_PLAN = ROOT / "docs/VIEWER_BUILD34_PLAN.md"
BUILD35_PLAN = ROOT / "docs/VIEWER_BUILD35_PLAN.md"

REQUIRED = [
    "modules/core/http.js", "modules/core/store.js", "modules/core/router.js", "modules/core/auth.js", "modules/core/snapshot.js",
    "modules/shared/format.js", "modules/shared/selectors.js", "modules/shared/components.js", "modules/shared/charts.js",
    "modules/shared/decision.js", "modules/shared/averaging.js", "modules/services/market-detail.js", "modules/services/sectors.js",
    "modules/services/coin-profile.js", "modules/pages/dashboard.js", "modules/pages/research.js", "modules/pages/assets.js",
    "modules/pages/paper.js", "modules/pages/strategy.js", "modules/pages/sectors.js", "modules/pages/records.js", "modules/pages/system.js",
    "modules/main.js", "modules/styles/charts.css", "modules/styles/strategy.css", "modules/styles/sectors.css", "modules/styles/records-system.css",
    "modules/styles/build29.css", "modules/styles/exchange-ui.css", "modules/styles/build32.css",
]
LEGACY_ROOT_PATTERNS = (
    "app.js", "asset-local-port.*", "asset-parity-shell.*", "exchange-phase3.*", "local-parity.*", "market-detail.*",
    "records-port.*", "strategy-lab-v1.*", "strategy-lab-v2.js", "viewer-best-port.*", "viewer-canonical-v1.*",
    "viewer-canonical-v2.*", "viewer-canonical-v3.*", "viewer-canonical-v4.*", "viewer-ia-v5.*", "viewer-performance-v1.*",
    "viewer-performance-v2.*", "viewer-shell-v2.*", "viewer-shell-v3.*", "viewer-ux-v4.*", "styles.css", "workspaces.css",
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
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
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
    selectors_js = text(PUBLIC / "modules/shared/selectors.js")
    dashboard_js = text(PUBLIC / "modules/pages/dashboard.js")
    research_js = text(PUBLIC / "modules/pages/research.js")
    assets_js = text(PUBLIC / "modules/pages/assets.js")
    paper_js = text(PUBLIC / "modules/pages/paper.js")
    strategy_js = text(PUBLIC / "modules/pages/strategy.js")
    records_js = text(PUBLIC / "modules/pages/records.js")
    sectors_js = text(PUBLIC / "modules/pages/sectors.js")
    system_js = text(PUBLIC / "modules/pages/system.js")
    build29_css = text(PUBLIC / "modules/styles/build29.css")
    exchange_css = text(PUBLIC / "modules/styles/exchange-ui.css")
    build32_css = text(PUBLIC / "modules/styles/build32.css")
    strategy_css = text(PUBLIC / "modules/styles/strategy.css")
    records_system_css = text(PUBLIC / "modules/styles/records-system.css")
    tokens_css = text(PUBLIC / "modules/styles/tokens.css")
    paper_css = text(PUBLIC / "modules/styles/paper.css")

    sector_api = text(ROOT / "cloudflare-pages/functions/api/sector-summary.ts")
    ingest_profiles = text(ROOT / "cloudflare-pages/functions/api/ingest-coin-profiles.ts")
    backlog_api = text(ROOT / "cloudflare-pages/functions/api/coin-profile-backlog.ts")
    taxonomy = text(ROOT / "cloudflare-pages/functions/lib/coin-taxonomy.ts")
    migration4 = text(ROOT / "cloudflare-pages/migrations/0004_coin_profile_cache.sql")
    migration5 = text(ROOT / "cloudflare-pages/migrations/0005_coin_profile_evidence.sql")
    enricher = text(ROOT / "b3_trader/coin_profile_enricher.py")
    precision_cycle = text(ROOT / "b3_trader/coin_profile_research_cycle.py")
    supervisor = text(ROOT / "b3_trader/research_supervisor.py")
    control = text(ROOT / "b3_trader/research_control.py")
    telegram = text(ROOT / "b3_trader/telegram_notify.py")
    performance_analytics = text(ROOT / "b3_trader/performance_analytics.py")
    strategy_snapshot = text(ROOT / "b3_trader/strategy_lab_snapshot.py")
    requirements = text(ROOT / "b3_trader/requirements.txt")
    repair = text(ROOT / "scripts/repair-local-sync.ps1")
    gitignore = text(ROOT / ".gitignore")
    checklist = text(CHECKLIST)

    static = {
        "build_35": 'crypto-viewer-build" content="2026.08.27-35' in index,
        "module_entry_v12": 'type="module" src="/modules/main.js?v=12"' in index and "system.js?v=35" in main_js,
        "all_required_modules": all((PUBLIC / path).exists() for path in REQUIRED),
        "apple_finance_tokens": all(token in tokens_css for token in ("#f5f5f7", "#1d1d1f", "#0066cc", "tabular-nums")),
        "quiet_filter_chips": ".chip-row button.active" in build29_css,
        "financial_values_no_wrap": "white-space:nowrap" in paper_css,
        "legacy_files_physically_absent": legacy_files_absent(),
        "seven_main_nav": all(f'data-route="{route}"' in index for route in ("dashboard", "research", "assets", "paper", "strategy", "sectors", "records")),
        "router_sector_route": "'sectors'" in router_js and "ROUTES" in router_js,
        "single_store": "from'./core/store.js'" in main_js and "createSectorsPage" in main_js and "createSystemPage" in main_js,
        "research_filtered_selection": "filteredRows" in research_js and "현재 조건에서 선택할 코인이 없습니다." in research_js,
        "paper_primary_hierarchy": ".paper-detail-kpis>span:nth-child(3)" in build29_css,
        "asset_direct_average": "추천 타점 · 즉시 평단" in assets_js and "calculateDirectAverage" in assets_js,
        "asset_averaging_read_only": all(token in assets_js for token in ("물타기 계산기", "최대 20회", "저장본", "DB 원본을 수정하지 않습니다")) and "averagingPlan" in selectors_js,
        "dashboard_live_patch": "function patchDashboard" in dashboard_js and "if(m.type==='snapshot')patchDashboard()" in dashboard_js,
        "dashboard_no_snapshot_full_render": "if(m.type==='snapshot')render()" not in dashboard_js,
        "dashboard_bottom_aligned": "max-width:1320px" in exchange_css,
        "dashboard_strategy_nowrap": ".section-panel>header button{white-space:nowrap" in exchange_css,
        "records_live_insert": all(token in records_js for token in ("refreshLive", "feed.prepend", "seenKeys")),
        "sector_full_coin_list": "slice(0, 14)" not in sector_api and "coins:item.coins.sort" in sector_api.replace(" ", ""),
        "sector_sortable_columns": all(token in sectors_js for token in ("data-sector-sort", "turnover_desc", "change_desc", "opportunity_desc")) and "sectorCoinSort" in store_js,
        "sector_bilingual_ui": all(token in sectors_js for token in ("name_ko", "name_en", "sector-coin-name")),
        "sector_range_shared": all(token in sectors_js for token in ("'1h'", "'6h'", "'24h'", "'7d'", "rangeControl('data-sector-range',range)")),
        "sector_d1_history": "sector_history" in sector_api,
        "coin_profile_evidence_migration": all(token in migration5 for token in ("business_summary_ko", "canonical_sector", "evidence_json", "research_status", "last_verified_at")) and "coin_profile_cache" in migration4,
        "coin_profile_enricher": all(token in enricher for token in ("class CoinProfileEnricher", "CoinMarketCap", "CoinGecko", "BITHUMB_MANUAL_URL", "completed_cycles")) and "pypdf" in requirements,
        "coin_profile_ingest": all(token in ingest_profiles for token in ("INGEST_TOKEN", "coin_profile_cache", "business_summary_ko", "evidence_json", "canonical_sector", "env.DB.batch")),
        "coin_profile_multisource": all(token in enricher for token in ("bithumb_manual", "coinmarketcap", "coingecko", "official_site", "source_code", "community")),
        "coin_profile_korean_manual": all(token in enricher for token in ("BITHUMB_MANUAL_URL", "_read_manual_pdf", "description_ko", "purpose_ko", "PdfReader", "feed-content")),
        "coin_profile_supervisor": "CoinProfileResearchCycle" in supervisor and '"coin-profile-enrichment"' in supervisor and '"coin-profile-enrichment"' in control,
        "coin_profile_precision_cycle": all(token in precision_cycle for token in ("class CoinProfileResearchCycle", "PRECISION_PER_EXCHANGE", "coin-profile-backlog", "_precision_once", "general = self.base.run_once()")),
        "coin_profile_balanced_backlog": all(token in backlog_api for token in ("queryExchange('bithumb')", "queryExchange('upbit')", "round-robin", "perExchange", "eligible_by_exchange", "quality_pending_by_exchange", "cooldown_by_exchange")),
        "coin_profile_no_sector_fallback": "profile.business_summary_ko||profile.description_ko||profile.business_summary_en||profile.description_en" in sectors_js and "chosen?.sector_business||''" not in sectors_js,
        "coin_profile_evidence_ui": all(token in sectors_js for token in ("근거 출처", "match_confidence", "last_verified_at", "coin-profile-community")) and "profile-verification" in build32_css,
        "sector_enriched_classification": all(token in sector_api for token in ("canonical_sector", "research_status", "business_summary_ko", "researched_count", "unresolved_count")) and "evidenceText" in sector_api,
        "taxonomy_evidence_classification": "evidenceText" in taxonomy and "matches(haystack" in taxonomy and "미분류 검토" in taxonomy,
        "project_research_progress": "프로젝트 조사" in sectors_js and "researched_count" in sectors_js,
        "performance_analytics_module": all(token in performance_analytics for token in ("strategy_lab_equity_history", "paper_portfolio_history", "coin_matrix", "HISTORY_BUCKET_SECONDS = 300", "MAX_HISTORY_POINTS = 2016")),
        "strategy_snapshot_v3": all(token in strategy_snapshot for token in ('"version": 3', "read_performance_analytics", "strategy_equity_history", "coin_matrix", "paper_history")),
        "strategy_equity_curve": all(token in strategy_js for token in ("전략 equity curve", "strategyEquityHistory", "drawdown_pct", "data-strategy-range")) and "strategy-history-panel" in strategy_css,
        "strategy_coin_performance": all(token in strategy_js for token in ("코인별 성과", "coinPerformance", "실현손익", "미실현")) and "strategyCoinMatrix" in selectors_js,
        "strategy_coin_matrix": all(token in strategy_js for token in ("코인 × 전략", "strategyCoinRows", "strategy-matrix-workspace")) and "strategyCoinRows" in selectors_js,
        "paper_portfolio_equity_drawdown": all(token in strategy_js for token in ("전체 PAPER equity / drawdown", "paperPortfolioHistory", "전체 PAPER 자산곡선", "전체 PAPER Drawdown")) and "paperPortfolioHistory" in selectors_js,
        "strategy_analytics_state": all(token in store_js for token in ("strategyTab:'overview'", "strategyRange:'24h'", "strategyCoinMarket:''")),
        "system_operations_backend": all(token in control for token in ("_git_summary", "_cloudflare_summary", "_warehouse_summary", '"operations":operations')),
        "system_operations_ui": all(token in system_js for token in ("코드 동기화", "Pages · 데이터 전송", "Parquet 분석 창고", "operationCards")) and ".operations-grid" in records_system_css,
        "system_component_diagnostics": "componentDiagnostics" in system_js and "component-diagnostic" in system_js and ".component-diagnostic" in records_system_css,
        "system_backup_status": all(token in control for token in ("_backup_summary", "local_backup_count", "drive_uploaded", "local_path_exposed", "remote_path_exposed")) and all(token in system_js for token in ("SQLite · Drive 백업", "local_backup_count", "drive_uploaded")),
        "system_buy_candidate_status": all(token in telegram for token in ("buy_candidate_sent_count", "last_buy_candidate_sent_at", "buy_candidate_only")) and all(token in control for token in ("buy_candidate_sent_count", "buy_candidate_only")) and "BUY_CANDIDATE 알림" in system_js,
        "system_remote_access_status": all(token in control for token in ("_remote_access_summary", "address_values_exposed", "remote_auth_required", "viewer_can_control_pc")) and all(token in system_js for token in ("휴대폰 · 원격 접속", "Tailscale", "원격 인증")),
        "system_secret_guard": all(token in control for token in ("secret_values_exposed", "address_values_exposed", "local_path_exposed", "remote_path_exposed")) and "IP·원격 경로 미노출" in system_js,
        "runtime_tmp_safe": "dashboard/runtime-demo-upbit.json.tmp" in gitignore and "dashboard/runtime-demo*.tmp" in repair,
        "privacy_contract": "AES-256-GCM" in text(PRIVATE_STORAGE),
        "taste_contract": "Do not change the approved information architecture" in text(TASTES),
        "checklist_reconciled": all(token in checklist for token in ("[x] 전체 PAPER equity curve", "[x] 전략 equity curve + drawdown", "[x] SQLite/Drive backup 상세", "[ ] GitHub Actions CI 상태를 Viewer에서 직접 표시")),
        "build29_plan": "strategy equity curve" in text(BUILD29_PLAN),
        "build30_plan": "in-place" in text(BUILD30_PLAN),
        "build31_plan": "14-coin cap" in text(BUILD31_PLAN),
        "build32_plan": all(token in text(BUILD32_PLAN) for token in ("전체 코인 사업·섹터 전수조사", "community", "strategy equity curve")),
        "build33_plan": all(token in text(BUILD33_PLAN) for token in ("Strategy / PAPER Performance Analytics", "Strategy equity curve", "Coin × strategy comparison", "Overall adaptive PAPER equity / drawdown")),
        "build34_plan": all(token in text(BUILD34_PLAN) for token in ("Operations Visibility", "Git status", "Cloudflare status", "Warehouse status", "Telegram readiness")),
        "build35_plan": all(token in text(BUILD35_PLAN) for token in ("Operations Completion", "SQLite / Drive backup status", "Telegram BUY_CANDIDATE status", "Phone / remote-access summary")),
    }

    print("\n=== MODULAR VIEWER V6 CONTRACT ===")
    print(json.dumps(static, ensure_ascii=False, indent=2))
    errors: list[str] = []
    pending: list[str] = []
    if not all(static.values()):
        errors.append("build 35 source contract is incomplete")
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
        "main_status": 0,
        "system_status": 0,
        "records_css_status": 0,
        "strategy_status": 0,
        "sectors_status": 0,
        "build_35": False,
        "module_entry_v12": False,
        "legacy_files_absent": False,
        "system_backup_ui": False,
        "system_buy_candidate_ui": False,
        "system_remote_access_ui": False,
        "strategy_analytics_ui": False,
        "coin_profile_ui": False,
    }
    if url:
        nonce = str(time.time_ns())
        si, ri = fetch(f"{url}/?modular={nonce}")
        sm, rm = fetch(f"{url}/modules/main.js?v=12&modular={nonce}")
        sy, rsy = fetch(f"{url}/modules/pages/system.js?v=35&modular={nonce}")
        rc, rrc = fetch(f"{url}/modules/styles/records-system.css?v=5&modular={nonce}")
        st, rst = fetch(f"{url}/modules/pages/strategy.js?modular={nonce}")
        ss, rs = fetch(f"{url}/modules/pages/sectors.js?modular={nonce}")
        legacy_statuses = {path: fetch(f"{url}/{path}?retired={nonce}")[0] for path in REMOTE_LEGACY_PATHS}
        remote_contract.update({
            "index_status": si,
            "main_status": sm,
            "system_status": sy,
            "records_css_status": rc,
            "strategy_status": st,
            "sectors_status": ss,
            "build_35": 'crypto-viewer-build" content="2026.08.27-35' in ri,
            "module_entry_v12": 'type="module" src="/modules/main.js?v=12"' in ri and "system.js?v=35" in rm,
            "legacy_files_absent": all(status == 404 for status in legacy_statuses.values()),
            "system_backup_ui": all(token in rsy for token in ("SQLite · Drive 백업", "drive_uploaded", "local_backup_count")),
            "system_buy_candidate_ui": all(token in rsy for token in ("BUY_CANDIDATE 알림", "buy_candidate_sent_count", "last_buy_candidate_sent_at")),
            "system_remote_access_ui": all(token in rsy for token in ("휴대폰 · 원격 접속", "remote_auth_required", "Tailscale")),
            "strategy_analytics_ui": all(token in rst for token in ("전략 equity curve", "코인별 성과", "코인 × 전략", "전체 PAPER equity / drawdown")),
            "coin_profile_ui": "프로젝트별 설명 수집 중" in rs and "profile.business_summary_ko" in rs,
        })
        print("remote_legacy_statuses=" + json.dumps(legacy_statuses, ensure_ascii=False, sort_keys=True))
        if any(code != 200 for code in (si, sm, sy, rc, st, ss)):
            pending.append("build 35 viewer assets are not reachable yet")
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
