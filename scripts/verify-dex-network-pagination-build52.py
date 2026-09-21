from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_launch_sources import GeckoTerminalDexSource


def main() -> None:
    parser = argparse.ArgumentParser(description="Build52 GeckoTerminal network pagination verifier")
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_NETWORK_PAGINATION_BUILD52_IMPORT=PASS")
        return

    with tempfile.TemporaryDirectory() as tmp:
        source = GeckoTerminalDexSource(
            network_cache_path=Path(tmp) / "network-map.json",
            now_fn=lambda: 1_000_000.0,
            sleep_fn=lambda _seconds: None,
            min_interval_seconds=0,
        )
        calls: list[int] = []
        pages = {
            1: {
                "data": [
                    {
                        "id": "eth",
                        "type": "network",
                        "attributes": {"coingecko_asset_platform_id": "ethereum"},
                    }
                ],
                "links": {"next": "https://api.geckoterminal.com/api/v2/networks?page=2"},
            },
            2: {
                "data": [
                    {
                        "id": "base",
                        "type": "network",
                        "attributes": {"coingecko_asset_platform_id": "base"},
                    }
                ],
                "links": {"next": None},
            },
        }

        def fake_get(path: str, *, params=None):
            page = int((params or {}).get("page") or 0)
            calls.append(page)
            if path != "/networks" or page not in pages:
                raise AssertionError(f"unexpected request: {path} page={page}")
            return pages[page]

        source._gt_get = fake_get  # type: ignore[method-assign]
        mapping = source.network_map({"ethereum", "unsupported-platform"})
        payload = {
            "ok": True,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "requested_pages": calls,
            "stopped_before_invalid_page": calls == [1, 2],
            "mapping": mapping,
            "unsupported_platform_mapped": "unsupported-platform" in mapping,
        }
        print("=== DEX NETWORK PAGINATION BUILD 52 RUNTIME ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if not (
            payload["stopped_before_invalid_page"]
            and mapping.get("ethereum") == "eth"
            and mapping.get("base") == "base"
            and not payload["unsupported_platform_mapped"]
            and not payload["can_place_orders"]
            and not payload["score_wired"]
        ):
            raise SystemExit("DEX_NETWORK_PAGINATION_BUILD52_RUNTIME=FAIL")
        print("DEX_NETWORK_PAGINATION_BUILD52_RUNTIME=PASS")


if __name__ == "__main__":
    main()
