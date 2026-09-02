from __future__ import annotations

from pathlib import Path

from b3_trader import market_flow_reliability_core as reliability_core
from b3_trader.market_flow_reliability import MarketFlowReliabilityStore


def test_reliability_wrapper_runs_full_cost_between_spread_cost_and_event_cluster(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "market.db"
    calls: list[str] = []

    def fake_base_compute(self, *, now=None):
        return {"ok": True, "status": "base_ok", "received_at": now}

    def fake_shadow_stage(store_cls, path_arg, stamp, stage_name):
        calls.append(stage_name)
        return {"ok": True, "status": "computed", "received_at": stamp}

    monkeypatch.setattr(reliability_core.MarketFlowReliabilityStore, "compute", fake_base_compute)
    monkeypatch.setattr(
        MarketFlowReliabilityStore,
        "_compute_shadow_stage",
        staticmethod(fake_shadow_stage),
    )

    store = MarketFlowReliabilityStore(path)
    try:
        result = store.compute(now=1_900_000_000.0)
    finally:
        store.close()

    assert calls == [
        "market_flow_cost_edge",
        "market_flow_full_cost_edge",
        "market_flow_full_cost_notional_sensitivity",
        "market_flow_event_cluster",
        "market_flow_event_reliability",
        "market_flow_full_cost_event_cluster",
        "market_flow_full_cost_event_reliability",
    ]
    assert result["full_cost_edge"]["ok"] is True
    assert result["full_cost_notional_sensitivity"]["ok"] is True
    assert result["full_cost_event_cluster"]["ok"] is True
    assert result["full_cost_event_reliability"]["ok"] is True
    assert result["post_reliability_pipeline"]["order"] == [
        "cost_edge",
        "full_cost_edge",
        "full_cost_notional_sensitivity",
        "event_cluster",
        "event_reliability",
        "full_cost_event_cluster",
        "full_cost_event_reliability",
    ]
    assert result["post_reliability_pipeline"]["forward_only_full_transaction_cost_observation"] is True
    assert result["post_reliability_pipeline"]["paper_notional_sensitivity_observation"] is True
    assert result["post_reliability_pipeline"]["full_cost_event_validation_pipeline"] is True
    assert result["post_reliability_pipeline"]["full_cost_event_promotion_wired_to_score"] is False
    assert result["post_reliability_pipeline"]["event_promotion_wired_to_score"] is False
    assert result["post_reliability_pipeline"]["can_place_orders"] is False
