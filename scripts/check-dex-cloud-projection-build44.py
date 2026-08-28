from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    projection = text("b3_trader/dex_launch_snapshot.py")
    lifecycle = text("b3_trader/cloudflare_snapshot_lifecycle.py")
    budget = text("b3_trader/cloudflare_snapshot_budget.py")
    panel = text("cloudflare-pages/public/modules/pages/dex-launch-panel.js")
    main_js = text("cloudflare-pages/public/modules/main.js")
    verifier = text("scripts/verify-dex-cloud-projection-build44.py")

    checks = {
        "build44_compact_projection_module": (
            "def build_dex_launch_snapshot" in projection
            and "DEFAULT_CASE_LIMIT = 16" in projection
            and "DEFAULT_ASSET_LIMIT_PER_CASE = 2" in projection
            and '"paper_only": True' in projection
            and '"shadow_only": True' in projection
        ),
        "build44_raw_dex_candles_never_queried": (
            "dex_launch_candles" not in projection
            and '"raw_candles_included": False' in projection
            and "OHLCV rows never leave local SQLite" in projection
        ),
        "build44_exact_identity_preserved": (
            '"token_address"' in projection
            and '"pool_address"' in projection
            and '"coingecko_id"' in projection
            and '"network_id"' in projection
            and '"identity_status"' in projection
        ),
        "build44_primary_pool_quality_only": (
            "p.selected_primary=1" in projection
            and '"reserve_usd"' in projection
            and '"volume_h24_usd"' in projection
            and '"gate_status"' in projection
        ),
        "build44_derived_feature_windows": (
            "PRE_WINDOWS" in projection
            and "POST_WINDOWS" in projection
            and "LAUNCH_WINDOWS" in projection
            and '"p5m_exact_minute"' in projection
            and '"pool_age_days_at_domestic_listing"' in projection
        ),
        "build44_projection_before_budget": (
            "from .dex_launch_snapshot import build_dex_launch_snapshot" in lifecycle
            and 'public["dex_launch"] = build_dex_launch_snapshot(DEMO_DB_PATH)' in lifecycle
            and lifecycle.index('public["dex_launch"]') < lifecycle.index("return apply_snapshot_budget(snapshot)")
        ),
        "build44_budget_limits_preserved": (
            "MAX_BODY_BYTES = 1_800_000" in budget
            and "TARGET_BODY_BYTES = 1_400_000" in budget
            and "RESERVED_HEADROOM_BYTES = MAX_BODY_BYTES - TARGET_BODY_BYTES" in budget
        ),
        "build44_viewer_panel_compact_only": (
            "installDexLaunchResearchPanel" in panel
            and "data-dex-launch-panel" in panel
            and "raw_candles_included===false" in panel
            and "raw OHLCV" in panel
            and "getMarketDetail" not in panel
            and "fetch(" not in panel
            and "installDexLaunchResearchPanel({store,root})" in main_js
        ),
        "build44_direct_verifier_import_bootstrap": (
            "ROOT = Path(__file__).resolve().parents[1]" in verifier
            and "sys.path.insert(0, str(ROOT))" in verifier
            and '"--import-check" in sys.argv' in verifier
            and "DEX_CLOUD_PROJECTION_BUILD44_IMPORT=PASS" in verifier
        ),
        "build44_no_paper_or_order_wiring": (
            "from .decision" not in projection
            and "from .order" not in projection
            and "place_order(" not in projection
        ),
    }

    print("=== DEX CLOUD PROJECTION BUILD 44 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        raise SystemExit(f"DEX_CLOUD_PROJECTION_BUILD44=FAIL: {', '.join(failed)}")
    print("DEX_CLOUD_PROJECTION_BUILD44=PASS")


if __name__ == "__main__":
    main()
