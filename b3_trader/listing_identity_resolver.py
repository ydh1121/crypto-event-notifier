from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

from .http_retry import get_with_retry
from .listing_identity import ListingIdentity, listing_identity_gate


USER_AGENT = "crypto-research-listing-identity/1.2"
CG_SEARCH_URL = "https://api.coingecko.com/api/v3/search"
CG_DETAIL_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}"
CG_RETRY_DELAY_FLOOR_SECONDS = 15.0
CG_RETRY_DELAY_CAP_SECONDS = 60.0
_GENERIC_NAME_WORDS = {
    "the", "token", "coin", "network", "protocol", "finance", "foundation",
    "project", "ecosystem", "platform", "labs", "dao",
}


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


def _name_tokens(value: Any) -> tuple[str, ...]:
    words = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return tuple(word for word in words if word not in _GENERIC_NAME_WORDS)


def _strong_name_match(expected: Any, candidate: Any) -> bool:
    left = _name_tokens(expected)
    right = _name_tokens(candidate)
    return bool(left and right and left == right)


def _domain(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        host = (urlparse(raw).hostname or "").lower().strip(".")
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _detail_domains(payload: dict[str, Any]) -> set[str]:
    links = payload.get("links") if isinstance(payload.get("links"), dict) else {}
    homepages = links.get("homepage") if isinstance(links.get("homepage"), list) else []
    return {host for host in (_domain(value) for value in homepages) if host}


def _normalize_contract_address(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.startswith("0x") or raw.startswith("0X"):
        return raw.lower()
    return raw


def _detail_platform_contracts(payload: dict[str, Any]) -> list[dict[str, str]]:
    platforms = payload.get("platforms") if isinstance(payload.get("platforms"), dict) else {}
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for platform_id, raw_address in platforms.items():
        platform = str(platform_id or "").strip()
        address = _normalize_contract_address(raw_address)
        if not platform or not address:
            continue
        key = (platform, address)
        if key in seen:
            continue
        seen.add(key)
        result.append({"platform_id": platform, "token_address": address})
    return result


def _detail_contracts(payload: dict[str, Any]) -> set[str]:
    return {row["token_address"] for row in _detail_platform_contracts(payload)}


class ListingIdentityResolver:
    """Read researched identity from the Cloudflare profile cache.

    Ticker-only matching is forbidden. When a remote identity is already verified
    but lacks CoinGecko evidence, a bounded cross-provider bridge may promote it
    to a CoinGecko id only after exact symbol + strong project-name matching and
    an independent domain/contract check when those anchors are available.
    """

    def __init__(self) -> None:
        load_dotenv(override=True)
        self._crosswalk_cache: dict[tuple[str, str, tuple[str, ...], str], dict[str, Any]] = {}

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

    @staticmethod
    def _coingecko_get(url: str, *, params: dict[str, Any], timeout: float) -> tuple[Any, int]:
        return get_with_retry(
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            params=params,
            timeout=timeout,
            attempts=3,
            retry_delay_floor_seconds=CG_RETRY_DELAY_FLOOR_SECONDS,
            retry_delay_cap_seconds=CG_RETRY_DELAY_CAP_SECONDS,
        )

    def _crosswalk_coingecko(self, identity: ListingIdentity) -> dict[str, Any]:
        key = (
            identity.symbol,
            identity.english_name.lower(),
            tuple(sorted(identity.official_domains)),
            identity.contract_address,
        )
        cached = self._crosswalk_cache.get(key)
        if cached is not None:
            return dict(cached)

        if not identity.english_name:
            result = {
                "status": "english_name_missing",
                "verified": False,
                "coin_id": "",
                "contracts_checked": False,
                "contracts": [],
            }
            self._crosswalk_cache[key] = result
            return dict(result)

        response, search_retries = self._coingecko_get(
            CG_SEARCH_URL,
            params={"query": identity.english_name},
            timeout=15,
        )
        payload = response.json()
        rows = payload.get("coins") if isinstance(payload, dict) and isinstance(payload.get("coins"), list) else []
        candidates = [
            row for row in rows
            if isinstance(row, dict)
            and str(row.get("symbol") or "").strip().upper() == identity.symbol
            and _strong_name_match(identity.english_name, row.get("name"))
            and str(row.get("id") or "").strip()
        ]
        candidates.sort(key=lambda row: int(row.get("market_cap_rank") or 999999))

        expected_domains = set(identity.official_domains)
        expected_contract = _normalize_contract_address(identity.contract_address)

        for candidate in candidates[:5]:
            coin_id = str(candidate.get("id") or "").strip()
            detail_response, detail_retries = self._coingecko_get(
                CG_DETAIL_URL.format(coin_id=coin_id),
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "false",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false",
                },
                timeout=18,
            )
            detail = detail_response.json()
            if not isinstance(detail, dict):
                continue
            if str(detail.get("id") or "").strip() != coin_id:
                continue
            if str(detail.get("symbol") or "").strip().upper() != identity.symbol:
                continue
            if not _strong_name_match(identity.english_name, detail.get("name")):
                continue

            detail_domains = _detail_domains(detail)
            domain_overlap = sorted(expected_domains & detail_domains)
            platform_contracts = _detail_platform_contracts(detail)
            contracts = {row["token_address"] for row in platform_contracts}
            contract_match = bool(expected_contract and expected_contract in contracts)

            if expected_domains and not domain_overlap and not contract_match:
                continue
            if not expected_domains and expected_contract and not contract_match:
                continue

            result = {
                "status": "verified",
                "verified": True,
                "coin_id": coin_id,
                "contracts_checked": True,
                "contracts": platform_contracts,
                "basis": {
                    "symbol_exact": True,
                    "strong_name_match": True,
                    "domain_overlap": domain_overlap,
                    "contract_match": contract_match,
                    "search_query_basis": "verified_english_name",
                },
                "retries": int(search_retries) + int(detail_retries),
            }
            self._crosswalk_cache[key] = result
            return dict(result)

        result = {
            "status": "coingecko_crosswalk_unverified",
            "verified": False,
            "coin_id": "",
            "contracts_checked": False,
            "contracts": [],
            "retries": int(search_retries),
        }
        self._crosswalk_cache[key] = result
        return dict(result)

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
        crosswalk: dict[str, Any] = {}

        if verified and not coingecko_id and identity.provider != "coingecko":
            try:
                crosswalk = self._crosswalk_coingecko(identity)
            except Exception as exc:
                crosswalk = {
                    "status": "coingecko_crosswalk_error",
                    "verified": False,
                    "coin_id": "",
                    "contracts_checked": False,
                    "contracts": [],
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }
            if crosswalk.get("verified") and str(crosswalk.get("coin_id") or "").strip():
                coingecko_id = str(crosswalk.get("coin_id") or "").strip()
                identity = ListingIdentity(
                    symbol=identity.symbol,
                    english_name=identity.english_name,
                    korean_name=identity.korean_name,
                    provider="coingecko",
                    provider_id=coingecko_id,
                    chain=identity.chain,
                    contract_address=identity.contract_address,
                    official_domains=identity.official_domains,
                    match_confidence=identity.match_confidence,
                    verified_at=identity.verified_at,
                )
                local_gate = listing_identity_gate(identity)
                verified = bool(remote_verified and local_gate["verified"])

        return {
            "status": (
                "verified_cross_provider"
                if verified and crosswalk.get("verified")
                else "verified" if verified else "profile_not_verified"
            ),
            "verified": verified,
            "identity": identity if verified else None,
            "identity_payload": identity.to_dict(),
            "coingecko_venue_id": coingecko_id,
            "coingecko_crosswalk": crosswalk,
            "local_gate": local_gate,
            "remote_gate": payload.get("gate") if isinstance(payload.get("gate"), dict) else {},
            "retries": retries + int(crosswalk.get("retries") or 0),
        }
