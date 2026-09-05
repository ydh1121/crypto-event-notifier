from __future__ import annotations

from b3_trader.market_detail_feature_projection import apply_market_feature_projection


def test_domestic_premium_projection_excludes_source_evidence() -> None:
    source = {
        "domestic_premium": {
            "feature_version": 1,
            "status": "computed",
            "identity_verified": True,
            "provider": "coingecko",
            "provider_id": "alpha-coin",
            "bithumb_price_krw": 100.0,
            "upbit_price_krw": 102.0,
            "reference_exchange": "binance",
            "reference_market": "AAAUSDT",
            "reference_quote_asset": "USDT",
            "reference_price_krw": 98.0,
            "reference_source_ts": 1000.0,
            "bithumb_premium_pct": 2.04,
            "upbit_premium_pct": 4.08,
            "foreign_verified_sources": 2,
            "foreign_price_gap_pct": 0.4,
            "received_at": 1100.0,
            "source_evidence": [{"raw": "do not project"}],
        }
    }
    result = apply_market_feature_projection(source, {})
    premium = result["domestic_premium"]
    assert result["version"] >= 8
    assert premium["status"] == "computed"
    assert premium["identity_verified"] is True
    assert premium["provider_id"] == "alpha-coin"
    assert premium["reference_exchange"] == "binance"
    assert premium["reference_price_krw"] == 98.0
    assert premium["bithumb_premium_pct"] == 2.04
    assert premium["upbit_premium_pct"] == 4.08
    assert premium["paper_only"] is True
    assert premium["score_wired"] is False
    assert "source_evidence" not in premium
