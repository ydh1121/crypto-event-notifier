from __future__ import annotations

import inspect

from b3_trader import market_ohlcv_research_cycle as cycle_module
from b3_trader.market_ohlcv_research_cycle import MarketOhlcvResearchCycle


def test_market_cycle_integrates_reliability_after_forward_reaction() -> None:
    source = inspect.getsource(MarketOhlcvResearchCycle)
    reaction_call = source.index("self.flow_reaction.compute_pending")
    reliability_call = source.index("self.flow_reliability.compute")
    assert reaction_call < reliability_call
    assert "self.flow_reliability = MarketFlowReliabilityStore(self.path)" in source
    assert "self.flow_reliability.close()" in source
    assert '"flow_reliability": flow_reliability_result' in source


def test_market_cycle_preregisters_reliability_contract_in_state_v8() -> None:
    source = inspect.getsource(MarketOhlcvResearchCycle.run_once)
    assert '"version": 8' in source
    assert '"source": "market_flow_reaction"' in source
    assert '"observation_min_per_venue": 20' in source
    assert '"promotion_min_per_venue": 50' in source
    assert '"promotion_min_pooled": 120' in source
    assert '"promotion_wilson_lower_pct": 50.0' in source
    assert '"feature_version": 1' in source
    assert '"score_wired": False' in source


def test_market_cycle_imports_reliability_without_live_wiring() -> None:
    module_source = inspect.getsource(cycle_module)
    assert "from .market_flow_reliability import MarketFlowReliabilityStore" in module_source
    assert "can_place_orders" in module_source
    assert "score_wired" in module_source
    assert "live_order" not in module_source.lower()
