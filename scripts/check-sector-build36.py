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
    page = text(PUBLIC / "modules" / "pages" / "sectors-v36.js")
    css = text(PUBLIC / "modules" / "styles" / "build36.css")
    identity = text(ROOT / "b3_trader" / "coin_profile_identity_safe.py")
    audit_client = text(ROOT / "b3_trader" / "coin_profile_identity_audit.py")
    supervisor = text(ROOT / "b3_trader" / "research_supervisor.py")
    backlog = text(ROOT / "cloudflare-pages" / "functions" / "api" / "coin-profile-backlog-v36.ts")
    audit_api = text(ROOT / "cloudflare-pages" / "functions" / "api" / "coin-profile-identity-audit.ts")
    repair = text(ROOT / "cloudflare-pages" / "functions" / "api" / "ingest-coin-profiles-repair.ts")
    plan = text(ROOT / "docs" / "VIEWER_BUILD36_PLAN.md")

    checks = {
        "sector_build_36_or_newer": any(f'crypto-sector-build" content="2026.08.27-{v}' in index for v in (36, 37)),
        "sector_v36_entry": "./pages/sectors-v36.js?v=36" in main_js,
        "sector_search": "data-sector-search" in page and "섹터 · 코인명 · 영문명 · 티커 검색" in page,
        "sector_filter_chips": all(token in page for token in ("조사완료", "추가조사", "상승", "하락", "미분류")),
        "sector_korean_primary": "profile.business_summary_ko||profile.description_ko||''" in page,
        "sector_identity_hide": "sameProjectName" in page and "자동 재조사" in page and "거래소 공식명" in page,
        "sector_mobile_no_forced_table": "min-width:0!important" in css and "grid-template-columns:repeat(3,minmax(0,1fr))" in css and "min-width:650px" not in css,
        "identity_safe_enricher": all(token in identity for token in ("IdentitySafeCoinProfileEnricher", "row_matches_candidate", "_read_manual_pdf_checked", "project_name_matches")),
        "strict_cmc_cg": "if not matched" in identity and "and row_matches_candidate(row, item.get(\"name\"))" in identity,
        "manual_pdf_identity": "if not _identity_in_text(row, text)" in identity,
        "supervisor_v36": "CoinProfileResearchCycleV36" in supervisor,
        "identity_audit_backlog": all(token in backlog for token in ("identity_mismatch", "exchangeMarketNames", "identity_mismatch_by_exchange", "audit_scope")),
        "identity_audit_api": all(token in audit_api for token in ("cached_english_name", "official_english_name", "audit_scope", "mismatches")),
        "identity_audit_command": "coin-profile-identity-audit" in audit_client,
        "identity_repair_ingest": "identity_repairs" in repair and "ON CONFLICT(exchange,market) DO UPDATE SET" in repair,
        "build36_plan": "ticker alone" in plan and "Mobile <=760px" in plan,
    }

    print("=== SECTOR BUILD 36 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    errors = []
    if not all(checks.values()):
        errors.append("Build 36 source contract incomplete")

    deploy = read_json(DEPLOY)
    url = str(deploy.get("viewer_url") or "").rstrip("/")
    remote = {}
    if url:
        for name, path in {
            "index": "/",
            "page": "/modules/pages/sectors-v36.js?v=36",
            "css": "/modules/styles/build36.css?v=1",
        }.items():
            try:
                response = requests.get(url + path, timeout=20, headers={"Cache-Control": "no-cache"})
                remote[name] = response.status_code
            except requests.RequestException:
                remote[name] = 0
        if any(code != 200 for code in remote.values()):
            errors.append("Build 36 remote assets not deployed")
    print("\n=== REMOTE BUILD 36 ===")
    print(json.dumps(remote, ensure_ascii=False, indent=2))
    print("\n=== RESULT ===")
    if errors:
        for item in errors:
            print("ERROR:", item)
        print("SECTOR_BUILD36=FAIL")
        raise SystemExit(1)
    print("SECTOR_BUILD36=PASS")


if __name__ == "__main__":
    main()
