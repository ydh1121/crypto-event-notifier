from __future__ import annotations

from pathlib import Path

from b3_trader.market_flow_absorption_consensus_v2 import (
    MarketFlowAbsorptionConsensusV2Store,
)


def test_consensus_v2_activation_bootstraps_before_sources_exist(tmp_path: Path) -> None:
    path = tmp_path / "consensus-v2-activation.sqlite3"

    store = MarketFlowAbsorptionConsensusV2Store(path)
    try:
        result = store.compute(now=1000.0)
        audit = store.audit()
    finally:
        store.close()

    assert result["ok"] is True
    assert result["status"] == "waiting_for_v1_divergence_and_identity_sources"
    assert result["activation_ts"] == 1000.0
    assert result["rows_written"] == 0
    assert result["consensus_rows"] == 0

    assert audit["ok"] is True
    assert audit["activation_present"] is True
    assert audit["activation_ts"] == 1000.0
    assert audit["row_count"] == 0
    assert audit["pre_activation_rows"] == 0
    assert audit["historical_v1_backfill"] is False
