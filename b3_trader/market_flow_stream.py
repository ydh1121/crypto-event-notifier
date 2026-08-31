from __future__ import annotations

import json
import os
import signal
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import websocket

from .market_flow_stream_store import MarketFlowStreamStore
from .research_control import atomic_json
from .research_work_lock import ResearchWorkLock

STATUS_PATH = Path("b3_trader/data/research-platform/market-flow-stream.json")
PROCESS_LOCK_PATH = Path("b3_trader/data/research-platform/market-flow-stream-process.lock")
DEFAULT_MARKETS = ("KRW-BTC", "KRW-ETH")
MAX_MARKETS = 8
STATUS_INTERVAL_SECONDS = 2.0
FEATURE_INTERVAL_SECONDS = 60.0
FLUSH_INTERVAL_SECONDS = 0.25
FLUSH_BATCH_SIZE = 200
RECONNECT_MAX_SECONDS = 30.0
ENDPOINTS = {
    "upbit": "wss://api.upbit.com/websocket/v1",
    "bithumb": "wss://ws-api.bithumb.com/websocket/v1",
}


def _epoch_seconds(value: Any) -> float:
    try:
        raw = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if raw > 100_000_000_000_000:
        return raw / 1_000_000.0
    if raw > 100_000_000_000:
        return raw / 1_000.0
    return raw


def normalize_stream_trade(exchange: str, row: dict[str, Any], received_at: float) -> dict[str, Any] | None:
    if str(row.get("type") or "trade").lower() != "trade":
        return None
    if str(row.get("stream_type") or "REALTIME").upper() == "SNAPSHOT":
        return None
    market = str(row.get("code") or row.get("market") or "").upper()
    side = str(row.get("ask_bid") or row.get("side") or "").upper()
    if side in {"BUY", "BID"}:
        side = "BID"
    elif side in {"SELL", "ASK"}:
        side = "ASK"
    else:
        return None
    try:
        price = float(row.get("trade_price") or 0.0)
        volume = float(row.get("trade_volume") or 0.0)
        trade_ts = _epoch_seconds(row.get("trade_timestamp") or row.get("timestamp"))
    except (TypeError, ValueError):
        return None
    sequential_id = str(row.get("sequential_id") or "")
    if not market or not sequential_id or price <= 0 or volume <= 0 or trade_ts <= 0:
        return None
    return {
        "exchange": str(exchange),
        "market": market,
        "sequential_id": sequential_id,
        "trade_ts": trade_ts,
        "trade_price": price,
        "trade_volume": volume,
        "quote_volume": price * volume,
        "aggressor_side": side,
        "side_source": "exchange",
        "received_at": float(received_at),
    }


def _subscription(exchange: str, markets: tuple[str, ...]) -> str:
    trade: dict[str, Any] = {"type": "trade", "codes": list(markets)}
    if exchange == "upbit":
        trade["is_only_realtime"] = True
    elif exchange == "bithumb":
        trade["isOnlyRealtime"] = True
    return json.dumps(
        [
            {"ticket": f"b3-flow-{exchange}-{uuid.uuid4()}"},
            trade,
            {"format": "DEFAULT"},
        ],
        separators=(",", ":"),
    )


def _parse_markets(raw: str | None) -> tuple[str, ...]:
    items = []
    for value in str(raw or "").split(","):
        market = value.strip().upper()
        if not market or not market.startswith("KRW-") or market in items:
            continue
        items.append(market)
        if len(items) >= MAX_MARKETS:
            break
    if not items:
        items = list(DEFAULT_MARKETS)
    for benchmark in reversed(DEFAULT_MARKETS):
        if benchmark not in items:
            items.insert(0, benchmark)
    return tuple(items[:MAX_MARKETS])


class StreamWorker:
    def __init__(
        self,
        exchange: str,
        markets: tuple[str, ...],
        stop_event: threading.Event,
        state: dict[str, Any],
        state_lock: threading.RLock,
        process_started_at: float,
    ) -> None:
        self.exchange = exchange
        self.endpoint = ENDPOINTS[exchange]
        self.markets = markets
        self.stop_event = stop_event
        self.state = state
        self.state_lock = state_lock
        self.process_started_at = process_started_at
        self.store: MarketFlowStreamStore | None = None
        self.app: websocket.WebSocketApp | None = None
        self.buffer: list[dict[str, Any]] = []
        self.last_flush_at = 0.0
        self.ever_connected = False

    def _update(self, **values: Any) -> None:
        with self.state_lock:
            self.state.update(values)
            self.state["updated_at"] = time.time()

    def _increment(self, key: str, amount: int = 1) -> None:
        with self.state_lock:
            self.state[key] = int(self.state.get(key) or 0) + int(amount)
            self.state["updated_at"] = time.time()

    def _flush(self, *, force: bool = False) -> None:
        if not self.store or not self.buffer:
            return
        now = time.time()
        if not force and len(self.buffer) < FLUSH_BATCH_SIZE and now - self.last_flush_at < FLUSH_INTERVAL_SECONDS:
            return
        rows = self.buffer
        self.buffer = []
        result = self.store.insert_trades(rows, received_at=now)
        self.last_flush_at = now
        self._increment("rows_observed", int(result.get("observed") or 0))
        self._increment("rows_inserted", int(result.get("inserted") or 0))

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        now = time.time()
        if self.ever_connected:
            self._increment("reconnects")
        self.ever_connected = True
        if self.store:
            self.store.mark_connected(
                self.exchange,
                self.markets,
                process_started_at=self.process_started_at,
                connected_since=now,
                reconnects=int(self.state.get("reconnects") or 0),
            )
        ws.send(_subscription(self.exchange, self.markets))
        self._update(
            connected=True,
            connected_since=now,
            last_error="",
            last_error_at=0.0,
            status="connected",
        )

    def _on_message(self, _ws: websocket.WebSocketApp, message: Any) -> None:
        received_at = time.time()
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            payload = json.loads(str(message))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            self._increment("parse_errors")
            return
        if not isinstance(payload, dict):
            self._increment("parse_errors")
            return
        row = normalize_stream_trade(self.exchange, payload, received_at)
        if row is None:
            return
        if row["market"] not in self.markets:
            return
        self.buffer.append(row)
        self._increment("messages")
        self._update(
            last_message_at=received_at,
            last_trade_ts=float(row["trade_ts"]),
        )
        self._flush()

    def _on_error(self, _ws: websocket.WebSocketApp, error: Any) -> None:
        now = time.time()
        self._update(
            last_error=f"{type(error).__name__}: {error}"[:500],
            last_error_at=now,
            status="reconnecting",
        )

    def _on_close(self, _ws: websocket.WebSocketApp, status_code: Any, message: Any) -> None:
        now = time.time()
        self._flush(force=True)
        if self.store:
            self.store.mark_disconnected(self.exchange, self.markets, disconnected_at=now)
        self._update(
            connected=False,
            last_disconnect_at=now,
            close_status_code=status_code,
            close_message=str(message or "")[:300],
            status="stopped" if self.stop_event.is_set() else "reconnecting",
        )

    def run(self) -> None:
        self.store = MarketFlowStreamStore()
        backoff = 1.0
        try:
            while not self.stop_event.is_set():
                self._update(status="connecting", endpoint=self.endpoint)
                self.app = websocket.WebSocketApp(
                    self.endpoint,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                try:
                    self.app.run_forever(
                        ping_interval=30,
                        ping_timeout=10,
                        skip_utf8_validation=True,
                    )
                except Exception as exc:
                    self._on_error(self.app, exc)
                finally:
                    self._flush(force=True)
                if self.stop_event.is_set():
                    break
                self.stop_event.wait(backoff)
                backoff = min(RECONNECT_MAX_SECONDS, max(1.0, backoff * 2.0))
                if bool(self.state.get("connected")):
                    backoff = 1.0
        finally:
            if self.store:
                try:
                    self.store.mark_disconnected(self.exchange, self.markets, disconnected_at=time.time())
                except Exception:
                    pass
                self.store.close()
                self.store = None
            self._update(connected=False, status="stopped")

    def stop(self) -> None:
        app = self.app
        if app is not None:
            try:
                app.close()
            except Exception:
                pass


class MarketFlowStreamService:
    """Dedicated public WebSocket process for continuous high-frequency flow."""

    def __init__(self, markets: tuple[str, ...] | None = None) -> None:
        self.markets = markets or _parse_markets(os.getenv("MARKET_FLOW_STREAM_MARKETS"))
        self.stop_event = threading.Event()
        self.started_at = time.time()
        self.state_lock = threading.RLock()
        self.states: dict[str, dict[str, Any]] = {
            exchange: {
                "exchange": exchange,
                "endpoint": endpoint,
                "status": "starting",
                "connected": False,
                "connected_since": 0.0,
                "last_disconnect_at": 0.0,
                "last_message_at": 0.0,
                "last_trade_ts": 0.0,
                "messages": 0,
                "rows_observed": 0,
                "rows_inserted": 0,
                "parse_errors": 0,
                "reconnects": 0,
                "last_error": "",
                "last_error_at": 0.0,
                "updated_at": self.started_at,
            }
            for exchange, endpoint in ENDPOINTS.items()
        }
        self.workers: dict[str, StreamWorker] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.process_lock_acquired = False
        self.window_features_written = 0
        self.last_feature_at = 0.0
        self.last_feature_error = ""

    def stop(self) -> None:
        self.stop_event.set()
        for worker in self.workers.values():
            worker.stop()

    def _status_payload(self, *, running: bool) -> dict[str, Any]:
        with self.state_lock:
            exchanges = {name: dict(state) for name, state in self.states.items()}
        return {
            "ok": not bool(self.last_feature_error),
            "status": "running" if running and not self.stop_event.is_set() else "stopped",
            "pid": os.getpid(),
            "running": bool(running) and not self.stop_event.is_set(),
            "started_at": self.started_at,
            "updated_at": time.time(),
            "process_lock_acquired": self.process_lock_acquired,
            "markets": list(self.markets),
            "exchanges": exchanges,
            "window_features_written": self.window_features_written,
            "last_feature_at": self.last_feature_at,
            "last_feature_error": self.last_feature_error,
            "network_public_only": True,
            "authentication_used": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "raw_cloud_projection": False,
            "cvd_scope": "websocket_contiguous_session",
        }

    def _write_status(self, *, running: bool) -> None:
        atomic_json(STATUS_PATH, self._status_payload(running=running))

    def _aggregate_windows(self, store: MarketFlowStreamStore) -> None:
        try:
            self.window_features_written += int(store.compute_window_features())
            self.last_feature_at = time.time()
            self.last_feature_error = ""
        except Exception as exc:
            self.last_feature_error = f"{type(exc).__name__}: {exc}"[:500]

    def run(self) -> None:
        process_lock = ResearchWorkLock(PROCESS_LOCK_PATH)
        if not process_lock.acquire():
            return
        self.process_lock_acquired = True
        aggregate_store = MarketFlowStreamStore()
        try:
            for exchange in ENDPOINTS:
                worker = StreamWorker(
                    exchange,
                    self.markets,
                    self.stop_event,
                    self.states[exchange],
                    self.state_lock,
                    self.started_at,
                )
                thread = threading.Thread(
                    target=worker.run,
                    name=f"market-flow-stream-{exchange}",
                    daemon=True,
                )
                self.workers[exchange] = worker
                self.threads[exchange] = thread
                thread.start()
            next_feature = time.time() + 5.0
            while not self.stop_event.wait(STATUS_INTERVAL_SECONDS):
                now = time.time()
                if now >= next_feature:
                    self._aggregate_windows(aggregate_store)
                    next_feature = now + FEATURE_INTERVAL_SECONDS
                self._write_status(running=True)
        finally:
            self.stop()
            for thread in self.threads.values():
                thread.join(timeout=5.0)
            self._aggregate_windows(aggregate_store)
            aggregate_store.close()
            self.process_lock_acquired = False
            self._write_status(running=False)
            process_lock.release()


def main() -> None:
    load_dotenv()
    service = MarketFlowStreamService()

    def _stop(_signum, _frame) -> None:
        service.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _stop)
        except (ValueError, OSError):
            pass
    service.run()


if __name__ == "__main__":
    main()
