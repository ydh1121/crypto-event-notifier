from __future__ import annotations

from typing import Any

from .http_retry import get_with_retry
from .listing_history_sources import CexSpotMarket
from .listing_identity import ListingIdentity, listing_identity_gate


COINGECKO_TICKERS_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/tickers"
COINGECKO_EXCHANGE_IDS = {
    "binance": ("binance",),
    "okx": ("okex",),
    "bybit": ("bybit_spot",),
}
USER_AGENT = "crypto-research-listing-venue/1.0"


class ListingVenueVerifier:
    """Cross-check an exchange pair against an already-verified provider coin id.

    A domestic identity match alone does not prove that a foreign venue's same
    symbol represents the same project. For the first CEX implementation, an
    exact CoinGecko coin-id + exchange-id + base/target ticker match is required
    before foreign candles are accepted into the listing-history store.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], tuple[list[dict[str, Any]], int]] = {}

    def _tickers(self, identity: ListingIdentity, exchange: str) -> tuple[list[dict[str, Any]], int]:
        key = (identity.provider_id, exchange)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        aliases = COINGECKO_EXCHANGE_IDS.get(exchange, ())
        all_rows: list[dict[str, Any]] = []
        retries_total = 0
        for exchange_id in aliases:
            response, retries = get_with_retry(
                COINGECKO_TICKERS_URL.format(coin_id=identity.provider_id),
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                params={
                    "exchange_ids": exchange_id,
                    "include_exchange_logo": "false",
                    "page": 1,
                    "depth": "false",
                },
                timeout=15,
                attempts=3,
            )
            retries_total += retries
            payload = response.json()
            rows = payload.get("tickers") if isinstance(payload, dict) else []
            for row in rows if isinstance(rows, list) else []:
                if isinstance(row, dict):
                    all_rows.append(row)
        result = (all_rows, retries_total)
        self._cache[key] = result
        return result

    def verify(self, identity: ListingIdentity, market: CexSpotMarket) -> dict[str, Any]:
        gate = listing_identity_gate(identity)
        if not gate["verified"]:
            return {"verified": False, "status": "identity_not_verified", "evidence": {}}
        if identity.provider != "coingecko" or not identity.provider_id:
            return {
                "verified": False,
                "status": "provider_venue_evidence_unavailable",
                "evidence": {"provider": identity.provider, "provider_id": identity.provider_id},
            }
        aliases = COINGECKO_EXCHANGE_IDS.get(market.exchange, ())
        if not aliases:
            return {"verified": False, "status": "unsupported_exchange", "evidence": {}}
        try:
            rows, retries = self._tickers(identity, market.exchange)
        except Exception as exc:
            return {
                "verified": False,
                "status": "provider_source_error",
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "evidence": {},
            }
        base = market.base_asset.upper()
        quote = market.quote_asset.upper()
        for row in rows:
            venue = row.get("market") if isinstance(row.get("market"), dict) else {}
            identifier = str(venue.get("identifier") or "").lower()
            row_base = str(row.get("base") or "").upper()
            row_target = str(row.get("target") or "").upper()
            if identifier not in aliases or row_base != base or row_target != quote:
                continue
            if bool(row.get("is_anomaly")):
                continue
            return {
                "verified": True,
                "status": "provider_pair_verified",
                "evidence": {
                    "provider": "coingecko",
                    "coin_id": identity.provider_id,
                    "exchange_id": identifier,
                    "base": row_base,
                    "target": row_target,
                    "trade_url": str(row.get("trade_url") or ""),
                    "last_traded_at": str(row.get("last_traded_at") or row.get("timestamp") or ""),
                    "is_stale": bool(row.get("is_stale")),
                    "retries": retries,
                },
            }
        return {
            "verified": False,
            "status": "provider_pair_not_found",
            "evidence": {
                "provider": "coingecko",
                "coin_id": identity.provider_id,
                "exchange_ids": list(aliases),
                "base": base,
                "target": quote,
                "ticker_rows_checked": len(rows),
            },
        }
