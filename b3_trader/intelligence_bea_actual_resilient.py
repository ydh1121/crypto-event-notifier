from __future__ import annotations

import re
import sqlite3
import time
from html.parser import HTMLParser
from typing import Any

from .http_retry import get_with_retry
from .intelligence_bea_actual import (
    BEA_AUTHORITY,
    BEA_PROVIDER_ID,
    DEFAULT_CAPTURE_WINDOW_SECONDS,
    DEFAULT_MAX_EVENTS,
    EXPECTED_METRIC_IDS,
    BeaActualCaptureService as ApiBeaActualCaptureService,
    BeaNipaClient,
    BeaReferencePeriod,
    parse_bea_reference_period,
)
from .intelligence_macro_release_values import (
    MacroReleaseValue,
    MacroReleaseValueStore,
    normalize_macro_release_value,
)

BEA_NEWS_PROVIDER_ID = "bea_official_news_release"
BEA_NEWS_DATA_RIGHTS = "official_us_government_public_release"
BEA_NEWS_SOURCE_FORMAT = "official_bea_news_release_html"
BEA_NEWS_URL_TEMPLATE = (
    "https://www.bea.gov/news/{year}/personal-income-and-outlays-{month_slug}-{year}"
)
BEA_NEWS_USER_AGENT = "crypto-event-notifier-phase5/1.0"
MAX_HTML_BYTES = 2_000_000


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._parts)).strip()


def _release_url(reference: BeaReferencePeriod) -> str:
    month_slug = __import__("calendar").month_name[reference.month].casefold()
    return BEA_NEWS_URL_TEMPLATE.format(
        year=reference.year,
        month_slug=month_slug,
    )


def _signed_percent(direction: str, value: str) -> float:
    number = float(value)
    normalized = str(direction or "").strip().casefold()
    if normalized == "increased":
        return number
    if normalized == "decreased":
        return -number
    raise ValueError(f"unsupported BEA change direction: {direction!r}")


def parse_bea_pce_news_release(
    html: str,
    *,
    event_id: str,
    reference: BeaReferencePeriod,
    known_at: float,
    source_url: str,
) -> list[MacroReleaseValue]:
    payload = str(html or "")
    if len(payload.encode("utf-8", errors="ignore")) > MAX_HTML_BYTES:
        raise ValueError("BEA news release payload exceeds bounded size")

    parser = _VisibleTextParser()
    parser.feed(payload)
    parser.close()
    text = parser.text

    month_name = __import__("calendar").month_name[reference.month]
    expected_title = f"Personal Income and Outlays, {month_name} {reference.year}"
    if expected_title.casefold() not in text.casefold():
        raise ValueError("BEA news release title/reference period mismatch")

    month_pattern = re.escape(month_name)
    mom_match = re.search(
        rf"From the preceding month,\s+the PCE price index for {month_pattern}\s+"
        r"(increased|decreased)\s+([0-9]+(?:\.[0-9]+)?)\s+percent\.\s+"
        r"Excluding food and energy,\s+the PCE price index(?:\s+also)?\s+"
        r"(increased|decreased)\s+([0-9]+(?:\.[0-9]+)?)\s+percent",
        text,
        flags=re.IGNORECASE,
    )
    yoy_match = re.search(
        rf"From the same month one year ago,\s+the PCE price index for {month_pattern}\s+"
        r"(increased|decreased)\s+([0-9]+(?:\.[0-9]+)?)\s+percent\.\s+"
        r"Excluding food and energy,\s+the PCE price index\s+"
        r"(increased|decreased)\s+([0-9]+(?:\.[0-9]+)?)\s+percent\s+from one year ago",
        text,
        flags=re.IGNORECASE,
    )
    if mom_match is None or yoy_match is None:
        raise ValueError("BEA PCE news release is missing complete headline/core MoM/YoY text")

    headline_mom = _signed_percent(mom_match.group(1), mom_match.group(2))
    core_mom = _signed_percent(mom_match.group(3), mom_match.group(4))
    headline_yoy = _signed_percent(yoy_match.group(1), yoy_match.group(2))
    core_yoy = _signed_percent(yoy_match.group(3), yoy_match.group(4))

    common = {
        "event_id": event_id,
        "event_type": "US_PCE",
        "value_role": "actual",
        "unit": "PERCENT",
        "reference_period": reference.label,
        "provider_id": BEA_NEWS_PROVIDER_ID,
        "provider_url": source_url,
        "authority": BEA_AUTHORITY,
        "data_rights": BEA_NEWS_DATA_RIGHTS,
        "known_at": known_at,
        "received_at": known_at,
        "revision_no": 0,
        "revision_label": "initial_news_release_capture",
    }

    def make(metric_id: str, numeric_value: float, sentence_role: str) -> MacroReleaseValue:
        return normalize_macro_release_value(
            **common,
            metric_id=metric_id,
            numeric_value=numeric_value,
            attributes={
                "source_format": BEA_NEWS_SOURCE_FORMAT,
                "sentence_role": sentence_role,
                "capture_policy": "first_complete_official_news_release_observation_within_release_window",
                "score_authority": False,
                "credential_exposed": False,
            },
        )

    return [
        make("US_PCE_PRICE_MOM_PCT", headline_mom, "headline_mom"),
        make("US_CORE_PCE_PRICE_MOM_PCT", core_mom, "core_mom"),
        make("US_PCE_PRICE_YOY_PCT", headline_yoy, "headline_yoy"),
        make("US_CORE_PCE_PRICE_YOY_PCT", core_yoy, "core_yoy"),
    ]


class ResilientBeaActualCaptureService(ApiBeaActualCaptureService):
    """Prefer the registered BEA API, with an official public release fallback.

    The fallback is used only when the registered API credential is unavailable or
    invalid. It captures the four PCE inflation actuals directly from the official
    BEA Personal Income and Outlays release inside the same bounded release window.
    No score/PAPER/order path is connected.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        client: BeaNipaClient | None = None,
        capture_window_seconds: float = DEFAULT_CAPTURE_WINDOW_SECONDS,
        max_events: int = DEFAULT_MAX_EVENTS,
    ) -> None:
        super().__init__(
            conn,
            client=client,
            capture_window_seconds=capture_window_seconds,
            max_events=max_events,
        )
        self.store = MacroReleaseValueStore(conn)

    def _existing_metrics(self, event_id: str) -> set[str]:
        rows = self.conn.execute(
            """SELECT metric_id FROM research_intelligence_macro_values
               WHERE event_id=? AND value_role='actual'
                 AND provider_id IN (?,?) AND revision_no=0""",
            (event_id, BEA_PROVIDER_ID, BEA_NEWS_PROVIDER_ID),
        ).fetchall()
        return {str(row["metric_id"]) for row in rows}

    def _fetch_news_release_values(self, row: sqlite3.Row, *, now: float) -> list[MacroReleaseValue]:
        reference = parse_bea_reference_period(str(row["title"] or ""))
        if reference is None:
            raise ValueError("cannot derive BEA PCE reference month from stored event title")
        url = _release_url(reference)
        response, _ = get_with_retry(
            url,
            headers={
                "User-Agent": BEA_NEWS_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
            },
            timeout=12,
            attempts=2,
        )
        return parse_bea_pce_news_release(
            str(response.text or ""),
            event_id=str(row["event_id"]),
            reference=reference,
            known_at=now,
            source_url=url,
        )

    def run_once(self, *, now: float | None = None, network_enabled: bool = False) -> dict[str, Any]:
        if self.client.credential_status == "ready":
            result = super().run_once(now=now, network_enabled=network_enabled)
            result["provider_mode"] = "registered_bea_api"
            return result

        current = float(now if now is not None else time.time())
        result: dict[str, Any] = {
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_enabled": bool(network_enabled),
            "credential_status": self.client.credential_status,
            "credential_exposed": False,
            "provider_mode": "official_bea_news_release_fallback",
            "events_considered": 0,
            "events_captured": 0,
            "actual_values_inserted": 0,
            "already_captured": 0,
            "missed_capture_window": 0,
            "partial_existing_fail_closed": 0,
            "capture_failures": 0,
            "network_requests": 0,
        }
        if not network_enabled:
            result["status"] = "network_disabled"
            return result

        expected = set(EXPECTED_METRIC_IDS)
        for row in self._due_events(current):
            result["events_considered"] += 1
            event_id = str(row["event_id"])
            existing = self._existing_metrics(event_id)
            if expected.issubset(existing):
                result["already_captured"] += 1
                continue
            if existing:
                result["partial_existing_fail_closed"] += 1
                continue
            scheduled_at = float(row["scheduled_at"])
            if current - scheduled_at > self.capture_window_seconds:
                result["missed_capture_window"] += 1
                continue
            try:
                result["network_requests"] += 1
                values = self._fetch_news_release_values(row, now=current)
                built = {value.metric_id for value in values}
                if built != expected:
                    raise ValueError(
                        f"incomplete BEA news-release metric set: {sorted(built)} != {sorted(expected)}"
                    )
                ingest = self.store.ingest(values, seen_at=current)
            except Exception as exc:
                result["capture_failures"] += 1
                result.setdefault("errors", []).append(
                    {"event_id": event_id, "error": f"{type(exc).__name__}: {exc}"[:300]}
                )
                continue
            result["events_captured"] += 1
            result["actual_values_inserted"] += int(ingest["inserted"])

        result["status"] = "ok" if int(result["capture_failures"]) == 0 else "partial"
        return result


# Keep the ingest-cycle import name stable.
BeaActualCaptureService = ResilientBeaActualCaptureService
