from __future__ import annotations

from pathlib import Path

from b3_trader.dex_launch_sources import GeckoTerminalDexSource


def test_network_map_stops_at_json_api_last_page_without_requesting_page_four(tmp_path: Path) -> None:
    source = GeckoTerminalDexSource(
        network_cache_path=tmp_path / "networks.json",
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
                    "attributes": {
                        "name": "Ethereum",
                        "coingecko_asset_platform_id": "ethereum",
                    },
                }
            ],
            "links": {
                "first": "https://api.geckoterminal.com/api/v2/networks?page=1",
                "prev": None,
                "next": "https://api.geckoterminal.com/api/v2/networks?page=2",
                "last": "https://api.geckoterminal.com/api/v2/networks?page=2",
            },
        },
        2: {
            "data": [
                {
                    "id": "base",
                    "type": "network",
                    "attributes": {
                        "name": "Base",
                        "coingecko_asset_platform_id": "base",
                    },
                }
            ],
            "links": {
                "first": "https://api.geckoterminal.com/api/v2/networks?page=1",
                "prev": "https://api.geckoterminal.com/api/v2/networks?page=1",
                "next": None,
                "last": "https://api.geckoterminal.com/api/v2/networks?page=2",
            },
        },
    }

    def fake_get(path: str, *, params=None):
        assert path == "/networks"
        page = int((params or {}).get("page") or 0)
        calls.append(page)
        if page not in pages:
            raise AssertionError(f"unexpected network page request: {page}")
        return pages[page]

    source._gt_get = fake_get  # type: ignore[method-assign]
    mapping = source.network_map({"ethereum", "unsupported-platform"})

    assert calls == [1, 2]
    assert mapping["ethereum"] == "eth"
    assert mapping["base"] == "base"
    assert "unsupported-platform" not in mapping


def test_network_page_metadata_is_backward_compatible_when_links_are_absent() -> None:
    assert GeckoTerminalDexSource._network_page_has_next({"data": []}) is None
    assert GeckoTerminalDexSource._network_page_has_next({"links": {"next": "page-2"}}) is True
    assert GeckoTerminalDexSource._network_page_has_next({"links": {"next": None}}) is False
