from __future__ import annotations

from pathlib import Path

import pytest

from b3_trader.market_fee_schedule import MarketFeeScheduleStore


def test_bithumb_profile_selection_is_not_retroactive(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "fees.sqlite3"
    store = MarketFeeScheduleStore(path)
    verified_at = 1_788_000_000.0
    selected_at = verified_at + 100.0
    monkeypatch.delenv("B3_BITHUMB_FEE_PROFILE", raising=False)
    monkeypatch.delenv("B3_BITHUMB_FEE_PROFILE_EFFECTIVE_FROM", raising=False)
    try:
        assert store.ensure_current_catalog(now=verified_at) == 3
        assert store.resolve_taker_fee("bithumb", "KRW-BTC", selected_at - 1.0) is None

        store.set_active_profile("bithumb", "KRW", "coupon_0_04", now=selected_at)

        assert store.resolve_taker_fee("bithumb", "KRW-BTC", selected_at - 1.0) is None
        selected = store.resolve_taker_fee("bithumb", "KRW-BTC", selected_at)
        assert selected is not None
        assert selected["profile"] == "coupon_0_04"
        assert selected["taker_fee_bps"] == 4.0
        assert selected["profile_effective_from"] == selected_at
        assert selected["profile_effective_to"] is None

        audit = store.audit()
        assert audit["ok"] is True
        assert audit["profile_resolution_by_at_ts"] is True
        assert audit["profile_selection_retroactive"] is False
        assert audit["profile_history_overlap_violations"] == 0
        assert audit["profile_history_open_interval_violations"] == 0
    finally:
        store.close()


def test_bithumb_profile_switch_preserves_time_segments(tmp_path: Path) -> None:
    path = tmp_path / "fees.sqlite3"
    store = MarketFeeScheduleStore(path)
    verified_at = 1_788_000_000.0
    standard_at = verified_at + 100.0
    coupon_at = verified_at + 200.0
    try:
        store.ensure_current_catalog(now=verified_at)
        store.set_active_profile("bithumb", "KRW", "standard", now=standard_at)
        store.set_active_profile("bithumb", "KRW", "coupon_0_04", now=coupon_at)

        assert store.resolve_taker_fee("bithumb", "KRW-BTC", standard_at - 1.0) is None

        standard = store.resolve_taker_fee("bithumb", "KRW-BTC", standard_at + 1.0)
        assert standard is not None
        assert standard["profile"] == "standard"
        assert standard["taker_fee_bps"] == 25.0
        assert standard["profile_effective_from"] == standard_at
        assert standard["profile_effective_to"] == coupon_at

        coupon = store.resolve_taker_fee("bithumb", "KRW-BTC", coupon_at + 1.0)
        assert coupon is not None
        assert coupon["profile"] == "coupon_0_04"
        assert coupon["taker_fee_bps"] == 4.0
        assert coupon["profile_effective_from"] == coupon_at
        assert coupon["profile_effective_to"] is None

        history = store.audit()["profile_history"]
        bithumb = [row for row in history if row["exchange"] == "bithumb"]
        assert len(bithumb) == 2
        assert bithumb[0]["effective_to"] == coupon_at
        assert bithumb[1]["effective_to"] is None
    finally:
        store.close()


def test_profile_activation_cannot_move_backward(tmp_path: Path) -> None:
    path = tmp_path / "fees.sqlite3"
    store = MarketFeeScheduleStore(path)
    verified_at = 1_788_000_000.0
    try:
        store.ensure_current_catalog(now=verified_at)
        store.set_active_profile("bithumb", "KRW", "standard", now=verified_at + 200.0)
        with pytest.raises(ValueError, match="cannot move backward"):
            store.set_active_profile("bithumb", "KRW", "coupon_0_04", now=verified_at + 100.0)
    finally:
        store.close()


def test_upbit_builtin_default_remains_forward_only(tmp_path: Path) -> None:
    path = tmp_path / "fees.sqlite3"
    store = MarketFeeScheduleStore(path)
    verified_at = 1_788_000_000.0
    try:
        store.ensure_current_catalog(now=verified_at)
        assert store.resolve_taker_fee("upbit", "KRW-BTC", verified_at - 1.0) is None
        resolved = store.resolve_taker_fee("upbit", "KRW-BTC", verified_at + 1.0)
        assert resolved is not None
        assert resolved["profile"] == "standard"
        assert resolved["profile_source"] == "built_in_default_upbit_krw"
    finally:
        store.close()
