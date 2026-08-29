from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_launch_quality import evaluate_dex_launch_quality


def audit_dex_sample(path: Path | str = DB_PATH) -> dict[str, Any]:
    """Read-only composition audit for DEX research samples.

    This audit deliberately does not redefine Build45 sample-ready thresholds and
    never wires DEX features into score, PAPER decisions, or orders.
    """

    db_path = Path(path)
    quality = evaluate_dex_launch_quality(db_path)
    base = {
        "ok": bool(quality.get("ok")),
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "advisory_only": True,
        "changes_build45_thresholds": False,
    }
    if not quality.get("ok") or not db_path.exists():
        return {**base, "quality": quality, "blocking_reason": "dex_quality_unavailable"}

    quality_rows = [row for row in (quality.get("cases") or []) if isinstance(row, dict)]
    quality_by_key = {str(row.get("case_key") or ""): row for row in quality_rows if row.get("case_key")}

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        listing_meta: dict[str, dict[str, Any]] = {}
        if "listing_history_cases" in tables:
            for row in conn.execute(
                "SELECT case_key,domestic_exchange,domestic_market,symbol,identity_verified FROM listing_history_cases"
            ).fetchall():
                listing_meta[str(row["case_key"])] = {
                    "exchange": str(row["domestic_exchange"] or "").lower(),
                    "market": str(row["domestic_market"] or "").upper(),
                    "symbol": str(row["symbol"] or "").upper(),
                    "identity_verified": bool(row["identity_verified"]),
                }

        usable_rows: list[dict[str, Any]] = []
        not_usable_rows: list[dict[str, Any]] = []
        for row in quality_rows:
            key = str(row.get("case_key") or "")
            merged = {**row, **listing_meta.get(key, {})}
            if bool(row.get("usable_for_shadow_analysis")):
                usable_rows.append(merged)
            else:
                not_usable_rows.append(merged)

        exchange_counts: Counter[str] = Counter(str(row.get("exchange") or "unknown") for row in usable_rows)
        completion_counts: Counter[str] = Counter(str(row.get("derived_completion") or "unknown") for row in usable_rows)
        failure_status_counts: Counter[str] = Counter(str(row.get("stored_status") or "unknown") for row in not_usable_rows)

        asset_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in usable_rows:
            asset_id = str(row.get("coingecko_id") or "").strip()
            if not asset_id:
                asset_id = f"unresolved:{row.get('case_key')}"
            asset_groups[asset_id].append(row)

        duplicate_groups = []
        for asset_id, rows in sorted(asset_groups.items()):
            if len(rows) <= 1 or asset_id.startswith("unresolved:"):
                continue
            duplicate_groups.append(
                {
                    "coingecko_id": asset_id,
                    "event_case_count": len(rows),
                    "exchanges": sorted({str(row.get("exchange") or "unknown") for row in rows}),
                    "markets": sorted(str(row.get("market") or "") for row in rows if row.get("market")),
                    "case_keys": sorted(str(row.get("case_key") or "") for row in rows),
                }
            )

        usable_count = len(usable_rows)
        unique_asset_count = len(asset_groups)
        exact_count = sum(1 for row in usable_rows if int(row.get("p5m_exact_asset_count") or 0) > 0)
        launch_count = sum(1 for row in usable_rows if int(row.get("launch_feature_asset_count") or 0) > 0)
        fully_complete_count = sum(1 for row in usable_rows if row.get("derived_completion") == "complete")
        partial_count = sum(1 for row in usable_rows if row.get("derived_completion") == "complete_partial")
        max_exchange_count = max(exchange_counts.values(), default=0)

        unresearched_verified = 0
        if "listing_history_cases" in tables and "dex_launch_case_status" in tables:
            unresearched_verified = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM listing_history_cases c
                    LEFT JOIN dex_launch_case_status d ON d.case_key=c.case_key
                    WHERE c.identity_verified=1
                      AND c.status NOT IN ('rejected_identity','rejected_notice')
                      AND d.case_key IS NULL
                    """
                ).fetchone()[0]
            )

        return {
            **base,
            "sample_ready_build45": bool(quality.get("sample_ready")),
            "build45_blocking_reasons": list(quality.get("blocking_reasons") or []),
            "event_cases": {
                "total_dex_cases": int(quality.get("case_count") or 0),
                "usable": usable_count,
                "not_usable": len(not_usable_rows),
                "unique_assets": unique_asset_count,
                "duplicate_event_cases": max(0, usable_count - unique_asset_count),
                "unique_asset_ratio": round(unique_asset_count / usable_count, 6) if usable_count else 0.0,
            },
            "coverage": {
                "exact_p5m_cases": exact_count,
                "exact_p5m_coverage": round(exact_count / usable_count, 6) if usable_count else 0.0,
                "launch_feature_cases": launch_count,
                "launch_feature_coverage": round(launch_count / usable_count, 6) if usable_count else 0.0,
                "fully_complete_cases": fully_complete_count,
                "fully_complete_ratio": round(fully_complete_count / usable_count, 6) if usable_count else 0.0,
                "complete_partial_cases": partial_count,
                "complete_partial_ratio": round(partial_count / usable_count, 6) if usable_count else 0.0,
            },
            "exchange_distribution": {
                "counts": dict(sorted(exchange_counts.items())),
                "max_exchange_share": round(max_exchange_count / usable_count, 6) if usable_count else 0.0,
            },
            "completion_distribution": dict(sorted(completion_counts.items())),
            "not_usable_status_distribution": dict(sorted(failure_status_counts.items())),
            "duplicate_asset_groups": duplicate_groups,
            "remaining": {
                "verified_listing_cases_without_dex_status": unresearched_verified,
            },
            "review": {
                "needs_more_event_cases_for_build45": usable_count < int(quality.get("thresholds", {}).get("min_usable_cases") or 20),
                "do_not_enable_shadow_score_yet": True,
                "reason": "composition_audit_is_advisory_until_sample_ready_and_reviewed",
            },
        }
    finally:
        conn.close()
