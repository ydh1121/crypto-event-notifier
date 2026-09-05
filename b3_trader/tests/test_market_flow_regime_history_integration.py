from __future__ import annotations

import inspect

from b3_trader.market_flow_reliability import MarketFlowReliabilityStore


def test_reliability_compute_captures_history_after_family_dedup() -> None:
    source = inspect.getsource(MarketFlowReliabilityStore.compute)
    promotion_call = source.index("promotion_gate.compute")
    confidence_call = source.index("regime_confidence.compute")
    dedup_call = source.index("family_dedup.compute")
    history_call = source.index("regime_history.capture")

    assert promotion_call < confidence_call < dedup_call < history_call
    assert '"regime_history": regime_history_result' in source
    assert "MarketFlowRegimeHistoryStore" in inspect.getsource(
        __import__("b3_trader.market_flow_reliability", fromlist=["MarketFlowReliabilityStore"])
    )
