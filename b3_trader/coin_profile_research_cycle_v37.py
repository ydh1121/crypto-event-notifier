from __future__ import annotations

import json

from .coin_profile_research_cycle_v36 import CoinProfileResearchCycleV36


class CoinProfileResearchCycleV37(CoinProfileResearchCycleV36):
    """Build 37 profile cycle with content-integrity backlog."""

    def _urls(self) -> tuple[str, str, str]:
        ingest, token = self.base._endpoint()
        if not ingest or not token:
            return "", "", ""
        root = ingest[: -len("/api/ingest-coin-profiles")] if ingest.endswith("/api/ingest-coin-profiles") else ingest.rstrip("/")
        return root + "/api/ingest-coin-profiles-repair", root + "/api/coin-profile-backlog-v37", token


def main() -> None:
    result = CoinProfileResearchCycleV37().run_once()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
