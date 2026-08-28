from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_launch_features import FEATURE_VERSION, build_dex_features
from .dex_launch_sources import DexCandle, GeckoTerminalDexSource
from .dex_launch_store import DexLaunchStore
from .listing_identity import ListingIdentity
from .listing_identity_resolver import ListingIdentityResolver
from .research_control import atomic_json


STATE_PATH = Path("b3_trader/data/research-platform/dex-launch-cycle-state.json")
MAX_CASES_PER_RUN = 1
MAX_CONTRACTS_PER_CASE = 2
MIN_POOL_LIQUIDITY_USD = 25_000.0
MIN_POOL_VOLUME_H24_USD = 10_000.0
DEX_OHLCV_HISTORY_SECONDS = 183 * 86400
DOMESTIC_HOURLY_LOOKBACK = 7 * 86400
DOMESTIC_HOURLY_FORWARD = 7 * 86400


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _filter(rows: list[DexCandle], start: float, end: float) -> list[DexCandle]:
    return [row for row in rows if float(start) <= row.ts <= float(end)]


def _stored_coingecko_id(row: dict[str, Any]) -> str:
    identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
    provider = str(identity.get("provider") or "").strip().lower()
    provider_id = str(identity.get("provider_id") or "").strip()
    return provider_id if provider == "coingecko" and provider_id else ""


class DexLaunchResearchCycle:
    """Exact-contract, public-source DEX sidecar; never wired to PAPER decisions."""

    def __init__(
        self,
        path: Path = DB_PATH,
        *,
        store: DexLaunchStore | None = None,
        identity_resolver: ListingIdentityResolver | None = None,
        source: GeckoTerminalDexSource | None = None,
        state_path: Path = STATE_PATH,
        max_cases_per_run: int = MAX_CASES_PER_RUN,
    ) -> None:
        self.path = Path(path)
        self.store = store or DexLaunchStore(self.path)
        self.identity_resolver = identity_resolver or ListingIdentityResolver()
        self.source = source or GeckoTerminalDexSource()
        self.state_path = Path(state_path)
        self.max_cases_per_run = max(1, min(3, int(max_cases_per_run)))
        self.min_liquidity_usd = _env_float("DEX_MIN_POOL_LIQUIDITY_USD", MIN_POOL_LIQUIDITY_USD)
        self.min_volume_h24_usd = _env_float("DEX_MIN_POOL_VOLUME_H24_USD", MIN_POOL_VOLUME_H24_USD)
        self._owns_store = store is None

    def close(self) -> None:
        if self._owns_store:
            self.store.close()

    def _coingecko_id(self, row: dict[str, Any]) -> tuple[str, str]:
        stored = _stored_coingecko_id(row)
        if stored:
            return stored, "stored_verified"
        try:
            result = self.identity_resolver.resolve(
                str(row.get("domestic_exchange") or ""),
                str(row.get("domestic_market") or ""),
            )
        except Exception as exc:
            return "", f"identity_error:{type(exc).__name__}"
        identity = result.get("identity") if isinstance(result, dict) else None
        if not result.get("verified") or not isinstance(identity, ListingIdentity):
            return "", str(result.get("status") or "identity_waiting")
        if identity.provider != "coingecko" or not identity.provider_id:
            return "", "coingecko_identity_missing"
        return str(identity.provider_id), "remote_verified"

    def _quality_pass(self, pool: dict[str, Any]) -> bool:
        return bool(
            _num(pool.get("reserve_usd")) >= self.min_liquidity_usd
            and _num(pool.get("volume_h24_usd")) >= self.min_volume_h24_usd
        )

    def _domestic_candles(
        self,
        *,
        network_id: str,
        pool_address: str,
        token_address: str,
        domestic_open_at: float,
    ) -> tuple[list[DexCandle], list[DexCandle]]:
        open_at = float(domestic_open_at or 0.0)
        if open_at <= 0:
            return [], []
        hourly_end = open_at + DOMESTIC_HOURLY_FORWARD + 3600
        hourly = self.source.ohlcv(
            network_id,
            pool_address,
            token_address,
            timeframe="hour",
            before_timestamp=hourly_end,
            limit=340,
            aggregate=1,
        )
        hourly = _filter(
            hourly,
            open_at - DOMESTIC_HOURLY_LOOKBACK - 3600,
            hourly_end,
        )
        minute_end = open_at + 16 * 60
        minute = self.source.ohlcv(
            network_id,
            pool_address,
            token_address,
            timeframe="minute",
            before_timestamp=minute_end,
            limit=24,
            aggregate=1,
        )
        minute = _filter(minute, open_at - 5 * 60, minute_end)
        return hourly, minute

    def _launch_candles(
        self,
        *,
        network_id: str,
        pool_address: str,
        token_address: str,
        pool_created_at: float,
        now: float,
    ) -> tuple[list[DexCandle], list[DexCandle]]:
        created = float(pool_created_at or 0.0)
        if created <= 0 or now - created > DEX_OHLCV_HISTORY_SECONDS:
            return [], []
        hour_end = created + 25 * 3600
        hourly = self.source.ohlcv(
            network_id,
            pool_address,
            token_address,
            timeframe="hour",
            before_timestamp=hour_end,
            limit=26,
            aggregate=1,
        )
        hourly = _filter(hourly, created - 3600, hour_end)
        minute_end = created + 16 * 60
        minute = self.source.ohlcv(
            network_id,
            pool_address,
            token_address,
            timeframe="minute",
            before_timestamp=minute_end,
            limit=20,
            aggregate=1,
        )
        minute = _filter(minute, created - 60, minute_end)
        return hourly, minute

    def _research_case(self, row: dict[str, Any], now: float) -> dict[str, Any]:
        case_key = str(row.get("case_key") or "")
        coingecko_id, identity_status = self._coingecko_id(row)
        if not coingecko_id:
            self.store.upsert_case_status(case_key, status="identity_waiting", error=identity_status)
            return {"case_key": case_key, "status": "identity_waiting", "identity_status": identity_status}

        try:
            contracts = self.source.coin_contracts(coingecko_id)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:400]
            self.store.upsert_case_status(
                case_key,
                coingecko_id=coingecko_id,
                status="source_waiting",
                error=error,
            )
            return {"case_key": case_key, "status": "source_waiting", "error": error}
        if not contracts:
            self.store.upsert_case_status(
                case_key,
                coingecko_id=coingecko_id,
                status="no_contract_identity",
                contract_count=0,
            )
            return {"case_key": case_key, "status": "no_contract_identity", "coingecko_id": coingecko_id}

        required_platforms = {str(item.get("platform_id") or "") for item in contracts if item.get("platform_id")}
        try:
            network_map = self.source.network_map(required_platforms)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:400]
            self.store.upsert_case_status(
                case_key,
                coingecko_id=coingecko_id,
                status="source_waiting",
                contract_count=len(contracts),
                error=error,
            )
            return {"case_key": case_key, "status": "source_waiting", "error": error}

        mapped = [
            {**item, "network_id": network_map.get(str(item.get("platform_id") or ""), "")}
            for item in contracts
            if network_map.get(str(item.get("platform_id") or ""), "")
        ]
        if not mapped:
            for item in contracts[:MAX_CONTRACTS_PER_CASE]:
                self.store.upsert_asset(
                    case_key=case_key,
                    coingecko_id=coingecko_id,
                    platform_id=str(item.get("platform_id") or ""),
                    network_id="",
                    token_address=str(item.get("token_address") or ""),
                    identity_status="network_unmapped",
                )
            self.store.upsert_case_status(
                case_key,
                coingecko_id=coingecko_id,
                status="network_unmapped",
                contract_count=len(contracts),
            )
            return {
                "case_key": case_key,
                "status": "network_unmapped",
                "coingecko_id": coingecko_id,
                "platforms": sorted(required_platforms),
            }

        accepted_total = 0
        researched_assets = 0
        source_errors: list[str] = []
        asset_results: list[dict[str, Any]] = []
        domestic_open_at = _num(row.get("domestic_open_at"))

        for item in mapped[:MAX_CONTRACTS_PER_CASE]:
            platform_id = str(item.get("platform_id") or "")
            network_id = str(item.get("network_id") or "")
            token_address = str(item.get("token_address") or "")
            asset_key = self.store.upsert_asset(
                case_key=case_key,
                coingecko_id=coingecko_id,
                platform_id=platform_id,
                network_id=network_id,
                token_address=token_address,
                identity_status="exact_contract_verified",
            )
            try:
                pools = self.source.token_pools(network_id, token_address)
            except Exception as exc:
                source_errors.append(f"{platform_id}:{type(exc).__name__}:{exc}"[:300])
                asset_results.append({"asset_key": asset_key, "status": "source_waiting", "pool_count": 0})
                continue

            accepted = [pool for pool in pools if self._quality_pass(pool)]
            primary = accepted[0] if accepted else None
            for pool in pools:
                is_primary = bool(primary and pool.get("pool_address") == primary.get("pool_address"))
                self.store.upsert_pool(
                    asset_key=asset_key,
                    pool=pool,
                    gate_status="accepted" if self._quality_pass(pool) else "rejected_quality",
                    selected_primary=is_primary,
                )
            accepted_total += len(accepted)
            if primary is None:
                asset_results.append(
                    {
                        "asset_key": asset_key,
                        "network_id": network_id,
                        "token_address": token_address,
                        "status": "pool_quality_waiting",
                        "pool_count": len(pools),
                        "accepted_pool_count": 0,
                    }
                )
                continue

            pool_address = str(primary.get("pool_address") or "")
            try:
                domestic_hourly, domestic_minute = self._domestic_candles(
                    network_id=network_id,
                    pool_address=pool_address,
                    token_address=token_address,
                    domestic_open_at=domestic_open_at,
                )
                launch_hourly, launch_minute = self._launch_candles(
                    network_id=network_id,
                    pool_address=pool_address,
                    token_address=token_address,
                    pool_created_at=_num(primary.get("pool_created_at")),
                    now=now,
                )
            except Exception as exc:
                source_errors.append(f"{platform_id}:{type(exc).__name__}:{exc}"[:300])
                asset_results.append(
                    {
                        "asset_key": asset_key,
                        "status": "source_waiting",
                        "pool_address": pool_address,
                    }
                )
                continue

            self.store.upsert_candles(
                asset_key=asset_key,
                pool_address=pool_address,
                series_kind="domestic_hourly",
                candles=domestic_hourly,
            )
            self.store.upsert_candles(
                asset_key=asset_key,
                pool_address=pool_address,
                series_kind="domestic_minute",
                candles=domestic_minute,
            )
            self.store.upsert_candles(
                asset_key=asset_key,
                pool_address=pool_address,
                series_kind="launch_hourly",
                candles=launch_hourly,
            )
            self.store.upsert_candles(
                asset_key=asset_key,
                pool_address=pool_address,
                series_kind="launch_minute",
                candles=launch_minute,
            )
            features = build_dex_features(
                domestic_open_at=domestic_open_at,
                pool_created_at=_num(primary.get("pool_created_at")),
                domestic_hourly=domestic_hourly,
                domestic_minute=domestic_minute,
                launch_hourly=launch_hourly,
                launch_minute=launch_minute,
                reserve_usd=_num(primary.get("reserve_usd")),
                volume_h24_usd=_num(primary.get("volume_h24_usd")),
                min_liquidity_usd=self.min_liquidity_usd,
                min_volume_h24_usd=self.min_volume_h24_usd,
            )
            self.store.upsert_features(
                asset_key=asset_key,
                pool_address=pool_address,
                feature_version=FEATURE_VERSION,
                features=features,
            )
            researched_assets += 1
            asset_results.append(
                {
                    "asset_key": asset_key,
                    "network_id": network_id,
                    "token_address": token_address,
                    "status": "collected",
                    "pool_address": pool_address,
                    "pool_count": len(pools),
                    "accepted_pool_count": len(accepted),
                    "domestic_hourly": len(domestic_hourly),
                    "domestic_minute": len(domestic_minute),
                    "launch_hourly": len(launch_hourly),
                    "launch_minute": len(launch_minute),
                    "p5m_exact_minute": bool(
                        ((features.get("domestic_listing_window") or {}).get("p5m_exact_minute"))
                        if isinstance(features.get("domestic_listing_window"), dict)
                        else False
                    ),
                }
            )

        if researched_assets > 0:
            status = "complete"
        elif accepted_total <= 0 and not source_errors:
            status = "pool_quality_waiting"
        else:
            status = "source_waiting"
        self.store.upsert_case_status(
            case_key,
            coingecko_id=coingecko_id,
            status=status,
            contract_count=len(contracts),
            accepted_pool_count=accepted_total,
            error="; ".join(source_errors)[:500],
        )
        return {
            "case_key": case_key,
            "market": row.get("domestic_market"),
            "status": status,
            "identity_status": identity_status,
            "coingecko_id": coingecko_id,
            "contract_count": len(contracts),
            "mapped_contract_count": len(mapped),
            "accepted_pool_count": accepted_total,
            "researched_assets": researched_assets,
            "source_errors": source_errors,
            "assets": asset_results,
        }

    def run_once(self) -> dict[str, Any]:
        started = time.time()
        now = time.time()
        pending = self.store.listing_cases(limit=500)
        picked = pending[: self.max_cases_per_run]
        results = [self._research_case(row, now) for row in picked]
        summary = {
            "status": "researched" if picked else "waiting_for_cases",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "feature_version": FEATURE_VERSION,
            "min_pool_liquidity_usd": self.min_liquidity_usd,
            "min_pool_volume_h24_usd": self.min_volume_h24_usd,
            "pending_cases": len(pending),
            "processed": len(picked),
            "complete": sum(1 for row in results if row.get("status") == "complete"),
            "identity_waiting": sum(1 for row in results if row.get("status") == "identity_waiting"),
            "pool_quality_waiting": sum(1 for row in results if row.get("status") == "pool_quality_waiting"),
            "source_waiting": sum(1 for row in results if row.get("status") == "source_waiting"),
            "results": results,
            "elapsed_seconds": round(time.time() - started, 3),
        }
        atomic_json(self.state_path, {**summary, "updated_at": time.time()})
        return summary


def main() -> None:
    cycle = DexLaunchResearchCycle()
    try:
        print(json.dumps(cycle.run_once(), ensure_ascii=False, indent=2))
    finally:
        cycle.close()


if __name__ == "__main__":
    main()
