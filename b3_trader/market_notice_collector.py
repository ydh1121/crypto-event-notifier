from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Protocol

from .auto_demo_v2 import DB_PATH
from .market_notice import MarketNotice
from .market_notice_sources import default_notice_sources
from .market_notice_store import MarketNoticeStore
from .research_work_lock import ResearchWorkLock


class NoticeSource(Protocol):
    exchange: str
    source: str

    def fetch(self) -> list[MarketNotice]: ...


class MarketNoticeCollector:
    """Independent official-notice sidecar. It never reads or places orders."""

    def __init__(self, path: Path = DB_PATH, *, sources: tuple[NoticeSource, ...] | None = None) -> None:
        self.path = Path(path)
        self.sources = tuple(sources or default_notice_sources())
        self._conn: sqlite3.Connection | None = None
        self._store: MarketNoticeStore | None = None

    def _notice_store(self) -> MarketNoticeStore:
        if self._store is not None:
            return self._store
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        self._conn = conn
        self._store = MarketNoticeStore(conn)
        return self._store

    def run_once(self) -> dict[str, Any]:
        with ResearchWorkLock() as work_lock:
            if not work_lock.acquired:
                return {
                    "status": "deferred_forward_research_work_lock_busy",
                    "paper_only": True,
                    "can_place_orders": False,
                    "network_fetches": False,
                    "database_mutation": False,
                    "sources_ok": 0,
                    "sources_failed": 0,
                    "received": 0,
                    "inserted": 0,
                    "state_updates": 0,
                    "sources": {},
                    "elapsed_seconds": 0.0,
                }
            return self._run_once_unlocked()

    def _run_once_unlocked(self) -> dict[str, Any]:
        started = time.time()
        store = self._notice_store()
        source_results: dict[str, dict[str, Any]] = {}
        successes = 0
        failures = 0
        received = 0
        inserted = 0
        state_updates = 0

        for source in self.sources:
            name = f"{str(source.exchange).lower()}:{str(source.source)}"
            try:
                notices = source.fetch()
                result = store.ingest(notices, seen_at=time.time())
                successes += 1
                received += int(result.get("received") or 0)
                inserted += int(result.get("inserted") or 0)
                state_updates += int(result.get("state_updates") or 0)
                source_results[name] = {
                    "status": "ok",
                    "received": int(result.get("received") or 0),
                    "inserted": int(result.get("inserted") or 0),
                    "state_updates": int(result.get("state_updates") or 0),
                    "by_kind": result.get("by_kind") if isinstance(result.get("by_kind"), dict) else {},
                }
            except Exception as exc:
                failures += 1
                source_results[name] = {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }

        if successes <= 0 and failures > 0:
            details = "; ".join(
                f"{name}={row.get('error')}" for name, row in source_results.items() if row.get("status") == "error"
            )
            raise RuntimeError(f"all market notice sources failed: {details[:600]}")

        return {
            "status": "partial" if failures else "collected",
            "paper_only": True,
            "can_place_orders": False,
            "sources_ok": successes,
            "sources_failed": failures,
            "received": received,
            "inserted": inserted,
            "state_updates": state_updates,
            "sources": source_results,
            "elapsed_seconds": round(time.time() - started, 3),
        }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
        self._conn = None
        self._store = None


def main() -> None:
    import json

    collector = MarketNoticeCollector()
    try:
        print(json.dumps(collector.run_once(), ensure_ascii=False, indent=2))
    finally:
        collector.close()


if __name__ == "__main__":
    main()
