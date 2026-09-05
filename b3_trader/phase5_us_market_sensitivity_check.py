from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .intelligence_event_response import PROVIDER_ID as EVENT_RESPONSE_PROVIDER_ID
from .intelligence_us_market_sensitivity import (
    STATS_PROVIDER_ID,
    STATS_VERSION,
    UsMarketSensitivityAccumulator,
)

TABLE = "research_us_market_sensitivity_stats"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def run_check(*, path: Path | str = DB_PATH) -> tuple[dict[str, Any], int]:
    db_path = Path(path)
    result: dict[str, Any] = {
        "ok": False,
        "status": "not_checked",
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_mutation": False,
        "network_requests": 0,
        "response_provider_id": EVENT_RESPONSE_PROVIDER_ID,
        "stats_provider_id": STATS_PROVIDER_ID,
        "stats_rows": 0,
        "samples_represented": 0,
        "event_types": [],
        "markets": [],
        "horizons": [],
        "readiness_counts": {},
        "violations": [],
    }
    if not db_path.exists():
        result["status"] = "database_missing"
        return result, 1

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, TABLE):
            result["status"] = "waiting_for_sensitivity_table"
            return result, 1
        rows = conn.execute(
            f"SELECT * FROM {TABLE} WHERE stats_provider_id=? ORDER BY event_type,horizon_seconds,exchange,market",
            (STATS_PROVIDER_ID,),
        ).fetchall()
        result["stats_rows"] = len(rows)
        if not rows:
            result["status"] = "waiting_for_event_response_samples"
            return result, 1

        violations: list[str] = []
        readiness_counts: dict[str, int] = {}
        event_types: set[str] = set()
        markets: set[str] = set()
        horizons: set[str] = set()
        samples_represented = 0

        for index, row in enumerate(rows):
            prefix = f"row[{index}]"
            event_type = str(row["event_type"] or "").strip().upper()
            source_id = str(row["source_id"] or "").strip().lower()
            exchange = str(row["exchange"] or "").strip().lower()
            market = str(row["market"] or "").strip().upper()
            horizon = str(row["horizon_label"] or "").strip().lower()
            if not all((event_type, source_id, exchange, market, horizon)):
                violations.append(f"{prefix}:identity_missing")
                continue
            event_types.add(event_type)
            markets.add(f"{exchange}:{market}")
            horizons.add(horizon)

            try:
                sample_count = int(row["sample_count"])
                event_count = int(row["distinct_event_count"])
                positive = int(row["positive_count"])
                negative = int(row["negative_count"])
                flat = int(row["flat_count"])
                version = int(row["stats_version"])
            except (TypeError, ValueError):
                violations.append(f"{prefix}:count_or_version_invalid")
                continue
            samples_represented += max(0, sample_count)
            if sample_count < 1:
                violations.append(f"{prefix}:sample_count_invalid")
            if event_count < 1 or event_count > sample_count:
                violations.append(f"{prefix}:distinct_event_count_invalid")
            if positive < 0 or negative < 0 or flat < 0 or positive + negative + flat != sample_count:
                violations.append(f"{prefix}:direction_counts_invalid")
            if version != STATS_VERSION:
                violations.append(f"{prefix}:stats_version_invalid")
            if str(row["response_provider_id"] or "") != EVENT_RESPONSE_PROVIDER_ID:
                violations.append(f"{prefix}:response_provider_invalid")
            if str(row["stats_provider_id"] or "") != STATS_PROVIDER_ID:
                violations.append(f"{prefix}:stats_provider_invalid")

            numeric_fields = (
                "horizon_seconds",
                "positive_rate_pct",
                "mean_return_pct",
                "median_return_pct",
                "mean_abs_return_pct",
                "min_return_pct",
                "max_return_pct",
                "first_event_ts",
                "last_event_ts",
                "calculated_at",
            )
            if any(not _finite(row[field]) for field in numeric_fields):
                violations.append(f"{prefix}:non_finite_numeric")
                continue
            if float(row["horizon_seconds"]) <= 0:
                violations.append(f"{prefix}:horizon_seconds_invalid")
            if float(row["first_event_ts"]) <= 0 or float(row["last_event_ts"]) < float(row["first_event_ts"]):
                violations.append(f"{prefix}:event_time_range_invalid")
            expected_positive_rate = positive / sample_count * 100.0 if sample_count > 0 else math.nan
            if not math.isfinite(expected_positive_rate) or abs(float(row["positive_rate_pct"]) - expected_positive_rate) > 1e-8:
                violations.append(f"{prefix}:positive_rate_invalid")
            minimum = float(row["min_return_pct"])
            maximum = float(row["max_return_pct"])
            mean = float(row["mean_return_pct"])
            median = float(row["median_return_pct"])
            mean_abs = float(row["mean_abs_return_pct"])
            if minimum > maximum or mean < minimum - 1e-12 or mean > maximum + 1e-12:
                violations.append(f"{prefix}:return_range_invalid")
            if median < minimum - 1e-12 or median > maximum + 1e-12:
                violations.append(f"{prefix}:median_range_invalid")
            if mean_abs < abs(mean) - 1e-12 or mean_abs < 0:
                violations.append(f"{prefix}:mean_abs_invalid")
            stddev = row["stddev_return_pct"]
            if sample_count == 1:
                if stddev is not None:
                    violations.append(f"{prefix}:single_sample_stddev_must_be_null")
            elif stddev is None or not _finite(stddev) or float(stddev) < 0:
                violations.append(f"{prefix}:stddev_invalid")

            readiness = str(row["readiness"] or "").strip()
            expected_readiness = UsMarketSensitivityAccumulator.readiness_for(sample_count)
            if readiness != expected_readiness:
                violations.append(f"{prefix}:readiness_invalid")
            readiness_counts[readiness] = int(readiness_counts.get(readiness) or 0) + 1

            try:
                attributes = json.loads(str(row["attributes_json"] or "{}"))
            except (json.JSONDecodeError, TypeError, ValueError):
                attributes = {}
                violations.append(f"{prefix}:attributes_invalid_json")
            if not isinstance(attributes, dict):
                attributes = {}
                violations.append(f"{prefix}:attributes_not_object")
            if attributes.get("descriptive_only") is not True:
                violations.append(f"{prefix}:descriptive_only_not_asserted")
            if attributes.get("score_authority") is not False:
                violations.append(f"{prefix}:score_authority_not_false")
            if attributes.get("promotion_eligible") is not False:
                violations.append(f"{prefix}:promotion_eligible_not_false")
            if attributes.get("missing_values_coerced_to_zero") is not False:
                violations.append(f"{prefix}:missing_semantics_not_asserted")

        result.update(
            {
                "samples_represented": samples_represented,
                "event_types": sorted(event_types),
                "markets": sorted(markets),
                "horizons": sorted(horizons),
                "readiness_counts": readiness_counts,
                "violations": violations[:20],
            }
        )
        if violations:
            result["status"] = "contract_violation"
            return result, 2
        result["ok"] = True
        result["status"] = "ok"
        return result, 0
    finally:
        conn.close()


def main() -> None:
    result, code = run_check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
