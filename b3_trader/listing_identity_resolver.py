from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from .http_retry import get_with_retry
from .listing_identity import ListingIdentity, listing_identity_gate


USER_AGENT = "crypto-research-listing-identity/1.0"


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
        identity = ListingIdentity.from_dict(
            {
                **source,
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
            "local_gate": local_gate,
            "remote_gate": payload.get("gate") if isinstance(payload.get("gate"), dict) else {},
            "retries": retries,
        }
