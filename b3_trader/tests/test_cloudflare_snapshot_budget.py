from __future__ import annotations

from copy import deepcopy

from b3_trader.cloudflare_snapshot_budget import (
    MAX_BODY_BYTES,
    TARGET_BODY_BYTES,
    apply_snapshot_budget,
    snapshot_bytes,
)


def _market(exchange: str, index: int) -> dict:
    return {
        "exchange": exchange,
        "market": f"KRW-C{index:03d}",
        "name": f"Coin {index}",
        "price": 1000 + index,
        "return_pct": index / 100,
        "opportunity_score": 50 + index % 40,
        "regime_score": 60,
        "entry_score": 55,
        "trade_intent": "HOLD",
        "lifecycle_state": "NORMAL",
    }


def _records(count: int) -> dict:
    return {
        "fills": [{"ts": i, "market": f"KRW-C{i:03d}", "reason": "x" * 120} for i in range(count)],
        "feedback": [{"ts": i, "market": f"KRW-C{i:03d}", "note": "y" * 160} for i in range(count)],
        "fill_count": count,
        "feedback_count": count,
        "updated_at": count,
    }


def _snapshot() -> dict:
    bithumb_rows = [_market("bithumb", i) for i in range(120)]
    upbit_rows = [_market("upbit", i) for i in range(80)]
    b_records = _records(80)
    u_records = _records(60)
    history = [[float(i), 1000000.0 + i, i / 100, -1.0, 0.0] for i in range(576)]
    paper = [[float(i), 1000000.0 + i, float(i), i / 100, -1.0, 0] for i in range(576)]
    matrix_b = [{"market": row["market"], "rows": [["e1", "balanced", 1, 2, 3, -1, 4, 2, 0]]} for row in bithumb_rows]
    matrix_u = [{"market": row["market"], "rows": [["e2", "balanced", 1, 2, 3, -1, 4, 2, 0]]} for row in upbit_rows]
    return {
        "source_ts": 1.0,
        "public": {
            "leaderboard": deepcopy(bithumb_rows),
            "best_market": deepcopy(bithumb_rows[0]),
            "market_lifecycle": {"counts": {"NORMAL": len(bithumb_rows)}},
            "recent_records": deepcopy(b_records),
            "exchanges": {
                "bithumb": {
                    "exchange": "bithumb",
                    "market_count": len(bithumb_rows),
                    "aggregate_virtual_capital_krw": 1,
                    "equity_krw": 1,
                    "cash_krw": 1,
                    "pnl_krw": 0,
                    "active_positions": 0,
                    "leaderboard": deepcopy(bithumb_rows),
                    "best_market": deepcopy(bithumb_rows[0]),
                    "market_lifecycle": {"counts": {"NORMAL": len(bithumb_rows)}},
                },
                "upbit": {
                    "exchange": "upbit",
                    "market_count": len(upbit_rows),
                    "aggregate_virtual_capital_krw": 1,
                    "equity_krw": 1,
                    "cash_krw": 1,
                    "pnl_krw": 0,
                    "active_positions": 0,
                    "leaderboard": deepcopy(upbit_rows),
                },
            },
            "exchange_records": {"bithumb": deepcopy(b_records), "upbit": deepcopy(u_records)},
            "strategy_lab": {
                "strategy_equity_history": {f"e{i}": deepcopy(history) for i in range(4)},
                "paper_history": {"bithumb": deepcopy(paper), "upbit": deepcopy(paper), "combined": deepcopy(paper)},
                "coin_matrix": {"bithumb": matrix_b, "upbit": matrix_u},
            },
        },
        "private": {},
    }


def test_budget_deduplicates_bithumb_without_breaking_selector_merge() -> None:
    source = _snapshot()
    before = snapshot_bytes(source)
    result = apply_snapshot_budget(source)
    public = result["public"]
    bithumb = public["exchanges"]["bithumb"]

    assert "leaderboard" not in bithumb
    assert "best_market" not in bithumb
    assert "market_lifecycle" not in bithumb
    assert bithumb["projection_inherits_root"] is True
    assert "bithumb" not in public["exchange_records"]

    # Mirrors the Viewer selector: {...public, ...selected}.
    merged = {**public, **bithumb}
    assert merged["leaderboard"] == public["leaderboard"]
    assert merged["best_market"] == public["best_market"]
    assert merged["recent_records"] == public["recent_records"]

    budget = public["snapshot_budget"]
    assert budget["max_body_bytes"] == MAX_BODY_BYTES
    assert budget["target_body_bytes"] == TARGET_BODY_BYTES
    assert budget["deduplicated_bithumb"]["leaderboard"] is True
    assert budget["deduplicated_bithumb"]["recent_records"] is True
    assert budget["raw_rows_added"] is False
    assert snapshot_bytes(result) < before


def test_budget_progressively_trims_optional_history_when_needed() -> None:
    source = _snapshot()
    public = source["public"]
    # Inflate only optional display history/record tails. Core market rows remain
    # untouched by the adaptive history compaction stages.
    public["strategy_lab"]["strategy_equity_history"] = {
        f"e{i}": [[float(j), 1.0, 2.0, 3.0, 4.0, "z" * 160] for j in range(900)]
        for i in range(10)
    }
    public["recent_records"] = _records(1200)
    public["exchange_records"]["bithumb"] = deepcopy(public["recent_records"])
    public["exchange_records"]["upbit"] = _records(1200)

    result = apply_snapshot_budget(source)
    budget = result["public"]["snapshot_budget"]
    assert budget["compact_level"] in {"history_384", "history_288", "history_144"}
    assert len(result["public"]["recent_records"]["fills"]) <= 60
    assert len(result["public"]["recent_records"]["feedback"]) <= 40
    assert budget["bytes_after"] == snapshot_bytes(result)
    assert budget["within_hard_limit"] == (snapshot_bytes(result) <= MAX_BODY_BYTES)
