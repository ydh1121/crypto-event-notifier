from __future__ import annotations

from b3_trader.market_detail_feature_projection import apply_market_feature_projection


def test_cross_exchange_gap_projection_is_compact_and_score_unwired() -> None:
    source = {
        "lifecycle_state": "NORMAL",
        "cross_exchange_gap": {
            "feature_version": 1,
            "identity_verified": True,
            "identity_basis": "symbol+official_name_exact",
            "gap_ready": True,
            "bithumb_price": 100.0,
            "upbit_price": 102.0,
            "bithumb_source_ts": 1000.0,
            "upbit_source_ts": 1060.0,
            "source_skew_seconds": 60.0,
            "upbit_vs_bithumb_pct": 2.0,
            "absolute_gap_pct": 2.0,
            "source_timeframe": "1m",
            "source_table": "research_market_ohlcv_mx",
            "received_at": 1100.0,
            "raw_rows": [{"should": "not project"}],
        },
    }
    result = apply_market_feature_projection(source, {})
    gap = result["cross_exchange_gap"]
    assert result["version"] >= 7
    assert gap["identity_verified"] is True
    assert gap["gap_ready"] is True
    assert gap["upbit_vs_bithumb_pct"] == 2.0
    assert gap["paper_only"] is True
    assert gap["score_wired"] is False
    assert "source_table" not in gap
    assert "raw_rows" not in gap
