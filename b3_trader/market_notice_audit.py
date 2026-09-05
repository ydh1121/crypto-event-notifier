from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .market_notice_store import MarketNoticeStore

TIMING_FIELDS = ("announcement_at", "deposit_at", "trade_open_at", "termination_at")


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "notice_id": str(row.get("notice_id") or ""),
        "title": str(row.get("title") or ""),
        "event_kind": str(row.get("event_kind") or ""),
        "symbols": row.get("symbols") if isinstance(row.get("symbols"), list) else [],
        **{field: float(row.get(field) or 0.0) for field in TIMING_FIELDS},
    }


def audit(path: Path = DB_PATH, *, rows: int = 5) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"ok": False, "configured": False, "path_exists": False, "exchanges": {}}
    conn = sqlite3.connect(str(path), timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        store = MarketNoticeStore(conn)
        exchanges: dict[str, Any] = {}
        for exchange in ("bithumb", "upbit"):
            recent = store.recent(exchange, 300)
            timing_counts = {
                field: sum(1 for row in recent if float(row.get(field) or 0.0) > 0)
                for field in TIMING_FIELDS
            }
            kinds = Counter(str(row.get("event_kind") or "OTHER") for row in recent)
            structured = [row for row in recent if any(float(row.get(field) or 0.0) > 0 for field in TIMING_FIELDS[1:])]
            exchanges[exchange] = {
                "notice_count": len(recent),
                "event_kinds": dict(sorted(kinds.items())),
                "timing_counts": timing_counts,
                "structured_sample": [_compact(row) for row in structured[: max(0, int(rows))]],
                "latest_sample": [_compact(row) for row in recent[: max(0, int(rows))]],
            }
        return {"ok": True, "configured": True, "path_exists": True, "exchanges": exchanges}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact official market notice/timing audit")
    parser.add_argument("--rows", type=int, default=4, help="sample rows per exchange (0-20)")
    args = parser.parse_args()
    result = audit(rows=max(0, min(20, int(args.rows))))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
