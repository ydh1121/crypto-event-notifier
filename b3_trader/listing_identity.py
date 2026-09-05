from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse


MIN_VERIFIED_CONFIDENCE = 0.80


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _domain(value: str) -> str:
    raw = _clean(value).lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        host = (urlparse(raw).hostname or "").lower().strip(".")
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _unique_domains(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        host = _domain(value)
        if host and host not in result:
            result.append(host)
    return tuple(result)


@dataclass(frozen=True)
class ListingIdentity:
    """Identity anchor for pre-listing research.

    Exchange tickers are allowed only after this object has passed the gate. A
    ticker alone is never sufficient because unrelated assets can share the
    same symbol across time or venues.
    """

    symbol: str
    english_name: str = ""
    korean_name: str = ""
    provider: str = ""
    provider_id: str = ""
    chain: str = ""
    contract_address: str = ""
    official_domains: tuple[str, ...] = ()
    match_confidence: float = 0.0
    verified_at: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ListingIdentity":
        domains = payload.get("official_domains")
        if not isinstance(domains, (list, tuple)):
            domains = [payload.get("homepage") or ""]
        try:
            confidence = float(payload.get("match_confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            verified_at = float(payload.get("verified_at") or payload.get("last_verified_at") or 0.0)
        except (TypeError, ValueError):
            verified_at = 0.0
        return cls(
            symbol=_clean(payload.get("symbol")).upper(),
            english_name=_clean(payload.get("english_name")),
            korean_name=_clean(payload.get("korean_name")),
            provider=_clean(payload.get("provider")).lower(),
            provider_id=_clean(payload.get("provider_id")),
            chain=_clean(payload.get("chain")).lower(),
            contract_address=_clean(payload.get("contract_address")).lower(),
            official_domains=_unique_domains(str(value) for value in domains if value),
            match_confidence=confidence,
            verified_at=verified_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "english_name": self.english_name,
            "korean_name": self.korean_name,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "chain": self.chain,
            "contract_address": self.contract_address,
            "official_domains": list(self.official_domains),
            "match_confidence": self.match_confidence,
            "verified_at": self.verified_at,
        }


def listing_identity_gate(identity: ListingIdentity) -> dict[str, Any]:
    """Return a fail-closed identity decision used before CEX/DEX discovery."""

    reasons: list[str] = []
    if not identity.symbol or not identity.symbol.replace("-", "").isalnum():
        reasons.append("symbol_missing_or_invalid")
    if not identity.provider or not identity.provider_id:
        reasons.append("provider_identity_missing")
    if identity.match_confidence < MIN_VERIFIED_CONFIDENCE:
        reasons.append("match_confidence_too_low")

    anchors = 0
    if identity.provider and identity.provider_id:
        anchors += 1
    if identity.chain and identity.contract_address:
        anchors += 1
    if identity.official_domains:
        anchors += 1
    if identity.english_name or identity.korean_name:
        anchors += 1

    # Provider id + at least one independent identity anchor is required. This
    # supports native-chain assets without a contract while still rejecting a
    # ticker-only match.
    if anchors < 2:
        reasons.append("independent_identity_anchor_missing")

    verified = not reasons
    return {
        "verified": verified,
        "reasons": reasons,
        "anchor_count": anchors,
        "contract_backed": bool(identity.chain and identity.contract_address),
        "domain_backed": bool(identity.official_domains),
        "provider_backed": bool(identity.provider and identity.provider_id),
        "confidence": round(identity.match_confidence, 6),
    }
