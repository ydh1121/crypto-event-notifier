from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

from .listing_history import postlisting_features, prelisting_features
from .listing_history_sources import BinanceSpotSource, CexSpotMarket, SpotListingSource, default_cex_sources
from .listing_history_store import ListingHistoryStore
from .listing_identity import ListingIdentity, listing_identity_gate


PRE_WINDOW_SECONDS = 8 * 24 * 3600
POST_WINDOW_SECONDS = 8 * 24 * 3600
QUOTE_PRIORITY = {"USDT": 0, "USDC": 1, "USD": 2, "FDUSD": 3, "BTC": 4}


@dataclass(frozen=True)
class DomesticListingCase:
    exchange: str
    market: str
    symbol: str
    announcement_at: float
    open_at: float
    open_price: float
    identity: ListingIdentity


class ListingHistoryCollector:
    """Collect public pre/post domestic-listing history after identity verification.

    This module does not discover identity and does not alter PAPER scores. It
    only consumes a verified identity, normalizes public CEX data and persists
    features for later validation.
    """

    def __init__(
        self,
        *,
        store: ListingHistoryStore | None = None,
        sources: Iterable[SpotListingSource] | None = None,
    ) -> None:
        self.store = store or ListingHistoryStore()
        self.sources = tuple(sources or default_cex_sources())

    def close(self) -> None:
        self.store.close()

    @staticmethod
    def _rank_market(row: CexSpotMarket) -> tuple[int, float, str]:
        return (
            QUOTE_PRIORITY.get(row.quote_asset.upper(), 99),
            row.listing_at if row.listing_at > 0 else float("inf"),
            row.market,
        )

    @staticmethod
    def _first_price_if_needed(source: SpotListingSource, market: CexSpotMarket) -> tuple[float, float]:
        listing_at = float(market.listing_at or 0)
        first_price = float(market.first_price or 0)
        if listing_at > 0 and first_price > 0:
            return listing_at, first_price
        if isinstance(source, BinanceSpotSource):
            first = source.first_candle(market.market)
            if first is not None:
                return listing_at or first.ts, first_price or first.open
        return listing_at, first_price

    def collect_case(self, case: DomesticListingCase) -> dict[str, Any]:
        started = time.time()
        gate = listing_identity_gate(case.identity)
        case_key = self.store.upsert_case(
            domestic_exchange=case.exchange,
            domestic_market=case.market,
            symbol=case.symbol,
            announcement_at=case.announcement_at,
            domestic_open_at=case.open_at,
            domestic_open_price=case.open_price,
            identity=case.identity,
            identity_verified=bool(gate["verified"]),
            status="collecting" if gate["verified"] else "rejected_identity",
        )
        if not gate["verified"]:
            return {
                "status": "rejected_identity",
                "case_key": case_key,
                "identity_gate": gate,
                "sources": {},
                "elapsed_seconds": round(time.time() - started, 3),
            }
        if case.open_at <= 0:
            self.store.update_case_status(case_key, "waiting_for_domestic_open")
            return {
                "status": "waiting_for_domestic_open",
                "case_key": case_key,
                "identity_gate": gate,
                "sources": {},
                "elapsed_seconds": round(time.time() - started, 3),
            }

        source_results: dict[str, Any] = {}
        successful = 0
        for source in self.sources:
            try:
                discovered = sorted(source.discover(case.identity), key=self._rank_market)
            except Exception as exc:
                source_results[source.exchange] = {
                    "status": "source_error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "markets": [],
                }
                continue
            if not discovered:
                source_results[source.exchange] = {"status": "not_listed", "markets": []}
                continue

            # One preferred quote market per CEX is enough for the first
            # pre-listing feature set. Additional pairs can be added later as
            # independent sources without changing the domain/store contract.
            market = discovered[0]
            listing_at, first_price = self._first_price_if_needed(source, market)
            start_ts = max(0.0, case.open_at - PRE_WINDOW_SECONDS)
            end_ts = case.open_at + POST_WINDOW_SECONDS
            if listing_at > 0:
                start_ts = max(listing_at, start_ts)
            try:
                candles = source.hourly_candles(market.market, start_ts=start_ts, end_ts=end_ts)
            except Exception as exc:
                source_results[source.exchange] = {
                    "status": "candle_error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "markets": [market.to_dict()],
                }
                continue

            if first_price <= 0 and candles:
                first_price = candles[0].open
            if listing_at <= 0 and candles:
                listing_at = candles[0].ts

            self.store.upsert_source(
                case_key=case_key,
                source_exchange=market.exchange,
                source_market=market.market,
                base_asset=market.base_asset,
                quote_asset=market.quote_asset,
                source_listing_at=listing_at,
                first_price=first_price,
                match_confidence=market.match_confidence,
                match_basis=market.match_basis,
            )
            stored = self.store.upsert_candles(
                case_key=case_key,
                source_exchange=market.exchange,
                source_market=market.market,
                candles=candles,
            )

            features: dict[str, Any] = {
                "version": 1,
                "identity_gate": gate,
                "domestic": {
                    "exchange": case.exchange,
                    "market": case.market,
                    "announcement_at": case.announcement_at,
                    "open_at": case.open_at,
                    "open_price": case.open_price if case.open_price > 0 else None,
                },
                "foreign": {
                    "exchange": market.exchange,
                    "market": market.market,
                    "quote_asset": market.quote_asset,
                    "listing_at": listing_at,
                    "first_price": first_price if first_price > 0 else None,
                    "match_confidence": market.match_confidence,
                    "match_basis": market.match_basis or {},
                },
            }
            if case.open_price > 0:
                features["prelisting"] = prelisting_features(
                    candles,
                    domestic_open_at=case.open_at,
                    domestic_open_price=case.open_price,
                    foreign_listing_at=listing_at,
                    foreign_first_price=first_price,
                )
                features["postlisting"] = postlisting_features(
                    candles,
                    domestic_open_at=case.open_at,
                    domestic_open_price=case.open_price,
                )
            else:
                features["prelisting"] = {"status": "waiting_for_domestic_open_price"}
                features["postlisting"] = {"status": "waiting_for_domestic_open_price"}
            self.store.upsert_features(
                case_key=case_key,
                source_exchange=market.exchange,
                source_market=market.market,
                features=features,
                feature_version=1,
            )
            successful += 1
            source_results[source.exchange] = {
                "status": "collected",
                "market": market.market,
                "listing_at": listing_at,
                "first_price": first_price,
                "candles": len(candles),
                "stored": stored,
            }

        if successful:
            status = "complete" if case.open_price > 0 else "waiting_for_domestic_open_price"
        else:
            status = "no_foreign_market_found"
        self.store.update_case_status(case_key, status)
        return {
            "status": status,
            "case_key": case_key,
            "identity_gate": gate,
            "sources_ok": successful,
            "sources": source_results,
            "elapsed_seconds": round(time.time() - started, 3),
        }
