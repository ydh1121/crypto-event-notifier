from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_fee_schedule import MarketFeeScheduleStore
from b3_trader.market_flow_full_cost_edge import MarketFlowFullCostEdgeStore
from b3_trader.market_orderbook_ladder import MarketOrderbookLadderStore


def _max_received_at(conn, table: str) -> float:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return 0.0
    row = conn.execute(f"SELECT COALESCE(MAX(received_at),0) FROM {table}").fetchone()
    return float(row[0] or 0.0) if row else 0.0


def _automatic_code_contract() -> bool:
    path = ROOT / "b3_trader" / "market_flow_reliability.py"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    markers = [
        "cost_edge_result = self._compute_shadow_stage(",
        "full_cost_result = self._compute_shadow_stage(",
        "event_cluster_result = self._compute_shadow_stage(",
        "event_reliability_result = self._compute_shadow_stage(",
    ]
    positions = [text.find(marker) for marker in markers]
    return all(position >= 0 for position in positions) and positions == sorted(positions)


def _bithumb_forward_profile_audit(fee_conn, full_conn) -> dict:
    profile = fee_conn.execute(
        """SELECT profile,source,effective_from,effective_to
           FROM research_market_fee_profile_history_mx
           WHERE exchange='bithumb' AND market_prefix='KRW' AND effective_to IS NULL
           ORDER BY effective_from DESC LIMIT 1"""
    ).fetchone()

    ready_by_exchange = {
        str(row["exchange"]): int(row["n"])
        for row in full_conn.execute(
            """SELECT exchange,COUNT(*) AS n
               FROM research_market_flow_full_cost_edge_mx
               WHERE full_cost_edge_ready=1
               GROUP BY exchange ORDER BY exchange"""
        ).fetchall()
    }

    if not profile:
        return {
            "profile_selected": False,
            "profile": None,
            "profile_source": None,
            "profile_effective_from": None,
            "ready_by_exchange": ready_by_exchange,
            "bithumb_ready_rows": int(ready_by_exchange.get("bithumb", 0)),
            "bithumb_ready_before_profile_effective_from": 0,
            "bithumb_ready_profile_mismatch": 0,
            "forward_profile_time_contract_clean": int(ready_by_exchange.get("bithumb", 0)) == 0,
        }

    profile_name = str(profile["profile"])
    effective_from = float(profile["effective_from"])
    pre_activation = int(full_conn.execute(
        """SELECT COUNT(*) FROM research_market_flow_full_cost_edge_mx
           WHERE exchange='bithumb' AND full_cost_edge_ready=1
             AND signal_feature_ts < ?""",
        (effective_from,),
    ).fetchone()[0])
    mismatch = int(full_conn.execute(
        """SELECT COUNT(*) FROM research_market_flow_full_cost_edge_mx
           WHERE exchange='bithumb' AND full_cost_edge_ready=1
             AND COALESCE(fee_profile,'') != ?""",
        (profile_name,),
    ).fetchone()[0])

    return {
        "profile_selected": True,
        "profile": profile_name,
        "profile_source": str(profile["source"]),
        "profile_effective_from": effective_from,
        "profile_effective_to": None if profile["effective_to"] is None else float(profile["effective_to"]),
        "ready_by_exchange": ready_by_exchange,
        "bithumb_ready_rows": int(ready_by_exchange.get("bithumb", 0)),
        "bithumb_ready_before_profile_effective_from": pre_activation,
        "bithumb_ready_profile_mismatch": mismatch,
        "forward_profile_time_contract_clean": pre_activation == 0 and mismatch == 0,
    }


def verify(
    *,
    require_ladder_data: bool,
    require_full_cost: bool,
    require_automatic_cycle: bool,
    require_bithumb_forward_profile: bool,
) -> tuple[bool, dict]:
    fee_store = MarketFeeScheduleStore()
    ladder_store = MarketOrderbookLadderStore()
    full_store = MarketFlowFullCostEdgeStore()
    try:
        fee = fee_store.audit()
        ladder = ladder_store.audit()
        full = full_store.audit()
        bithumb_forward = _bithumb_forward_profile_audit(fee_store.conn, full_store.conn)
        raw_reliability_ts = _max_received_at(full_store.conn, "research_market_flow_reliability_mx")
        full_cost_ts = _max_received_at(full_store.conn, "research_market_flow_full_cost_edge_mx")
    finally:
        full_store.close()
        ladder_store.close()
        fee_store.close()

    automatic_code_contract = _automatic_code_contract()
    automatic_capture = (
        raw_reliability_ts > 0.0
        and full_cost_ts > 0.0
        and abs(raw_reliability_ts - full_cost_ts) <= 0.000001
    )

    checks = {
        "fee_catalog_ready": bool(fee.get("ok")) and int(fee.get("catalog_rows") or 0) >= 3,
        "upbit_fee_profile_resolves": fee.get("upbit_krw_profile") == "standard",
        "bithumb_fee_profile_fail_closed_or_selected": (
            fee.get("bithumb_krw_profile") in {None, "standard", "coupon_0_04"}
        ),
        "fee_forward_only_no_historical_backfill": fee.get("historical_fee_backfill") is False,
        "bithumb_profile_history_time_contract_clean": bool(bithumb_forward.get("forward_profile_time_contract_clean")),
        "ladder_tables_ready": bool(ladder.get("tables_ready")),
        "ladder_contract_clean": bool(ladder.get("ok")),
        "ladder_prior_only": ladder.get("prior_only_minute_boundary") is True,
        "ladder_historical_backfill_disabled": ladder.get("historical_backfill") is False,
        "full_cost_audit_ok": bool(full.get("ok")),
        "full_cost_readiness_contract_clean": int(full.get("readiness_contract_violations") or 0) == 0,
        "full_cost_formula_contract_clean": int(full.get("formula_contract_violations") or 0) == 0,
        "full_cost_future_ladder_contract_clean": int(full.get("future_ladder_violations") or 0) == 0,
        "no_wiring_columns": not bool(full.get("suspicious_wiring_columns")),
        "paper_only": full.get("paper_only") is True,
        "shadow_only": full.get("shadow_only") is True,
        "score_unwired": full.get("score_wired") is False,
        "cannot_place_orders": full.get("can_place_orders") is False,
        "raw_cloud_projection_disabled": full.get("raw_cloud_projection") is False,
        "automatic_cycle_code_contract": automatic_code_contract,
        "automatic_full_cost_captured_latest_reliability": automatic_capture,
        "bithumb_forward_profile_selected": bool(bithumb_forward.get("profile_selected")),
    }
    if require_ladder_data:
        checks["ladder_data_present"] = int(ladder.get("row_count") or 0) > 0
    if require_full_cost:
        checks["full_cost_data_present"] = int(full.get("full_cost_ready_rows") or 0) > 0
    required = [
        "fee_catalog_ready",
        "upbit_fee_profile_resolves",
        "bithumb_fee_profile_fail_closed_or_selected",
        "fee_forward_only_no_historical_backfill",
        "bithumb_profile_history_time_contract_clean",
        "ladder_tables_ready",
        "ladder_contract_clean",
        "ladder_prior_only",
        "ladder_historical_backfill_disabled",
        "full_cost_audit_ok",
        "full_cost_readiness_contract_clean",
        "full_cost_formula_contract_clean",
        "full_cost_future_ladder_contract_clean",
        "no_wiring_columns",
        "paper_only",
        "shadow_only",
        "score_unwired",
        "cannot_place_orders",
        "raw_cloud_projection_disabled",
    ]
    if require_ladder_data:
        required.append("ladder_data_present")
    if require_full_cost:
        required.append("full_cost_data_present")
    if require_automatic_cycle:
        required.extend([
            "automatic_cycle_code_contract",
            "automatic_full_cost_captured_latest_reliability",
        ])
    if require_bithumb_forward_profile:
        required.extend([
            "bithumb_forward_profile_selected",
            "bithumb_profile_history_time_contract_clean",
        ])
    ok = all(bool(checks[name]) for name in required)
    return ok, {
        "status": "runtime_verified" if ok else "runtime_failed",
        "checks": checks,
        "automatic_pipeline_received_at": {
            "raw_reliability": raw_reliability_ts,
            "full_cost_edge": full_cost_ts,
        },
        "bithumb_forward_profile_audit": bithumb_forward,
        "fee_audit": fee,
        "ladder_audit": ladder,
        "full_cost_audit": full,
        "expected_current_semantics": {
            "current_fee_catalog_is_forward_only": True,
            "bithumb_coupon_is_never_assumed": True,
            "bithumb_selected_profile_applies_only_from_activation_time": True,
            "bithumb_ready_before_profile_activation_is_forbidden": True,
            "top5_ladder_is_one_latest_snapshot_per_minute": True,
            "cost_lookup_uses_immediately_prior_minute_only": True,
            "cost_lookup_requires_source_strictly_before_boundary": True,
            "cost_lookup_max_age_seconds": 5.0,
            "historical_ladder_backfill_forbidden": True,
            "full_cost_is_not_probability_or_trading_score": True,
            "full_cost_runs_automatically_after_spread_cost_edge": True,
            "full_cost_is_not_yet_used_by_spread_only_event_reliability": True,
        },
        "read_only_except_schema_open": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-ladder-data", action="store_true")
    parser.add_argument("--require-full-cost", action="store_true")
    parser.add_argument("--require-automatic-cycle", action="store_true")
    parser.add_argument("--require-bithumb-forward-profile", action="store_true")
    args = parser.parse_args()
    ok, payload = verify(
        require_ladder_data=bool(args.require_ladder_data),
        require_full_cost=bool(args.require_full_cost),
        require_automatic_cycle=bool(args.require_automatic_cycle),
        require_bithumb_forward_profile=bool(args.require_bithumb_forward_profile),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not ok:
        print("MARKET_FLOW_FULL_COST_RUNTIME=FAIL")
        raise SystemExit(1)
    print("MARKET_FLOW_FULL_COST_RUNTIME=PASS")


if __name__ == "__main__":
    main()
