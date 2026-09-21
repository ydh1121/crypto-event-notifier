from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .dex_launch_sources import DexCandle, normalize_contract_address


DEFAULT_DB_PATH = Path("b3_trader/data/auto_demo.sqlite3")
RETRYABLE_CASE_STATUSES = {
    "identity_waiting",
    "network_unmapped",
    "pool_quality_waiting",
    "source_waiting",
}
DEFAULT_RETRY_AFTER_SECONDS = 6 * 3600


class DexLaunchStore:
    """Additive local SQLite store for exact-contract DEX launch research."""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=20)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dex_launch_case_status (
              case_key TEXT PRIMARY KEY,
              coingecko_id TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL,
              contract_count INTEGER NOT NULL DEFAULT 0,
              accepted_pool_count INTEGER NOT NULL DEFAULT 0,
              error TEXT NOT NULL DEFAULT '',
              updated_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_dex_launch_case_status_status
              ON dex_launch_case_status(status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS dex_launch_assets (
              asset_key TEXT PRIMARY KEY,
              case_key TEXT NOT NULL,
              coingecko_id TEXT NOT NULL,
              platform_id TEXT NOT NULL,
              network_id TEXT NOT NULL DEFAULT '',
              token_address TEXT NOT NULL,
              identity_status TEXT NOT NULL,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(case_key, platform_id, token_address)
            );

            CREATE INDEX IF NOT EXISTS idx_dex_launch_assets_case
              ON dex_launch_assets(case_key, updated_at DESC);

            CREATE TABLE IF NOT EXISTS dex_launch_pools (
              asset_key TEXT NOT NULL,
              pool_address TEXT NOT NULL,
              dex_id TEXT NOT NULL DEFAULT '',
              pool_name TEXT NOT NULL DEFAULT '',
              pool_created_at REAL NOT NULL DEFAULT 0,
              reserve_usd REAL NOT NULL DEFAULT 0,
              volume_h24_usd REAL NOT NULL DEFAULT 0,
              volume_h6_usd REAL NOT NULL DEFAULT 0,
              volume_h1_usd REAL NOT NULL DEFAULT 0,
              volume_m5_usd REAL NOT NULL DEFAULT 0,
              base_token_address TEXT NOT NULL DEFAULT '',
              quote_token_address TEXT NOT NULL DEFAULT '',
              gate_status TEXT NOT NULL DEFAULT 'rejected_quality',
              selected_primary INTEGER NOT NULL DEFAULT 0,
              updated_at REAL NOT NULL,
              PRIMARY KEY(asset_key, pool_address)
            );

            CREATE INDEX IF NOT EXISTS idx_dex_launch_pools_gate
              ON dex_launch_pools(gate_status, selected_primary, updated_at DESC);

            CREATE TABLE IF NOT EXISTS dex_launch_candles (
              asset_key TEXT NOT NULL,
              pool_address TEXT NOT NULL,
              series_kind TEXT NOT NULL,
              candle_ts REAL NOT NULL,
              interval_seconds INTEGER NOT NULL,
              open REAL NOT NULL,
              high REAL NOT NULL,
              low REAL NOT NULL,
              close REAL NOT NULL,
              volume_usd REAL NOT NULL DEFAULT 0,
              PRIMARY KEY(asset_key, pool_address, series_kind, candle_ts, interval_seconds)
            );

            CREATE INDEX IF NOT EXISTS idx_dex_launch_candles_asset_time
              ON dex_launch_candles(asset_key, pool_address, series_kind, candle_ts);

            CREATE TABLE IF NOT EXISTS dex_launch_features (
              asset_key TEXT NOT NULL,
              pool_address TEXT NOT NULL,
              feature_version INTEGER NOT NULL,
              calculated_at REAL NOT NULL,
              feature_json TEXT NOT NULL DEFAULT '{}',
              PRIMARY KEY(asset_key, pool_address)
            );
            """
        )
        self.conn.commit()

    @staticmethod
    def asset_key(case_key: str, platform_id: str, token_address: str) -> str:
        return "|".join(
            (
                str(case_key or "").strip(),
                str(platform_id or "").strip(),
                normalize_contract_address(token_address),
            )
        )

    def listing_cases(self, *, limit: int = 500, retry_after_seconds: float = DEFAULT_RETRY_AFTER_SECONDS) -> list[dict[str, Any]]:
        tables = {
            str(row["name"])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "listing_history_cases" not in tables:
            return []
        cutoff = time.time() - max(0.0, float(retry_after_seconds))
        retryable = tuple(sorted(RETRYABLE_CASE_STATUSES))
        placeholders = ",".join("?" for _ in retryable)
        rows = self.conn.execute(
            f"""
            SELECT c.case_key,c.domestic_exchange,c.domestic_market,c.symbol,c.domestic_open_at,
                   c.identity_json,c.identity_verified,c.status AS listing_status,
                   d.status AS dex_status,d.updated_at AS dex_updated_at
            FROM listing_history_cases c
            LEFT JOIN dex_launch_case_status d ON d.case_key=c.case_key
            WHERE c.identity_verified=1
              AND c.status NOT IN ('rejected_identity','rejected_notice')
              AND (
                d.case_key IS NULL
                OR (d.status IN ({placeholders}) AND d.updated_at<=?)
              )
            ORDER BY CASE WHEN c.domestic_open_at>0 THEN c.domestic_open_at ELSE c.updated_at END DESC
            LIMIT ?
            """,
            (*retryable, cutoff, max(1, min(500, int(limit)))),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["identity"] = json.loads(str(item.pop("identity_json") or "{}"))
            except json.JSONDecodeError:
                item["identity"] = {}
            result.append(item)
        return result

    def upsert_case_status(
        self,
        case_key: str,
        *,
        coingecko_id: str = "",
        status: str,
        contract_count: int = 0,
        accepted_pool_count: int = 0,
        error: str = "",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO dex_launch_case_status(
              case_key,coingecko_id,status,contract_count,accepted_pool_count,error,updated_at
            ) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(case_key) DO UPDATE SET
              coingecko_id=CASE WHEN excluded.coingecko_id<>'' THEN excluded.coingecko_id ELSE dex_launch_case_status.coingecko_id END,
              status=excluded.status,
              contract_count=excluded.contract_count,
              accepted_pool_count=excluded.accepted_pool_count,
              error=excluded.error,
              updated_at=excluded.updated_at
            """,
            (
                str(case_key),
                str(coingecko_id or ""),
                str(status or "source_waiting"),
                max(0, int(contract_count)),
                max(0, int(accepted_pool_count)),
                str(error or "")[:500],
                time.time(),
            ),
        )
        self.conn.commit()

    def upsert_asset(
        self,
        *,
        case_key: str,
        coingecko_id: str,
        platform_id: str,
        network_id: str,
        token_address: str,
        identity_status: str,
    ) -> str:
        now = time.time()
        key = self.asset_key(case_key, platform_id, token_address)
        self.conn.execute(
            """
            INSERT INTO dex_launch_assets(
              asset_key,case_key,coingecko_id,platform_id,network_id,token_address,identity_status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(asset_key) DO UPDATE SET
              network_id=excluded.network_id,
              identity_status=excluded.identity_status,
              updated_at=excluded.updated_at
            """,
            (
                key,
                str(case_key),
                str(coingecko_id),
                str(platform_id),
                str(network_id or ""),
                normalize_contract_address(token_address),
                str(identity_status),
                now,
                now,
            ),
        )
        self.conn.commit()
        return key

    def upsert_pool(self, *, asset_key: str, pool: dict[str, Any], gate_status: str, selected_primary: bool) -> None:
        self.conn.execute(
            """
            INSERT INTO dex_launch_pools(
              asset_key,pool_address,dex_id,pool_name,pool_created_at,reserve_usd,volume_h24_usd,
              volume_h6_usd,volume_h1_usd,volume_m5_usd,base_token_address,quote_token_address,
              gate_status,selected_primary,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(asset_key,pool_address) DO UPDATE SET
              dex_id=excluded.dex_id,pool_name=excluded.pool_name,pool_created_at=excluded.pool_created_at,
              reserve_usd=excluded.reserve_usd,volume_h24_usd=excluded.volume_h24_usd,
              volume_h6_usd=excluded.volume_h6_usd,volume_h1_usd=excluded.volume_h1_usd,
              volume_m5_usd=excluded.volume_m5_usd,base_token_address=excluded.base_token_address,
              quote_token_address=excluded.quote_token_address,gate_status=excluded.gate_status,
              selected_primary=excluded.selected_primary,updated_at=excluded.updated_at
            """,
            (
                str(asset_key),
                normalize_contract_address(pool.get("pool_address")),
                str(pool.get("dex_id") or ""),
                str(pool.get("name") or ""),
                float(pool.get("pool_created_at") or 0.0),
                float(pool.get("reserve_usd") or 0.0),
                float(pool.get("volume_h24_usd") or 0.0),
                float(pool.get("volume_h6_usd") or 0.0),
                float(pool.get("volume_h1_usd") or 0.0),
                float(pool.get("volume_m5_usd") or 0.0),
                normalize_contract_address(pool.get("base_token_address")),
                normalize_contract_address(pool.get("quote_token_address")),
                str(gate_status),
                1 if selected_primary else 0,
                time.time(),
            ),
        )
        self.conn.commit()

    def upsert_candles(
        self,
        *,
        asset_key: str,
        pool_address: str,
        series_kind: str,
        candles: Iterable[DexCandle],
    ) -> int:
        rows = [
            (
                str(asset_key),
                normalize_contract_address(pool_address),
                str(series_kind),
                float(row.ts),
                int(row.interval_seconds),
                float(row.open),
                float(row.high),
                float(row.low),
                float(row.close),
                float(row.volume_usd),
            )
            for row in candles
            if row.ts > 0 and row.close > 0
        ]
        if not rows:
            return 0
        self.conn.executemany(
            """
            INSERT INTO dex_launch_candles(
              asset_key,pool_address,series_kind,candle_ts,interval_seconds,open,high,low,close,volume_usd
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(asset_key,pool_address,series_kind,candle_ts,interval_seconds) DO UPDATE SET
              open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,volume_usd=excluded.volume_usd
            """,
            rows,
        )
        self.conn.commit()
        return len(rows)

    def upsert_features(
        self,
        *,
        asset_key: str,
        pool_address: str,
        feature_version: int,
        features: dict[str, Any],
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO dex_launch_features(asset_key,pool_address,feature_version,calculated_at,feature_json)
            VALUES(?,?,?,?,?)
            ON CONFLICT(asset_key,pool_address) DO UPDATE SET
              feature_version=excluded.feature_version,
              calculated_at=excluded.calculated_at,
              feature_json=excluded.feature_json
            """,
            (
                str(asset_key),
                normalize_contract_address(pool_address),
                int(feature_version),
                time.time(),
                json.dumps(features, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        self.conn.commit()

    def audit(self) -> dict[str, Any]:
        tables = {
            str(row["name"])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {
            "dex_launch_case_status",
            "dex_launch_assets",
            "dex_launch_pools",
            "dex_launch_candles",
            "dex_launch_features",
        }
        if not required.issubset(tables):
            return {"ok": False, "tables": {name: name in tables for name in sorted(required)}}
        statuses = {
            str(row["status"]): int(row["n"])
            for row in self.conn.execute(
                "SELECT status,COUNT(*) AS n FROM dex_launch_case_status GROUP BY status ORDER BY status"
            ).fetchall()
        }
        return {
            "ok": True,
            "tables": {name: True for name in sorted(required)},
            "case_count": int(self.conn.execute("SELECT COUNT(*) FROM dex_launch_case_status").fetchone()[0]),
            "case_status_counts": statuses,
            "asset_count": int(self.conn.execute("SELECT COUNT(*) FROM dex_launch_assets").fetchone()[0]),
            "pool_count": int(self.conn.execute("SELECT COUNT(*) FROM dex_launch_pools").fetchone()[0]),
            "accepted_pool_count": int(
                self.conn.execute("SELECT COUNT(*) FROM dex_launch_pools WHERE gate_status='accepted'").fetchone()[0]
            ),
            "primary_pool_count": int(
                self.conn.execute("SELECT COUNT(*) FROM dex_launch_pools WHERE selected_primary=1").fetchone()[0]
            ),
            "candle_count": int(self.conn.execute("SELECT COUNT(*) FROM dex_launch_candles").fetchone()[0]),
            "feature_count": int(self.conn.execute("SELECT COUNT(*) FROM dex_launch_features").fetchone()[0]),
            "paper_only": True,
            "can_place_orders": False,
        }
