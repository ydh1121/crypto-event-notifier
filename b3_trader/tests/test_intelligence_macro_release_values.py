from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_event_store import IntelligenceEventStore
from b3_trader.intelligence_macro_release_values import (
    MacroReleaseValueStore,
    normalize_macro_release_value,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _macro_event(store: IntelligenceEventStore, *, event_id: str = "cpi-2026-08", scheduled_at: float = 1000.0) -> str:
    event = normalize_intelligence_event(
        source_id="us_bls_release_calendar",
        source_family="macro_calendar",
        event_type="US_CPI",
        title="Consumer Price Index August 2026",
        source_url="https://www.bls.gov/schedule/news_release/cpi.htm",
        external_id=event_id,
        scheduled_at=scheduled_at,
        received_at=900,
    )
    store.ingest([event], seen_at=900)
    return event.event_id


def _value(
    *,
    event_id: str,
    role: str,
    value: float,
    known_at: float,
    provider: str,
    unit: str = "percent",
    period: str = "2026-08",
    revision_no: int = 0,
    revision_label: str = "initial",
):
    return normalize_macro_release_value(
        event_id=event_id,
        event_type="US_CPI",
        metric_id="CPI_YOY",
        value_role=role,
        numeric_value=value,
        unit=unit,
        reference_period=period,
        provider_id=provider,
        provider_url=f"https://{provider}.example.com/data",
        authority="fixture authority",
        data_rights="research-use fixture",
        known_at=known_at,
        received_at=known_at + 1,
        revision_no=revision_no,
        revision_label=revision_label,
        attributes={"fixture": True},
    )


def test_compute_surprise_uses_only_pre_release_consensus_and_initial_actual() -> None:
    conn = _conn()
    event_id = _macro_event(IntelligenceEventStore(conn), scheduled_at=1000)
    store = MacroReleaseValueStore(conn)
    store.ingest(
        [
            _value(event_id=event_id, role="consensus", value=2.8, known_at=900, provider="consensus_a"),
            _value(event_id=event_id, role="consensus", value=2.9, known_at=990, provider="consensus_a"),
            _value(event_id=event_id, role="actual", value=3.1, known_at=1005, provider="bls_official"),
            _value(
                event_id=event_id,
                role="actual",
                value=3.0,
                known_at=2000,
                provider="bls_official",
                revision_no=1,
                revision_label="revised",
            ),
        ],
        seen_at=2100,
    )
    result = store.compute_surprise(
        event_id=event_id,
        metric_id="CPI_YOY",
        consensus_provider_id="consensus_a",
        actual_provider_id="bls_official",
    )
    assert result is not None
    assert result["anchor_kind"] == "scheduled_at"
    assert result["anchor_at"] == 1000
    assert result["consensus_value"] == pytest.approx(2.9)
    assert result["consensus_known_at"] == 990
    assert result["actual_value"] == pytest.approx(3.1)
    assert result["actual_revision_no"] == 0
    assert result["absolute_surprise"] == pytest.approx(0.2)
    assert result["relative_surprise_pct"] == pytest.approx(0.2 / 2.9 * 100.0)
    assert result["z_surprise"] is None
    assert result["score_contribution"] is None
    assert result["confidence"] is None
    assert result["confidence_status"] == "not_promoted"
    assert result["lookahead_safe"] is True


def test_consensus_at_or_after_release_boundary_is_rejected() -> None:
    conn = _conn()
    event_id = _macro_event(IntelligenceEventStore(conn), scheduled_at=1000)
    store = MacroReleaseValueStore(conn)
    store.ingest(
        [
            _value(event_id=event_id, role="consensus", value=2.9, known_at=1000, provider="consensus_a"),
            _value(event_id=event_id, role="actual", value=3.1, known_at=1001, provider="bls_official"),
        ],
        seen_at=1100,
    )
    assert store.compute_surprise(
        event_id=event_id,
        metric_id="CPI_YOY",
        consensus_provider_id="consensus_a",
        actual_provider_id="bls_official",
    ) is None


def test_actual_before_release_boundary_is_rejected() -> None:
    conn = _conn()
    event_id = _macro_event(IntelligenceEventStore(conn), scheduled_at=1000)
    store = MacroReleaseValueStore(conn)
    store.ingest(
        [
            _value(event_id=event_id, role="consensus", value=2.9, known_at=990, provider="consensus_a"),
            _value(event_id=event_id, role="actual", value=3.1, known_at=999, provider="bls_official"),
        ],
        seen_at=1100,
    )
    assert store.compute_surprise(
        event_id=event_id,
        metric_id="CPI_YOY",
        consensus_provider_id="consensus_a",
        actual_provider_id="bls_official",
    ) is None


def test_unit_or_reference_period_mismatch_fails_closed() -> None:
    conn = _conn()
    event_id = _macro_event(IntelligenceEventStore(conn), scheduled_at=1000)
    store = MacroReleaseValueStore(conn)
    store.ingest(
        [
            _value(event_id=event_id, role="consensus", value=2.9, known_at=990, provider="consensus_unit"),
            _value(event_id=event_id, role="actual", value=3.1, known_at=1001, provider="actual_unit", unit="index"),
            _value(event_id=event_id, role="consensus", value=2.9, known_at=990, provider="consensus_period"),
            _value(event_id=event_id, role="actual", value=3.1, known_at=1001, provider="actual_period", period="2026-07"),
        ],
        seen_at=1100,
    )
    assert store.compute_surprise(
        event_id=event_id,
        metric_id="CPI_YOY",
        consensus_provider_id="consensus_unit",
        actual_provider_id="actual_unit",
    ) is None
    assert store.compute_surprise(
        event_id=event_id,
        metric_id="CPI_YOY",
        consensus_provider_id="consensus_period",
        actual_provider_id="actual_period",
    ) is None


def test_revisions_are_preserved_as_separate_rows_and_can_be_audited() -> None:
    conn = _conn()
    event_id = _macro_event(IntelligenceEventStore(conn), scheduled_at=1000)
    store = MacroReleaseValueStore(conn)
    initial = _value(event_id=event_id, role="actual", value=3.1, known_at=1005, provider="bls_official")
    revised = _value(
        event_id=event_id,
        role="actual",
        value=3.0,
        known_at=2000,
        provider="bls_official",
        revision_no=1,
        revision_label="revised",
    )
    assert store.ingest([initial, revised], seen_at=2100) == {"received": 2, "inserted": 2, "updated": 0}
    rows = store.history(event_id=event_id, metric_id="CPI_YOY")
    assert [(row["revision_no"], row["numeric_value"]) for row in rows] == [(0, 3.1), (1, 3.0)]


def test_zero_consensus_keeps_absolute_surprise_but_relative_is_none() -> None:
    conn = _conn()
    event_id = _macro_event(IntelligenceEventStore(conn), scheduled_at=1000)
    store = MacroReleaseValueStore(conn)
    store.ingest(
        [
            _value(event_id=event_id, role="consensus", value=0.0, known_at=990, provider="consensus_a"),
            _value(event_id=event_id, role="actual", value=0.2, known_at=1001, provider="bls_official"),
        ],
        seen_at=1100,
    )
    result = store.compute_surprise(
        event_id=event_id,
        metric_id="CPI_YOY",
        consensus_provider_id="consensus_a",
        actual_provider_id="bls_official",
    )
    assert result is not None
    assert result["absolute_surprise"] == pytest.approx(0.2)
    assert result["relative_surprise_pct"] is None


def test_macro_value_layer_has_no_score_paper_decision_or_order_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_macro_release_values.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
