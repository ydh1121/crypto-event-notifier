from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import requests

from .config import Settings
from .research_control import platform_snapshot

DEMO_STATUS_PATH = Path("dashboard/runtime-demo.json")
MAX_RANKING_ROWS = 5000
MAX_BODY_BYTES = 1_800_000


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


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


def _compact_market(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "market", "symbol", "name", "price", "equity_krw", "return_pct", "cash_krw",
        "position_value_krw", "position_avg_price", "unrealized_pnl_krw", "realized_pnl_krw",
        "max_drawdown_pct", "closed_trades", "win_rate_pct", "opportunity_score", "regime_score",
        "entry_score", "suggested_weight_pct", "trade_intent", "signal_ts", "has_position",
        "state_class", "state_label",
    )
    return {key: row.get(key) for key in keys if key in row}


def _manual_holdings(journal_db: str, price_by_market: dict[str, float]) -> dict[str, Any]:
    path = Path(journal_db)
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
                "market": row.get("market"),
                "volume": volume,
                "avg_price": avg_price,
                "current_price": current_price,
                "invested_krw": round(invested, 2),
                "value_krw": round(value, 2),
                "unrealized_pnl_krw": round(pnl, 2),
                "unrealized_pnl_pct": round(pnl_pct, 4),
                "updated_ts": row.get("updated_ts"),
            }
        )
    return {
        "holdings": items,
        "invested_krw": round(invested_total, 2),
        "value_krw": round(value_total, 2),
        "pnl_krw": round(value_total - invested_total, 2),
    }


class CloudflareSnapshotPublisher:
    """Outbound-only publisher for the read-only Cloudflare Pages viewer."""

    def __init__(self) -> None:
        self.settings = Settings()

    def build_snapshot(self) -> dict[str, Any]:
        demo = _read_json(DEMO_STATUS_PATH)
        leaderboard_source = demo.get("leaderboard") if isinstance(demo.get("leaderboard"), list) else []
        leaderboard = [
            _compact_market(row)
            for row in leaderboard_source[:MAX_RANKING_ROWS]
            if isinstance(row, dict)
        ]
        price_by_market = {
            str(row.get("market")): _number(row.get("price"))
            for row in leaderboard
            if row.get("market")
        }
        start = _number(demo.get("aggregate_virtual_capital_krw"))
        equity = _number(demo.get("equity_krw"))
        pnl = equity - start if start > 0 else 0.0
        public_payload = {
            "version": 1,
            "paper_only": True,
            "source_updated_at": _number(demo.get("updated_at")),
            "published_at": time.time(),
            "market_count": int(demo.get("market_count") or len(leaderboard)),
            "scanned_count": int(demo.get("scanned_count") or 0),
            "scan_total": int(demo.get("scan_total") or 0),
            "active_positions": int(demo.get("active_positions") or 0),
            "aggregate_virtual_capital_krw": round(start, 2),
            "equity_krw": round(equity, 2),
            "cash_krw": round(_number(demo.get("cash_krw")), 2),
            "pnl_krw": round(pnl, 2),
            "return_pct": round(pnl / start * 100.0, 6) if start > 0 else 0.0,
            "best_market": _compact_market(demo.get("best_market") or {}) if isinstance(demo.get("best_market"), dict) else None,
            "leaderboard": leaderboard,
            "research_node": platform_snapshot(),
        }
        private_payload: dict[str, Any] = {}
        if _bool_env("CLOUDFLARE_PUBLISH_PRIVATE_HOLDINGS", False):
            private_payload["manual_holdings"] = _manual_holdings(self.settings.journal_db, price_by_market)
        return {"source_ts": public_payload["source_updated_at"], "public": public_payload, "private": private_payload}

    def publish_once(self) -> dict[str, Any]:
        url = os.getenv("CLOUDFLARE_VIEWER_INGEST_URL", "").strip()
        token = os.getenv("CLOUDFLARE_VIEWER_INGEST_TOKEN", "").strip()
        if not url or not token:
            return {
                "status": "not_configured",
                "configured": False,
                "private_holdings_enabled": _bool_env("CLOUDFLARE_PUBLISH_PRIVATE_HOLDINGS", False),
            }
        snapshot = self.build_snapshot()
        body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_BODY_BYTES:
            raise RuntimeError(f"snapshot is too large: {len(body)} bytes")
        response = requests.post(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "crypto-auto-trader-local-publisher/1.0",
            },
            timeout=20,
        )
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError:
            result = {"ok": True}
        return {
            "status": "published",
            "configured": True,
            "bytes": len(body),
            "markets": len(snapshot["public"].get("leaderboard") or []),
            "source_ts": snapshot.get("source_ts"),
            "private_holdings_enabled": bool(snapshot.get("private")),
            "remote": result if isinstance(result, dict) else {},
        }


def main() -> None:
    print(json.dumps(CloudflareSnapshotPublisher().publish_once(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
