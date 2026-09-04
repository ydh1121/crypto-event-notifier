from __future__ import annotations

import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .intelligence_event_response import HORIZONS, OBSERVATION_TOLERANCE_SECONDS, PROVIDER_ID


def run_check(*, path: Path | str = DB_PATH) -> tuple[dict[str, Any], int]:
    db_path = Path(path)
    result: dict[str, Any] = {
        "ok": False,
        "status": "not_checked",
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_mutation": False,
        "provider_id": PROVIDER_ID,
        "required_horizons": [label for label, _ in HORIZONS],
        "sample_count": 0,
        "events_with_samples": 0,
        "markets": [],
        "horizon_counts": {},
        "latest_event": {},
    }
    if not db_path.exists():
        result["status"] = "database_missing"
        return result, 1

    try:
        conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        result["status"] = "database_open_error"
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return result, 2

    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_intelligence_event_responses'"
        ).fetchone()
        if table is None:
            result["status"] = "response_table_missing"
            return result, 1

        rows = conn.execute(
            """SELECT event_id,event_type,source_id,exchange,market,horizon_label,horizon_seconds,
                      event_ts,baseline_trade_ts,baseline_price,target_ts,target_trade_ts,target_price,
                      return_pct,observation_tolerance_seconds,captured_at
               FROM research_intelligence_event_responses
               WHERE provider_id=?
               ORDER BY captured_at DESC,event_ts DESC,horizon_seconds,exchange,market""",
            (PROVIDER_ID,),
        ).fetchall()
        result["sample_count"] = len(rows)
        if not rows:
            result["status"] = "waiting_for_observable_event"
            return result, 1

        allowed = {label: float(seconds) for label, seconds in HORIZONS}
        invalid: list[str] = []
        horizon_counts: dict[str, int] = {}
        markets: set[str] = set()
        events: set[str] = set()
        for row in rows:
            event_id = str(row["event_id"])
            label = str(row["horizon_label"])
            events.add(event_id)
            markets.add(f"{row['exchange']}:{row['market']}")
            horizon_counts[label] = horizon_counts.get(label, 0) + 1
            if label not in allowed or abs(float(row["horizon_seconds"]) - allowed.get(label, -1.0)) > 1e-9:
                invalid.append(f"invalid_horizon:{event_id}:{label}")
                continue
            event_ts = float(row["event_ts"])
            baseline_ts = float(row["baseline_trade_ts"])
            target_ts = float(row["target_ts"])
            target_trade_ts = float(row["target_trade_ts"])
            baseline_price = float(row["baseline_price"])
            target_price = float(row["target_price"])
            response = float(row["return_pct"])
            tolerance = float(row["observation_tolerance_seconds"])
            if baseline_price <= 0 or target_price <= 0 or not math.isfinite(response):
                invalid.append(f"invalid_numeric:{event_id}:{label}")
            if baseline_ts > event_ts or event_ts - baseline_ts > tolerance + 1e-6:
                invalid.append(f"invalid_baseline_semantics:{event_id}:{label}")
            if target_trade_ts < target_ts or target_trade_ts - target_ts > tolerance + 1e-6:
                invalid.append(f"invalid_target_semantics:{event_id}:{label}")
            if tolerance > OBSERVATION_TOLERANCE_SECONDS + 1e-6:
                invalid.append(f"unexpected_tolerance:{event_id}:{label}")

        result["events_with_samples"] = len(events)
        result["markets"] = sorted(markets)
        result["horizon_counts"] = {label: horizon_counts.get(label, 0) for label, _ in HORIZONS}
        latest = rows[0]
        result["latest_event"] = {
            "event_id": str(latest["event_id"]),
            "event_type": str(latest["event_type"]),
            "source_id": str(latest["source_id"]),
            "exchange": str(latest["exchange"]),
            "market": str(latest["market"]),
            "horizon": str(latest["horizon_label"]),
            "return_pct": float(latest["return_pct"]),
        }
        if invalid:
            result["status"] = "contract_violation"
            result["violations"] = invalid[:20]
            return result, 2

        result["ok"] = True
        result["status"] = "ok"
        return result, 0
    except sqlite3.Error as exc:
        result["status"] = "database_query_error"
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return result, 2
    finally:
        conn.close()


def main() -> None:
    result, code = run_check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
