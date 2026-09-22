"""Bounded journal transport through the existing authenticated market-details API."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def _bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def detail_items(item: dict[str, Any], max_bytes: int = 165_000) -> list[dict[str, Any]]:
    """Keep small journals inline; split large ones without dropping a single fill.

    Immutable chunks are sent before their manifest. A partially failed upload
    leaves the previous manifest usable; new pages are content-addressed.
    They use the existing table, auth and budget, never a new canonical database.
    """
    item = copy.deepcopy(item)
    chunks: list[dict[str, Any]] = []
    experiments = item["detail"].get("strategy_lab", {}).get("experiments", [])
    for experiment in sorted(experiments, key=lambda e: len(e.get("journal", {}).get("rows", [])), reverse=True):
        if len(_bytes({"details": [item]})) <= max_bytes:
            break
        journal = experiment.get("journal", {})
        rows = journal.pop("rows", [])
        refs = []
        # One chunk fits comfortably below the existing per-row ingestion bound.
        pending: list[list[Any]] = []
        def finish() -> None:
            if not pending:
                return
            data = {"kind": "strategy_lab_journal", "experiment_id": experiment["experiment_id"],
                    "columns": journal["columns"], "rows": pending[:], "count": len(pending)}
            digest = hashlib.sha256(_bytes(data)).hexdigest()[:40]
            strategy = f"lab-journal:{digest}"
            refs.append({"strategy": strategy, "count": len(pending)})
            chunks.append({"key": f"{item['exchange']}|{item['market']}|{strategy}",
                           "exchange": item["exchange"], "market": item["market"], "strategy": strategy,
                           "source_ts": pending[-1][1], "detail": data})
            pending.clear()
        for row in rows:
            if pending and (len(pending) >= 400 or len(_bytes(pending + [row])) > 90_000):
                finish()
            pending.append(row)
        finish()
        journal["chunks"] = refs
    if len(_bytes({"details": [item]})) > max_bytes:
        raise ValueError("market detail exceeds transport budget without journal rows")
    return [*chunks, item]
