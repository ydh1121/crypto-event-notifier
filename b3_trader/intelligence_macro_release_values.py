from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

VALUE_ROLES = {"previous", "consensus", "actual"}
MACRO_VALUE_VERSION = 1
_EPSILON = 1e-12


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _finite(value: Any, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _https_url(value: str, *, name: str) -> str:
    text = _clean(value)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{name} must be an https URL")
    return text


def _normalized_unit(value: str) -> str:
    unit = _clean(value).upper()
    if not unit:
        raise ValueError("unit is required")
    return unit


def _normalized_period(value: str) -> str:
    period = _clean(value).upper()
    if not period:
        raise ValueError("reference_period is required")
    return period


def _value_id(
    *,
    event_id: str,
    metric_id: str,
    value_role: str,
    provider_id: str,
    reference_period: str,
    revision_no: int,
    known_at: float,
) -> str:
    payload = json.dumps(
        [event_id, metric_id, value_role, provider_id, reference_period, revision_no, round(known_at, 3)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "imv:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class MacroReleaseValue:
    value_id: str
    event_id: str
    event_type: str
    metric_id: str
    value_role: str
    numeric_value: float
    unit: str
    reference_period: str
    provider_id: str
    provider_url: str
    authority: str
    data_rights: str
    known_at: float
    received_at: float
    revision_no: int
    revision_label: str
    attributes: dict[str, Any]
    version: int = MACRO_VALUE_VERSION


def normalize_macro_release_value(
    *,
    event_id: str,
    event_type: str,
    metric_id: str,
    value_role: str,
    numeric_value: float,
    unit: str,
    reference_period: str,
    provider_id: str,
    provider_url: str,
    authority: str,
    data_rights: str,
    known_at: float,
    received_at: float | None = None,
    revision_no: int = 0,
    revision_label: str = "initial",
    attributes: Mapping[str, Any] | None = None,
    version: int = MACRO_VALUE_VERSION,
) -> MacroReleaseValue:
    clean_event_id = _clean(event_id)
    clean_event_type = _clean(event_type).upper()
    clean_metric = _clean(metric_id).upper()
    clean_role = _clean(value_role).lower()
    clean_provider = _clean(provider_id).lower()
    clean_authority = _clean(authority)
    clean_rights = _clean(data_rights)
    if not clean_event_id or not clean_event_type or not clean_metric:
        raise ValueError("event_id/event_type/metric_id are required")
    if clean_role not in VALUE_ROLES:
        raise ValueError(f"unsupported macro value role: {value_role!r}")
    if not clean_provider or not clean_authority or not clean_rights:
        raise ValueError("provider_id/authority/data_rights are required")
    value = _finite(numeric_value, name="numeric_value")
    known = _finite(known_at, name="known_at")
    received = _finite(received_at if received_at is not None else time.time(), name="received_at")
    if known <= 0 or received <= 0:
        raise ValueError("known_at/received_at must be positive")
    revision = int(revision_no)
    if revision < 0:
        raise ValueError("revision_no must be >= 0")
    label = _clean(revision_label) or ("initial" if revision == 0 else f"revision_{revision}")
    normalized_version = int(version)
    if normalized_version < 1:
        raise ValueError("version must be >= 1")
    normalized_unit = _normalized_unit(unit)
    normalized_period = _normalized_period(reference_period)
    provider_link = _https_url(provider_url, name="provider_url")
    return MacroReleaseValue(
        value_id=_value_id(
            event_id=clean_event_id,
            metric_id=clean_metric,
            value_role=clean_role,
            provider_id=clean_provider,
            reference_period=normalized_period,
            revision_no=revision,
            known_at=known,
        ),
        event_id=clean_event_id,
        event_type=clean_event_type,
        metric_id=clean_metric,
        value_role=clean_role,
        numeric_value=value,
        unit=normalized_unit,
        reference_period=normalized_period,
        provider_id=clean_provider,
        provider_url=provider_link,
        authority=clean_authority,
        data_rights=clean_rights,
        known_at=known,
        received_at=received,
        revision_no=revision,
        revision_label=label,
        attributes=dict(attributes or {}),
        version=normalized_version,
    )


class MacroReleaseValueStore:
    """Store macro previous/consensus/actual evidence without scoring it."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_intelligence_macro_values (
                value_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                metric_id TEXT NOT NULL,
                value_role TEXT NOT NULL,
                numeric_value REAL NOT NULL,
                unit TEXT NOT NULL,
                reference_period TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                provider_url TEXT NOT NULL,
                authority TEXT NOT NULL,
                data_rights TEXT NOT NULL,
                known_at REAL NOT NULL,
                received_at REAL NOT NULL,
                revision_no INTEGER NOT NULL DEFAULT 0,
                revision_label TEXT NOT NULL,
                attributes_json TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL DEFAULT 1,
                first_seen_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(event_id,metric_id,value_role,provider_id,reference_period,revision_no,known_at)
            );
            CREATE INDEX IF NOT EXISTS idx_intelligence_macro_values_event_metric
                ON research_intelligence_macro_values(event_id,metric_id,value_role,known_at DESC);
            CREATE INDEX IF NOT EXISTS idx_intelligence_macro_values_provider
                ON research_intelligence_macro_values(provider_id,event_type,metric_id,known_at DESC);
            """
        )
        self.conn.commit()

    def ingest(
        self,
        values: Iterable[MacroReleaseValue],
        *,
        seen_at: float | None = None,
    ) -> dict[str, int]:
        now = float(seen_at if seen_at is not None else time.time())
        if now <= 0:
            raise ValueError("seen_at must be positive")
        received = inserted = updated = 0
        for item in values:
            if item.value_role not in VALUE_ROLES:
                raise ValueError(f"unsupported macro value role: {item.value_role!r}")
            received += 1
            exists = self.conn.execute(
                "SELECT 1 FROM research_intelligence_macro_values WHERE value_id=?",
                (item.value_id,),
            ).fetchone()
            self.conn.execute(
                """INSERT INTO research_intelligence_macro_values(
                    value_id,event_id,event_type,metric_id,value_role,numeric_value,unit,reference_period,
                    provider_id,provider_url,authority,data_rights,known_at,received_at,revision_no,
                    revision_label,attributes_json,version,first_seen_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(value_id) DO UPDATE SET
                    numeric_value=excluded.numeric_value,
                    provider_url=excluded.provider_url,
                    authority=excluded.authority,
                    data_rights=excluded.data_rights,
                    received_at=excluded.received_at,
                    revision_label=excluded.revision_label,
                    attributes_json=excluded.attributes_json,
                    version=CASE WHEN excluded.version>research_intelligence_macro_values.version
                                 THEN excluded.version ELSE research_intelligence_macro_values.version END,
                    updated_at=excluded.updated_at""",
                (
                    item.value_id,item.event_id,item.event_type,item.metric_id,item.value_role,
                    item.numeric_value,item.unit,item.reference_period,item.provider_id,item.provider_url,
                    item.authority,item.data_rights,item.known_at,item.received_at,item.revision_no,
                    item.revision_label,
                    json.dumps(item.attributes, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
                    item.version,now,now,
                ),
            )
            if exists:
                updated += 1
            else:
                inserted += 1
        self.conn.commit()
        return {"received": received, "inserted": inserted, "updated": updated}

    def _release_anchor(self, event_id: str) -> tuple[str, float, str] | None:
        tables = {
            str(row[0])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "research_intelligence_events" not in tables:
            return None
        row = self.conn.execute(
            """SELECT event_type,scheduled_at,published_at,observed_at
               FROM research_intelligence_events WHERE event_id=?""",
            (_clean(event_id),),
        ).fetchone()
        if row is None:
            return None
        # For macro surprise the scheduled release boundary is authoritative when
        # available. It prevents a later actual/revision timestamp from moving the
        # pre-release consensus cutoff forward in hindsight.
        scheduled = float(row["scheduled_at"] or 0.0)
        published = float(row["published_at"] or 0.0)
        observed = float(row["observed_at"] or 0.0)
        if scheduled > 0:
            return "scheduled_at", scheduled, str(row["event_type"])
        if published > 0:
            return "published_at", published, str(row["event_type"])
        if observed > 0:
            return "observed_at", observed, str(row["event_type"])
        return None

    def _select_value(
        self,
        *,
        event_id: str,
        metric_id: str,
        role: str,
        provider_id: str,
        relation: str,
        anchor_at: float,
        revision_no: int | None = None,
    ) -> sqlite3.Row | None:
        clauses = ["event_id=?", "metric_id=?", "value_role=?", "provider_id=?"]
        params: list[Any] = [
            _clean(event_id),
            _clean(metric_id).upper(),
            _clean(role).lower(),
            _clean(provider_id).lower(),
        ]
        if revision_no is not None:
            clauses.append("revision_no=?")
            params.append(int(revision_no))
        if relation == "before":
            clauses.append("known_at<?")
            params.append(anchor_at)
            order = "known_at DESC, revision_no DESC"
        elif relation == "after":
            clauses.append("known_at>=?")
            params.append(anchor_at)
            order = "known_at ASC, revision_no ASC"
        else:
            raise ValueError(f"unsupported relation: {relation!r}")
        return self.conn.execute(
            f"""SELECT * FROM research_intelligence_macro_values
                WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT 1""",
            tuple(params),
        ).fetchone()

    def compute_surprise(
        self,
        *,
        event_id: str,
        metric_id: str,
        consensus_provider_id: str,
        actual_provider_id: str,
        actual_revision_no: int = 0,
    ) -> dict[str, Any] | None:
        anchor = self._release_anchor(event_id)
        if anchor is None:
            return None
        anchor_kind, anchor_at, event_type = anchor
        consensus = self._select_value(
            event_id=event_id,
            metric_id=metric_id,
            role="consensus",
            provider_id=consensus_provider_id,
            relation="before",
            anchor_at=anchor_at,
        )
        actual = self._select_value(
            event_id=event_id,
            metric_id=metric_id,
            role="actual",
            provider_id=actual_provider_id,
            relation="after",
            anchor_at=anchor_at,
            revision_no=actual_revision_no,
        )
        if consensus is None or actual is None:
            return None
        if str(consensus["unit"]) != str(actual["unit"]):
            return None
        if str(consensus["reference_period"]) != str(actual["reference_period"]):
            return None
        consensus_value = float(consensus["numeric_value"])
        actual_value = float(actual["numeric_value"])
        absolute = actual_value - consensus_value
        relative = None
        if abs(consensus_value) > _EPSILON:
            relative = absolute / abs(consensus_value) * 100.0
        return {
            "event_id": _clean(event_id),
            "event_type": event_type,
            "metric_id": _clean(metric_id).upper(),
            "reference_period": str(actual["reference_period"]),
            "unit": str(actual["unit"]),
            "anchor_kind": anchor_kind,
            "anchor_at": anchor_at,
            "consensus_value": consensus_value,
            "consensus_provider_id": str(consensus["provider_id"]),
            "consensus_known_at": float(consensus["known_at"]),
            "actual_value": actual_value,
            "actual_provider_id": str(actual["provider_id"]),
            "actual_known_at": float(actual["known_at"]),
            "actual_revision_no": int(actual["revision_no"]),
            "absolute_surprise": absolute,
            "relative_surprise_pct": relative,
            "z_surprise": None,
            "score_contribution": None,
            "confidence": None,
            "confidence_status": "not_promoted",
            "lookahead_safe": True,
        }

    def history(
        self,
        *,
        event_id: str,
        metric_id: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses = ["event_id=?"]
        params: list[Any] = [_clean(event_id)]
        if metric_id:
            clauses.append("metric_id=?")
            params.append(_clean(metric_id).upper())
        params.append(max(1, min(2000, int(limit))))
        rows = self.conn.execute(
            f"""SELECT * FROM research_intelligence_macro_values
                WHERE {' AND '.join(clauses)}
                ORDER BY metric_id,value_role,known_at,revision_no LIMIT ?""",
            tuple(params),
        ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            result = dict(row)
            try:
                result["attributes"] = json.loads(str(result.pop("attributes_json") or "{}"))
            except (json.JSONDecodeError, TypeError, ValueError):
                result["attributes"] = {}
            output.append(result)
        return output
