from __future__ import annotations

from b3_trader.listing_history_sources import BinanceSpotSource, BybitSpotSource, OkxSpotSource
from b3_trader.listing_identity import ListingIdentity


def identity() -> ListingIdentity:
    return ListingIdentity(
        symbol="ABC",
        english_name="Alpha Beta Coin",
        provider="coingecko",
        provider_id="alpha-beta-coin",
        official_domains=("example.org",),
        match_confidence=0.95,
    )


def test_binance_discovery_requires_verified_identity() -> None:
    source = BinanceSpotSource()
    source._get = lambda path, params: {  # type: ignore[method-assign]
        "symbols": [
            {"symbol": "ABCUSDT", "baseAsset": "ABC", "quoteAsset": "USDT", "status": "TRADING"},
            {"symbol": "XYZUSDT", "baseAsset": "XYZ", "quoteAsset": "USDT", "status": "TRADING"},
        ]
    }
    rows = source.discover(identity())
    assert [row.market for row in rows] == ["ABCUSDT"]
    assert rows[0].match_basis["identity_gate"] == "verified"


def test_okx_discovery_uses_listing_time() -> None:
    source = OkxSpotSource()
    source._get = lambda path, params: {  # type: ignore[method-assign]
        "code": "0",
        "data": [
            {
                "instId": "ABC-USDT",
                "baseCcy": "ABC",
                "quoteCcy": "USDT",
                "state": "live",
                "listTime": "1700000000000",
                "contTdSwTime": "1700003600000",
            }
        ],
    }
    rows = source.discover(identity())
    assert len(rows) == 1
    assert rows[0].listing_at == 1700003600.0


def test_bybit_discovery_uses_launch_time() -> None:
    source = BybitSpotSource()
    source._get = lambda path, params: {  # type: ignore[method-assign]
        "retCode": 0,
        "result": {
            "list": [
                {
                    "symbol": "ABCUSDT",
                    "baseCoin": "ABC",
                    "quoteCoin": "USDT",
                    "status": "Trading",
                    "launchTime": "1700010000000",
                }
            ]
        },
    }
    rows = source.discover(identity())
    assert len(rows) == 1
    assert rows[0].listing_at == 1700010000.0


def test_unverified_identity_blocks_source_lookup() -> None:
    source = BinanceSpotSource()
    source._get = lambda path, params: (_ for _ in ()).throw(AssertionError("network should not be reached"))  # type: ignore[method-assign]
    weak = ListingIdentity(symbol="ABC", match_confidence=1.0)
    try:
        source.discover(weak)
    except ValueError as exc:
        assert "not verified" in str(exc)
    else:
        raise AssertionError("weak identity must fail closed")
