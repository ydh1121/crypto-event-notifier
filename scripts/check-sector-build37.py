from __future__ import annotations

import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "cloudflare-pages" / "public"
DEPLOY = ROOT / "b3_trader" / "data" / "research-platform" / "cloudflare-pages-deploy-state.json"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def main() -> None:
    index = text(PUBLIC / "index.html")
    main_js = text(PUBLIC / "modules" / "main.js")
    sector_page = text(PUBLIC / "modules" / "pages" / "sectors-v36.js")
    build36_css = text(PUBLIC / "modules" / "styles" / "build36.css")
    build37_css = text(PUBLIC / "modules" / "styles" / "build37.css")
    ime = text(PUBLIC / "modules" / "shared" / "sector-ime-guard.js")
    sorter = text(PUBLIC / "modules" / "shared" / "table-sort-enhancer.js")
    integrity = text(ROOT / "cloudflare-pages" / "functions" / "lib" / "coin-profile-integrity.ts")
    integrity_api = text(ROOT / "cloudflare-pages" / "functions" / "api" / "coin-profile-integrity-audit.ts")
    per_market_integrity = text(ROOT / "cloudflare-pages" / "functions" / "api" / "coin-profile-integrity.ts")
    backlog = text(ROOT / "cloudflare-pages" / "functions" / "api" / "coin-profile-backlog-v37.ts")
    service = text(PUBLIC / "modules" / "services" / "coin-profile.js")
    cycle = text(ROOT / "b3_trader" / "coin_profile_research_cycle_v36.py")
    audit_client = text(ROOT / "b3_trader" / "coin_profile_integrity_audit.py")
    plan = text(ROOT / "docs" / "VIEWER_BUILD37_PLAN.md")
    sort_audit = text(ROOT / "docs" / "VIEWER_TABLE_SORT_AUDIT_BUILD37.md")

    checks = {
        "sector_build_37": 'crypto-sector-build" content="2026.08.27-37' in index,
        "main_v13": '/modules/main.js?v=13' in index,
        "sector_search_and_filters": "data-sector-search" in sector_page and all(token in sector_page for token in ("조사완료", "추가조사", "상승", "하락", "미분류")),
        "sector_mobile_cards": "grid-template-columns:repeat(3,minmax(0,1fr))" in build36_css and "min-width:650px" not in build36_css,
        "ime_guard_installed": "installSectorImeGuard" in main_js and "compositionstart" in ime and "compositionend" in ime and "event.isComposing" in ime,
        "table_sort_installed": "installTableSortEnhancer" in main_js and "strategy-overview" in sorter and "strategy-coins" in sorter and "strategy-matrix" in sorter and "paper-compare" in sorter,
        "table_sort_bidirectional": "current.dir==='desc'?'asc':'desc'" in sorter and "aria-sort" in sorter,
        "table_sort_layout_safe": "smart-sort-arrow" in build37_css and "min-width:" not in build37_css and "grid-template-columns:repeat(" not in build37_css,
        "content_integrity_library": all(token in integrity for token in ("evaluateProfileIntegrity", "content_foreign_identity", "provider_foreign_identity", "homepage_foreign_identity", "content_lead_name_mismatch", "compactLead", "projectsInUrl")),
        "full_content_audit_api": all(token in integrity_api for token in ("evaluateProfileIntegrity", "market_scope", "cached_scope", "profile_missing", "korean_missing", "rows_truncated")),
        "profile_audit_krw_only": "market LIKE 'KRW-%'" in integrity_api and "scope:'krw_only'" in integrity_api and "startsWith('KRW-')" in integrity_api,
        "per_market_integrity_guard": "status:finding.reasons.length?'mismatch':'ok'" in per_market_integrity,
        "viewer_hides_bad_profile": "coin-profile-integrity" in service and "integrity?.status==='mismatch'" in service,
        "integrity_backlog_v37": all(token in backlog for token in ("evaluateProfileIntegrity", "identity_mismatch", "profile_missing", "missing_profile_by_exchange", "balanced")),
        "profile_backlog_krw_only": "market LIKE 'KRW-%'" in backlog and "scope:'krw_only'" in backlog and "startsWith('KRW-')" in backlog,
        "supervisor_uses_v37_backlog": "coin-profile-backlog-v37" in cycle,
        "integrity_audit_command": "coin-profile-integrity-audit" in audit_client and "sample_rows" in audit_client and "--full" in audit_client,
        "pypdf_warning_guard": 'logging.getLogger("pypdf").setLevel(logging.ERROR)' in cycle,
        "build37_plan": "Coin-profile integrity" in plan and "Korean IME" in plan,
        "table_sort_audit": "의도적으로 정렬 UI를 추가하지 않음" in sort_audit and "전략 연구 > 코인×전략" in sort_audit,
    }

    print("=== SECTOR BUILD 37 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    errors = []
    if not all(checks.values()):
        errors.append("Build 37 source contract incomplete")

    deploy = read_json(DEPLOY)
    url = str(deploy.get("viewer_url") or "").rstrip("/")
    remote = {}
    if url:
        for name, path in {
            "index": "/",
            "main": "/modules/main.js?v=13",
            "sector_page": "/modules/pages/sectors-v36.js?v=36",
            "build37_css": "/modules/styles/build37.css?v=1",
            "ime": "/modules/shared/sector-ime-guard.js?v=37",
            "sorter": "/modules/shared/table-sort-enhancer.js?v=37",
        }.items():
            try:
                response = requests.get(url + path, timeout=20, headers={"Cache-Control": "no-cache"})
                remote[name] = response.status_code
            except requests.RequestException:
                remote[name] = 0
        if any(code != 200 for code in remote.values()):
            errors.append("Build 37 remote assets not deployed")
    print("\n=== REMOTE BUILD 37 ===")
    print(json.dumps(remote, ensure_ascii=False, indent=2))
    print("\n=== RESULT ===")
    if errors:
        for item in errors:
            print("ERROR:", item)
        print("SECTOR_BUILD37=FAIL")
        raise SystemExit(1)
    print("SECTOR_BUILD37=PASS")


if __name__ == "__main__":
    main()
