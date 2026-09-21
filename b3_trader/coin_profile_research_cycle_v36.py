from __future__ import annotations

import json
import logging
from typing import Any

from .coin_profile_enricher import _normalize, _text
from .coin_profile_identity_safe import IdentitySafeCoinProfileEnricher, _manual_intro_identity_matches
from .coin_profile_research_cycle import CoinProfileResearchCycle


class CoinProfileResearchCycleV36(CoinProfileResearchCycle):
    """Build 36+ profile cycle with strict project identity and content-integrity repair."""

    def __init__(self) -> None:
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        self.base = IdentitySafeCoinProfileEnricher()
        self.session = self.base.session

    def _urls(self) -> tuple[str, str, str]:
        ingest, token = self.base._endpoint()
        if not ingest or not token:
            return "", "", ""
        root = ingest[: -len("/api/ingest-coin-profiles")] if ingest.endswith("/api/ingest-coin-profiles") else ingest.rstrip("/")
        return root + "/api/ingest-coin-profiles-repair", root + "/api/coin-profile-backlog-v37", token

    @staticmethod
    def _repair_profile_matches_current(row: dict[str, str], profile: dict[str, Any]) -> bool:
        """A repair may overwrite quarantined data only with a current-asset lead."""

        for key in ("business_summary_ko", "description_ko"):
            value = _text(profile.get(key))
            if value and _manual_intro_identity_matches(row, value):
                return True
        english = _normalize(profile.get("description_en"))
        expected = _normalize(row.get("english_name"))
        return bool(english and expected and english.startswith(expected))

    @staticmethod
    def _quarantine_profile(row: dict[str, str], profile: dict[str, Any]) -> dict[str, Any]:
        """Replace known cross-contamination with an exchange-only safe shell."""

        safe = dict(profile)
        safe.update({
            "exchange": row["exchange"],
            "market": row["market"],
            "symbol": row["symbol"],
            "korean_name": row.get("korean_name") or row["symbol"],
            "english_name": row.get("english_name") or row["symbol"],
            "provider": "exchange",
            "provider_id": "",
            "description_ko": "",
            "description_en": "",
            "business_summary_ko": "",
            "business_summary_en": "",
            "categories": [],
            "tags": [],
            "homepage": "",
            "image_url": "",
            "official_docs": "",
            "whitepaper": "",
            "source_code": "",
            "community": [],
            "evidence": [],
            "research_status": "unresolved",
            "summary_source": "",
            "source_count": 0,
            "match_confidence": 0.0,
            "replace_existing": True,
            "identity_repair": True,
            "identity_quarantined": True,
        })
        return safe

    def _deepen_profile(self, row: dict[str, str], profile: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
        profile = super()._deepen_profile(row, profile, reasons)
        if "identity_mismatch" in reasons:
            if not self._repair_profile_matches_current(row, profile):
                return self._quarantine_profile(row, profile)
            profile["replace_existing"] = True
            profile["identity_repair"] = True
            profile["identity_quarantined"] = False
        return profile

    def run_once(self) -> dict[str, Any]:
        """General research and precision repair are failure-isolated.

        A transient D1/general ingest failure must never block identity mismatch
        quarantine and repair, because stale cross-contaminated descriptions are
        more harmful than temporarily missing general enrichment.
        """

        try:
            general = self.base.run_once()
        except Exception as exc:
            general = {
                "status": "general_error",
                "configured": True,
                "processed": 0,
                "stored": 0,
                "failed": 1,
                "failures": [f"{type(exc).__name__}: {str(exc)[:500]}"],
            }
        ingest, backlog_url, token = self._urls()
        if not ingest or not backlog_url or not token:
            return {**general, "precision": {"status": "not_configured", "processed": 0}}
        try:
            precision = self._precision_once(ingest, backlog_url, token)
        except Exception as exc:
            precision = {
                "status": "precision_error",
                "processed": 0,
                "stored": 0,
                "failed": 1,
                "failures": [f"{type(exc).__name__}: {str(exc)[:500]}"],
            }
        return {**general, "precision": precision}


def main() -> None:
    result = CoinProfileResearchCycleV36().run_once()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
