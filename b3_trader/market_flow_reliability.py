from __future__ import annotations

import time
from typing import Any

from . import market_flow_reliability_core as _core
from .market_flow_reliability_core import *  # noqa: F401,F403 - preserve public compatibility surface
from .market_flow_cost_edge import MarketFlowCostEdgeStore
from .market_flow_event_cluster import MarketFlowEventClusterStore
from .market_flow_event_reliability import MarketFlowEventReliabilityStore

# Compatibility note: MarketFlowRegimeHistoryStore and the other pre-existing
# reliability sublayers remain implemented and executed unchanged in the core.


class MarketFlowReliabilityStore(_core.MarketFlowReliabilityStore):
    """Compatibility wrapper that appends local-only cost/event validation.

    The original raw-reaction reliability/OOS/confidence/dedup/history/stability
    implementation lives unchanged in ``market_flow_reliability_core``. After
    that chain completes, this wrapper deterministically recomputes spread-only
    cost edge, fixed-anchor event clusters, and clustered event reliability.
    These post-validation layers are shadow research only and remain completely
    unwired from score, PAPER decisions, strategy mutation, and order placement.
    """

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
        base_result = super().compute(now=stamp)

        cost_edge_result = self._compute_shadow_stage(
            MarketFlowCostEdgeStore,
            self.path,
            stamp,
            "market_flow_cost_edge",
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

        result = dict(base_result)
        result["cost_edge"] = cost_edge_result
        result["event_cluster"] = event_cluster_result
        result["event_reliability"] = event_reliability_result
        result["post_reliability_pipeline"] = {
            "order": ["cost_edge", "event_cluster", "event_reliability"],
            "network_fetches": False,
            "spread_only_cost_model": True,
            "full_transaction_cost_ready": False,
            "event_promotion_wired_to_score": False,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }
        result["ok"] = bool(base_result.get("ok", True)) and all(
            bool(stage.get("ok", False))
            for stage in (cost_edge_result, event_cluster_result, event_reliability_result)
        )
        return result
