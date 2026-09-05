from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.listing_identity import ListingIdentity
from b3_trader.temporal_identity_preparation import TemporalIdentityPreparationRunner


class FakeResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def resolve(self, exchange: str, market: str) -> dict:
        self.calls.append((exchange, market))
        symbol = market.split("-")[-1]
        identity = ListingIdentity(
            symbol=symbol,
            english_name=f"{symbol} Project",
            korean_name="테스트",
            provider="coingecko",
            provider_id=f"coin-{symbol.lower()}",
            chain="",
            contract_address="",
            official_domains=(f"{symbol.lower()}.example",),
            match_confidence=0.99,
            verified_at=1_800_000_000.0,
        )
        return {"status": "verified", "verified": True, "identity": identity}


def _seed(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE listing_history_cases (
          case_key TEXT PRIMARY KEY,
          domestic_exchange TEXT NOT NULL,
          domestic_market TEXT NOT NULL,
          domestic_notice_id TEXT NOT NULL DEFAULT '',
          symbol TEXT NOT NULL,
          announcement_at REAL NOT NULL DEFAULT 0,
          domestic_open_at REAL NOT NULL DEFAULT 0,
          domestic_open_price REAL NOT NULL DEFAULT 0,
          identity_json TEXT NOT NULL DEFAULT '{}',
          identity_verified INTEGER NOT NULL DEFAULT 0,
          identity_confidence REAL NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'pending_identity',
          created_at REAL NOT NULL,
          updated_at REAL NOT NULL
        );
        CREATE TABLE dex_launch_case_status (
          case_key TEXT PRIMARY KEY,
          coingecko_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          contract_count INTEGER NOT NULL DEFAULT 0,
          accepted_pool_count INTEGER NOT NULL DEFAULT 0,
          error TEXT NOT NULL DEFAULT '',
          updated_at REAL NOT NULL
        );
        """
    )
    rows = [
        ("bithumb|KRW-JUN1|notice:1", "bithumb", "KRW-JUN1", "1", "JUN1", 1781000000.0, 1781000000.0, 0.0, "{}", 0, 0.0, "pending_identity", 1.0, 1.0),
        ("upbit|KRW-JUN2|notice:2", "upbit", "KRW-JUN2", "2", "JUN2", 1781100000.0, 1781100000.0, 0.0, "{}", 0, 0.0, "pending_identity", 1.0, 1.0),
        ("bithumb|KRW-JUL|notice:3", "bithumb", "KRW-JUL", "3", "JUL", 1783000000.0, 1783000000.0, 0.0, "{}", 0, 0.0, "pending_identity", 1.0, 1.0),
        ("upbit|KRW-USED|notice:4", "upbit", "KRW-USED", "4", "USED", 1781200000.0, 1781200000.0, 0.0, "{}", 0, 0.0, "pending_identity", 1.0, 1.0),
        ("bithumb|KRW-VERIFIED|notice:5", "bithumb", "KRW-VERIFIED", "5", "VERIFIED", 1781300000.0, 1781300000.0, 0.0, json.dumps({"provider": "coingecko", "provider_id": "existing"}), 1, 0.99, "complete", 1.0, 1.0),
    ]
    conn.executemany("INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.execute(
        "INSERT INTO dex_launch_case_status VALUES(?,?,?,?,?,?,?)",
        ("upbit|KRW-USED|notice:4", "used", "complete", 1, 1, "", 1.0),
    )
    conn.commit()
    conn.close()


def test_build58_prepares_only_pre_july_unverified_no_dex(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite3"
    _seed(db)
    resolver = FakeResolver()
    monkeypatch.setattr(
        "b3_trader.temporal_identity_preparation.evaluate_dex_launch_quality",
        lambda _path: {"cases": [{"usable_for_shadow_analysis": True, "coingecko_id": "existing"}]},
    )
    runner = TemporalIdentityPreparationRunner(
        db,
        state_path=tmp_path / "state.json",
        status_path=tmp_path / "status.json",
        resolver=resolver,
    )
    plan = runner.plan(now=1_800_000_000.0)
    assert plan["action"] == "temporal_identity_prepare"
    assert plan["candidate_count"] == 2
    assert [row["symbol"] for row in plan["candidates"]] == ["JUN1", "JUN2"]
    assert plan["later_pending_count"] == 1
    assert plan["later_pending_preview"][0]["symbol"] == "JUL"

    result = runner.run_once(max_cases=2)
    assert result["processed"] == 2
    assert result["prepared_exact_coingecko"] == 2
    assert resolver.calls == [("bithumb", "KRW-JUN1"), ("upbit", "KRW-JUN2")]
    assert all(row["new_unique_candidate"] for row in result["results"])

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    prepared = conn.execute(
        "SELECT symbol,identity_verified,identity_json,status FROM listing_history_cases WHERE symbol IN ('JUN1','JUN2') ORDER BY symbol"
    ).fetchall()
    july = conn.execute("SELECT identity_verified FROM listing_history_cases WHERE symbol='JUL'").fetchone()
    used = conn.execute("SELECT identity_verified FROM listing_history_cases WHERE symbol='USED'").fetchone()
    conn.close()
    assert [int(row["identity_verified"]) for row in prepared] == [1, 1]
    assert all(json.loads(row["identity_json"])["provider"] == "coingecko" for row in prepared)
    assert all(row["status"] == "pending_identity" for row in prepared)
    assert int(july["identity_verified"]) == 0
    assert int(used["identity_verified"]) == 0
