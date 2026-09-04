from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from .auto_demo_v2 import DB_PATH
from .intelligence_bea_actual import BeaActualCaptureService
from .intelligence_bea_schedule import BeaReleaseScheduleSource
from .intelligence_bls_actual import BlsActualCaptureService
from .intelligence_bls_calendar_resilient import ResilientBlsReleaseCalendarSource
from .intelligence_event import IntelligenceEvent
from .intelligence_event_store import IntelligenceEventStore
from .intelligence_fomc_calendar import FomcMeetingCalendarSource
from .intelligence_official_news import CFTC_FEED, SEC_FEED, OfficialPressReleaseRssSource
from .intelligence_trading_economics_consensus import TradingEconomicsConsensusCaptureService

SourceFetcher = Callable[[float], list[IntelligenceEvent]]
DEFAULT_SOURCE_ORDER = (
    "us_bls_release_calendar",
    "us_bea_release_schedule",
    "us_fed_fomc_calendar",
    "us_sec_press_releases",
    "us_cftc_press_releases",
)


def default_intelligence_fetchers() -> dict[str, SourceFetcher]:
    bls = ResilientBlsReleaseCalendarSource()
    bea = BeaReleaseScheduleSource()
    fomc = FomcMeetingCalendarSource()
    sec = OfficialPressReleaseRssSource(SEC_FEED)
    cftc = OfficialPressReleaseRssSource(CFTC_FEED)

    def fetch_fomc(now: float) -> list[IntelligenceEvent]:
        year = datetime.fromtimestamp(now, tz=timezone.utc).year
        return fomc.fetch(min_year=year - 1, max_year=year + 2, received_at=now)

    return {
        "us_bls_release_calendar": lambda now: bls.fetch(now=now),
        "us_bea_release_schedule": lambda now: bea.fetch(now=now),
        "us_fed_fomc_calendar": fetch_fomc,
        "us_sec_press_releases": lambda now: sec.fetch(received_at=now),
        "us_cftc_press_releases": lambda now: cftc.fetch(received_at=now),
    }


class IntelligenceIngestCycle:
    """Bounded Phase 5 macro/news ingest coordinator.

    Networking is opt-in per run. The cycle persists normalized evidence only and
    has no score, PAPER, position-sizing or live-order authority. BLS and BEA
    official calendars feed bounded initial-actual capture, while the reviewed
    Trading Economics adapter may capture one complete pre-release consensus
    snapshot when its subscription API key is configured. Missing credentials
    fail closed without breaking official-source ingest.
    """

    def __init__(
        self,
        path: Path = DB_PATH,
        *,
        fetchers: dict[str, SourceFetcher] | None = None,
        conn: sqlite3.Connection | None = None,
        bls_actual_capture: BlsActualCaptureService | None = None,
        bea_actual_capture: BeaActualCaptureService | None = None,
        consensus_capture: TradingEconomicsConsensusCaptureService | None = None,
    ) -> None:
        self.path = Path(path)
        self.fetchers = dict(fetchers or default_intelligence_fetchers())
        self.conn = conn or sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.store = IntelligenceEventStore(self.conn)
        self.bls_actual_capture = bls_actual_capture or BlsActualCaptureService(self.conn)
        self.bea_actual_capture = bea_actual_capture or BeaActualCaptureService(self.conn)
        self.consensus_capture = consensus_capture or TradingEconomicsConsensusCaptureService(self.conn)
        self._owns_conn = conn is None

    def close(self) -> None:
        if self._owns_conn:
            self.conn.close()

    def run_once(
        self,
        *,
        network_enabled: bool = False,
        source_ids: Iterable[str] | None = None,
        now: float | None = None,
    ) -> dict[str, object]:
        current = float(now if now is not None else time.time())
        requested = tuple(
            dict.fromkeys(
                str(source_id or "").strip().lower()
                for source_id in (source_ids if source_ids is not None else DEFAULT_SOURCE_ORDER)
                if str(source_id or "").strip()
            )
        )
        result: dict[str, object] = {
            "paper_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_enabled": bool(network_enabled),
            "requested_sources": list(requested),
            "source_results": {},
            "events_received": 0,
            "events_inserted": 0,
            "events_updated": 0,
            "source_failures": 0,
            "macro_actual_capture": {"status": "not_requested"},
            "bea_actual_capture": {"status": "not_requested"},
            "consensus_capture": {"status": "not_requested"},
        }
        if not network_enabled:
            result["status"] = "network_disabled"
            return result

        source_results: dict[str, object] = {}
        for source_id in requested:
            fetcher = self.fetchers.get(source_id)
            if fetcher is None:
                source_results[source_id] = {
                    "status": "unsupported_source",
                    "events": 0,
                    "inserted": 0,
                    "updated": 0,
                }
                result["source_failures"] = int(result["source_failures"]) + 1
                continue
            try:
                events = list(fetcher(current))
                ingest = self.store.ingest(events, seen_at=current)
            except Exception as exc:
                source_results[source_id] = {
                    "status": "source_error",
                    "events": 0,
                    "inserted": 0,
                    "updated": 0,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }
                result["source_failures"] = int(result["source_failures"]) + 1
                continue
            source_results[source_id] = {
                "status": "ok",
                "events": int(ingest["received"]),
                "inserted": int(ingest["inserted"]),
                "updated": int(ingest["updated"]),
            }
            result["events_received"] = int(result["events_received"]) + int(ingest["received"])
            result["events_inserted"] = int(result["events_inserted"]) + int(ingest["inserted"])
            result["events_updated"] = int(result["events_updated"]) + int(ingest["updated"])

        result["source_results"] = source_results
        if "us_bls_release_calendar" in requested:
            try:
                capture = self.bls_actual_capture.run_once(now=current, network_enabled=True)
            except Exception as exc:
                capture = {
                    "status": "capture_error",
                    "paper_only": True,
                    "can_place_orders": False,
                    "score_mutation": False,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }
                result["source_failures"] = int(result["source_failures"]) + 1
            else:
                if str(capture.get("status") or "") == "partial":
                    result["source_failures"] = int(result["source_failures"]) + 1
            result["macro_actual_capture"] = capture

        if "us_bea_release_schedule" in requested:
            try:
                bea_capture = self.bea_actual_capture.run_once(now=current, network_enabled=True)
            except Exception as exc:
                bea_capture = {
                    "status": "capture_error",
                    "paper_only": True,
                    "can_place_orders": False,
                    "score_mutation": False,
                    "credential_exposed": False,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }
                result["source_failures"] = int(result["source_failures"]) + 1
            else:
                if str(bea_capture.get("status") or "") == "partial":
                    result["source_failures"] = int(result["source_failures"]) + 1
            result["bea_actual_capture"] = bea_capture

        if {"us_bls_release_calendar", "us_bea_release_schedule"}.intersection(requested):
            try:
                consensus = self.consensus_capture.run_once(now=current, network_enabled=True)
            except Exception as exc:
                consensus = {
                    "status": "capture_error",
                    "paper_only": True,
                    "can_place_orders": False,
                    "score_mutation": False,
                    "credential_exposed": False,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }
                result["source_failures"] = int(result["source_failures"]) + 1
            else:
                if str(consensus.get("status") or "") == "partial":
                    result["source_failures"] = int(result["source_failures"]) + 1
            result["consensus_capture"] = consensus

        result["status"] = "ok" if int(result["source_failures"]) == 0 else "partial"
        return result
