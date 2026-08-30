from __future__ import annotations

import json
import math
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_launch_quality import evaluate_dex_launch_quality
from .dex_launch_research_cycle import DEX_OHLCV_HISTORY_SECONDS
from .dex_shadow_readiness_audit import MIN_LAUNCH_FEATURE_COVERAGE
from .dex_shadow_remediation_runner import STATE_PATH


MINUTE_REFERENCE_TOLERANCE_SECONDS = 15 * 60
HOURLY_REFERENCE_TOLERANCE_SECONDS = 3600


def _json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _source_key(row: dict[str, Any]) -> tuple[str, str, str, float]:
    return (
        str(row.get("network_id") or ""),
        str(row.get("token_address") or ""),
        str(row.get("pool_address") or ""),
        float(row.get("pool_created_at") or 0.0),
    )


def _candle_stat(
    stats: dict[tuple[str, str, str], dict[str, Any]],
    asset_key: str,
    pool_address: str,
    kind: str,
) -> dict[str, Any]:
    return dict(stats.get((asset_key, pool_address, kind), {}))


def _reference_delta(stat: dict[str, Any], created: float) -> float | None:
    first = float(stat.get("first_ts") or 0.0)
    if created <= 0 or first < created:
        return None
    return round(first - created, 3)


def audit_dex_launch_coverage(
    path: Path | str = DB_PATH,
    *,
    state_path: Path | str = STATE_PATH,
    now: float | None = None,
) -> dict[str, Any]:
    """Read-only diagnosis for the final Build53 launch-coverage blocker."""

    db_path = Path(path)
    current_now = float(now if now is not None else time.time())
    quality = evaluate_dex_launch_quality(db_path)
    base = {
        "ok": bool(quality.get("ok")),
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "advisory_only": True,
        "read_only": True,
        "network_fetches": False,
        "changes_build53_thresholds": False,
        "changes_feature_criteria": False,
    }
    if not quality.get("ok") or not db_path.exists():
        return {**base, "blocking_reason": "dex_quality_unavailable", "quality": quality}

    usable_rows = [
        row
        for row in (quality.get("cases") or [])
        if isinstance(row, dict) and row.get("usable_for_shadow_analysis") and row.get("case_key")
    ]
    usable_keys = {str(row.get("case_key")) for row in usable_rows}
    quality_by_key = {str(row.get("case_key")): row for row in usable_rows}
    usable_count = len(usable_rows)
    current_launch_count = sum(
        1 for row in usable_rows if int(row.get("launch_feature_asset_count") or 0) > 0
    )
    required_launch_count = (
        int(math.ceil(MIN_LAUNCH_FEATURE_COVERAGE * usable_count)) if usable_count else 0
    )

    state = _read_json(Path(state_path))
    attempts = state.get("launch_attempted_at") if isinstance(state.get("launch_attempted_at"), dict) else {}
    attempted_assets = {str(key) for key in attempts if str(key)}

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required_tables = {
            "dex_launch_assets",
            "dex_launch_pools",
            "dex_launch_features",
            "dex_launch_candles",
        }
        if not required_tables.issubset(tables):
            return {
                **base,
                "ok": False,
                "blocking_reason": "required_tables_missing",
                "missing_tables": sorted(required_tables - tables),
            }

        candle_stats: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in conn.execute(
            """
            SELECT asset_key,pool_address,series_kind,COUNT(*) AS n,
                   MIN(candle_ts) AS first_ts,MAX(candle_ts) AS last_ts
            FROM dex_launch_candles
            WHERE series_kind IN ('launch_hourly','launch_minute')
            GROUP BY asset_key,pool_address,series_kind
            """
        ).fetchall():
            candle_stats[(str(row["asset_key"]), str(row["pool_address"]), str(row["series_kind"]))] = {
                "count": int(row["n"] or 0),
                "first_ts": float(row["first_ts"] or 0.0),
                "last_ts": float(row["last_ts"] or 0.0),
            }

        attempted_source_keys: set[tuple[str, str, str, float]] = set()
        if attempted_assets:
            asset_list = sorted(attempted_assets)
            for start in range(0, len(asset_list), 500):
                chunk = asset_list[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"""
                    SELECT a.network_id,a.token_address,p.pool_address,p.pool_created_at
                    FROM dex_launch_assets a
                    JOIN dex_launch_pools p ON p.asset_key=a.asset_key
                    WHERE p.selected_primary=1 AND a.asset_key IN ({placeholders})
                    """,
                    tuple(chunk),
                ).fetchall()
                for row in rows:
                    attempted_source_keys.add(_source_key(dict(row)))

        primary_rows: list[dict[str, Any]] = []
        accepted_pools_by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if usable_keys:
            placeholders = ",".join("?" for _ in usable_keys)
            primary_rows = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT a.case_key,a.asset_key,a.network_id,a.token_address,
                           p.pool_address,p.dex_id,p.pool_created_at,p.reserve_usd,p.volume_h24_usd,
                           p.gate_status,p.selected_primary,f.feature_json
                    FROM dex_launch_assets a
                    JOIN dex_launch_pools p ON p.asset_key=a.asset_key
                    LEFT JOIN dex_launch_features f
                      ON f.asset_key=p.asset_key AND f.pool_address=p.pool_address
                    WHERE p.selected_primary=1
                      AND a.case_key IN ({placeholders})
                    ORDER BY a.case_key,a.asset_key
                    """,
                    tuple(sorted(usable_keys)),
                ).fetchall()
            ]
            for row in conn.execute(
                f"""
                SELECT a.case_key,a.asset_key,a.network_id,a.token_address,
                       p.pool_address,p.dex_id,p.pool_created_at,p.reserve_usd,p.volume_h24_usd,p.selected_primary
                FROM dex_launch_assets a
                JOIN dex_launch_pools p ON p.asset_key=a.asset_key
                WHERE p.gate_status='accepted'
                  AND a.case_key IN ({placeholders})
                ORDER BY a.asset_key,p.selected_primary DESC,p.pool_created_at ASC
                """,
                tuple(sorted(usable_keys)),
            ).fetchall():
                accepted_pools_by_asset[str(row["asset_key"])].append(dict(row))
    finally:
        conn.close()

    case_assets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    classification_counts: Counter[str] = Counter()
    fresh_source_keys: set[tuple[str, str, str, float]] = set()
    partial_reference_gap: list[dict[str, Any]] = []
    inconsistent_reference_rows: list[dict[str, Any]] = []
    alternate_pool_opportunities: list[dict[str, Any]] = []

    for row in primary_rows:
        case_key = str(row.get("case_key") or "")
        asset_key = str(row.get("asset_key") or "")
        pool_address = str(row.get("pool_address") or "")
        created = float(row.get("pool_created_at") or 0.0)
        feature = _json(row.get("feature_json"))
        launch = feature.get("pool_launch_window") if isinstance(feature.get("pool_launch_window"), dict) else {}
        launch_status = str(launch.get("status") or "feature_missing")
        hourly = _candle_stat(candle_stats, asset_key, pool_address, "launch_hourly")
        minute = _candle_stat(candle_stats, asset_key, pool_address, "launch_minute")
        hourly_delta = _reference_delta(hourly, created)
        minute_delta = _reference_delta(minute, created)
        reference_available = bool(
            (minute_delta is not None and minute_delta <= MINUTE_REFERENCE_TOLERANCE_SECONDS)
            or (hourly_delta is not None and hourly_delta <= HOURLY_REFERENCE_TOLERANCE_SECONDS)
        )
        source_key = _source_key(row)
        source_attempted = bool(source_key in attempted_source_keys)
        within_history = bool(created > 0 and current_now - created <= DEX_OHLCV_HISTORY_SECONDS)

        if launch_status == "collected":
            classification = "collected"
        elif created <= 0 or launch_status == "pool_created_at_missing":
            classification = "pool_created_at_missing"
        elif not within_history:
            classification = "history_window_expired"
        elif reference_available:
            classification = "persisted_reference_present_status_unavailable"
        elif int(hourly.get("count") or 0) > 0 or int(minute.get("count") or 0) > 0:
            classification = "partial_candles_without_launch_reference"
        elif source_attempted:
            classification = "attempted_source_unavailable"
        else:
            classification = "unattempted_source_candidate"

        if classification == "unattempted_source_candidate":
            fresh_source_keys.add(source_key)
        detail = {
            "case_key": case_key,
            "asset_key": asset_key,
            "network_id": str(row.get("network_id") or ""),
            "token_address": str(row.get("token_address") or ""),
            "pool_address": pool_address,
            "dex_id": str(row.get("dex_id") or ""),
            "pool_created_at": created,
            "pool_age_days": round(max(0.0, current_now - created) / 86400.0, 4) if created > 0 else None,
            "launch_status": launch_status,
            "launch_hourly_count": int(hourly.get("count") or 0),
            "launch_minute_count": int(minute.get("count") or 0),
            "first_launch_hourly_delta_seconds": hourly_delta,
            "first_launch_minute_delta_seconds": minute_delta,
            "reference_available_by_original_build42_rule": reference_available,
            "source_previously_attempted": source_attempted,
            "within_geckoterminal_history_window": within_history,
            "classification": classification,
        }
        case_assets[case_key].append(detail)
        classification_counts[classification] += 1
        if classification == "partial_candles_without_launch_reference":
            partial_reference_gap.append(detail)
        elif classification == "persisted_reference_present_status_unavailable":
            inconsistent_reference_rows.append(detail)

        for alt in accepted_pools_by_asset.get(asset_key, []):
            if bool(alt.get("selected_primary")):
                continue
            alt_created = float(alt.get("pool_created_at") or 0.0)
            if alt_created <= 0 or current_now - alt_created > DEX_OHLCV_HISTORY_SECONDS:
                continue
            alt_key = _source_key(alt)
            alternate_pool_opportunities.append(
                {
                    "case_key": case_key,
                    "asset_key": asset_key,
                    "network_id": str(alt.get("network_id") or ""),
                    "token_address": str(alt.get("token_address") or ""),
                    "pool_address": str(alt.get("pool_address") or ""),
                    "dex_id": str(alt.get("dex_id") or ""),
                    "pool_created_at": alt_created,
                    "pool_age_days": round(max(0.0, current_now - alt_created) / 86400.0, 4),
                    "reserve_usd": float(alt.get("reserve_usd") or 0.0),
                    "volume_h24_usd": float(alt.get("volume_h24_usd") or 0.0),
                    "source_previously_attempted": bool(alt_key in attempted_source_keys),
                    "reason": "accepted_non_primary_pool_within_history_window",
                }
            )

    counted_cases: list[dict[str, Any]] = []
    missing_cases: list[dict[str, Any]] = []
    for case_key in sorted(usable_keys):
        quality_row = quality_by_key.get(case_key, {})
        item = {
            "case_key": case_key,
            "coingecko_id": str(quality_row.get("coingecko_id") or ""),
            "launch_feature_asset_count": int(quality_row.get("launch_feature_asset_count") or 0),
            "assets": case_assets.get(case_key, []),
        }
        if item["launch_feature_asset_count"] > 0:
            counted_cases.append(item)
        else:
            missing_cases.append(item)

    alternate_pool_opportunities.sort(
        key=lambda row: (
            bool(row.get("source_previously_attempted")),
            float(row.get("pool_age_days") or math.inf),
            str(row.get("case_key") or ""),
        )
    )

    if inconsistent_reference_rows:
        next_action = "audit_feature_persistence_consistency_before_more_source_calls"
    elif alternate_pool_opportunities:
        next_action = "targeted_alternate_accepted_pool_probe_review"
    elif fresh_source_keys:
        next_action = "bounded_fresh_primary_source_recovery"
    else:
        next_action = "external_historical_source_or_sample_expansion_review"

    return {
        **base,
        "launch_feature_criteria": {
            "counted_when": "feature_json.pool_launch_window.status == collected",
            "reference_rule": {
                "minute_after_pool_created_within_seconds": MINUTE_REFERENCE_TOLERANCE_SECONDS,
                "fallback_hour_after_pool_created_within_seconds": HOURLY_REFERENCE_TOLERANCE_SECONDS,
            },
            "partial_hourly_rows_alone_are_not_sufficient": True,
        },
        "summary": {
            "usable_event_cases": usable_count,
            "launch_feature_cases": current_launch_count,
            "required_launch_feature_cases": required_launch_count,
            "additional_launch_cases_needed": max(0, required_launch_count - current_launch_count),
            "launch_feature_coverage": round(current_launch_count / usable_count, 6) if usable_count else 0.0,
            "fresh_primary_source_count": len(fresh_source_keys),
            "alternate_accepted_pool_candidates": len(alternate_pool_opportunities),
            "persisted_reference_inconsistencies": len(inconsistent_reference_rows),
        },
        "classification_counts": dict(sorted(classification_counts.items())),
        "counted_cases": counted_cases,
        "missing_cases": missing_cases,
        "partial_reference_gap_assets": partial_reference_gap,
        "persisted_reference_inconsistencies": inconsistent_reference_rows,
        "alternate_pool_opportunities": alternate_pool_opportunities,
        "build54_recoverable_recent_warning": {
            "age_only_classification_can_overstate_recovery": True,
            "reason": "Build54 treats unavailable primary pools inside the 183-day window as recoverable; Build60 also checks source attempts and launch-reference candle proximity.",
        },
        "recommended_next_action": next_action,
        "review": {
            "wire_shadow_score_now": False,
            "reason": "Build60 is read-only diagnosis; Build53 must pass before shadow-score implementation.",
        },
    }
