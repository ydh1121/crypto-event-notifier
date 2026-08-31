from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .config import Settings
from .http_retry import post_with_retry
from .multi_exchange_store import BITHUMB_CUTOVER_MIGRATION
from .research_control import platform_snapshot
from .strategy_lab_snapshot import read_strategy_lab_snapshot

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_STATUS_PATH = REPO_ROOT / "dashboard/runtime-demo.json"
UPBIT_STATUS_PATH = REPO_ROOT / "dashboard/runtime-demo-upbit.json"
DEMO_DB_PATH = REPO_ROOT / "b3_trader/data/auto_demo.sqlite3"
MAX_RANKING_ROWS = 5000
MAX_BODY_BYTES = 1_800_000
RECENT_FILL_LIMIT = 80
RECENT_FEEDBACK_LIMIT = 60
RECENT_DECISION_LIMIT = 80
RECENT_SYSTEM_EVENT_LIMIT = 80
DECISION_SCAN_LIMIT = 4000
MANUAL_HOLDINGS_SNAPSHOT_INTERVAL_SECONDS = 300
MANUAL_HOLDINGS_RETENTION_SECONDS = 90 * 86400
MANUAL_HOLDINGS_VIEWER_HISTORY_LIMIT = 2016


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _compact_market(
    row: dict[str, Any], *, exchange: str = "", strategy: str = "adaptive"
) -> dict[str, Any]:
    keys = (
        "key", "exchange", "strategy", "market", "symbol", "name", "price", "equity_krw",
        "return_pct", "cash_krw", "position_value_krw", "position_cost_krw", "position_avg_price",
        "unrealized_pnl_krw", "realized_pnl_krw", "max_drawdown_pct", "closed_trades",
        "win_rate_pct", "opportunity_score", "regime_score", "entry_score", "suggested_weight_pct",
        "trade_intent", "signal_ts", "has_position", "state_class", "state_label", "warning",
    )
    result = {key: row.get(key) for key in keys if key in row}
    market = str(result.get("market") or row.get("market") or "")
    resolved_exchange = str(result.get("exchange") or exchange or "").lower()
    resolved_strategy = str(result.get("strategy") or strategy or "adaptive").lower()
    if resolved_exchange:
        result["exchange"] = resolved_exchange
    if resolved_strategy:
        result["strategy"] = resolved_strategy
    if market and resolved_exchange and "key" not in result:
        result["key"] = f"{resolved_exchange}|{market}|{resolved_strategy}"
    return result


def _exchange_payload(demo: dict[str, Any], exchange: str, strategy: str = "adaptive") -> dict[str, Any]:
    source = demo.get("leaderboard") if isinstance(demo.get("leaderboard"), list) else []
    leaderboard = [
        _compact_market(row, exchange=exchange, strategy=strategy)
        for row in source[:MAX_RANKING_ROWS]
        if isinstance(row, dict)
    ]
    start = _number(demo.get("aggregate_virtual_capital_krw"))
    equity = _number(demo.get("equity_krw"))
    pnl = equity - start if start > 0 else 0.0
    return {
        "exchange": exchange,
        "strategy": strategy,
        "paper_only": True,
        "source_updated_at": _number(demo.get("updated_at")),
        "market_count": int(demo.get("market_count") or len(leaderboard)),
        "scanned_count": int(demo.get("scanned_count") or 0),
        "scan_total": int(demo.get("scan_total") or 0),
        "active_positions": int(demo.get("active_positions") or 0),
        "warning_markets": int(demo.get("warning_markets") or 0),
        "aggregate_virtual_capital_krw": round(start, 2),
        "equity_krw": round(equity, 2),
        "cash_krw": round(_number(demo.get("cash_krw")), 2),
        "pnl_krw": round(pnl, 2),
        "return_pct": round(pnl / start * 100.0, 6) if start > 0 else 0.0,
        "best_market": (
            _compact_market(demo.get("best_market") or {}, exchange=exchange, strategy=strategy)
            if isinstance(demo.get("best_market"), dict)
            else None
        ),
        "leaderboard": leaderboard,
    }


def _journal_path(journal_db: str) -> Path:
    path = Path(journal_db)
    return path if path.is_absolute() else REPO_ROOT / path


def _manual_holdings(journal_db: str, price_by_market: dict[str, float]) -> dict[str, Any]:
    path = _journal_path(journal_db)
    if not path.exists():
        return {
            "holdings": [], "invested_krw": 0.0, "value_krw": 0.0, "pnl_krw": 0.0,
            "holding_count": 0, "priced_holding_count": 0, "valuation_complete": True,
        }
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='manual_holdings' LIMIT 1"
        ).fetchone()
        if not exists:
            return {
                "holdings": [], "invested_krw": 0.0, "value_krw": 0.0, "pnl_krw": 0.0,
                "holding_count": 0, "priced_holding_count": 0, "valuation_complete": True,
            }
        rows = conn.execute(
            "SELECT market,volume,avg_price,updated_ts FROM manual_holdings ORDER BY market"
        ).fetchall()
    finally:
        conn.close()

    items: list[dict[str, Any]] = []
    invested_total = 0.0
    value_total = 0.0
    holding_count = 0
    priced_holding_count = 0
    for source in rows:
        row = dict(source)
        volume = max(0.0, _number(row.get("volume")))
        avg_price = max(0.0, _number(row.get("avg_price")))
        current_price = max(0.0, _number(price_by_market.get(str(row.get("market")))))
        invested = volume * avg_price
        value = volume * current_price if current_price > 0 else 0.0
        pnl = value - invested if current_price > 0 else 0.0
        pnl_pct = pnl / invested * 100.0 if invested > 0 and current_price > 0 else 0.0
        if volume > 0:
            holding_count += 1
            if current_price > 0:
                priced_holding_count += 1
        invested_total += invested
        value_total += value
        items.append(
            {
                "market": row.get("market"), "volume": volume, "avg_price": avg_price,
                "current_price": current_price, "invested_krw": round(invested, 2),
                "value_krw": round(value, 2), "unrealized_pnl_krw": round(pnl, 2),
                "unrealized_pnl_pct": round(pnl_pct, 4), "updated_ts": row.get("updated_ts"),
            }
        )
    valuation_complete = holding_count == priced_holding_count
    return {
        "holdings": items,
        "invested_krw": round(invested_total, 2),
        "value_krw": round(value_total, 2),
        "pnl_krw": round(value_total - invested_total, 2) if valuation_complete else 0.0,
        "holding_count": holding_count,
        "priced_holding_count": priced_holding_count,
        "valuation_complete": valuation_complete,
    }


def _record_manual_holdings_snapshot(
    journal_db: str,
    summary: dict[str, Any],
    *,
    now: float | None = None,
) -> bool:
    if int(summary.get("holding_count") or 0) <= 0 or not bool(summary.get("valuation_complete")):
        return False
    path = _journal_path(journal_db)
    if not path.exists():
        return False
    stamp = float(now if now is not None else time.time())
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS manual_holdings_value_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    invested_krw REAL NOT NULL,
                    value_krw REAL NOT NULL,
                    pnl_krw REAL NOT NULL,
                    holding_count INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_manual_holdings_value_snapshots_ts
                ON manual_holdings_value_snapshots(ts);
                """
            )
            latest = conn.execute(
                "SELECT ts FROM manual_holdings_value_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if latest and stamp - _number(latest[0]) < MANUAL_HOLDINGS_SNAPSHOT_INTERVAL_SECONDS:
                return False
            conn.execute(
                "INSERT INTO manual_holdings_value_snapshots"
                "(ts,invested_krw,value_krw,pnl_krw,holding_count) VALUES (?,?,?,?,?)",
                (
                    stamp,
                    _number(summary.get("invested_krw")),
                    _number(summary.get("value_krw")),
                    _number(summary.get("pnl_krw")),
                    int(summary.get("holding_count") or 0),
                ),
            )
            conn.execute(
                "DELETE FROM manual_holdings_value_snapshots WHERE ts < ?",
                (stamp - MANUAL_HOLDINGS_RETENTION_SECONDS,),
            )
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def _manual_holdings_history(
    journal_db: str,
    *,
    limit: int = MANUAL_HOLDINGS_VIEWER_HISTORY_LIMIT,
) -> dict[str, Any]:
    path = _journal_path(journal_db)
    if not path.exists():
        return {"interval_seconds": MANUAL_HOLDINGS_SNAPSHOT_INTERVAL_SECONDS, "retention_days": 90, "points": []}
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='manual_holdings_value_snapshots' LIMIT 1"
        ).fetchone()
        if not exists:
            return {"interval_seconds": MANUAL_HOLDINGS_SNAPSHOT_INTERVAL_SECONDS, "retention_days": 90, "points": []}
        rows = conn.execute(
            "SELECT ts,invested_krw,value_krw,pnl_krw,holding_count "
            "FROM manual_holdings_value_snapshots ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), MANUAL_HOLDINGS_VIEWER_HISTORY_LIMIT)),),
        ).fetchall()
    except sqlite3.Error:
        return {"interval_seconds": MANUAL_HOLDINGS_SNAPSHOT_INTERVAL_SECONDS, "retention_days": 90, "points": []}
    finally:
        conn.close()
    points = [
        [
            round(_number(row["ts"]), 3),
            round(_number(row["invested_krw"]), 2),
            round(_number(row["value_krw"]), 2),
            round(_number(row["pnl_krw"]), 2),
            int(row["holding_count"] or 0),
        ]
        for row in reversed(rows)
    ]
    return {
        "interval_seconds": MANUAL_HOLDINGS_SNAPSHOT_INTERVAL_SECONDS,
        "retention_days": 90,
        "points": points,
    }


def _safe_system_event_payload(kind: str, encoded: Any) -> dict[str, Any]:
    payload = _json_object(encoded)
    result: dict[str, Any] = {}
    for key in ("market", "reason", "error"):
        value = payload.get(key)
        if value not in (None, ""):
            result[key] = str(value)[:160]
    for key in ("fills", "open_positions"):
        if key in payload:
            result[key] = int(_number(payload.get(key)))
    for key in ("cash_krw", "price", "order_krw", "spread_bps", "estimated_slippage_bps"):
        if key in payload:
            result[key] = round(_number(payload.get(key)), 6)
    reasons = payload.get("reasons")
    if isinstance(reasons, list):
        result["reasons"] = [str(value)[:120] for value in reasons[:4]]
    result["kind"] = str(kind)[:80]
    return result


def _journal_records(journal_db: str) -> dict[str, Any]:
    empty = {"decision_changes": [], "system_events": [], "updated_at": 0.0}
    path = _journal_path(journal_db)
    if not path.exists():
        return empty
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        decision_changes: list[dict[str, Any]] = []
        if "snapshots" in tables:
            rows = conn.execute(
                "SELECT ts,market,price,regime_score,entry_score,action "
                "FROM snapshots ORDER BY id DESC LIMIT ?",
                (DECISION_SCAN_LIMIT,),
            ).fetchall()
            previous_by_market: dict[str, str] = {}
            for source in reversed(rows):
                market = str(source["market"] or "")
                action = str(source["action"] or "")
                previous = previous_by_market.get(market)
                if previous is not None and action and action != previous:
                    decision_changes.append(
                        {
                            "exchange": "bithumb",
                            "ts": _number(source["ts"]),
                            "market": market,
                            "symbol": market.removeprefix("KRW-"),
                            "from_action": previous,
                            "to_action": action,
                            "price": round(_number(source["price"]), 12),
                            "regime_score": round(_number(source["regime_score"]), 3),
                            "entry_score": round(_number(source["entry_score"]), 3),
                        }
                    )
                if action:
                    previous_by_market[market] = action
            decision_changes = list(reversed(decision_changes[-RECENT_DECISION_LIMIT:]))

        system_events: list[dict[str, Any]] = []
        if "events" in tables:
            rows = conn.execute(
                "SELECT ts,kind,payload_json FROM events ORDER BY id DESC LIMIT ?",
                (RECENT_SYSTEM_EVENT_LIMIT,),
            ).fetchall()
            system_events = [
                {
                    "ts": _number(row["ts"]),
                    **_safe_system_event_payload(str(row["kind"] or "event"), row["payload_json"]),
                }
                for row in rows
            ]
        latest = max(
            [0.0]
            + [_number(row.get("ts")) for row in decision_changes]
            + [_number(row.get("ts")) for row in system_events]
        )
        return {
            "decision_changes": decision_changes,
            "system_events": system_events,
            "updated_at": latest,
        }
    except sqlite3.Error:
        return empty
    finally:
        conn.close()


def _records_payload(
    fill_rows: list[sqlite3.Row],
    feedback_rows: list[sqlite3.Row],
    fill_count: int,
    feedback_count: int,
    *,
    exchange: str,
    strategy: str = "adaptive",
) -> dict[str, Any]:
    fills = [
        {
            "exchange": exchange, "strategy": strategy,
            "ts": _number(row["ts"]), "market": row["market"], "symbol": row["symbol"],
            "side": row["side"], "price": round(_number(row["price"]), 12),
            "krw": round(_number(row["krw"]), 2), "realized_pnl": round(_number(row["realized_pnl"]), 2),
            "return_pct": round(_number(row["return_pct"]), 4), "reason": str(row["reason"] or "")[:220],
        }
        for row in fill_rows
    ]
    feedback: list[dict[str, Any]] = []
    for row in feedback_rows:
        before = _json_object(row["profile_before_json"])
        after = _json_object(row["profile_after_json"])
        feedback.append(
            {
                "exchange": exchange, "strategy": strategy,
                "ts": _number(row["ts"]), "market": row["market"],
                "outcome_return_pct": round(_number(row["outcome_return_pct"]), 4),
                "realized_pnl": round(_number(row["realized_pnl"]), 2),
                "holding_seconds": round(_number(row["holding_seconds"]), 1),
                "note": str(row["note"] or "")[:260],
                "profile_change": {
                    "regime_before": round(_number(before.get("regime_floor")), 3),
                    "regime_after": round(_number(after.get("regime_floor")), 3),
                    "entry_before": round(_number(before.get("entry_floor")), 3),
                    "entry_after": round(_number(after.get("entry_floor")), 3),
                    "weight_before": round(_number(before.get("base_weight_pct")), 3),
                    "weight_after": round(_number(after.get("base_weight_pct")), 3),
                },
            }
        )
    latest = max([0.0] + [_number(row.get("ts")) for row in fills] + [_number(row.get("ts")) for row in feedback])
    return {
        "strategy": strategy,
        "fills": fills, "feedback": feedback, "fill_count": fill_count,
        "feedback_count": feedback_count, "updated_at": latest,
    }


def _recent_research_records(path: Path = DEMO_DB_PATH) -> dict[str, Any]:
    empty = {"strategy": "adaptive", "fills": [], "feedback": [], "fill_count": 0, "feedback_count": 0, "updated_at": 0.0}
    if not path.exists():
        return empty
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "research_fills" not in tables or "research_feedback" not in tables:
            return empty
        fill_rows = conn.execute(
            "SELECT ts,market,symbol,side,price,krw,realized_pnl,return_pct,reason FROM research_fills ORDER BY id DESC LIMIT ?",
            (RECENT_FILL_LIMIT,),
        ).fetchall()
        feedback_rows = conn.execute(
            "SELECT ts,market,outcome_return_pct,realized_pnl,holding_seconds,profile_before_json,profile_after_json,note FROM research_feedback ORDER BY id DESC LIMIT ?",
            (RECENT_FEEDBACK_LIMIT,),
        ).fetchall()
        fill_count = int(conn.execute("SELECT COUNT(*) FROM research_fills").fetchone()[0])
        feedback_count = int(conn.execute("SELECT COUNT(*) FROM research_feedback").fetchone()[0])
        return _records_payload(
            fill_rows, feedback_rows, fill_count, feedback_count,
            exchange="bithumb", strategy="adaptive",
        )
    except sqlite3.Error:
        return empty
    finally:
        conn.close()


def _recent_scoped_records(exchange: str, strategy: str = "adaptive", path: Path = DEMO_DB_PATH) -> dict[str, Any]:
    empty = {"strategy": strategy, "fills": [], "feedback": [], "fill_count": 0, "feedback_count": 0, "updated_at": 0.0}
    if not path.exists():
        return empty
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "research_fills_mx" not in tables or "research_feedback_mx" not in tables:
            return empty
        fill_rows = conn.execute(
            """SELECT ts,market,symbol,side,price,krw,realized_pnl,return_pct,reason
               FROM research_fills_mx WHERE exchange=? AND strategy=? ORDER BY id DESC LIMIT ?""",
            (exchange, strategy, RECENT_FILL_LIMIT),
        ).fetchall()
        feedback_rows = conn.execute(
            """SELECT ts,market,outcome_return_pct,realized_pnl,holding_seconds,profile_before_json,profile_after_json,note
               FROM research_feedback_mx WHERE exchange=? AND strategy=? ORDER BY id DESC LIMIT ?""",
            (exchange, strategy, RECENT_FEEDBACK_LIMIT),
        ).fetchall()
        fill_count = int(conn.execute(
            "SELECT COUNT(*) FROM research_fills_mx WHERE exchange=? AND strategy=?", (exchange, strategy)
        ).fetchone()[0])
        feedback_count = int(conn.execute(
            "SELECT COUNT(*) FROM research_feedback_mx WHERE exchange=? AND strategy=?", (exchange, strategy)
        ).fetchone()[0])
        return _records_payload(
            fill_rows, feedback_rows, fill_count, feedback_count,
            exchange=exchange, strategy=strategy,
        )
    except sqlite3.Error:
        return empty
    finally:
        conn.close()


def _migration_applied(name: str, path: Path = DEMO_DB_PATH) -> bool:
    if not path.exists():
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_store_migrations'"
        ).fetchone()
        if not table:
            return False
        return bool(conn.execute("SELECT 1 FROM research_store_migrations WHERE name=?", (name,)).fetchone())
    except sqlite3.Error:
        return False
    finally:
        conn.close()


class CloudflareSnapshotPublisher:
    """Outbound-only publisher for the read-only Cloudflare Pages viewer."""

    def __init__(self) -> None:
        load_dotenv(REPO_ROOT / ".env", override=True)
        self.settings = Settings()

    def build_snapshot(self) -> dict[str, Any]:
        load_dotenv(REPO_ROOT / ".env", override=True)
        bithumb_demo = _read_json(DEMO_STATUS_PATH)
        upbit_demo = _read_json(UPBIT_STATUS_PATH)
        bithumb = _exchange_payload(bithumb_demo, "bithumb")
        upbit = _exchange_payload(upbit_demo, "upbit") if upbit_demo else _exchange_payload({}, "upbit")
        leaderboard = bithumb["leaderboard"]
        price_by_market = {
            str(row.get("market")): _number(row.get("price"))
            for row in leaderboard if row.get("market")
        }
        recent_bithumb = (
            _recent_scoped_records("bithumb")
            if _migration_applied(BITHUMB_CUTOVER_MIGRATION)
            else _recent_research_records()
        )
        recent_upbit = _recent_scoped_records("upbit")
        strategy_lab = read_strategy_lab_snapshot(DEMO_DB_PATH)
        journal_records = _journal_records(self.settings.journal_db)
        manual_holdings = _manual_holdings(self.settings.journal_db, price_by_market)
        _record_manual_holdings_snapshot(self.settings.journal_db, manual_holdings)
        public_payload = {
            "version": 3,
            "paper_only": True,
            "exchange": "bithumb",
            "strategy": "adaptive",
            "source_updated_at": bithumb["source_updated_at"],
            "multi_exchange_updated_at": max(
                _number(bithumb.get("source_updated_at")), _number(upbit.get("source_updated_at"))
            ),
            "published_at": time.time(),
            # Backward-compatible Bithumb root contract used by the current viewer.
            "market_count": bithumb["market_count"],
            "scanned_count": bithumb["scanned_count"],
            "scan_total": bithumb["scan_total"],
            "active_positions": bithumb["active_positions"],
            "aggregate_virtual_capital_krw": bithumb["aggregate_virtual_capital_krw"],
            "equity_krw": bithumb["equity_krw"],
            "cash_krw": bithumb["cash_krw"],
            "pnl_krw": bithumb["pnl_krw"],
            "return_pct": bithumb["return_pct"],
            "best_market": bithumb["best_market"],
            "leaderboard": leaderboard,
            "research_node": platform_snapshot(),
            "recent_records": recent_bithumb,
            "journal_records": journal_records,
            "strategy_lab": strategy_lab,
            # Phase 3 contract. New UI can switch/compare without breaking old readers.
            "exchanges": {"bithumb": bithumb, "upbit": upbit},
            "exchange_records": {"bithumb": recent_bithumb, "upbit": recent_upbit},
        }
        private_payload: dict[str, Any] = {}
        if _bool_env("CLOUDFLARE_PUBLISH_PRIVATE_HOLDINGS", False):
            private_payload["manual_holdings"] = manual_holdings
            private_payload["manual_holdings_history"] = _manual_holdings_history(self.settings.journal_db)
        source_ts = max(
            _number(public_payload.get("source_updated_at")),
            _number(public_payload.get("multi_exchange_updated_at")),
            _number(strategy_lab.get("updated_at")),
            _number(journal_records.get("updated_at")),
        )
        return {"source_ts": source_ts, "public": public_payload, "private": private_payload}

    def publish_once(self) -> dict[str, Any]:
        load_dotenv(REPO_ROOT / ".env", override=True)
        url = os.getenv("CLOUDFLARE_VIEWER_INGEST_URL", "").strip()
        token = os.getenv("CLOUDFLARE_VIEWER_INGEST_TOKEN", "").strip()
        if not url or not token:
            return {
                "status": "not_configured", "configured": False,
                "private_holdings_enabled": _bool_env("CLOUDFLARE_PUBLISH_PRIVATE_HOLDINGS", False),
            }
        snapshot = self.build_snapshot()
        body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_BODY_BYTES:
            raise RuntimeError(f"snapshot is too large: {len(body)} bytes")
        response, retries = post_with_retry(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}", "Content-Type": "application/json",
                "User-Agent": "crypto-auto-trader-local-publisher/2.0",
            },
            timeout=20,
            attempts=3,
        )
        try:
            result = response.json()
        except ValueError:
            result = {"ok": True}
        exchanges = snapshot["public"].get("exchanges") or {}
        lab = snapshot["public"].get("strategy_lab") or {}
        return {
            "status": "published", "configured": True, "bytes": len(body), "retries": retries,
            "markets": len(snapshot["public"].get("leaderboard") or []),
            "exchange_markets": {
                name: len((payload or {}).get("leaderboard") or [])
                for name, payload in exchanges.items() if isinstance(payload, dict)
            },
            "strategy_lab_experiments": len(lab.get("experiments") or []),
            "journal_decision_changes": len((snapshot["public"].get("journal_records") or {}).get("decision_changes") or []),
            "journal_system_events": len((snapshot["public"].get("journal_records") or {}).get("system_events") or []),
            "source_ts": snapshot.get("source_ts"), "private_holdings_enabled": bool(snapshot.get("private")),
            "remote": result if isinstance(result, dict) else {},
        }


def main() -> None:
    print(json.dumps(CloudflareSnapshotPublisher().publish_once(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
