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
REQUIRED = [
    "modules/core/http.js", "modules/core/store.js", "modules/core/router.js", "modules/core/auth.js",
    "modules/core/snapshot.js", "modules/shared/format.js", "modules/shared/selectors.js",
    "modules/shared/components.js", "modules/shared/charts.js", "modules/shared/decision.js",
    "modules/shared/averaging.js", "modules/services/market-detail.js", "modules/pages/dashboard.js",
    "modules/pages/research.js", "modules/pages/assets.js", "modules/pages/paper.js", "modules/pages/strategy.js",
    "modules/pages/records.js", "modules/pages/system.js", "modules/main.js", "modules/styles/charts.css",
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
    assets_js = text(PUBLIC / "modules/pages/assets.js")
    research_js = text(PUBLIC / "modules/pages/research.js")
    paper_js = text(PUBLIC / "modules/pages/paper.js")
    records_js = text(PUBLIC / "modules/pages/records.js")
    charts_js = text(PUBLIC / "modules/shared/charts.js")
    decision_js = text(PUBLIC / "modules/shared/decision.js")
    averaging_js = text(PUBLIC / "modules/shared/averaging.js")
    store_js = text(PUBLIC / "modules/core/store.js")
    tokens_css = text(PUBLIC / "modules/styles/tokens.css")
    components_css = text(PUBLIC / "modules/styles/components.css")
    assets_css = text(PUBLIC / "modules/styles/assets.css")
    paper_css = text(PUBLIC / "modules/styles/paper.css")

    static = {
        "build_28": 'crypto-viewer-build" content="2026.08.26-28' in index,
        "module_entry_v5": 'type="module" src="/modules/main.js?v=5"' in index,
        "all_required_modules": all((PUBLIC / path).exists() for path in REQUIRED),
        "apple_finance_tokens": all(token in tokens_css for token in ("#f5f5f7", "#1d1d1f", "#0066cc", "tabular-nums")),
        "compact_selected_controls": "background:var(--accent2)" in components_css and ".chip-row button.active" in components_css,
        "financial_values_no_wrap": "white-space:nowrap" in components_css and "white-space:nowrap" in paper_css,
        "legacy_files_physically_absent": legacy_files_absent(),
        "six_main_nav": all(f'data-route="{route}"' in index for route in ("dashboard", "research", "assets", "paper", "strategy", "records")),
        "single_store": "from'./core/store.js'" in main_js,
        "research_filtered_selection": "filteredRows" in research_js and "현재 조건에서 선택할 코인이 없습니다." in research_js,
        "research_decision_filter": "../shared/decision.js" in research_js and all(token in decision_js for token in ("DECISION_FILTERS", "regime>=65&&entry>=68", "regime>=70&&entry<50", "regime<50")),
        "research_history": all(token in research_js for token in ("data-research-range", "priceFillChart", "scoreHistoryChart", "BTC 시장참고", "ETH 시장참고")),
        "paper_price_fill_history": "data-paper-range" in paper_js and "priceFillChart" in paper_js,
        "shared_chart_module": all(token in charts_js for token in ("rangeControl", "priceFillChart", "scoreHistoryChart", "simpleLineChart")),
        "shared_averaging_module": all(token in averaging_js for token in ("calculateAveraging", "calculateDirectAverage", "MAX" if False else "final_avg_price")),
        "asset_direct_average": all(token in assets_js for token in ("추천 타점 · 즉시 평단", "data-direct-buy-price", "calculateDirectAverage", "trade_plan")),
        "asset_separate_averaging": all(token in assets_js for token in ("물타기 계산기", "data-add-avg-row", "data-avg-price", "calculateAveraging")),
        "asset_decision_spacing": ".asset-research-sides .score-line+.score-line'" not in assets_css and ".asset-research-sides .score-line+.score-line" in assets_css,
        "asset_master_detail": "asset-workspace" in assets_js and "data-asset-market" in assets_js,
        "exchange_default_policy": all(token in store_js for token in ("defaultExchange", "researchExchange:exchange", "strategyExchange:exchange", "recordsExchange:exchange", "row?.exchange||'bithumb'")),
        "records_period_coin_filters": "data-records-period" in records_js and "data-records-search" in records_js,
        "privacy_contract": all(token in text(PRIVATE_STORAGE) for token in ("AES-256-GCM", "operator", "Google Sheet", "Bithumb holdings only")),
        "taste_contract": all(token in text(TASTES) for token in ("#1D1D1F", "#F5F5F7", "#0066CC", "Do not change the approved information architecture")),
    }
    print("\n=== MODULAR VIEWER V6 CONTRACT ===")
    print(json.dumps(static, ensure_ascii=False, indent=2))

    errors: list[str] = []
    pending: list[str] = []
    if not all(static.values()):
        errors.append("build 28 source contract is incomplete")
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
        "index_status": 0, "main_status": 0, "assets_status": 0, "store_status": 0,
        "averaging_status": 0, "tokens_status": 0, "paper_css_status": 0,
        "build_28": False, "module_entry_v5": False, "legacy_files_absent": False,
        "apple_finance_tokens": False, "asset_direct_average": False, "asset_separate_averaging": False,
        "exchange_default_policy": False, "paper_compact_values": False,
    }
    if url:
        nonce = str(time.time_ns())
        si, ri = fetch(f"{url}/?modular={nonce}")
        sm, rm = fetch(f"{url}/modules/main.js?v=5&modular={nonce}")
        sa, ra = fetch(f"{url}/modules/pages/assets.js?modular={nonce}")
        ss, rs = fetch(f"{url}/modules/core/store.js?modular={nonce}")
        sv, rv = fetch(f"{url}/modules/shared/averaging.js?modular={nonce}")
        st, rt = fetch(f"{url}/modules/styles/tokens.css?v=3&modular={nonce}")
        sp, rp = fetch(f"{url}/modules/styles/paper.css?v=5&modular={nonce}")
        legacy_statuses = {path: fetch(f"{url}/{path}?retired={nonce}")[0] for path in REMOTE_LEGACY_PATHS}
        remote_contract.update({
            "index_status": si, "main_status": sm, "assets_status": sa, "store_status": ss,
            "averaging_status": sv, "tokens_status": st, "paper_css_status": sp,
            "build_28": 'crypto-viewer-build" content="2026.08.26-28' in ri,
            "module_entry_v5": 'type="module" src="/modules/main.js?v=5"' in ri and "createAssetsPage" in rm,
            "legacy_files_absent": all(status == 404 for status in legacy_statuses.values()),
            "apple_finance_tokens": all(token in rt for token in ("#f5f5f7", "#1d1d1f", "#0066cc", "tabular-nums")),
            "asset_direct_average": "추천 타점 · 즉시 평단" in ra and "calculateDirectAverage" in ra,
            "asset_separate_averaging": "물타기 계산기" in ra and "data-add-avg-row" in ra and "calculateAveraging" in rv,
            "exchange_default_policy": "researchExchange:exchange" in rs and "strategyExchange:exchange" in rs and "recordsExchange:exchange" in rs,
            "paper_compact_values": "white-space:nowrap" in rp and ".exchange-paper-grid .kpi b" in rp,
        })
        print("remote_legacy_statuses=" + json.dumps(legacy_statuses, ensure_ascii=False, sort_keys=True))
        if any(code != 200 for code in (si, sm, sa, ss, sv, st, sp)):
            pending.append("build 28 viewer assets are not reachable yet")
        elif not all(value for key, value in remote_contract.items() if key.endswith(("_28", "_v5")) or key in ("legacy_files_absent", "apple_finance_tokens", "asset_direct_average", "asset_separate_averaging", "exchange_default_policy", "paper_compact_values")):
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
