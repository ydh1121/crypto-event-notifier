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

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_STATUS_PATH = REPO_ROOT / "dashboard/runtime-demo.json"
UPBIT_STATUS_PATH = REPO_ROOT / "dashboard/runtime-demo-upbit.json"
DEMO_DB_PATH = REPO_ROOT / "b3_trader/data/auto_demo.sqlite3"
MAX_RANKING_ROWS = 5000
MAX_BODY_BYTES = 1_800_000
RECENT_FILL_LIMIT = 80
RECENT_FEEDBACK_LIMIT = 60


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


def _manual_holdings(journal_db: str, price_by_market: dict[str, float]) -> dict[str, Any]:
    path = Path(journal_db)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        return {"holdings": [], "invested_krw": 0.0, "value_krw": 0.0, "pnl_krw": 0.0}
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='manual_holdings' LIMIT 1"
        ).fetchone()
        if not exists:
            return {"holdings": [], "invested_krw": 0.0, "value_krw": 0.0, "pnl_krw": 0.0}
        rows = conn.execute(
            "SELECT market,volume,avg_price,updated_ts FROM manual_holdings ORDER BY market"
        ).fetchall()
    finally:
        conn.close()

    items: list[dict[str, Any]] = []
    invested_total = 0.0
    value_total = 0.0
    for source in rows:
        row = dict(source)
        volume = max(0.0, _number(row.get("volume")))
        avg_price = max(0.0, _number(row.get("avg_price")))
        current_price = max(0.0, _number(price_by_market.get(str(row.get("market")))))
        invested = volume * avg_price
        value = volume * current_price if current_price > 0 else 0.0
        pnl = value - invested if current_price > 0 else 0.0
        pnl_pct = pnl / invested * 100.0 if invested > 0 and current_price > 0 else 0.0
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
    return {
        "holdings": items,
        "invested_krw": round(invested_total, 2),
        "value_krw": round(value_total, 2),
        "pnl_krw": round(value_total - invested_total, 2),
    }


def _records_payload(
    fill_rows: list[sqlite3.Row],
    feedback_rows: list[sqlite3.Row],
    fill_count: int,
    feedback_count: int,
    *,
    exchange: str,
) -> dict[str, Any]:
    fills = [
        {
            "exchange": exchange,
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
                "exchange": exchange,
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
        "fills": fills, "feedback": feedback, "fill_count": fill_count,
        "feedback_count": feedback_count, "updated_at": latest,
    }


def _recent_research_records(path: Path = DEMO_DB_PATH) -> dict[str, Any]:
    empty = {"fills": [], "feedback": [], "fill_count": 0, "feedback_count": 0, "updated_at": 0.0}
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
        return _records_payload(fill_rows, feedback_rows, fill_count, feedback_count, exchange="bithumb")
    except sqlite3.Error:
        return empty
    finally:
        conn.close()


def _recent_scoped_records(exchange: str, strategy: str = "adaptive", path: Path = DEMO_DB_PATH) -> dict[str, Any]:
    empty = {"fills": [], "feedback": [], "fill_count": 0, "feedback_count": 0, "updated_at": 0.0}
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
        return _records_payload(fill_rows, feedback_rows, fill_count, feedback_count, exchange=exchange)
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
        public_payload = {
            "version": 2,
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
            # Phase 3 contract. New UI can switch/compare without breaking old readers.
            "exchanges": {"bithumb": bithumb, "upbit": upbit},
            "exchange_records": {"bithumb": recent_bithumb, "upbit": recent_upbit},
        }
        private_payload: dict[str, Any] = {}
        if _bool_env("CLOUDFLARE_PUBLISH_PRIVATE_HOLDINGS", False):
            private_payload["manual_holdings"] = _manual_holdings(self.settings.journal_db, price_by_market)
        source_ts = max(
            _number(public_payload.get("source_updated_at")), _number(public_payload.get("multi_exchange_updated_at"))
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
        return {
            "status": "published", "configured": True, "bytes": len(body), "retries": retries,
            "markets": len(snapshot["public"].get("leaderboard") or []),
            "exchange_markets": {
                name: len((payload or {}).get("leaderboard") or [])
                for name, payload in exchanges.items() if isinstance(payload, dict)
            },
            "source_ts": snapshot.get("source_ts"), "private_holdings_enabled": bool(snapshot.get("private")),
            "remote": result if isinstance(result, dict) else {},
        }


def main() -> None:
    print(json.dumps(CloudflareSnapshotPublisher().publish_once(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
