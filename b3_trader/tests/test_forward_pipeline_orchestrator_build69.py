from __future__ import annotations

from pathlib import Path

from b3_trader.forward_pipeline_orchestrator import ForwardPipelineOrchestrator


class FakeIntake:
    def __init__(self, *, plan_payload, run_payload) -> None:
        self.plan_payload = plan_payload
        self.run_payload = run_payload

    def plan(self):
        return self.plan_payload

    def run_once(self):
        return self.run_payload


class FakeEnrichment:
    def __init__(self, *, plan_payload, run_payload) -> None:
        self.plan_payload = plan_payload
        self.run_payload = run_payload
        self.run_calls = 0

    def plan(self):
        return self.plan_payload

    def run_once(self):
        self.run_calls += 1
        return self.run_payload


def _intake_factory(plan_payload, run_payload):
    def factory(**kwargs):
        del kwargs
        return FakeIntake(plan_payload=plan_payload, run_payload=run_payload)
    return factory


def _enrichment_factory(holder, plan_payload, run_payload):
    def factory(**kwargs):
        del kwargs
        obj = FakeEnrichment(plan_payload=plan_payload, run_payload=run_payload)
        holder.append(obj)
        return obj
    return factory


def _score(**overrides):
    payload = {
        "ok": True,
        "status": "forward_waiting_no_eligible_cases",
        "forward_eligible_case_count": 0,
        "case_score_count": 0,
        "all_forward_eligible_cases_scored": True,
        "historical_rows_scored_as_v2": False,
        "distribution": {"count": 0},
        "confidence_distribution": {"count": 0},
        "case_scores": [],
    }
    payload.update(overrides)
    return payload


def test_no_new_notice_skips_enrichment_run(tmp_path: Path):
    holders = []
    intake_payload = {
        "ok": True,
        "status": "intake_complete",
        "network_fetches": True,
        "unique_forward_notices": 0,
        "market_notices_inserted": 0,
        "seed": {"seeded_new_cases": 0},
        "forward_counts_after": {"total_forward_intake_cases": 0},
        "source_results": {},
    }
    enrichment_plan = {
        "ok": True,
        "status": "planned",
        "candidate_count": 0,
        "preview": [],
        "review": {"run_allowed": False},
    }
    orchestrator = ForwardPipelineOrchestrator(
        tmp_path / "db.sqlite3",
        intake_factory=_intake_factory({}, intake_payload),
        enrichment_factory=_enrichment_factory(
            holders,
            enrichment_plan,
            {"ok": True, "status": "enriched", "processed": 1, "usable_gain": 1},
        ),
        score_audit_fn=lambda path: _score(),
    )
    result = orchestrator.run_once()
    assert result["ok"] is True
    assert result["status"] == "waiting_no_forward_cases"
    assert result["summary"]["processed_forward_cases"] == 0
    assert holders[0].run_calls == 0
    assert result["steps"]["build68_enrichment_run"] is None


def test_candidate_runs_one_enrichment_then_score_audit(tmp_path: Path):
    holders = []
    intake_payload = {
        "ok": True,
        "status": "intake_complete",
        "network_fetches": True,
        "unique_forward_notices": 1,
        "market_notices_inserted": 1,
        "seed": {"seeded_new_cases": 1},
        "forward_counts_after": {"total_forward_intake_cases": 1},
        "source_results": {},
    }
    enrichment_plan = {
        "ok": True,
        "status": "planned",
        "candidate_count": 1,
        "preview": [{"case_key": "upbit|KRW-NEW|notice:1"}],
        "review": {"run_allowed": True},
    }
    enrichment_run = {
        "ok": True,
        "status": "enriched",
        "network_fetches": True,
        "database_mutation": True,
        "processed": 1,
        "usable_gain": 1,
        "results": [{"case_key": "upbit|KRW-NEW|notice:1", "status": "usable"}],
    }
    audit_calls = []
    orchestrator = ForwardPipelineOrchestrator(
        tmp_path / "db.sqlite3",
        intake_factory=_intake_factory({}, intake_payload),
        enrichment_factory=_enrichment_factory(holders, enrichment_plan, enrichment_run),
        score_audit_fn=lambda path: audit_calls.append(path) or _score(
            status="scored_forward_only",
            forward_eligible_case_count=1,
            case_score_count=1,
            case_scores=[{"case_key": "upbit|KRW-NEW|notice:1", "shadow_score": 63.0, "confidence": 1.0}],
        ),
    )
    result = orchestrator.run_once()
    assert result["ok"] is True
    assert result["status"] == "processed_forward_case"
    assert result["summary"]["processed_forward_cases"] == 1
    assert result["summary"]["usable_gain"] == 1
    assert result["summary"]["case_score_count"] == 1
    assert holders[0].run_calls == 1
    assert len(audit_calls) == 1


def test_partial_intake_fails_closed_before_enrichment(tmp_path: Path):
    holders = []
    intake_payload = {
        "ok": False,
        "status": "intake_partial",
        "network_fetches": True,
        "unique_forward_notices": 0,
        "market_notices_inserted": 0,
        "seed": {"seeded_new_cases": 0},
        "source_results": {"upbit": {"errors": ["boom"]}},
    }
    audit_calls = []
    orchestrator = ForwardPipelineOrchestrator(
        tmp_path / "db.sqlite3",
        intake_factory=_intake_factory({}, intake_payload),
        enrichment_factory=_enrichment_factory(
            holders,
            {"ok": True, "status": "planned", "candidate_count": 1, "review": {"run_allowed": True}},
            {"ok": True, "status": "enriched", "processed": 1},
        ),
        score_audit_fn=lambda path: audit_calls.append(path) or _score(),
    )
    result = orchestrator.run_once()
    assert result["ok"] is False
    assert result["status"] == "intake_partial_stop"
    assert holders == []
    assert audit_calls == []


def test_plan_is_read_only(tmp_path: Path):
    holders = []
    orchestrator = ForwardPipelineOrchestrator(
        tmp_path / "db.sqlite3",
        intake_factory=_intake_factory(
            {
                "ok": True,
                "status": "planned",
                "network_fetches": False,
                "unique_forward_notices": 0,
                "market_notices_inserted": 0,
                "seed": {},
                "source_results": {},
            },
            {},
        ),
        enrichment_factory=_enrichment_factory(
            holders,
            {"ok": True, "status": "planned", "candidate_count": 0, "preview": [], "review": {"run_allowed": False}},
            {},
        ),
        score_audit_fn=lambda path: _score(),
    )
    result = orchestrator.plan()
    assert result["status"] == "planned"
    assert result["read_only_plan"] is True
    assert result["network_fetches"] is False
    assert result["database_mutation"] is False
    assert holders[0].run_calls == 0
