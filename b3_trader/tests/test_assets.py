import json

import pytest

from b3_trader.assets import AssetRegistry, default_profile, normalize_market


def test_normalize_ticker():
    assert normalize_market("b3") == "KRW-B3"
    assert normalize_market("KRW-xrp") == "KRW-XRP"
    assert normalize_market("1inch") == "KRW-1INCH"


def test_normalize_rejects_ratio_or_malformed_market():
    for value in ("ETH/BTC", "KRW-ETH/BTC", "KRW-ETH BTC", "BTC-USDT"):
        with pytest.raises(ValueError):
            normalize_market(value)


def test_registry_roundtrip(tmp_path):
    path = tmp_path / "assets.json"
    registry = AssetRegistry(str(path))
    assert registry.get("B3") is not None
    profile = registry.add_generic("SEI")
    assert profile.market == "KRW-SEI"
    loaded = AssetRegistry(str(path))
    assert loaded.get("KRW-SEI").context_mode == "generic_alt"


def test_registry_skips_invalid_asset_without_losing_valid_rows(tmp_path):
    path = tmp_path / "assets.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "assets": [
                    {"market": "KRW-B3", "symbol": "B3", "enabled": True},
                    {"market": "KRW-ETH/BTC", "symbol": "ETH/BTC", "enabled": True},
                    {"market": "KRW-SEI", "symbol": "SEI", "enabled": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    registry = AssetRegistry(str(path))
    markets = [row.market for row in registry.list()]
    assert markets == ["KRW-B3", "KRW-SEI"]


def test_invalid_related_market_is_ignored(tmp_path):
    path = tmp_path / "assets.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "assets": [
                    {
                        "market": "KRW-B3",
                        "symbol": "B3",
                        "enabled": True,
                        "related_markets": ["KRW-IMX", "ETH/BTC"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = AssetRegistry(str(path))
    assert registry.get("B3").related_markets == ("KRW-IMX",)


def test_b3_default_context():
    profile = default_profile("B3")
    assert profile.context_mode == "base_gaming"
    assert "KRW-IMX" in profile.related_markets
