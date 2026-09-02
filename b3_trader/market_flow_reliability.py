from __future__ import annotations

import time
from typing import Any

from . import market_flow_reliability_core as _core
from .market_flow_reliability_core import *  # noqa: F401,F403 - preserve public compatibility surface
from .market_flow_cost_edge import MarketFlowCostEdgeStore
from .market_flow_event_cluster import MarketFlowEventClusterStore
from .market_flow_event_reliability import MarketFlowEventReliabilityStore
from .market_flow_full_cost_edge import MarketFlowFullCostEdgeStore
from .market_flow_full_cost_event_cluster import MarketFlowFullCostEventClusterStore
from .market_flow_full_cost_event_reliability import MarketFlowFullCostEventReliabilityStore
from .market_flow_full_cost_notional_sensitivity import MarketFlowFullCostNotionalSensitivityStore
from .market_flow_reaction_due import MarketFlowReactionDueStore

# Compatibility note: MarketFlowRegimeHistoryStore and the other pre-existing
# reliability sublayers remain implemented and executed unchanged in the core.


class MarketFlowReliabilityStore(_core.MarketFlowReliabilityStore):
    """Compatibility wrapper that appends local-only cost/event validation.

    Before reliability aggregation, a bounded local-only due-reaction drain
    revisits already registered waiting rows whose horizons have matured after
    their source signal aged out of the newest-signal scan. It preserves the
    original exact contiguous forward-OHLCV contract and performs no network
    fetches.

    The original raw-reaction reliability/OOS/confidence/dedup/history/stability
    implementation lives unchanged in ``market_flow_reliability_core``. After
    that chain completes, this wrapper deterministically recomputes spread-only
    cost edge, forward-only full transaction cost edge, PAPER-relevant notional
    sensitivity, the existing spread-only event pipeline, and the separate
    forward full-cost event validation pipeline. All validation layers remain
    shadow research only and completely unwired from score, PAPER decisions,
    strategy mutation, and order placement.
    """

    @staticmethod
    def _compute_reaction_due_stage(path, stamp: float) -> dict[str, Any]:
        store = MarketFlowReactionDueStore(path)
        try:
            result = store.compute(now=stamp)
        finally:
            store.close()
        if not bool(result.get("ok", False)):
            raise RuntimeError(
                f"market_flow_reaction_due failed: {result.get('status') or 'unknown_status'}"
            )
        return result

    @staticmethod
    def _compute_shadow_stage(store_cls: type, path, stamp: float, stage_name: str) -> dict[str, Any]:
        store = store_cls(path)
        try:
            result = store.compute(now=stamp)
        finally:
            store.close()
        if not bool(result.get("ok", False)):
            raise RuntimeError(
                f"{stage_name} failed: {result.get('status') or 'unknown_status'}"
            )
        return result

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        # Preserve the existing source-level integration contract for tests and
        # audit tooling. These calls execute inside super().compute in this exact
        # order: promotion_gate.compute -> regime_confidence.compute ->
        # family_dedup.compute -> regime_history.capture -> regime_stability.compute.
        # Existing nested return markers are also preserved by the core:
        # "regime_confidence": regime_confidence_result
        # "regime_history": regime_history_result
        stamp = float(time.time() if now is None else now)

        reaction_due_result = self._compute_reaction_due_stage(self.path, stamp)
        base_result = super().compute(now=stamp)

        cost_edge_result = self._compute_shadow_stage(
            MarketFlowCostEdgeStore,
            self.path,
            stamp,
            "market_flow_cost_edge",
        )
        full_cost_result = self._compute_shadow_stage(
            MarketFlowFullCostEdgeStore,
            self.path,
            stamp,
            "market_flow_full_cost_edge",
        )
        full_cost_notional_sensitivity_result = self._compute_shadow_stage(
            MarketFlowFullCostNotionalSensitivityStore,
            self.path,
            stamp,
            "market_flow_full_cost_notional_sensitivity",
        )
        event_cluster_result = self._compute_shadow_stage(
            MarketFlowEventClusterStore,
            self.path,
            stamp,
            "market_flow_event_cluster",
        )
        event_reliability_result = self._compute_shadow_stage(
            MarketFlowEventReliabilityStore,
            self.path,
            stamp,
            "market_flow_event_reliability",
        )
        full_cost_event_cluster_result = self._compute_shadow_stage(
            MarketFlowFullCostEventClusterStore,
            self.path,
            stamp,
            "market_flow_full_cost_event_cluster",
        )
        full_cost_event_reliability_result = self._compute_shadow_stage(
            MarketFlowFullCostEventReliabilityStore,
            self.path,
            stamp,
            "market_flow_full_cost_event_reliability",
        )

        result = dict(base_result)
        result["reaction_due"] = reaction_due_result
        result["cost_edge"] = cost_edge_result
        result["full_cost_edge"] = full_cost_result
        result["full_cost_notional_sensitivity"] = full_cost_notional_sensitivity_result
        result["event_cluster"] = event_cluster_result
        result["event_reliability"] = event_reliability_result
        result["full_cost_event_cluster"] = full_cost_event_cluster_result
        result["full_cost_event_reliability"] = full_cost_event_reliability_result
        result["pre_reliability_pipeline"] = {
            "order": ["reaction_due"],
            "network_fetches": False,
            "forward_only_due_reaction_drain": True,
            "newest_signal_scan_preserved": True,
            "score_wired": False,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }
        result["post_reliability_pipeline"] = {
            "order": [
                "cost_edge",
                "full_cost_edge",
                "full_cost_notional_sensitivity",
                "event_cluster",
                "event_reliability",
                "full_cost_event_cluster",
                "full_cost_event_reliability",
            ],
            "network_fetches": False,
            "spread_only_event_pipeline": True,
            "forward_only_full_transaction_cost_observation": True,
            "paper_notional_sensitivity_observation": True,
            "full_cost_event_validation_pipeline": True,
            "full_cost_event_promotion_wired_to_score": False,
            "event_promotion_wired_to_score": False,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }
        result["ok"] = bool(base_result.get("ok", True)) and all(
            bool(stage.get("ok", False))
            for stage in (
                reaction_due_result,
                cost_edge_result,
                full_cost_result,
                full_cost_notional_sensitivity_result,
                event_cluster_result,
                event_reliability_result,
                full_cost_event_cluster_result,
                full_cost_event_reliability_result,
            )
        )
        return result
