from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_regime_history import (
    HISTORY_BUCKET_SECONDS,
    HISTORY_RETENTION_DAYS,
    MarketFlowRegimeHistoryStore,
)
from b3_trader.market_flow_reliability import MarketFlowReliabilityStore


def _max_value(store: MarketFlowRegimeHistoryStore, table: str, column: str) -> float:
    exists = store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return 0.0
    row = store.conn.execute(f"SELECT COALESCE(MAX({column}),0) FROM {table}").fetchone()
    return float(row[0] or 0.0) if row else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-automatic-cycle", action="store_true")
    args = parser.parse_args()

    store = MarketFlowRegimeHistoryStore()
    try:
        audit = store.audit()
        current_confidence_received = _max_value(
            store,"research_market_flow_regime_confidence_mx","received_at"
        )
        current_family_received = _max_value(
            store,"research_market_flow_family_dedup_mx","received_at"
        )
        history_confidence_source = _max_value(
            store,"research_market_flow_regime_confidence_history_mx","source_received_at"
        )
        history_family_source = _max_value(
            store,"research_market_flow_family_history_mx","source_received_at"
        )
    finally:
        store.close()

    reliability_source = inspect.getsource(MarketFlowReliabilityStore.compute)
    automatic_code_contract = (
        "regime_history.capture" in reliability_source
        and '"regime_history": regime_history_result' in reliability_source
        and reliability_source.index("family_dedup.compute")
        < reliability_source.index("regime_history.capture")
    )
    current_state_captured = (
        current_confidence_received > 0
        and current_family_received > 0
        and history_confidence_source + 0.000001 >= current_confidence_received
        and history_family_source + 0.000001 >= current_family_received
    )

    checks = {
        "confidence_table_ready": audit.get("confidence_table_exists") is True,
        "family_table_ready": audit.get("family_table_exists") is True,
        "audit_ok": audit.get("ok") is True,
        "bucket_contract_exact": int(audit.get("bucket_seconds") or 0) == HISTORY_BUCKET_SECONDS,
        "retention_contract_exact": int(audit.get("retention_days") or 0) == HISTORY_RETENTION_DAYS,
        "confidence_bucket_clean": int(audit.get("confidence_bucket_violations") or 0) == 0,
        "family_bucket_clean": int(audit.get("family_bucket_violations") or 0) == 0,
        "probability_contract_clean": int(audit.get("probability_contract_violations") or 0) == 0,
        "base_gate_semantics_clean": int(audit.get("base_gate_semantics_violations") or 0) == 0,
        "retention_clean": int(audit.get("retention_contract_violations") or 0) == 0,
        "paper_only": audit.get("paper_only") is True,
        "shadow_only": audit.get("shadow_only") is True,
        "score_unwired": audit.get("score_wired") is False,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "cannot_modify_strategy": audit.get("can_modify_strategy") is False,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "data_present": int(audit.get("confidence_row_count") or 0) > 0 and int(audit.get("family_row_count") or 0) > 0,
        "automatic_cycle_code_contract": automatic_code_contract,
        "automatic_history_captured_current_state": current_state_captured,
    }
    required = [
        "confidence_table_ready","family_table_ready","audit_ok","bucket_contract_exact",
        "retention_contract_exact","confidence_bucket_clean","family_bucket_clean",
        "probability_contract_clean","base_gate_semantics_clean","retention_clean",
        "paper_only","shadow_only","score_unwired","cannot_place_orders",
        "cannot_modify_strategy","raw_cloud_projection_disabled",
    ]
    if args.require_data:
        required.append("data_present")
    if args.require_automatic_cycle:
        required.extend([
            "automatic_cycle_code_contract",
            "automatic_history_captured_current_state",
        ])

    ok = all(bool(checks[name]) for name in required)
    payload = {
        "status": "runtime_verified" if ok else "runtime_verification_failed",
        "checks": checks,
        "automatic_refresh_evidence": {
            "current_confidence_received_at": current_confidence_received,
            "history_confidence_source_received_at": history_confidence_source,
            "current_family_received_at": current_family_received,
            "history_family_source_received_at": history_family_source,
        },
        "audit": audit,
        "expected_current_semantics": {
            "current_state_tables_remain_authoritative": True,
            "history_bucket_seconds": HISTORY_BUCKET_SECONDS,
            "history_retention_days": HISTORY_RETENTION_DAYS,
            "same_bucket_recompute_is_upsert_not_append": True,
            "confidence_history_is_not_probability_or_trading_score": True,
            "family_representative_changes_are_preserved_across_buckets": True,
            "base_gate_started_is_monotonic_oos_lifecycle_fact": True,
            "base_promotion_ready_is_current_sample_gate_result": True,
        },
        "read_only": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FLOW_REGIME_HISTORY_RUNTIME={'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
