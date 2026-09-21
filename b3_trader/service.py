from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from dotenv import load_dotenv

from .config import Settings
from .main import run as run_trader


BOOT_TS = time.time()
BOT_ERROR: dict[str, str] | None = None


def _read_journal(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {
            "ready": False,
            "reason": "journal_not_created",
            "last_snapshot": None,
            "counts": {"snapshots": 0, "fills": 0, "events": 0},
            "recent_fills": [],
            "recent_events": [],
        }

    conn = sqlite3.connect(path, timeout=1.0)
    conn.row_factory = sqlite3.Row
    try:
        counts: dict[str, int] = {}
        for table in ("snapshots", "fills", "events"):
            try:
                counts[table] = int(
                    conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
                )
            except sqlite3.OperationalError:
                counts[table] = 0

        last = None
        try:
            row = conn.execute(
                """
                SELECT id, ts, market, price, regime_score, entry_score, action, payload_json
                FROM snapshots
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if row:
                last = {
                    "id": int(row["id"]),
                    "ts": float(row["ts"]),
                    "market": row["market"],
                    "price": float(row["price"]),
                    "regime_score": float(row["regime_score"]),
                    "entry_score": float(row["entry_score"]),
                    "action": row["action"],
                    "payload": json.loads(row["payload_json"]),
                }
        except sqlite3.OperationalError:
            last = None

        recent_fills: list[dict[str, Any]] = []
        try:
            rows = conn.execute(
                """
                SELECT id, ts, mode, market, side, price, volume, krw, reason, payload_json
                FROM fills
                ORDER BY id DESC
                LIMIT 50
                """
            ).fetchall()
            for row in reversed(rows):
                recent_fills.append(
                    {
                        "id": int(row["id"]),
                        "ts": float(row["ts"]),
                        "mode": row["mode"],
                        "market": row["market"],
                        "side": row["side"],
                        "price": float(row["price"]),
                        "volume": float(row["volume"]),
                        "krw": float(row["krw"]),
                        "reason": row["reason"],
                        "payload": json.loads(row["payload_json"]),
                    }
                )
        except sqlite3.OperationalError:
            pass

        recent_events: list[dict[str, Any]] = []
        try:
            rows = conn.execute(
                """
                SELECT id, ts, kind, payload_json
                FROM events
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()
            for row in reversed(rows):
                recent_events.append(
                    {
                        "id": int(row["id"]),
                        "ts": float(row["ts"]),
                        "kind": row["kind"],
                        "payload": json.loads(row["payload_json"]),
                    }
                )
        except sqlite3.OperationalError:
            pass

        return {
            "ready": last is not None,
            "last_snapshot": last,
            "counts": counts,
            "recent_fills": recent_fills,
            "recent_events": recent_events,
        }
    finally:
        conn.close()


def _bot_runner() -> None:
    global BOT_ERROR
    try:
        run_trader()
    except BaseException as exc:
        BOT_ERROR = {"type": type(exc).__name__, "message": str(exc)}
        raise


class Handler(BaseHTTPRequestHandler):
    server_version = "B3Trader/0.3"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        load_dotenv()
        settings = Settings()
        path = self.path.split("?", 1)[0]

        if path == "/ready":
            self._json(
                200,
                {
                    "ok": True,
                    "service": "b3-trader",
                    "phase": 3,
                    "mode": "PAPER",
                    "uptime_seconds": round(time.time() - BOOT_TS, 1),
                },
            )
            return

        if path not in {"/health", "/checkpoint"}:
            self._json(404, {"ok": False, "error": "not_found"})
            return

        try:
            journal = _read_journal(settings.journal_db)
            last = journal.get("last_snapshot")
            age = None
            if last:
                age = max(0.0, time.time() - float(last["ts"]))
            healthy = (
                BOT_ERROR is None
                and last is not None
                and age is not None
                and age <= settings.health_stale_seconds
            )

            payload = {
                "ok": healthy,
                "service": "b3-trader",
                "phase": 3,
                "mode": "PAPER",
                "uptime_seconds": round(time.time() - BOOT_TS, 1),
                "snapshot_age_seconds": round(age, 2) if age is not None else None,
                "bot_error": BOT_ERROR,
                **journal,
            }

            if path == "/health":
                payload.pop("recent_fills", None)
                payload.pop("recent_events", None)

            self._json(200 if healthy or path == "/checkpoint" else 503, payload)
        except Exception as exc:
            self._json(
                503,
                {
                    "ok": False,
                    "service": "b3-trader",
                    "error": type(exc).__name__,
                    "message": str(exc),
                    "bot_error": BOT_ERROR,
                },
            )

    def log_message(self, fmt: str, *args: Any) -> None:
        print(
            json.dumps(
                {
                    "http": fmt % args,
                    "client": self.client_address[0] if self.client_address else None,
                },
                ensure_ascii=False,
            )
        )


def main() -> None:
    load_dotenv()
    settings = Settings()
    thread = threading.Thread(target=_bot_runner, name="b3-trader", daemon=True)
    thread.start()

    server = ThreadingHTTPServer(("0.0.0.0", settings.service_port), Handler)
    print(
        json.dumps(
            {
                "service": "b3-trader-http",
                "port": settings.service_port,
                "mode": "PAPER",
                "phase": 3,
            },
            ensure_ascii=False,
        )
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
