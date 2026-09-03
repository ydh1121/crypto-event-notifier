from __future__ import annotations

from pathlib import Path

from b3_trader import market_flow_reliability_core as reliability_core
from b3_trader.market_flow_reliability import MarketFlowReliabilityStore


def test_reliability_wrapper_runs_consensus_v2_as_forward_pre_stage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "market.db"
    shadow_calls: list[str] = []
    pre_calls: list[str] = []

    def fake_base_compute(self, *, now=None):
        return {"ok": True, "status": "base_ok", "received_at": now}

    def fake_due(path_arg, stamp):
        pre_calls.append("reaction_due")
        return {"ok": True, "status": "computed", "received_at": stamp}

    def fake_consensus(path_arg, stamp):
        pre_calls.append("absorption_consensus_v2")
        return {
            "ok": True,
            "status": "computed",
            "activation_ts": stamp,
            "consensus_rows": 0,
            "received_at": stamp,
        }

    def fake_forward(path_arg, stamp):
        pre_calls.append("absorption_consensus_v2_forward")
        return {
            "ok": True,
            "status": "computed",
            "activation_ts": stamp,
            "reaction_rows_registered": 0,
            "reference_notional_krw": 750000.0,
            "received_at": stamp,
        }

    def fake_shadow(store_cls, path_arg, stamp, stage_name):
        shadow_calls.append(stage_name)
        return {"ok": True, "status": "computed", "received_at": stamp}

    monkeypatch.setattr(reliability_core.MarketFlowReliabilityStore, "compute", fake_base_compute)
    monkeypatch.setattr(
        MarketFlowReliabilityStore,
        "_compute_reaction_due_stage",
        staticmethod(fake_due),
    )
    monkeypatch.setattr(
        MarketFlowReliabilityStore,
        "_compute_absorption_consensus_v2_stage",
        staticmethod(fake_consensus),
    )
    monkeypatch.setattr(
        MarketFlowReliabilityStore,
        "_compute_absorption_consensus_v2_forward_stage",
        staticmethod(fake_forward),
    )
    monkeypatch.setattr(
        MarketFlowReliabilityStore,
        "_compute_shadow_stage",
        staticmethod(fake_shadow),
    )

    store = MarketFlowReliabilityStore(path)
    try:
        result = store.compute(now=1_900_000_000.0)
    finally:
        store.close()

    assert result["ok"] is True
    assert pre_calls == [
        "reaction_due",
        "absorption_consensus_v2",
        "absorption_consensus_v2_forward",
    ]
    assert result["pre_reliability_pipeline"]["order"] == [
        "reaction_due",
        "absorption_consensus_v2",
        "absorption_consensus_v2_forward",
    ]
    assert result["pre_reliability_pipeline"]["forward_only_absorption_consensus_v2"] is True
    assert result["pre_reliability_pipeline"]["absorption_consensus_v2_historical_backfill"] is False
    assert result["pre_reliability_pipeline"]["absorption_consensus_v2_v1_threshold_retuning"] is False
    assert result["pre_reliability_pipeline"]["absorption_consensus_v2_forward_historical_backfill"] is False
    assert result["pre_reliability_pipeline"]["absorption_consensus_v2_forward_entry_policy"] == (
        "strict_next_5m_boundary_after_consensus_recorded"
    )
    assert result["pre_reliability_pipeline"]["absorption_consensus_v2_forward_reference_notional_krw"] == 750000.0
    assert result["pre_reliability_pipeline"]["score_wired"] is False
    assert result["pre_reliability_pipeline"]["can_place_orders"] is False
    assert result["absorption_consensus_v2"]["consensus_rows"] == 0
    assert result["absorption_consensus_v2_forward"]["reaction_rows_registered"] == 0
    assert shadow_calls == [
        "market_flow_cost_edge",
        "market_flow_full_cost_edge",
        "market_flow_full_cost_notional_sensitivity",
        "market_flow_event_cluster",
        "market_flow_event_reliability",
        "market_flow_full_cost_event_cluster",
        "market_flow_full_cost_event_reliability",
        "market_flow_absorption_consensus_v2_oos_comparator",
    ]
    assert result["post_reliability_pipeline"]["v1_v2_oos_comparator_separate_activation"] is True
    assert result["post_reliability_pipeline"]["v1_v2_oos_comparator_reference_notional_krw"] == 750000.0
    assert result["post_reliability_pipeline"]["v1_v2_oos_comparator_historical_backfill"] is False
    assert result["post_reliability_pipeline"]["v1_v2_oos_comparator_winner_selection"] is False
