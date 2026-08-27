from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

from .listing_history import postlisting_features, prelisting_features
from .listing_history_sources import BinanceSpotSource, CexSpotMarket, SpotListingSource, default_cex_sources
from .listing_history_store import ListingHistoryStore
from .listing_identity import ListingIdentity, listing_identity_gate
from .listing_venue_verifier import ListingVenueVerifier


PRE_WINDOW_SECONDS = 8 * 24 * 3600
POST_WINDOW_SECONDS = 8 * 24 * 3600
POST_COMPLETE_SECONDS = 7 * 24 * 3600
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
    notice_id: str = ""


class ListingHistoryCollector:
    """Collect public pre/post domestic-listing history after identity verification.

    This module does not discover identity and does not alter PAPER scores. It
    only consumes a verified identity, provider-verifies an exact foreign CEX
    pair, normalizes public candles and persists features for later validation.
    """

    def __init__(
        self,
        *,
        store: ListingHistoryStore | None = None,
        sources: Iterable[SpotListingSource] | None = None,
        venue_verifier: ListingVenueVerifier | None = None,
    ) -> None:
        self.store = store or ListingHistoryStore()
        self.sources = tuple(sources or default_cex_sources())
        self.venue_verifier = venue_verifier or ListingVenueVerifier()

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

        if listing_at > 0 and first_price <= 0:
            try:
                launch_rows = source.hourly_candles(
                    market.market,
                    start_ts=max(0.0, listing_at - 60.0),
                    end_ts=listing_at + 2 * 3600.0,
                )
            except Exception:
                launch_rows = []
            launch_rows = [
                row for row in launch_rows
                if listing_at - 3600.0 <= row.ts <= listing_at + 2 * 3600.0
            ]
            if launch_rows:
                first = sorted(launch_rows, key=lambda row: row.ts)[0]
                return listing_at, float(first.open)

        # Binance exchangeInfo does not expose launchTime. Its kline history can
        # explicitly request the first exchange candle without confusing it with
        # the T-8d research-window boundary.
        if listing_at <= 0 and isinstance(source, BinanceSpotSource):
            first = source.first_candle(market.market)
            if first is not None:
                return float(first.ts), float(first.open)
        return listing_at, first_price

    def _verified_market(
        self,
        identity: ListingIdentity,
        discovered: list[CexSpotMarket],
    ) -> tuple[CexSpotMarket | None, dict[str, Any]]:
        evidence_rows: list[dict[str, Any]] = []
        for market in sorted(discovered, key=self._rank_market):
            evidence = self.venue_verifier.verify(identity, market)
            evidence_rows.append({"market": market.market, **evidence})
            if evidence.get("verified"):
                basis = dict(market.match_basis or {})
                basis["provider_pair_verification"] = evidence.get("evidence") or {}
                verified = CexSpotMarket(
                    exchange=market.exchange,
                    market=market.market,
                    base_asset=market.base_asset,
                    quote_asset=market.quote_asset,
                    listing_at=market.listing_at,
                    state=market.state,
                    first_price=market.first_price,
                    match_confidence=market.match_confidence,
                    match_basis=basis,
                )
                return verified, {"status": "verified", "checks": evidence_rows}
        return None, {"status": "venue_unverified", "checks": evidence_rows}

    def collect_case(self, case: DomesticListingCase) -> dict[str, Any]:
        started = time.time()
        now = time.time()
        gate = listing_identity_gate(case.identity)
        case_key = self.store.upsert_case(
            domestic_exchange=case.exchange,
            domestic_market=case.market,
            domestic_notice_id=case.notice_id,
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
                discovered = source.discover(case.identity)
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

            market, venue_result = self._verified_market(case.identity, discovered)
            if market is None:
                source_results[source.exchange] = {
                    "status": "venue_unverified",
                    "markets": [row.to_dict() for row in discovered[:8]],
                    "venue_verification": venue_result,
                }
                continue

            listing_at, first_price = self._first_price_if_needed(source, market)
            start_ts = max(0.0, case.open_at - PRE_WINDOW_SECONDS)
            end_ts = min(now, case.open_at + POST_WINDOW_SECONDS)
            if listing_at > 0:
                start_ts = max(listing_at, start_ts)
            if end_ts <= start_ts:
                source_results[source.exchange] = {
                    "status": "waiting_for_market_time",
                    "markets": [market.to_dict()],
                    "venue_verification": venue_result,
                }
                continue
            try:
                candles = source.hourly_candles(market.market, start_ts=start_ts, end_ts=end_ts)
            except Exception as exc:
                source_results[source.exchange] = {
                    "status": "candle_error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "markets": [market.to_dict()],
                    "venue_verification": venue_result,
                }
                continue

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
                "venue_verification": venue_result,
                "domestic": {
                    "exchange": case.exchange,
                    "market": case.market,
                    "notice_id": case.notice_id,
                    "announcement_at": case.announcement_at,
                    "open_at": case.open_at,
                    "open_price": case.open_price if case.open_price > 0 else None,
                },
                "foreign": {
                    "exchange": market.exchange,
                    "market": market.market,
                    "quote_asset": market.quote_asset,
                    "listing_at": listing_at if listing_at > 0 else None,
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
                "venue_verification": venue_result,
            }

        if successful:
            if case.open_price <= 0:
                status = "waiting_for_domestic_open_price"
            elif now < case.open_at + POST_COMPLETE_SECONDS:
                status = "tracking_postlisting"
            else:
                status = "complete"
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
