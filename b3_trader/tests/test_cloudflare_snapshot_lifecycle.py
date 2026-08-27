from __future__ import annotations

from b3_trader.cloudflare_snapshot_lifecycle import apply_lifecycle_projection


def test_lifecycle_projection_adds_states_without_reclassifying() -> None:
    payload = {
        "leaderboard": [
            {"market": "KRW-AAA", "return_pct": 1.0},
            {"market": "KRW-BBB", "return_pct": -1.0},
        ],
        "best_market": {"market": "KRW-AAA"},
    }
    demo = {
        "leaderboard": [
            {"market": "KRW-AAA", "lifecycle_state": "NEW_LISTING"},
            {"market": "KRW-BBB", "lifecycle_state": "CAUTION"},
        ],
        "market_lifecycle": {
            "market_count": 2,
            "counts": {"NEW_LISTING": 1, "CAUTION": 1},
            "attention": [{"market": "KRW-AAA", "state": "NEW_LISTING"}],
            "transitions": [{"market": "KRW-AAA", "from": "", "to": "NEW_LISTING"}],
        },
    }

    apply_lifecycle_projection(payload, demo)

    assert payload["leaderboard"][0]["lifecycle_state"] == "NEW_LISTING"
    assert payload["leaderboard"][1]["lifecycle_state"] == "CAUTION"
    assert payload["best_market"]["lifecycle_state"] == "NEW_LISTING"
    assert payload["market_lifecycle"]["counts"] == {"NEW_LISTING": 1, "CAUTION": 1}
    assert payload["market_lifecycle"]["shadow_only"] is True
