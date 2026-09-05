from __future__ import annotations

import math
import re
import sqlite3
import time
from typing import Any

FEATURE_VERSION = 1
SOURCE_TIMEFRAME = "1m"
MAX_PRICE_AGE_SECONDS = 15.0 * 60.0
MAX_SOURCE_SKEW_SECONDS = 5.0 * 60.0


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalized_name(value: Any) -> str:
    return "".join(re.findall(r"[0-9a-z가-힣]+", str(value or "").lower()))


def _symbol(market: Any) -> str:
    text = str(market or "").upper().strip()
    return text.split("-", 1)[1] if text.startswith("KRW-") and "-" in text else ""


class MarketCrossExchangeGapEngine:
    """Derive latest Bithumb-vs-Upbit KRW price gaps from local 1m OHLCV.

    This research feature never joins markets by ticker alone. A pair is eligible
    only when both exchanges expose the same KRW symbol and the normalized
    official market names are exactly equal. Price observations must also be
    recent and close in time. The result is latest-only and is not wired to
    PAPER scoring or order paths.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_cross_exchange_gap_mx(
                market TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                bithumb_market TEXT NOT NULL,
                upbit_market TEXT NOT NULL,
                bithumb_name TEXT NOT NULL,
                upbit_name TEXT NOT NULL,
                identity_verified INTEGER NOT NULL DEFAULT 0,
                identity_basis TEXT NOT NULL,
                bithumb_price REAL,
                upbit_price REAL,
                bithumb_source_ts REAL,
                upbit_source_ts REAL,
                source_skew_seconds REAL,
                upbit_vs_bithumb_pct REAL,
                absolute_gap_pct REAL,
                gap_ready INTEGER NOT NULL DEFAULT 0,
                source_timeframe TEXT NOT NULL DEFAULT '1m',
                source_table TEXT NOT NULL DEFAULT 'research_market_ohlcv_mx',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_research_market_cross_exchange_gap_received
            ON research_market_cross_exchange_gap_mx(received_at DESC);
            """
        )
        self.conn.commit()

    def _latest(self, exchange: str, market: str) -> dict[str, float] | None:
        row = self.conn.execute(
            """SELECT candle_ts,close,received_at
               FROM research_market_ohlcv_mx
               WHERE exchange=? AND market=? AND timeframe=?
               ORDER BY candle_ts DESC LIMIT 1""",
            (str(exchange), str(market), SOURCE_TIMEFRAME),
        ).fetchone()
        if not row:
            return None
        ts = _finite(row["candle_ts"])
        price = _finite(row["close"])
        received_at = _finite(row["received_at"])
        if ts is None or price is None or received_at is None or ts <= 0 or price <= 0:
            return None
        return {"ts": ts, "price": price, "received_at": received_at}

    def compute(
        self,
        *,
        bithumb_names: dict[str, str],
        upbit_names: dict[str, str],
        now: float | None = None,
    ) -> dict[str, Any]:
        started = time.time()
        current = float(now or time.time())
        common = sorted(set(bithumb_names) & set(upbit_names))
        prepared: list[tuple[Any, ...]] = []
        ready = 0
        identity_rejected = 0
        stale_or_skewed = 0

        for market in common:
            symbol = _symbol(market)
            bithumb_name = str(bithumb_names.get(market) or "").strip()
            upbit_name = str(upbit_names.get(market) or "").strip()
            name_left = _normalized_name(bithumb_name)
            name_right = _normalized_name(upbit_name)
            identity_verified = bool(symbol and name_left and name_left == name_right)
            identity_basis = "symbol+official_name_exact" if identity_verified else "identity_mismatch"
            bithumb = self._latest("bithumb", market) if identity_verified else None
            upbit = self._latest("upbit", market) if identity_verified else None
            gap_ready = False
            directional: float | None = None
            absolute: float | None = None
            skew: float | None = None

            if not identity_verified:
                identity_rejected += 1
            elif bithumb is not None and upbit is not None:
                skew = abs(float(bithumb["ts"]) - float(upbit["ts"]))
                latest_age = max(current - float(bithumb["ts"]), current - float(upbit["ts"]))
                if latest_age <= MAX_PRICE_AGE_SECONDS and skew <= MAX_SOURCE_SKEW_SECONDS:
                    base = float(bithumb["price"])
                    other = float(upbit["price"])
                    directional = (other / base - 1.0) * 100.0
                    absolute = abs(directional)
                    gap_ready = True
                    ready += 1
                else:
                    stale_or_skewed += 1
            else:
                stale_or_skewed += 1

            prepared.append(
                (
                    market,
                    symbol,
                    market,
                    market,
                    bithumb_name,
                    upbit_name,
                    1 if identity_verified else 0,
                    identity_basis,
                    bithumb["price"] if bithumb is not None else None,
                    upbit["price"] if upbit is not None else None,
                    bithumb["ts"] if bithumb is not None else None,
                    upbit["ts"] if upbit is not None else None,
                    skew,
                    directional,
                    absolute,
                    1 if gap_ready else 0,
                    SOURCE_TIMEFRAME,
                    "research_market_ohlcv_mx",
                    current,
                    FEATURE_VERSION,
                )
            )

        if prepared:
            self.conn.executemany(
                """INSERT INTO research_market_cross_exchange_gap_mx(
                       market,symbol,bithumb_market,upbit_market,bithumb_name,upbit_name,
                       identity_verified,identity_basis,bithumb_price,upbit_price,
                       bithumb_source_ts,upbit_source_ts,source_skew_seconds,
                       upbit_vs_bithumb_pct,absolute_gap_pct,gap_ready,source_timeframe,
                       source_table,received_at,feature_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(market) DO UPDATE SET
                       symbol=excluded.symbol,
                       bithumb_market=excluded.bithumb_market,
                       upbit_market=excluded.upbit_market,
                       bithumb_name=excluded.bithumb_name,
                       upbit_name=excluded.upbit_name,
                       identity_verified=excluded.identity_verified,
                       identity_basis=excluded.identity_basis,
                       bithumb_price=excluded.bithumb_price,
                       upbit_price=excluded.upbit_price,
                       bithumb_source_ts=excluded.bithumb_source_ts,
                       upbit_source_ts=excluded.upbit_source_ts,
                       source_skew_seconds=excluded.source_skew_seconds,
                       upbit_vs_bithumb_pct=excluded.upbit_vs_bithumb_pct,
                       absolute_gap_pct=excluded.absolute_gap_pct,
                       gap_ready=excluded.gap_ready,
                       source_timeframe=excluded.source_timeframe,
                       source_table=excluded.source_table,
                       received_at=excluded.received_at,
                       feature_version=excluded.feature_version""",
                prepared,
            )
            self.conn.commit()

        return {
            "ok": True,
            "status": "computed" if prepared else "waiting_for_common_markets",
            "common_markets": len(common),
            "rows_written": len(prepared),
            "gap_ready_rows": ready,
            "identity_rejected_rows": identity_rejected,
            "stale_or_skewed_rows": stale_or_skewed,
            "identity_basis": "symbol+official_name_exact",
            "source_timeframe": SOURCE_TIMEFRAME,
            "max_price_age_seconds": MAX_PRICE_AGE_SECONDS,
            "max_source_skew_seconds": MAX_SOURCE_SKEW_SECONDS,
            "feature_version": FEATURE_VERSION,
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "elapsed_seconds": round(time.time() - started, 4),
        }

    def read_market(self, market: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM research_market_cross_exchange_gap_mx WHERE market=?",
            (str(market).upper(),),
        ).fetchone()
        return dict(row) if row else {}

    def audit(self) -> dict[str, Any]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_cross_exchange_gap_mx'"
        ).fetchone()
        if not exists:
            return {"table_exists": False, "row_count": 0, "gap_ready_rows": 0}
        row = self.conn.execute(
            """SELECT COUNT(*) AS rows,
                      SUM(CASE WHEN identity_verified=1 THEN 1 ELSE 0 END) AS identity_verified_rows,
                      SUM(CASE WHEN gap_ready=1 THEN 1 ELSE 0 END) AS gap_ready_rows,
                      MAX(received_at) AS received_at
               FROM research_market_cross_exchange_gap_mx"""
        ).fetchone()
        return {
            "table_exists": True,
            "row_count": int(row["rows"] or 0),
            "identity_verified_rows": int(row["identity_verified_rows"] or 0),
            "gap_ready_rows": int(row["gap_ready_rows"] or 0),
            "received_at": float(row["received_at"] or 0.0),
            "feature_version": FEATURE_VERSION,
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
        }
