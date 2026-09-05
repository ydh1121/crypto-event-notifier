from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .dex_shadow_score_v2_forward import audit_dex_shadow_score_v2_forward
from .dex_shadow_score_v2_preregistration import FORWARD_CUTOFF_TS, FORWARD_CUTOFF_UTC
from .forward_sample_enrichment import ForwardSampleEnrichment
from .forward_sample_intake import DEFAULT_PAGES_PER_EXCHANGE, ForwardSampleIntake


BUILD69_VERSION = 1
BUILD69_NAME = "dex_forward_pipeline_orchestrator_v1"

IntakeFactory = Callable[..., ForwardSampleIntake]
EnrichmentFactory = Callable[..., ForwardSampleEnrichment]
ScoreAuditFn = Callable[[Path | str], dict[str, Any]]


class ForwardPipelineOrchestrator:
    """Bounded forward-only orchestration for Build67 -> Build68 -> Build66.

    Build69 owns no identity, listing-history, DEX, scoring, strategy, position,
    Cloudflare, or order implementation. It invokes the already-bounded forward
    owners exactly once each. A partial official-notice intake fails closed before
    enrichment. There is no loop over cases: Build68 remains hard-bounded to one
    selected post-cutoff case per invocation.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        pages_per_exchange: int = DEFAULT_PAGES_PER_EXCHANGE,
        intake_factory: IntakeFactory = ForwardSampleIntake,
        enrichment_factory: EnrichmentFactory = ForwardSampleEnrichment,
        score_audit_fn: ScoreAuditFn = audit_dex_shadow_score_v2_forward,
    ) -> None:
        self.path = Path(path)
        self.pages_per_exchange = int(pages_per_exchange)
        self.intake_factory = intake_factory
        self.enrichment_factory = enrichment_factory
        self.score_audit_fn = score_audit_fn

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": True,
            "build69_version": BUILD69_VERSION,
            "build69_name": BUILD69_NAME,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "paper_ab_wired": False,
            "live_promotion_allowed": False,
            "forward_only": True,
            "forward_boundary": {
                "cutoff_utc": FORWARD_CUTOFF_UTC,
                "cutoff_unix": FORWARD_CUTOFF_TS,
                "pre_cutoff_cases_selectable": False,
            },
            "bounds": {
                "intake_runs_per_invocation": 1,
                "enrichment_runs_per_invocation": 1,
                "score_audits_per_invocation": 1,
                "max_enrichment_cases_per_invocation": 1,
            },
            "isolation": {
                "build47_historical_cursor_read": False,
                "build47_historical_cursor_mutation": False,
                "generic_listing_history_supervisor_enabled": False,
                "generic_dex_launch_supervisor_enabled": False,
            },
            "safety": {
                "strategy_signal_mutation": False,
                "position_sizing_mutation": False,
                "order_path_mutation": False,
                "cloudflare_publishing": False,
                "training_or_fitting": False,
                "trade_threshold": None,
            },
        }

    @staticmethod
    def _intake_summary(payload: dict[str, Any]) -> dict[str, Any]:
        source_results = payload.get("source_results") if isinstance(payload.get("source_results"), dict) else {}
        return {
            "ok": bool(payload.get("ok")),
            "status": str(payload.get("status") or ""),
            "network_fetches": bool(payload.get("network_fetches")),
            "unique_forward_notices": int(payload.get("unique_forward_notices") or 0),
            "market_notices_inserted": int(payload.get("market_notices_inserted") or 0),
            "seeded_new_cases": int((payload.get("seed") or {}).get("seeded_new_cases") or 0),
            "forward_counts_after": payload.get("forward_counts_after") or {},
            "source_results": source_results,
        }

    @staticmethod
    def _enrichment_plan_summary(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": bool(payload.get("ok")),
            "status": str(payload.get("status") or ""),
            "candidate_count": int(payload.get("candidate_count") or 0),
            "preview": payload.get("preview") or [],
            "run_allowed": bool((payload.get("review") or {}).get("run_allowed")),
        }

    @staticmethod
    def _enrichment_run_summary(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": bool(payload.get("ok")),
            "status": str(payload.get("status") or ""),
            "network_fetches": bool(payload.get("network_fetches")),
            "database_mutation": bool(payload.get("database_mutation")),
            "processed": int(payload.get("processed") or 0),
            "usable_gain": int(payload.get("usable_gain") or 0),
            "results": payload.get("results") or [],
        }

    @staticmethod
    def _score_summary(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": bool(payload.get("ok")),
            "status": str(payload.get("status") or ""),
            "forward_eligible_case_count": int(payload.get("forward_eligible_case_count") or 0),
            "case_score_count": int(payload.get("case_score_count") or 0),
            "all_forward_eligible_cases_scored": bool(payload.get("all_forward_eligible_cases_scored")),
            "historical_rows_scored_as_v2": bool(payload.get("historical_rows_scored_as_v2")),
            "distribution": payload.get("distribution") or {},
            "confidence_distribution": payload.get("confidence_distribution") or {},
            "preview": [
                {
                    "case_key": str(row.get("case_key") or ""),
                    "shadow_score": row.get("shadow_score"),
                    "confidence": row.get("confidence"),
                }
                for row in (payload.get("case_scores") or [])[:5]
                if isinstance(row, dict)
            ],
        }

    def plan(self) -> dict[str, Any]:
        intake = self.intake_factory(path=self.path, pages_per_exchange=self.pages_per_exchange)
        enrichment = self.enrichment_factory(path=self.path)
        intake_plan = intake.plan()
        enrichment_plan = enrichment.plan()
        score = self.score_audit_fn(self.path)
        candidate_count = int(enrichment_plan.get("candidate_count") or 0)
        return {
            **self._base(),
            "status": "planned",
            "read_only_plan": True,
            "network_fetches": False,
            "database_mutation": False,
            "steps": {
                "build67_intake": self._intake_summary(intake_plan),
                "build68_enrichment_plan": self._enrichment_plan_summary(enrichment_plan),
                "build68_enrichment_run": None,
                "build66_score_audit": self._score_summary(score),
            },
            "review": {
                "run_allowed": True,
                "current_candidate_count": candidate_count,
                "next_action": "run_build69_forward_pipeline_once",
            },
        }

    def run_once(self) -> dict[str, Any]:
        started = time.time()
        intake = self.intake_factory(path=self.path, pages_per_exchange=self.pages_per_exchange)
        intake_result = intake.run_once()
        intake_summary = self._intake_summary(intake_result)

        if not intake_result.get("ok") or intake_result.get("status") != "intake_complete":
            return {
                **self._base(),
                "ok": False,
                "status": "intake_partial_stop",
                "network_fetches": bool(intake_result.get("network_fetches")),
                "database_mutation": bool(
                    int(intake_result.get("market_notices_inserted") or 0)
                    or int((intake_result.get("seed") or {}).get("seeded_new_cases") or 0)
                ),
                "steps": {
                    "build67_intake": intake_summary,
                    "build68_enrichment_plan": None,
                    "build68_enrichment_run": None,
                    "build66_score_audit": None,
                },
                "elapsed_seconds": round(time.time() - started, 3),
                "review": {
                    "next_action": "repair_official_notice_intake_before_forward_enrichment",
                },
            }

        enrichment = self.enrichment_factory(path=self.path)
        enrichment_plan = enrichment.plan()
        enrichment_plan_summary = self._enrichment_plan_summary(enrichment_plan)
        candidate_count = int(enrichment_plan.get("candidate_count") or 0)

        enrichment_result: dict[str, Any] | None = None
        if candidate_count > 0 and bool((enrichment_plan.get("review") or {}).get("run_allowed")):
            enrichment_result = enrichment.run_once()

        score_result = self.score_audit_fn(self.path)
        score_summary = self._score_summary(score_result)
        enrichment_summary = (
            self._enrichment_run_summary(enrichment_result) if enrichment_result is not None else None
        )

        processed = int((enrichment_result or {}).get("processed") or 0)
        usable_gain = int((enrichment_result or {}).get("usable_gain") or 0)
        new_notice_count = int(intake_result.get("unique_forward_notices") or 0)
        if processed > 0:
            status = "processed_forward_case"
        elif candidate_count > 0:
            status = "candidate_not_processed"
        elif new_notice_count > 0:
            status = "intake_only_waiting_enrichment_candidate"
        else:
            status = "waiting_no_forward_cases"

        ok = bool(
            intake_result.get("ok")
            and enrichment_plan.get("ok")
            and (enrichment_result is None or enrichment_result.get("ok"))
            and score_result.get("ok")
            and not score_result.get("historical_rows_scored_as_v2")
        )
        return {
            **self._base(),
            "ok": ok,
            "status": status,
            "network_fetches": True,
            "database_mutation": bool(
                int(intake_result.get("market_notices_inserted") or 0)
                or int((intake_result.get("seed") or {}).get("seeded_new_cases") or 0)
                or bool((enrichment_result or {}).get("database_mutation"))
            ),
            "steps": {
                "build67_intake": intake_summary,
                "build68_enrichment_plan": enrichment_plan_summary,
                "build68_enrichment_run": enrichment_summary,
                "build66_score_audit": score_summary,
            },
            "summary": {
                "new_forward_notices": new_notice_count,
                "candidate_count": candidate_count,
                "processed_forward_cases": processed,
                "usable_gain": usable_gain,
                "forward_eligible_case_count": int(score_result.get("forward_eligible_case_count") or 0),
                "case_score_count": int(score_result.get("case_score_count") or 0),
            },
            "elapsed_seconds": round(time.time() - started, 3),
            "review": {
                "build70_sample_ledger_allowed": True,
                "paper_ab_wired": False,
                "live_promotion_allowed": False,
                "next_action": (
                    "build70_forward_sample_ledger_and_readiness"
                    if ok
                    else "repair_build69_forward_pipeline_contract"
                ),
            },
        }
