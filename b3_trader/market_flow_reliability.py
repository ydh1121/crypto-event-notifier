from __future__ import annotations

import time
from typing import Any

from . import market_flow_reliability_core as _core
from .market_flow_reliability_core import *  # noqa: F401,F403 - preserve public compatibility surface
from .market_flow_absorption_consensus_v2 import MarketFlowAbsorptionConsensusV2Store
from .market_flow_absorption_consensus_v2_forward import MarketFlowAbsorptionConsensusV2ForwardStore
from .market_flow_absorption_consensus_v2_oos_comparator import (
    MarketFlowAbsorptionConsensusV2OosComparatorStore,
)
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
    """Compatibility wrapper that appends local-only forward validation layers.

    Before reliability aggregation, a bounded local-only due-reaction drain
    revisits already registered waiting rows whose horizons have matured after
    their source signal aged out of the newest-signal scan. A separate v2
    absorption-consensus layer records only post-activation exact 5m
    Bithumb+Upbit agreement over the frozen v1 heuristic.

    A second independent v2-forward activation then prevents already observed
    consensus rows from becoming performance samples. Eligible future consensus
    is evaluated from the strictly next 5m boundary with exact forward OHLCV,
    versioned fees and prior-only top-5 ladder execution at 750,000 KRW. It is
    stored only in v2-specific tables and remains completely separate from v1
    reaction/reliability tables.

    After v1 750K notional sensitivity has refreshed, a third independent
    comparator activation preregisters the calendar window used to compare v1
    and v2. Pre-comparator outcomes are retained as context only. The comparator
    uses cross-exchange 750K full-cost events, reports descriptive deltas, and
    never selects a winner.

    The original raw-reaction reliability/OOS/confidence/dedup/history/stability
    implementation lives unchanged in ``market_flow_reliability_core``. All
    appended validation layers remain shadow research only and completely
    unwired from score, PAPER decisions, strategy mutation, and order placement.
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
    def _compute_absorption_consensus_v2_stage(path, stamp: float) -> dict[str, Any]:
        store = MarketFlowAbsorptionConsensusV2Store(path)
        try:
            result = store.compute(now=stamp)
        finally:
            store.close()
        if not bool(result.get("ok", False)):
            raise RuntimeError(
                "market_flow_absorption_consensus_v2 failed: "
                f"{result.get('status') or 'unknown_status'}"
            )
        return result

    @staticmethod
    def _compute_absorption_consensus_v2_forward_stage(path, stamp: float) -> dict[str, Any]:
        store = MarketFlowAbsorptionConsensusV2ForwardStore(path)
        try:
            result = store.compute(now=stamp)
        finally:
            store.close()
        if not bool(result.get("ok", False)):
            raise RuntimeError(
                "market_flow_absorption_consensus_v2_forward failed: "
                f"{result.get('status') or 'unknown_status'}"
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
        stamp = float(time.time() if now is None else now)

        reaction_due_result = self._compute_reaction_due_stage(self.path, stamp)
        absorption_consensus_v2_result = self._compute_absorption_consensus_v2_stage(
            self.path, stamp
        )
        absorption_consensus_v2_forward_result = self._compute_absorption_consensus_v2_forward_stage(
            self.path, stamp
        )
        base_result = super().compute(now=stamp)

        cost_edge_result = self._compute_shadow_stage(
            MarketFlowCostEdgeStore, self.path, stamp, "market_flow_cost_edge"
        )
        full_cost_result = self._compute_shadow_stage(
            MarketFlowFullCostEdgeStore, self.path, stamp, "market_flow_full_cost_edge"
        )
        full_cost_notional_sensitivity_result = self._compute_shadow_stage(
            MarketFlowFullCostNotionalSensitivityStore,
            self.path,
            stamp,
            "market_flow_full_cost_notional_sensitivity",
        )
        event_cluster_result = self._compute_shadow_stage(
            MarketFlowEventClusterStore, self.path, stamp, "market_flow_event_cluster"
        )
        event_reliability_result = self._compute_shadow_stage(
            MarketFlowEventReliabilityStore, self.path, stamp, "market_flow_event_reliability"
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
        absorption_consensus_v2_oos_comparator_result = self._compute_shadow_stage(
            MarketFlowAbsorptionConsensusV2OosComparatorStore,
            self.path,
            stamp,
            "market_flow_absorption_consensus_v2_oos_comparator",
        )

        result = dict(base_result)
        result["reaction_due"] = reaction_due_result
        result["absorption_consensus_v2"] = absorption_consensus_v2_result
        result["absorption_consensus_v2_forward"] = absorption_consensus_v2_forward_result
        result["cost_edge"] = cost_edge_result
        result["full_cost_edge"] = full_cost_result
        result["full_cost_notional_sensitivity"] = full_cost_notional_sensitivity_result
        result["event_cluster"] = event_cluster_result
        result["event_reliability"] = event_reliability_result
        result["full_cost_event_cluster"] = full_cost_event_cluster_result
        result["full_cost_event_reliability"] = full_cost_event_reliability_result
        result["absorption_consensus_v2_oos_comparator"] = absorption_consensus_v2_oos_comparator_result
        result["pre_reliability_pipeline"] = {
            "order": [
                "reaction_due",
                "absorption_consensus_v2",
                "absorption_consensus_v2_forward",
            ],
            "network_fetches": False,
            "forward_only_due_reaction_drain": True,
            "newest_signal_scan_preserved": True,
            "forward_only_absorption_consensus_v2": True,
            "absorption_consensus_v2_historical_backfill": False,
            "absorption_consensus_v2_v1_threshold_retuning": False,
            "absorption_consensus_v2_forward_historical_backfill": False,
            "absorption_consensus_v2_forward_entry_policy":
                "strict_next_5m_boundary_after_consensus_recorded",
            "absorption_consensus_v2_forward_reference_notional_krw": 750000.0,
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
                "market_flow_absorption_consensus_v2_oos_comparator",
            ],
            "network_fetches": False,
            "spread_only_event_pipeline": True,
            "forward_only_full_transaction_cost_observation": True,
            "paper_notional_sensitivity_observation": True,
            "full_cost_event_validation_pipeline": True,
            "v1_v2_oos_comparator_separate_activation": True,
            "v1_v2_oos_comparator_reference_notional_krw": 750000.0,
            "v1_v2_oos_comparator_historical_backfill": False,
            "v1_v2_oos_comparator_winner_selection": False,
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
                absorption_consensus_v2_result,
                absorption_consensus_v2_forward_result,
                cost_edge_result,
                full_cost_result,
                full_cost_notional_sensitivity_result,
                event_cluster_result,
                event_reliability_result,
                full_cost_event_cluster_result,
                full_cost_event_reliability_result,
                absorption_consensus_v2_oos_comparator_result,
            )
        )
        return result
