from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import websocket


PUBLIC_WS_URL = "wss://ws-api.bithumb.com/websocket/v1"
PRIVATE_WS_URL = "wss://ws-api.bithumb.com/websocket/v2/private"


@dataclass(frozen=True)
class CachedMessage:
    received_at: float
    payload: dict[str, Any]


class RealtimeMarketCache:
    """Thread-safe latest-message cache keyed by (type, market)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[tuple[str, str], CachedMessage] = {}

    def update(self, payload: dict[str, Any]) -> None:
        message_type = str(payload.get("type") or "")
        code = str(payload.get("code") or "*")
        if not message_type:
            return
        with self._lock:
            self._data[(message_type, code)] = CachedMessage(time.time(), payload)

    def latest(
        self,
        message_type: str,
        market: str = "*",
        max_age_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            item = self._data.get((message_type, market))
        if item is None:
            return None
        if max_age_seconds is not None and time.time() - item.received_at > max_age_seconds:
            return None
        return dict(item.payload)


class BithumbWebSocketStream:
    """Small reconnecting WebSocket runner.

    It intentionally never submits orders. Public and private streams only feed
    observable state into the local cache.
    """

    def __init__(
        self,
        *,
        name: str,
        url: str,
        subscription_factory: Callable[[], list[dict[str, Any]]],
        cache: RealtimeMarketCache,
        header_factory: Callable[[], list[str]] | None = None,
    ) -> None:
        self.name = name
        self.url = url
        self.subscription_factory = subscription_factory
        self.cache = cache
        self.header_factory = header_factory
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ws: websocket.WebSocketApp | None = None
        self.last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                headers = self.header_factory() if self.header_factory else None

                def on_open(ws: websocket.WebSocketApp) -> None:
                    nonlocal backoff
                    backoff = 1.0
                    ws.send(json.dumps(self.subscription_factory()))

                def on_message(_: websocket.WebSocketApp, message: str | bytes) -> None:
                    try:
                        if isinstance(message, bytes):
                            message = message.decode("utf-8")
                        payload = json.loads(message)
                        if isinstance(payload, dict):
                            self.cache.update(payload)
                    except Exception as exc:
                        self.last_error = f"decode:{type(exc).__name__}:{exc}"

                def on_error(_: websocket.WebSocketApp, error: Any) -> None:
                    self.last_error = f"{type(error).__name__}:{error}"

                self._ws = websocket.WebSocketApp(
                    self.url,
                    header=headers,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                )
                self._ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}:{exc}"

            if self._stop.is_set():
                break
            time.sleep(backoff)
            backoff = min(backoff * 2.0, 30.0)


def public_market_stream(
    markets: list[str],
    cache: RealtimeMarketCache,
) -> BithumbWebSocketStream:
    normalized = sorted({market.upper() for market in markets})

    def subscription() -> list[dict[str, Any]]:
        return [
            {"ticket": f"b3-public-{uuid.uuid4()}"},
            {"type": "ticker", "codes": normalized, "is_only_realtime": True},
            {"type": "trade", "codes": normalized, "is_only_realtime": True},
            {"type": "orderbook", "codes": normalized, "is_only_realtime": True},
            {"format": "DEFAULT"},
        ]

    return BithumbWebSocketStream(
        name="bithumb-public-ws",
        url=PUBLIC_WS_URL,
        subscription_factory=subscription,
        cache=cache,
    )


def private_account_stream(
    markets: list[str],
    cache: RealtimeMarketCache,
    authorization_header_factory: Callable[[], str],
) -> BithumbWebSocketStream:
    normalized = sorted({market.upper() for market in markets})

    def subscription() -> list[dict[str, Any]]:
        return [
            {"ticket": f"b3-private-{uuid.uuid4()}"},
            {"type": "myOrder", "codes": normalized},
            {"type": "myAsset"},
            {"format": "DEFAULT"},
        ]

    return BithumbWebSocketStream(
        name="bithumb-private-ws",
        url=PRIVATE_WS_URL,
        subscription_factory=subscription,
        cache=cache,
        header_factory=lambda: [f"Authorization: {authorization_header_factory()}"],
    )
