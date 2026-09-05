from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import AdaptiveProfile, DB_PATH, START_KRW

DEFAULT_EXCHANGE = "bithumb"
DEFAULT_STRATEGY = "adaptive"
BITHUMB_CUTOVER_MIGRATION = "bithumb_legacy_to_scoped_v1"


def paper_key(exchange: str, market: str, strategy: str) -> str:
    return f"{exchange.strip().lower()}|{market.strip().upper()}|{strategy.strip().lower()}"


class MultiExchangeStore:
    """Phase 3 storage keyed by exchange + market + strategy.

    The existing Bithumb-only research_* tables stay untouched. This store owns
    parallel *_mx tables. Legacy Bithumb data is copied only during the guarded
    cutover; Upbit never triggers that copy.
    """

    def __init__(self, path: Path = DB_PATH, *, migrate_legacy: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        if migrate_legacy:
            self.migrate_legacy_bithumb()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_accounts_mx (
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                strategy TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                cash_krw REAL NOT NULL,
                volume REAL NOT NULL DEFAULT 0,
                avg_price REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                peak_equity REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL DEFAULT 0,
                peak_price REAL NOT NULL DEFAULT 0,
                last_buy_at REAL NOT NULL DEFAULT 0,
                last_trade_at REAL NOT NULL DEFAULT 0,
                entry_ts REAL NOT NULL DEFAULT 0,
                entry_signal_json TEXT NOT NULL DEFAULT '{}',
                updated_ts REAL NOT NULL,
                PRIMARY KEY(exchange, market, strategy)
            );
            CREATE INDEX IF NOT EXISTS idx_research_accounts_mx_exchange_strategy
                ON research_accounts_mx(exchange, strategy, market);

            CREATE TABLE IF NOT EXISTS research_profiles_mx (
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                strategy TEXT NOT NULL,
                regime_floor REAL NOT NULL,
                entry_floor REAL NOT NULL,
                exploration_floor REAL NOT NULL,
                base_weight_pct REAL NOT NULL,
                max_position_pct REAL NOT NULL,
                closed_trades INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                ema_return_pct REAL NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                updated_ts REAL NOT NULL,
                PRIMARY KEY(exchange, market, strategy)
            );

            CREATE TABLE IF NOT EXISTS research_signals_mx (
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                strategy TEXT NOT NULL,
                symbol TEXT NOT NULL,
                ts REAL NOT NULL,
                price REAL NOT NULL,
                turnover_24h REAL NOT NULL,
                change_24h_pct REAL NOT NULL,
                liquidity_score REAL NOT NULL,
                regime_score REAL NOT NULL,
                entry_score REAL NOT NULL,
                opportunity_score REAL NOT NULL,
                strategy_action TEXT NOT NULL,
                trade_intent TEXT NOT NULL,
                suggested_weight_pct REAL NOT NULL,
                reason TEXT NOT NULL,
                signal_json TEXT NOT NULL,
                PRIMARY KEY(exchange, market, strategy)
            );

            CREATE TABLE IF NOT EXISTS research_fills_mx (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                strategy TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL NOT NULL,
                krw REAL NOT NULL,
                weight_pct REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                return_pct REAL NOT NULL DEFAULT 0,
                reason TEXT NOT NULL,
                signal_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_research_fills_mx_scope_ts
                ON research_fills_mx(exchange, market, strategy, ts DESC);

            CREATE TABLE IF NOT EXISTS research_feedback_mx (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                strategy TEXT NOT NULL,
                outcome_return_pct REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                holding_seconds REAL NOT NULL,
                profile_before_json TEXT NOT NULL,
                profile_after_json TEXT NOT NULL,
                signal_json TEXT NOT NULL,
                note TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_research_feedback_mx_scope_ts
                ON research_feedback_mx(exchange, market, strategy, ts DESC);

            CREATE TABLE IF NOT EXISTS research_equity_mx (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                strategy TEXT NOT NULL,
                equity_krw REAL NOT NULL,
                return_pct REAL NOT NULL,
                cash_krw REAL NOT NULL,
                position_value_krw REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_research_equity_mx_scope_ts
                ON research_equity_mx(exchange, market, strategy, ts DESC);

            CREATE TABLE IF NOT EXISTS research_market_memory_mx (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                signal_ts REAL NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                strategy TEXT NOT NULL,
                price REAL NOT NULL,
                change_24h_pct REAL NOT NULL,
                turnover_24h REAL NOT NULL,
                liquidity_score REAL NOT NULL,
                regime_score REAL NOT NULL,
                entry_score REAL NOT NULL,
                opportunity_score REAL NOT NULL,
                suggested_weight_pct REAL NOT NULL,
                trade_intent TEXT NOT NULL,
                asset_return_pct REAL NOT NULL DEFAULT 0,
                pullback_pct REAL NOT NULL DEFAULT 0,
                volatility_pct REAL NOT NULL DEFAULT 0,
                orderbook_imbalance REAL NOT NULL DEFAULT 0,
                fib_retrace REAL,
                btc_return_pct REAL NOT NULL DEFAULT 0,
                eth_return_pct REAL NOT NULL DEFAULT 0,
                asset_vs_majors_pct REAL NOT NULL DEFAULT 0,
                price_delta_pct REAL NOT NULL DEFAULT 0,
                opportunity_delta REAL NOT NULL DEFAULT 0,
                regime_delta REAL NOT NULL DEFAULT 0,
                entry_delta REAL NOT NULL DEFAULT 0,
                feature_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(exchange, market, strategy, signal_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_research_market_memory_mx_scope_ts
                ON research_market_memory_mx(exchange, market, strategy, ts DESC);

            CREATE TABLE IF NOT EXISTS research_store_migrations (
                name TEXT PRIMARY KEY,
                applied_ts REAL NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        self.conn.commit()

    def _table_exists(self, name: str) -> bool:
        return bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone())

    def migration_record(self, name: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT name,applied_ts,details_json FROM research_store_migrations WHERE name=?", (name,)
        ).fetchone()
        if not row:
            return {}
        result = dict(row)
        try:
            details = json.loads(str(result.pop("details_json") or "{}"))
        except json.JSONDecodeError:
            details = {}
        result["details"] = details if isinstance(details, dict) else {}
        return result

    def _record_migration(self, name: str, details: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO research_store_migrations(name,applied_ts,details_json) VALUES(?,?,?)
               ON CONFLICT(name) DO UPDATE SET applied_ts=excluded.applied_ts,details_json=excluded.details_json""",
            (name, time.time(), json.dumps(details, ensure_ascii=False, separators=(",", ":"))),
        )
        self.conn.commit()

    def migrate_legacy_bithumb(self) -> dict[str, int]:
        """Copy legacy Bithumb state before the scoped cutover. Safe to rerun before cutover."""
        counts: dict[str, int] = {}
        before = self.conn.total_changes
        if self._table_exists("research_accounts"):
            self.conn.execute(
                """INSERT INTO research_accounts_mx(
                    exchange,market,strategy,symbol,name,cash_krw,volume,avg_price,realized_pnl,
                    peak_equity,max_drawdown_pct,peak_price,last_buy_at,last_trade_at,entry_ts,
                    entry_signal_json,updated_ts)
                SELECT ?,market,?,symbol,name,cash_krw,volume,avg_price,realized_pnl,peak_equity,
                    max_drawdown_pct,peak_price,last_buy_at,last_trade_at,entry_ts,entry_signal_json,updated_ts
                FROM research_accounts WHERE 1=1
                ON CONFLICT(exchange,market,strategy) DO UPDATE SET
                    symbol=excluded.symbol,name=excluded.name,cash_krw=excluded.cash_krw,
                    volume=excluded.volume,avg_price=excluded.avg_price,realized_pnl=excluded.realized_pnl,
                    peak_equity=excluded.peak_equity,max_drawdown_pct=excluded.max_drawdown_pct,
                    peak_price=excluded.peak_price,last_buy_at=excluded.last_buy_at,
                    last_trade_at=excluded.last_trade_at,entry_ts=excluded.entry_ts,
                    entry_signal_json=excluded.entry_signal_json,updated_ts=excluded.updated_ts""",
                (DEFAULT_EXCHANGE, DEFAULT_STRATEGY),
            )
            counts["accounts"] = self.conn.total_changes - before
            before = self.conn.total_changes
        if self._table_exists("research_profiles"):
            self.conn.execute(
                """INSERT INTO research_profiles_mx(
                    exchange,market,strategy,regime_floor,entry_floor,exploration_floor,base_weight_pct,
                    max_position_pct,closed_trades,wins,ema_return_pct,version,updated_ts)
                SELECT ?,market,?,regime_floor,entry_floor,exploration_floor,base_weight_pct,
                    max_position_pct,closed_trades,wins,ema_return_pct,version,updated_ts
                FROM research_profiles WHERE 1=1
                ON CONFLICT(exchange,market,strategy) DO UPDATE SET
                    regime_floor=excluded.regime_floor,entry_floor=excluded.entry_floor,
                    exploration_floor=excluded.exploration_floor,base_weight_pct=excluded.base_weight_pct,
                    max_position_pct=excluded.max_position_pct,closed_trades=excluded.closed_trades,
                    wins=excluded.wins,ema_return_pct=excluded.ema_return_pct,
                    version=excluded.version,updated_ts=excluded.updated_ts""",
                (DEFAULT_EXCHANGE, DEFAULT_STRATEGY),
            )
            counts["profiles"] = self.conn.total_changes - before
            before = self.conn.total_changes
        if self._table_exists("research_signals"):
            self.conn.execute(
                """INSERT INTO research_signals_mx(
                    exchange,market,strategy,symbol,ts,price,turnover_24h,change_24h_pct,liquidity_score,
                    regime_score,entry_score,opportunity_score,strategy_action,trade_intent,
                    suggested_weight_pct,reason,signal_json)
                SELECT ?,market,?,symbol,ts,price,turnover_24h,change_24h_pct,liquidity_score,
                    regime_score,entry_score,opportunity_score,strategy_action,trade_intent,
                    suggested_weight_pct,reason,signal_json FROM research_signals WHERE 1=1
                ON CONFLICT(exchange,market,strategy) DO UPDATE SET
                    symbol=excluded.symbol,ts=excluded.ts,price=excluded.price,
                    turnover_24h=excluded.turnover_24h,change_24h_pct=excluded.change_24h_pct,
                    liquidity_score=excluded.liquidity_score,regime_score=excluded.regime_score,
                    entry_score=excluded.entry_score,opportunity_score=excluded.opportunity_score,
                    strategy_action=excluded.strategy_action,trade_intent=excluded.trade_intent,
                    suggested_weight_pct=excluded.suggested_weight_pct,reason=excluded.reason,
                    signal_json=excluded.signal_json""",
                (DEFAULT_EXCHANGE, DEFAULT_STRATEGY),
            )
            counts["signals"] = self.conn.total_changes - before
            before = self.conn.total_changes
        if self._table_exists("research_fills"):
            self.conn.execute(
                """INSERT INTO research_fills_mx(
                    ts,exchange,market,strategy,symbol,side,price,volume,krw,weight_pct,
                    realized_pnl,return_pct,reason,signal_json)
                SELECT f.ts,?,f.market,?,f.symbol,f.side,f.price,f.volume,f.krw,f.weight_pct,
                    f.realized_pnl,f.return_pct,f.reason,f.signal_json FROM research_fills f
                WHERE NOT EXISTS(
                    SELECT 1 FROM research_fills_mx x
                    WHERE x.exchange=? AND x.market=f.market AND x.strategy=? AND x.ts=f.ts
                      AND x.side=f.side AND x.price=f.price AND x.volume=f.volume
                )""",
                (DEFAULT_EXCHANGE, DEFAULT_STRATEGY, DEFAULT_EXCHANGE, DEFAULT_STRATEGY),
            )
            counts["fills"] = self.conn.total_changes - before
            before = self.conn.total_changes
        if self._table_exists("research_feedback"):
            self.conn.execute(
                """INSERT INTO research_feedback_mx(
                    ts,exchange,market,strategy,outcome_return_pct,realized_pnl,holding_seconds,
                    profile_before_json,profile_after_json,signal_json,note)
                SELECT f.ts,?,f.market,?,f.outcome_return_pct,f.realized_pnl,f.holding_seconds,
                    f.profile_before_json,f.profile_after_json,f.signal_json,f.note FROM research_feedback f
                WHERE NOT EXISTS(
                    SELECT 1 FROM research_feedback_mx x
                    WHERE x.exchange=? AND x.market=f.market AND x.strategy=? AND x.ts=f.ts
                      AND x.realized_pnl=f.realized_pnl AND x.outcome_return_pct=f.outcome_return_pct
                )""",
                (DEFAULT_EXCHANGE, DEFAULT_STRATEGY, DEFAULT_EXCHANGE, DEFAULT_STRATEGY),
            )
            counts["feedback"] = self.conn.total_changes - before
            before = self.conn.total_changes
        if self._table_exists("research_equity"):
            self.conn.execute(
                """INSERT INTO research_equity_mx(
                    ts,exchange,market,strategy,equity_krw,return_pct,cash_krw,position_value_krw)
                SELECT e.ts,?,e.market,?,e.equity_krw,e.return_pct,e.cash_krw,e.position_value_krw
                FROM research_equity e
                WHERE NOT EXISTS(
                    SELECT 1 FROM research_equity_mx x
                    WHERE x.exchange=? AND x.market=e.market AND x.strategy=? AND x.ts=e.ts
                )""",
                (DEFAULT_EXCHANGE, DEFAULT_STRATEGY, DEFAULT_EXCHANGE, DEFAULT_STRATEGY),
            )
            counts["equity"] = self.conn.total_changes - before
            before = self.conn.total_changes
        if self._table_exists("research_market_memory"):
            self.conn.execute(
                """INSERT OR IGNORE INTO research_market_memory_mx(
                    ts,signal_ts,exchange,market,strategy,price,change_24h_pct,turnover_24h,liquidity_score,
                    regime_score,entry_score,opportunity_score,suggested_weight_pct,trade_intent,
                    asset_return_pct,pullback_pct,volatility_pct,orderbook_imbalance,fib_retrace,
                    btc_return_pct,eth_return_pct,asset_vs_majors_pct,price_delta_pct,opportunity_delta,
                    regime_delta,entry_delta,feature_json)
                SELECT ts,signal_ts,?,market,?,price,change_24h_pct,turnover_24h,liquidity_score,
                    regime_score,entry_score,opportunity_score,suggested_weight_pct,trade_intent,
                    asset_return_pct,pullback_pct,volatility_pct,orderbook_imbalance,fib_retrace,
                    btc_return_pct,eth_return_pct,asset_vs_majors_pct,price_delta_pct,opportunity_delta,
                    regime_delta,entry_delta,feature_json FROM research_market_memory""",
                (DEFAULT_EXCHANGE, DEFAULT_STRATEGY),
            )
            counts["memory"] = self.conn.total_changes - before
        self.conn.commit()
        return counts

    def verify_legacy_bithumb_parity(self) -> dict[str, Any]:
        table_pairs = {
            "accounts": ("research_accounts", "research_accounts_mx"),
            "profiles": ("research_profiles", "research_profiles_mx"),
            "signals": ("research_signals", "research_signals_mx"),
            "fills": ("research_fills", "research_fills_mx"),
            "feedback": ("research_feedback", "research_feedback_mx"),
            "equity": ("research_equity", "research_equity_mx"),
            "memory": ("research_market_memory", "research_market_memory_mx"),
        }
        counts: dict[str, dict[str, int]] = {}
        errors: list[str] = []
        for name, (legacy_table, scoped_table) in table_pairs.items():
            legacy_count = int(self.conn.execute(f"SELECT COUNT(*) FROM {legacy_table}").fetchone()[0]) if self._table_exists(legacy_table) else 0
            scoped_count = int(self.conn.execute(
                f"SELECT COUNT(*) FROM {scoped_table} WHERE exchange=? AND strategy=?",
                (DEFAULT_EXCHANGE, DEFAULT_STRATEGY),
            ).fetchone()[0])
            counts[name] = {"legacy": legacy_count, "scoped": scoped_count}
            if legacy_count != scoped_count:
                errors.append(f"{name} count mismatch {legacy_count}!={scoped_count}")

        state_checks = {
            "accounts": """SELECT COUNT(*) FROM research_accounts l LEFT JOIN research_accounts_mx x
                ON x.exchange=? AND x.market=l.market AND x.strategy=?
                WHERE x.market IS NULL OR x.symbol IS NOT l.symbol OR x.name IS NOT l.name
                   OR x.cash_krw IS NOT l.cash_krw OR x.volume IS NOT l.volume OR x.avg_price IS NOT l.avg_price
                   OR x.realized_pnl IS NOT l.realized_pnl OR x.peak_equity IS NOT l.peak_equity
                   OR x.max_drawdown_pct IS NOT l.max_drawdown_pct OR x.peak_price IS NOT l.peak_price
                   OR x.last_buy_at IS NOT l.last_buy_at OR x.last_trade_at IS NOT l.last_trade_at
                   OR x.entry_ts IS NOT l.entry_ts OR x.entry_signal_json IS NOT l.entry_signal_json
                   OR x.updated_ts IS NOT l.updated_ts""",
            "profiles": """SELECT COUNT(*) FROM research_profiles l LEFT JOIN research_profiles_mx x
                ON x.exchange=? AND x.market=l.market AND x.strategy=?
                WHERE x.market IS NULL OR x.regime_floor IS NOT l.regime_floor OR x.entry_floor IS NOT l.entry_floor
                   OR x.exploration_floor IS NOT l.exploration_floor OR x.base_weight_pct IS NOT l.base_weight_pct
                   OR x.max_position_pct IS NOT l.max_position_pct OR x.closed_trades IS NOT l.closed_trades
                   OR x.wins IS NOT l.wins OR x.ema_return_pct IS NOT l.ema_return_pct
                   OR x.version IS NOT l.version OR x.updated_ts IS NOT l.updated_ts""",
            "signals": """SELECT COUNT(*) FROM research_signals l LEFT JOIN research_signals_mx x
                ON x.exchange=? AND x.market=l.market AND x.strategy=?
                WHERE x.market IS NULL OR x.symbol IS NOT l.symbol OR x.ts IS NOT l.ts OR x.price IS NOT l.price
                   OR x.turnover_24h IS NOT l.turnover_24h OR x.change_24h_pct IS NOT l.change_24h_pct
                   OR x.liquidity_score IS NOT l.liquidity_score OR x.regime_score IS NOT l.regime_score
                   OR x.entry_score IS NOT l.entry_score OR x.opportunity_score IS NOT l.opportunity_score
                   OR x.strategy_action IS NOT l.strategy_action OR x.trade_intent IS NOT l.trade_intent
                   OR x.suggested_weight_pct IS NOT l.suggested_weight_pct OR x.reason IS NOT l.reason
                   OR x.signal_json IS NOT l.signal_json""",
        }
        mismatches: dict[str, int] = {}
        for name, sql in state_checks.items():
            if not self._table_exists(f"research_{name}"):
                mismatches[name] = 0
                continue
            mismatch = int(self.conn.execute(sql, (DEFAULT_EXCHANGE, DEFAULT_STRATEGY)).fetchone()[0])
            mismatches[name] = mismatch
            if mismatch:
                errors.append(f"{name} state mismatch rows={mismatch}")
        return {"ok": not errors, "counts": counts, "state_mismatches": mismatches, "errors": errors}

    def cutover_legacy_bithumb(self) -> dict[str, Any]:
        existing = self.migration_record(BITHUMB_CUTOVER_MIGRATION)
        if existing:
            return {"status": "already_applied", "migration": existing}
        migrated = self.migrate_legacy_bithumb()
        verification = self.verify_legacy_bithumb_parity()
        if not verification.get("ok"):
            raise RuntimeError("Bithumb legacy->scoped verification failed: " + "; ".join(verification.get("errors") or []))
        details = {"exchange": DEFAULT_EXCHANGE, "strategy": DEFAULT_STRATEGY, "migrated": migrated, "verification": verification}
        self._record_migration(BITHUMB_CUTOVER_MIGRATION, details)
        return {"status": "applied", **details}

    def ensure_market(self, exchange: str, market: str, strategy: str, symbol: str, name: str) -> None:
        exchange, market, strategy = exchange.lower(), market.upper(), strategy.lower()
        now = time.time()
        self.conn.execute(
            """INSERT OR IGNORE INTO research_accounts_mx(
                exchange,market,strategy,symbol,name,cash_krw,volume,avg_price,realized_pnl,peak_equity,
                max_drawdown_pct,peak_price,last_buy_at,last_trade_at,entry_ts,entry_signal_json,updated_ts)
                VALUES(?,?,?,?,?,?,0,0,0,?,0,0,0,0,0,'{}',?)""",
            (exchange, market, strategy, symbol, name, START_KRW, START_KRW, now),
        )
        profile = AdaptiveProfile()
        self.conn.execute(
            """INSERT OR IGNORE INTO research_profiles_mx(
                exchange,market,strategy,regime_floor,entry_floor,exploration_floor,base_weight_pct,
                max_position_pct,closed_trades,wins,ema_return_pct,version,updated_ts)
                VALUES(?,?,?,?,?,?,?,?,0,0,0,1,?)""",
            (exchange, market, strategy, profile.regime_floor, profile.entry_floor,
             profile.exploration_floor, profile.base_weight_pct, profile.max_position_pct, now),
        )
        self.conn.execute(
            "UPDATE research_accounts_mx SET symbol=?,name=? WHERE exchange=? AND market=? AND strategy=?",
            (symbol, name, exchange, market, strategy),
        )
        self.conn.commit()

    def account(self, exchange: str, market: str, strategy: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM research_accounts_mx WHERE exchange=? AND market=? AND strategy=?",
            (exchange.lower(), market.upper(), strategy.lower()),
        ).fetchone()
        return dict(row) if row else {}

    def profile(self, exchange: str, market: str, strategy: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM research_profiles_mx WHERE exchange=? AND market=? AND strategy=?",
            (exchange.lower(), market.upper(), strategy.lower()),
        ).fetchone()
        return dict(row) if row else {}

    def counts(self) -> dict[str, int]:
        names = ["research_accounts_mx", "research_profiles_mx", "research_signals_mx",
                 "research_fills_mx", "research_feedback_mx", "research_equity_mx",
                 "research_market_memory_mx"]
        return {name: int(self.conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) for name in names}

    def scope_counts(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT exchange,strategy,COUNT(*) AS accounts
               FROM research_accounts_mx GROUP BY exchange,strategy ORDER BY exchange,strategy"""
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.conn.close()
