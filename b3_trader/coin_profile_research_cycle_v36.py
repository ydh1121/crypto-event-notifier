from __future__ import annotations

import json
import logging
from typing import Any

from .coin_profile_identity_safe import IdentitySafeCoinProfileEnricher
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

    def _deepen_profile(self, row: dict[str, str], profile: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
        profile = super()._deepen_profile(row, profile, reasons)
        if "identity_mismatch" in reasons:
            profile["replace_existing"] = True
            profile["identity_repair"] = True
        return profile


def main() -> None:
    result = CoinProfileResearchCycleV36().run_once()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
