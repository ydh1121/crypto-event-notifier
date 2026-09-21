from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from .listing_history import prelisting_features, price_at_or_before, reaction_features
from .listing_history_sources import BinanceSpotSource, CexSpotMarket, SpotListingSource, default_cex_sources
from .listing_history_store import ListingHistoryStore
from .listing_identity import ListingIdentity, listing_identity_gate
from .listing_quote_rate import ListingQuoteRateResolver
from .listing_venue_verifier import ListingVenueVerifier


PRE_WINDOW_SECONDS = 8 * 24 * 3600
POST_WINDOW_SECONDS = 8 * 24 * 3600
POST_COMPLETE_SECONDS = 7 * 24 * 3600
FINE_POST_WINDOW_SECONDS = 15 * 60
FEATURE_VERSION = 3
QUOTE_PRIORITY = {"USDT": 0, "USDC": 1, "USD": 2, "FDUSD": 3, "BTC": 4}


class QuoteRateResolver(Protocol):
    def resolve(self, quote_asset: str, target_ts: float) -> dict[str, Any]: ...


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
    """Collect verified foreign CEX history without mixing quote currencies.

    This module does not discover identity and does not alter PAPER scores. It
    consumes verified identity, provider-verifies an exact foreign CEX pair,
    normalizes public candles, resolves quote→KRW only when public evidence is
    available, and persists features for later validation.
    """

    def __init__(
        self,
        *,
        store: ListingHistoryStore | None = None,
        sources: Iterable[SpotListingSource] | None = None,
        venue_verifier: ListingVenueVerifier | None = None,
        quote_rate_resolver: QuoteRateResolver | None = None,
    ) -> None:
        self.store = store or ListingHistoryStore()
        self.sources = tuple(sources or default_cex_sources())
        self.venue_verifier = venue_verifier or ListingVenueVerifier()
        self.quote_rate_resolver = quote_rate_resolver or ListingQuoteRateResolver()

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
        fine_source_errors = 0
        quote_rate_cache: dict[str, dict[str, Any]] = {}
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

            minute_rows = []
            fine_status = "not_due"
            fine_error = ""
            fine_fetch = getattr(source, "minute_candles", None)
            if now >= case.open_at + 5 * 60:
                if callable(fine_fetch):
                    try:
                        minute_rows = fine_fetch(
                            market.market,
                            start_ts=case.open_at,
                            end_ts=min(now, case.open_at + FINE_POST_WINDOW_SECONDS),
                        )
                        fine_status = "collected" if minute_rows else "no_trade_candles"
                    except Exception as exc:
                        fine_source_errors += 1
                        fine_status = "source_error"
                        fine_error = f"{type(exc).__name__}: {exc}"[:300]
                else:
                    fine_source_errors += 1
                    fine_status = "unsupported"

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
            fine_stored = self.store.upsert_candles(
                case_key=case_key,
                source_exchange=market.exchange,
                source_market=market.market,
                candles=minute_rows,
            )

            quote = market.quote_asset.upper()
            if quote not in quote_rate_cache:
                try:
                    quote_rate_cache[quote] = self.quote_rate_resolver.resolve(quote, case.open_at)
                except Exception as exc:
                    quote_rate_cache[quote] = {
                        "status": "resolver_error",
                        "found": False,
                        "rate": 0.0,
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                    }
            quote_rate = quote_rate_cache[quote]
            quote_to_krw = float(quote_rate.get("rate") or 0.0) if quote_rate.get("found") else 0.0
            foreign_open = price_at_or_before(candles, case.open_at)
            foreign_open_price = float(foreign_open.get("price") or 0.0) if foreign_open else 0.0

            features: dict[str, Any] = {
                "version": FEATURE_VERSION,
                "identity_gate": gate,
                "venue_verification": venue_result,
                "domestic": {
                    "exchange": case.exchange,
                    "market": case.market,
                    "notice_id": case.notice_id,
                    "announcement_at": case.announcement_at,
                    "open_at": case.open_at,
                    "open_price_krw": case.open_price if case.open_price > 0 else None,
                },
                "foreign": {
                    "exchange": market.exchange,
                    "market": market.market,
                    "quote_asset": market.quote_asset,
                    "listing_at": listing_at if listing_at > 0 else None,
                    "first_price": first_price if first_price > 0 else None,
                    "price_at_domestic_open": foreign_open,
                    "match_confidence": market.match_confidence,
                    "match_basis": market.match_basis or {},
                },
                "quote_to_krw": quote_rate,
                "fine_reaction_source": {
                    "status": fine_status,
                    "error": fine_error,
                    "interval_seconds": 60 if minute_rows else None,
                    "candles": len(minute_rows),
                },
            }
            if case.open_price > 0:
                features["prelisting"] = prelisting_features(
                    candles,
                    domestic_open_at=case.open_at,
                    domestic_open_price=case.open_price,
                    quote_asset=market.quote_asset,
                    quote_to_krw_at_open=quote_to_krw,
                    foreign_listing_at=listing_at,
                    foreign_first_price=first_price,
                )
                features["foreign_postlisting"] = (
                    reaction_features(
                        candles,
                        anchor_at=case.open_at,
                        anchor_price=foreign_open_price,
                        fine_candles=minute_rows,
                    )
                    if foreign_open_price > 0
                    else {"status": "foreign_open_price_missing"}
                )
            else:
                features["prelisting"] = {"status": "waiting_for_domestic_open_price"}
                features["foreign_postlisting"] = {"status": "waiting_for_domestic_open_price"}
            self.store.upsert_features(
                case_key=case_key,
                source_exchange=market.exchange,
                source_market=market.market,
                features=features,
                feature_version=FEATURE_VERSION,
            )
            successful += 1
            source_results[source.exchange] = {
                "status": "collected",
                "market": market.market,
                "listing_at": listing_at,
                "first_price": first_price,
                "candles": len(candles),
                "stored": stored,
                "minute_candles": len(minute_rows),
                "minute_stored": fine_stored,
                "fine_reaction_status": fine_status,
                "fine_reaction_error": fine_error,
                "quote_to_krw": quote_rate,
                "domestic_listing_premium_pct": (
                    features.get("prelisting", {}).get("domestic_listing_premium_pct")
                    if isinstance(features.get("prelisting"), dict)
                    else None
                ),
                "venue_verification": venue_result,
            }

        if successful:
            if case.open_price <= 0:
                status = "waiting_for_domestic_open_price"
            elif fine_source_errors:
                status = "foreign_source_waiting"
            elif now < case.open_at + POST_COMPLETE_SECONDS:
                status = "tracking_postlisting"
            else:
                status = "complete"
        else:
            source_statuses = {
                str(value.get("status") or "")
                for value in source_results.values()
                if isinstance(value, dict)
            }
            if "venue_unverified" in source_statuses:
                status = "venue_verification_waiting"
            elif source_statuses & {"source_error", "candle_error", "waiting_for_market_time"}:
                status = "foreign_source_waiting"
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
