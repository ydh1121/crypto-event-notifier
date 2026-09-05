from __future__ import annotations

import json
import math
import sqlite3
import time
from typing import Any, Iterable, Protocol

from .listing_history import ListingCandle
from .listing_history_sources import CexSpotMarket, SpotListingSource, default_cex_sources
from .listing_identity import ListingIdentity
from .listing_identity_resolver import ListingIdentityResolver
from .listing_quote_rate import ListingQuoteRateResolver
from .listing_venue_verifier import ListingVenueVerifier

FEATURE_VERSION = 1
MAX_FOREIGN_PRICE_AGE_SECONDS = 15.0 * 60.0
QUOTE_PRIORITY = {"USDT": 0, "USDC": 1, "BTC": 2, "KRW": 3}
SOURCE_PRIORITY = {"binance": 0, "okx": 1, "bybit": 2}


class IdentityResolver(Protocol):
    def resolve(self, exchange: str, market: str) -> dict[str, Any]: ...


class VenueVerifier(Protocol):
    def verify(self, identity: ListingIdentity, market: CexSpotMarket) -> dict[str, Any]: ...


class QuoteResolver(Protocol):
    def resolve(self, quote_asset: str, target_ts: float) -> dict[str, Any]: ...


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _symbol(market: str) -> str:
    value = str(market or "").upper()
    return value.split("-", 1)[1] if value.startswith("KRW-") and "-" in value else ""


def _market_rank(row: CexSpotMarket) -> tuple[int, int, str]:
    return (
        QUOTE_PRIORITY.get(str(row.quote_asset).upper(), 99),
        SOURCE_PRIORITY.get(str(row.exchange).lower(), 99),
        str(row.market),
    )


class MarketDomesticPremiumEngine:
    """Latest-only verified foreign-reference premium/discount research.

    The domestic market must first have a ready Bithumb/Upbit local 1m gap.
    Both domestic profiles must independently resolve to the same verified
    provider identity. Foreign pairs are accepted only after the existing
    CoinGecko exact coin-id × venue × pair verifier passes. Quote currencies are
    converted to KRW only through the existing public quote-rate resolver.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        identity_resolver: IdentityResolver | None = None,
        sources: Iterable[SpotListingSource] | None = None,
        venue_verifier: VenueVerifier | None = None,
        quote_resolver: QuoteResolver | None = None,
    ) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.identity_resolver = identity_resolver or ListingIdentityResolver()
        self.sources = tuple(sources or default_cex_sources())
        self.venue_verifier = venue_verifier or ListingVenueVerifier()
        self.quote_resolver = quote_resolver or ListingQuoteRateResolver()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_domestic_premium_mx(
                market TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                identity_verified INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                bithumb_price_krw REAL,
                upbit_price_krw REAL,
                reference_exchange TEXT,
                reference_market TEXT,
                reference_quote_asset TEXT,
                reference_price_quote REAL,
                quote_to_krw REAL,
                reference_price_krw REAL,
                reference_source_ts REAL,
                bithumb_premium_pct REAL,
                upbit_premium_pct REAL,
                foreign_verified_sources INTEGER NOT NULL DEFAULT 0,
                foreign_price_gap_pct REAL,
                source_evidence_json TEXT NOT NULL DEFAULT '[]',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_research_market_domestic_premium_received
            ON research_market_domestic_premium_mx(received_at DESC);
            """
        )
        self.conn.commit()

    def _domestic_gap(self, market: str) -> dict[str, Any]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_cross_exchange_gap_mx'"
        ).fetchone()
        if not exists:
            return {}
        row = self.conn.execute(
            """SELECT market,identity_verified,gap_ready,bithumb_price,upbit_price,
                      bithumb_source_ts,upbit_source_ts
               FROM research_market_cross_exchange_gap_mx WHERE market=?""",
            (str(market).upper(),),
        ).fetchone()
        return dict(row) if row else {}

    @staticmethod
    def _same_identity(left: dict[str, Any], right: dict[str, Any]) -> tuple[ListingIdentity | None, str, str]:
        if not left.get("verified") or not right.get("verified"):
            return None, "", ""
        left_identity = left.get("identity")
        right_identity = right.get("identity")
        if not isinstance(left_identity, ListingIdentity) or not isinstance(right_identity, ListingIdentity):
            return None, "", ""
        if (
            not left_identity.provider
            or not left_identity.provider_id
            or left_identity.provider != right_identity.provider
            or left_identity.provider_id != right_identity.provider_id
            or left_identity.symbol != right_identity.symbol
        ):
            return None, "", ""
        return left_identity, left_identity.provider, left_identity.provider_id

    @staticmethod
    def _latest_foreign_candle(source: SpotListingSource, market: CexSpotMarket, *, now: float) -> ListingCandle | None:
        rows = source.minute_candles(
            market.market,
            start_ts=max(0.0, now - MAX_FOREIGN_PRICE_AGE_SECONDS),
            end_ts=now,
        )
        valid = [
            row for row in rows
            if isinstance(row, ListingCandle)
            and row.ts > 0
            and row.close > 0
            and now - row.ts <= MAX_FOREIGN_PRICE_AGE_SECONDS
        ]
        return max(valid, key=lambda row: row.ts) if valid else None

    def _write(
        self,
        *,
        market: str,
        provider: str,
        provider_id: str,
        identity_verified: bool,
        status: str,
        domestic: dict[str, Any],
        reference: dict[str, Any] | None,
        sources: list[dict[str, Any]],
        foreign_gap: float | None,
        now: float,
    ) -> None:
        ref = reference or {}
        bithumb_price = _finite(domestic.get("bithumb_price"))
        upbit_price = _finite(domestic.get("upbit_price"))
        reference_krw = _finite(ref.get("price_krw"))
        self.conn.execute(
            """INSERT INTO research_market_domestic_premium_mx(
                   market,symbol,provider,provider_id,identity_verified,status,
                   bithumb_price_krw,upbit_price_krw,reference_exchange,reference_market,
                   reference_quote_asset,reference_price_quote,quote_to_krw,reference_price_krw,
                   reference_source_ts,bithumb_premium_pct,upbit_premium_pct,
                   foreign_verified_sources,foreign_price_gap_pct,source_evidence_json,received_at,feature_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(market) DO UPDATE SET
                   symbol=excluded.symbol,provider=excluded.provider,provider_id=excluded.provider_id,
                   identity_verified=excluded.identity_verified,status=excluded.status,
                   bithumb_price_krw=excluded.bithumb_price_krw,upbit_price_krw=excluded.upbit_price_krw,
                   reference_exchange=excluded.reference_exchange,reference_market=excluded.reference_market,
                   reference_quote_asset=excluded.reference_quote_asset,reference_price_quote=excluded.reference_price_quote,
                   quote_to_krw=excluded.quote_to_krw,reference_price_krw=excluded.reference_price_krw,
                   reference_source_ts=excluded.reference_source_ts,bithumb_premium_pct=excluded.bithumb_premium_pct,
                   upbit_premium_pct=excluded.upbit_premium_pct,foreign_verified_sources=excluded.foreign_verified_sources,
                   foreign_price_gap_pct=excluded.foreign_price_gap_pct,source_evidence_json=excluded.source_evidence_json,
                   received_at=excluded.received_at,feature_version=excluded.feature_version""",
            (
                str(market).upper(),
                _symbol(market),
                provider,
                provider_id,
                1 if identity_verified else 0,
                status,
                bithumb_price,
                upbit_price,
                str(ref.get("exchange") or ""),
                str(ref.get("market") or ""),
                str(ref.get("quote_asset") or ""),
                _finite(ref.get("price_quote")),
                _finite(ref.get("quote_to_krw")),
                reference_krw,
                _finite(ref.get("source_ts")),
                ((bithumb_price / reference_krw - 1.0) * 100.0) if bithumb_price and reference_krw else None,
                ((upbit_price / reference_krw - 1.0) * 100.0) if upbit_price and reference_krw else None,
                len(sources),
                foreign_gap,
                json.dumps(sources[:6], ensure_ascii=False, separators=(",", ":")),
                now,
                FEATURE_VERSION,
            ),
        )
        self.conn.commit()

    def collect_market(self, market: str, *, now: float | None = None) -> dict[str, Any]:
        started = time.time()
        current = float(now or time.time())
        domestic = self._domestic_gap(market)
        if not domestic or not bool(domestic.get("identity_verified")) or not bool(domestic.get("gap_ready")):
            self._write(
                market=market, provider="", provider_id="", identity_verified=False,
                status="domestic_gap_not_ready", domestic=domestic, reference=None,
                sources=[], foreign_gap=None, now=current,
            )
            return {
                "ok": True,
                "status": "domestic_gap_not_ready",
                "market": str(market).upper(),
                "verified_sources": 0,
                "paper_only": True,
                "score_wired": False,
                "can_place_orders": False,
                "elapsed_seconds": round(time.time() - started, 3),
            }

        left = self.identity_resolver.resolve("bithumb", market)
        right = self.identity_resolver.resolve("upbit", market)
        identity, provider, provider_id = self._same_identity(left, right)
        if identity is None:
            self._write(
                market=market, provider="", provider_id="", identity_verified=False,
                status="domestic_identity_unverified", domestic=domestic, reference=None,
                sources=[], foreign_gap=None, now=current,
            )
            return {
                "ok": True,
                "status": "domestic_identity_unverified",
                "market": str(market).upper(),
                "verified_sources": 0,
                "paper_only": True,
                "score_wired": False,
                "can_place_orders": False,
                "elapsed_seconds": round(time.time() - started, 3),
            }

        verified_sources: list[dict[str, Any]] = []
        quote_cache: dict[str, dict[str, Any]] = {}
        source_errors: list[str] = []
        for source in self.sources:
            try:
                discovered = sorted(source.discover(identity), key=_market_rank)
            except Exception as exc:
                source_errors.append(f"{getattr(source, 'exchange', 'source')}:discover:{type(exc).__name__}"[:120])
                continue
            accepted: CexSpotMarket | None = None
            verification: dict[str, Any] = {}
            for candidate in discovered:
                if candidate.quote_asset.upper() not in QUOTE_PRIORITY:
                    continue
                verification = self.venue_verifier.verify(identity, candidate)
                if verification.get("verified"):
                    accepted = candidate
                    break
            if accepted is None:
                continue
            try:
                candle = self._latest_foreign_candle(source, accepted, now=current)
            except Exception as exc:
                source_errors.append(f"{accepted.exchange}:candle:{type(exc).__name__}"[:120])
                continue
            if candle is None:
                continue
            quote = accepted.quote_asset.upper()
            if quote not in quote_cache:
                try:
                    quote_cache[quote] = self.quote_resolver.resolve(quote, candle.ts)
                except Exception as exc:
                    quote_cache[quote] = {"found": False, "status": "resolver_error", "error": type(exc).__name__}
            rate = quote_cache[quote]
            quote_to_krw = _finite(rate.get("rate")) if rate.get("found") else None
            if quote_to_krw is None or quote_to_krw <= 0:
                continue
            price_krw = float(candle.close) * quote_to_krw
            verified_sources.append(
                {
                    "exchange": accepted.exchange,
                    "market": accepted.market,
                    "quote_asset": quote,
                    "price_quote": float(candle.close),
                    "quote_to_krw": quote_to_krw,
                    "price_krw": price_krw,
                    "source_ts": float(candle.ts),
                    "identity_provider": provider,
                    "identity_provider_id": provider_id,
                    "venue_status": str(verification.get("status") or ""),
                }
            )

        verified_sources.sort(
            key=lambda row: (
                QUOTE_PRIORITY.get(str(row.get("quote_asset") or ""), 99),
                SOURCE_PRIORITY.get(str(row.get("exchange") or ""), 99),
            )
        )
        prices = [float(row["price_krw"]) for row in verified_sources if _finite(row.get("price_krw"))]
        foreign_gap = ((max(prices) / min(prices) - 1.0) * 100.0) if len(prices) >= 2 and min(prices) > 0 else None
        reference = verified_sources[0] if verified_sources else None
        status = "computed" if reference is not None else "foreign_reference_unavailable"
        self._write(
            market=market,
            provider=provider,
            provider_id=provider_id,
            identity_verified=True,
            status=status,
            domestic=domestic,
            reference=reference,
            sources=verified_sources,
            foreign_gap=foreign_gap,
            now=current,
        )
        return {
            "ok": True,
            "status": status,
            "market": str(market).upper(),
            "provider": provider,
            "provider_id": provider_id,
            "verified_sources": len(verified_sources),
            "reference_exchange": str(reference.get("exchange") or "") if reference else "",
            "reference_market": str(reference.get("market") or "") if reference else "",
            "foreign_price_gap_pct": foreign_gap,
            "source_errors": source_errors[:4],
            "network_public_only": True,
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "elapsed_seconds": round(time.time() - started, 3),
        }

    def read_market(self, market: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM research_market_domestic_premium_mx WHERE market=?",
            (str(market).upper(),),
        ).fetchone()
        if not row:
            return {}
        result = dict(row)
        try:
            result["source_evidence"] = json.loads(str(result.pop("source_evidence_json") or "[]"))
        except json.JSONDecodeError:
            result["source_evidence"] = []
        result["identity_verified"] = bool(result.get("identity_verified"))
        result["paper_only"] = True
        result["score_wired"] = False
        return result

    def audit(self) -> dict[str, Any]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_domestic_premium_mx'"
        ).fetchone()
        if not exists:
            return {"table_exists": False, "row_count": 0, "computed_rows": 0}
        row = self.conn.execute(
            """SELECT COUNT(*) AS rows,
                      SUM(CASE WHEN status='computed' THEN 1 ELSE 0 END) AS computed_rows,
                      SUM(CASE WHEN status='computed' AND identity_verified=0 THEN 1 ELSE 0 END) AS identity_gate_violations,
                      SUM(CASE WHEN status='computed' AND reference_price_krw IS NULL THEN 1 ELSE 0 END) AS reference_null_violations,
                      MAX(received_at) AS received_at
               FROM research_market_domestic_premium_mx"""
        ).fetchone()
        return {
            "table_exists": True,
            "row_count": int(row["rows"] or 0),
            "computed_rows": int(row["computed_rows"] or 0),
            "identity_gate_violations": int(row["identity_gate_violations"] or 0),
            "reference_null_violations": int(row["reference_null_violations"] or 0),
            "received_at": float(row["received_at"] or 0.0),
            "feature_version": FEATURE_VERSION,
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
        }
