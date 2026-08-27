from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

from .http_retry import get_with_retry
from .listing_identity import ListingIdentity, listing_identity_gate


USER_AGENT = "crypto-research-listing-identity/1.0"


def _coingecko_id_from_evidence(values: Any) -> str:
    rows = values if isinstance(values, list) else []
    for row in rows:
        if not isinstance(row, dict) or str(row.get("source") or "").lower() != "coingecko":
            continue
        raw = str(row.get("url") or "").strip()
        if not raw:
            continue
        try:
            path = urlparse(raw).path
        except ValueError:
            continue
        match = re.search(r"/coins/([^/?#]+)", path, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


class ListingIdentityResolver:
    """Read already-researched identity from the Cloudflare profile cache.

    This avoids duplicating CoinGecko/CMC/manual research inside listing-history.
    Only profile rows already marked verified/corroborated by the profile pipeline
    are eligible; weaker rows remain pending instead of falling back to ticker.
    """

    def __init__(self) -> None:
        load_dotenv(override=True)

    @staticmethod
    def _endpoint() -> tuple[str, str]:
        load_dotenv(override=True)
        ingest = os.getenv("CLOUDFLARE_VIEWER_INGEST_URL", "").strip()
        token = os.getenv("CLOUDFLARE_VIEWER_INGEST_TOKEN", "").strip()
        if not ingest or not token:
            return "", ""
        if ingest.endswith("/api/ingest"):
            return ingest[: -len("/api/ingest")] + "/api/coin-profile-identity", token
        return ingest.rstrip("/") + "/api/coin-profile-identity", token

    def resolve(self, exchange: str, market: str) -> dict[str, Any]:
        url, token = self._endpoint()
        if not url or not token:
            return {"status": "not_configured", "verified": False, "identity": None}
        response, retries = get_with_retry(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            params={"exchange": str(exchange).lower(), "market": str(market).upper()},
            timeout=15,
            attempts=3,
        )
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("ok"):
            return {"status": "invalid_response", "verified": False, "identity": None, "retries": retries}
        if not payload.get("found"):
            return {"status": "profile_missing", "verified": False, "identity": None, "retries": retries}
        source = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
        evidence = source.get("evidence") if isinstance(source.get("evidence"), list) else []
        coingecko_id = str(source.get("coingecko_id") or "").strip() or _coingecko_id_from_evidence(evidence)
        provider = str(source.get("provider") or "").strip().lower()
        provider_id = str(source.get("provider_id") or "").strip()
        # Multi-source profiles can store a CMC numeric id in provider_id. If a
        # CoinGecko id is already part of the verified profile evidence, prefer
        # that stable id because it can cross-check exact CEX venue tickers.
        if coingecko_id:
            provider = "coingecko"
            provider_id = coingecko_id
        identity = ListingIdentity.from_dict(
            {
                **source,
                "provider": provider,
                "provider_id": provider_id,
                "official_domains": [source.get("homepage") or ""],
                "verified_at": source.get("last_verified_at") or 0,
            }
        )
        local_gate = listing_identity_gate(identity)
        remote_verified = bool(payload.get("verified"))
        verified = bool(remote_verified and local_gate["verified"])
        return {
            "status": "verified" if verified else "profile_not_verified",
            "verified": verified,
            "identity": identity if verified else None,
            "identity_payload": identity.to_dict(),
            "coingecko_venue_id": coingecko_id,
            "local_gate": local_gate,
            "remote_gate": payload.get("gate") if isinstance(payload.get("gate"), dict) else {},
            "retries": retries,
        }
