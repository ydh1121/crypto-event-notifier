from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests

TWELVE_DATA_API_ROOT = "https://api.twelvedata.com"
TWELVE_DATA_TIME_SERIES_URL = f"{TWELVE_DATA_API_ROOT}/time_series"
TWELVE_DATA_PROVIDER_ID = "twelve_data_us_indices"
TWELVE_DATA_AUTHORITY = "Twelve Data"
TWELVE_DATA_DATA_RIGHTS = "provider_subscription_market_data_internal_research_only_unless_license_allows_distribution"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_ATTEMPTS = 2
SUPPORTED_INTERVALS = {"1min", "5min", "15min", "30min", "45min", "1h", "2h", "4h", "8h"}
DEFAULT_INDEX_SYMBOLS = {
    "SP500": "SPX",
    "NASDAQ_COMPOSITE": "IXIC",
    "VIX": "VIX",
}


@dataclass(frozen=True)
class IndexBar:
    market_id: str
    requested_symbol: str
    provider_symbol: str
    interval: str
    datetime: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    exchange: str
    exchange_timezone: str
    instrument_type: str


class TwelveDataIndexClient:
    """Bounded Twelve Data intraday client for SPX, Nasdaq Composite and VIX.

    The API key is sent in the recommended Authorization header so it does not
    appear in request URLs or ordinary exception text. This client is research
    data only and has no scoring, PAPER decision, sizing or order authority.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        session: Any | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        attempts: int = DEFAULT_ATTEMPTS,
        symbols: dict[str, str] | None = None,
    ) -> None:
        configured = api_key if api_key is not None else os.getenv("TWELVE_DATA_API_KEY", "")
        self.api_key = str(configured or "").strip()
        self.session = session or requests.Session()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.attempts = max(1, min(3, int(attempts)))

        defaults = {
            "SP500": os.getenv("TWELVE_DATA_SP500_SYMBOL", DEFAULT_INDEX_SYMBOLS["SP500"]),
            "NASDAQ_COMPOSITE": os.getenv(
                "TWELVE_DATA_NASDAQ_SYMBOL", DEFAULT_INDEX_SYMBOLS["NASDAQ_COMPOSITE"]
            ),
            "VIX": os.getenv("TWELVE_DATA_VIX_SYMBOL", DEFAULT_INDEX_SYMBOLS["VIX"]),
        }
        if symbols:
            defaults.update(symbols)
        self.symbols = {
            str(key or "").strip().upper(): str(value or "").strip().upper()
            for key, value in defaults.items()
            if str(key or "").strip() and str(value or "").strip()
        }

    @property
    def credential_status(self) -> str:
        return "ready" if self.api_key else "missing"

    def required_symbols(self) -> dict[str, str]:
        required = {key: self.symbols.get(key, "") for key in DEFAULT_INDEX_SYMBOLS}
        missing = [key for key, symbol in required.items() if not symbol]
        if missing:
            raise ValueError(f"missing Twelve Data index symbol configuration: {missing}")
        return required

    @staticmethod
    def _parse_number(value: object, *, name: str) -> float:
        try:
            parsed = float(str(value or "").replace(",", ""))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Twelve Data bar {name} is invalid") from exc
        return parsed

    def fetch_time_series(
        self,
        market_id: str,
        *,
        interval: str = "1min",
        outputsize: int = 3,
    ) -> list[IndexBar]:
        if self.credential_status != "ready":
            raise ValueError("Twelve Data API credential is missing")

        clean_market = str(market_id or "").strip().upper()
        symbols = self.required_symbols()
        if clean_market not in symbols:
            raise ValueError(f"unsupported U.S. index market_id: {market_id!r}")
        symbol = symbols[clean_market]

        clean_interval = str(interval or "").strip().lower()
        if clean_interval not in SUPPORTED_INTERVALS:
            raise ValueError(f"unsupported Twelve Data intraday interval: {interval!r}")
        size = max(1, min(32, int(outputsize)))

        params = {
            "symbol": symbol,
            "interval": clean_interval,
            "outputsize": str(size),
            "order": "asc",
            "format": "JSON",
        }
        headers = {
            "Authorization": f"apikey {self.api_key}",
            "User-Agent": "crypto-event-notifier-phase5/1.0",
            "Accept": "application/json",
        }

        response = None
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.session.get(
                    TWELVE_DATA_TIME_SERIES_URL,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                status_code = int(getattr(response, "status_code", 200))
                if status_code in {409, 429, 500, 502, 503, 504}:
                    last_error = RuntimeError(f"Twelve Data transient HTTP {status_code}")
                    if attempt + 1 < self.attempts:
                        time.sleep(0.25 * (attempt + 1))
                        continue
                response.raise_for_status()
                break
            except (requests.ConnectionError, requests.Timeout, RuntimeError) as exc:
                last_error = exc
                if attempt + 1 >= self.attempts:
                    raise
                time.sleep(0.25 * (attempt + 1))
        else:
            if last_error is not None:
                raise last_error
            raise RuntimeError("Twelve Data request failed")

        if response is None:
            raise RuntimeError("Twelve Data request returned no response")

        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Twelve Data response must be a JSON object")
        if str(body.get("status") or "").strip().casefold() == "error":
            code = str(body.get("code") or "provider_error").strip()
            message = " ".join(str(body.get("message") or "provider error").split())[:220]
            raise ValueError(f"Twelve Data error {code}: {message}")

        meta = body.get("meta")
        values = body.get("values")
        if not isinstance(meta, dict) or not isinstance(values, list) or not values:
            raise ValueError("Twelve Data response is missing meta/values")

        provider_symbol = str(meta.get("symbol") or "").strip().upper()
        if not provider_symbol:
            raise ValueError("Twelve Data response is missing meta.symbol")
        instrument_type = str(meta.get("type") or "").strip()
        if instrument_type and "index" not in instrument_type.casefold():
            raise ValueError(
                f"Twelve Data symbol {symbol} resolved to non-index type {instrument_type!r}"
            )

        exchange = str(meta.get("exchange") or "").strip()
        exchange_timezone = str(meta.get("exchange_timezone") or "").strip()
        result: list[IndexBar] = []
        for raw in values:
            if not isinstance(raw, dict):
                continue
            stamp = str(raw.get("datetime") or "").strip()
            if not stamp:
                continue
            volume_raw = raw.get("volume")
            volume = None
            if volume_raw not in {None, "", "null"}:
                try:
                    volume = float(str(volume_raw).replace(",", ""))
                except (TypeError, ValueError):
                    volume = None
            result.append(
                IndexBar(
                    market_id=clean_market,
                    requested_symbol=symbol,
                    provider_symbol=provider_symbol,
                    interval=clean_interval,
                    datetime=stamp,
                    open=self._parse_number(raw.get("open"), name="open"),
                    high=self._parse_number(raw.get("high"), name="high"),
                    low=self._parse_number(raw.get("low"), name="low"),
                    close=self._parse_number(raw.get("close"), name="close"),
                    volume=volume,
                    exchange=exchange,
                    exchange_timezone=exchange_timezone,
                    instrument_type=instrument_type,
                )
            )

        if not result:
            raise ValueError("Twelve Data response produced no valid intraday bars")
        return result
