from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .http_retry import get_with_retry
from .research_control import atomic_json


GT_BASE_URL = "https://api.geckoterminal.com/api/v2"
GT_ACCEPT = "application/json;version=20230203"
CG_DETAIL_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}"
USER_AGENT = "crypto-research-dex-launch/42"
NETWORK_CACHE_PATH = Path("b3_trader/data/research-platform/geckoterminal-network-map.json")
NETWORK_CACHE_SECONDS = 24 * 3600
DEFAULT_GT_MIN_INTERVAL_SECONDS = 6.2
MAX_NETWORK_PAGES = 10
MAX_POOL_ROWS = 20
MAX_OHLCV_RESULTS = 1000


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _parse_time(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def normalize_contract_address(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.startswith("0x") or raw.startswith("0X"):
        return raw.lower()
    return raw


@dataclass(frozen=True)
class DexCandle:
    ts: float
    open: float
    high: float
    low: float
    close: float
    volume_usd: float
    interval_seconds: int


class GeckoTerminalDexSource:
    """Public DEX source keyed only by exact chain and contract addresses."""

    def __init__(
        self,
        *,
        network_cache_path: Path = NETWORK_CACHE_PATH,
        now_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
        min_interval_seconds: float | None = None,
    ) -> None:
        self.network_cache_path = Path(network_cache_path)
        self.now_fn = now_fn
        self.sleep_fn = sleep_fn
        configured = os.getenv("DEX_GT_MIN_INTERVAL_SECONDS", "").strip()
        if min_interval_seconds is None:
            try:
                min_interval_seconds = float(configured) if configured else DEFAULT_GT_MIN_INTERVAL_SECONDS
            except ValueError:
                min_interval_seconds = DEFAULT_GT_MIN_INTERVAL_SECONDS
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self._last_gt_request_at = 0.0
        self._network_map: dict[str, str] = {}

    def _pace(self) -> None:
        if self.min_interval_seconds <= 0 or self._last_gt_request_at <= 0:
            return
        delay = self.min_interval_seconds - (self.now_fn() - self._last_gt_request_at)
        if delay > 0:
            self.sleep_fn(delay)

    def _gt_get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._pace()
        try:
            response, _retries = get_with_retry(
                f"{GT_BASE_URL}{path}",
                headers={"Accept": GT_ACCEPT, "User-Agent": USER_AGENT},
                params=params or {},
                timeout=18,
                attempts=3,
            )
        finally:
            self._last_gt_request_at = self.now_fn()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("GeckoTerminal returned a non-object response")
        return payload

    @staticmethod
    def _read_cache(path: Path, now: float) -> dict[str, str]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        updated_at = _num(payload.get("updated_at"))
        if updated_at <= 0 or now - updated_at > NETWORK_CACHE_SECONDS:
            return {}
        source = payload.get("platform_to_network")
        if not isinstance(source, dict):
            return {}
        return {
            str(platform).strip(): str(network).strip()
            for platform, network in source.items()
            if str(platform).strip() and str(network).strip()
        }

    def network_map(self, required_platforms: set[str] | None = None) -> dict[str, str]:
        required = {str(item).strip() for item in (required_platforms or set()) if str(item).strip()}
        if not self._network_map:
            self._network_map = self._read_cache(self.network_cache_path, self.now_fn())
        if required and required.issubset(self._network_map):
            return dict(self._network_map)
        if self._network_map and not required:
            return dict(self._network_map)

        mapping = dict(self._network_map)
        for page in range(1, MAX_NETWORK_PAGES + 1):
            payload = self._gt_get("/networks", params={"page": page})
            rows = payload.get("data") if isinstance(payload.get("data"), list) else []
            if not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                attributes = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
                platform = str(attributes.get("coingecko_asset_platform_id") or "").strip()
                network = str(row.get("id") or "").strip()
                if platform and network:
                    mapping[platform] = network
            if required and required.issubset(mapping):
                break

        self._network_map = mapping
        if mapping:
            atomic_json(
                self.network_cache_path,
                {"updated_at": self.now_fn(), "platform_to_network": dict(sorted(mapping.items()))},
            )
        return dict(mapping)

    def coin_contracts(self, coingecko_id: str) -> list[dict[str, str]]:
        coin_id = str(coingecko_id or "").strip()
        if not coin_id:
            return []
        response, _retries = get_with_retry(
            CG_DETAIL_URL.format(coin_id=coin_id),
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "false",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false",
            },
            timeout=18,
            attempts=3,
        )
        payload = response.json()
        if not isinstance(payload, dict) or str(payload.get("id") or "").strip() != coin_id:
            return []
        platforms = payload.get("platforms") if isinstance(payload.get("platforms"), dict) else {}
        result: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for platform_id, raw_address in platforms.items():
            platform = str(platform_id or "").strip()
            address = normalize_contract_address(raw_address)
            if not platform or not address:
                continue
            key = (platform, address)
            if key in seen:
                continue
            seen.add(key)
            result.append({"platform_id": platform, "token_address": address})
        return result

    @staticmethod
    def _included_addresses(payload: dict[str, Any]) -> dict[str, str]:
        result: dict[str, str] = {}
        included = payload.get("included") if isinstance(payload.get("included"), list) else []
        for row in included:
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id") or "").strip()
            attributes = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
            address = normalize_contract_address(attributes.get("address"))
            if row_id and address:
                result[row_id] = address
        return result

    def token_pools(self, network_id: str, token_address: str) -> list[dict[str, Any]]:
        network = str(network_id or "").strip()
        token = normalize_contract_address(token_address)
        if not network or not token:
            return []
        payload = self._gt_get(
            f"/networks/{network}/tokens/{token}/pools",
            params={
                "page": 1,
                "sort": "h24_volume_usd_liquidity_desc",
                "include": "base_token,quote_token,dex",
            },
        )
        addresses = self._included_addresses(payload)
        rows = payload.get("data") if isinstance(payload.get("data"), list) else []
        result: list[dict[str, Any]] = []
        for row in rows[:MAX_POOL_ROWS]:
            if not isinstance(row, dict):
                continue
            attributes = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
            relationships = row.get("relationships") if isinstance(row.get("relationships"), dict) else {}

            def relation_id(name: str) -> str:
                relation = relationships.get(name) if isinstance(relationships.get(name), dict) else {}
                data = relation.get("data") if isinstance(relation.get("data"), dict) else {}
                return str(data.get("id") or "").strip()

            base_id = relation_id("base_token")
            quote_id = relation_id("quote_token")
            volume = attributes.get("volume_usd") if isinstance(attributes.get("volume_usd"), dict) else {}
            pool_address = normalize_contract_address(attributes.get("address"))
            if not pool_address:
                continue
            result.append(
                {
                    "pool_address": pool_address,
                    "name": str(attributes.get("name") or ""),
                    "dex_id": relation_id("dex"),
                    "pool_created_at": _parse_time(attributes.get("pool_created_at")),
                    "reserve_usd": _num(attributes.get("reserve_in_usd")),
                    "volume_h24_usd": _num(volume.get("h24")),
                    "volume_h6_usd": _num(volume.get("h6")),
                    "volume_h1_usd": _num(volume.get("h1")),
                    "volume_m5_usd": _num(volume.get("m5")),
                    "base_token_address": addresses.get(base_id, ""),
                    "quote_token_address": addresses.get(quote_id, ""),
                }
            )
        return result

    def ohlcv(
        self,
        network_id: str,
        pool_address: str,
        token_address: str,
        *,
        timeframe: str,
        before_timestamp: float,
        limit: int,
        aggregate: int = 1,
    ) -> list[DexCandle]:
        network = str(network_id or "").strip()
        pool = normalize_contract_address(pool_address)
        token = normalize_contract_address(token_address)
        frame = str(timeframe or "").strip().lower()
        if frame not in {"minute", "hour", "day"} or not network or not pool or not token:
            return []
        interval = {"minute": 60, "hour": 3600, "day": 86400}[frame] * max(1, int(aggregate))
        payload = self._gt_get(
            f"/networks/{network}/pools/{pool}/ohlcv/{frame}",
            params={
                "aggregate": max(1, int(aggregate)),
                "before_timestamp": int(float(before_timestamp)),
                "limit": max(1, min(MAX_OHLCV_RESULTS, int(limit))),
                "currency": "usd",
                "token": token,
                "include_empty_intervals": "false",
            },
        )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        attributes = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
        rows = attributes.get("ohlcv_list") if isinstance(attributes.get("ohlcv_list"), list) else []
        result: list[DexCandle] = []
        for item in rows:
            if not isinstance(item, list) or len(item) < 6:
                continue
            ts, open_, high, low, close, volume = item[:6]
            candle = DexCandle(
                ts=_num(ts),
                open=_num(open_),
                high=_num(high),
                low=_num(low),
                close=_num(close),
                volume_usd=_num(volume),
                interval_seconds=interval,
            )
            if candle.ts > 0 and candle.close > 0:
                result.append(candle)
        result.sort(key=lambda row: row.ts)
        return result
