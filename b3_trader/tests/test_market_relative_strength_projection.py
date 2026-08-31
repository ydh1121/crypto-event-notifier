from __future__ import annotations

import sqlite3

from b3_trader.market_detail_feature_projection import apply_market_feature_projection
from b3_trader.market_feature_store import MarketFeatureStore
from b3_trader.market_relative_strength import MarketRelativeStrengthEngine


def test_relative_strength_projects_only_bounded_derived_fields() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    engine = MarketRelativeStrengthEngine(conn)
    conn.execute(
        """INSERT INTO research_market_relative_strength_mx(
               exchange,market,horizon_days,as_of_ts,asset_return_pct,btc_return_pct,eth_return_pct,
               vs_btc_pp,vs_eth_pp,breadth_positive_pct,breadth_median_return_pct,vs_breadth_median_pp,
               breadth_sample_count,breadth_universe_count,breadth_coverage_pct,breadth_ready,
               source_timeframe,source_table,source_ts,received_at,feature_version
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "bithumb", "KRW-AAA", 7, 1000.0, 12.0, 5.0, 7.0,
            7.0, 5.0, 62.5, 3.0, 9.0,
            300, 400, 75.0, 1,
            "1d", "research_market_ohlcv_mx", 1000.0, 1010.0, 1,
        ),
    )
    conn.commit()

    source = MarketFeatureStore(conn).relative_strength(exchange="bithumb", market="KRW-AAA")
    payload = apply_market_feature_projection(
        {"relative_strength": source, "return_windows": {}, "lifecycle_state": "NORMAL"},
        {},
    )

    row = payload["relative_strength"]["horizons"]["7"]
    assert row["asset_return_pct"] == 12.0
    assert row["vs_btc_pp"] == 7.0
    assert row["vs_eth_pp"] == 5.0
    assert row["breadth_positive_pct"] == 62.5
    assert row["breadth_ready"] is True
    assert row["source_timeframe"] == "1d"
    assert payload["relative_strength"]["paper_only"] is True
    assert payload["relative_strength"]["score_wired"] is False
    assert "source_table" not in row
    assert payload["version"] >= 6
