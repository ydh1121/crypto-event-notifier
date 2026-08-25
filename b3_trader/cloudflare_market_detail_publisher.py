from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = REPO_ROOT / "b3_trader/data/research-platform/cloudflare-market-detail-state.json"
MAX_BODY_BYTES = 1_500_000
MAX_SINGLE_DETAIL_BYTES = 170_000
SOURCE_CONFIGS = (
    {
        "exchange": "bithumb",
        "strategy": "adaptive",
        "status": REPO_ROOT / "dashboard/runtime-demo.json",
        "details": REPO_ROOT / "dashboard/demo-runtime",
        "priority": 8,
        "rotating": 32,
        "max_batch": 40,
    },
    {
        "exchange": "upbit",
        "strategy": "adaptive",
        "status": REPO_ROOT / "dashboard/runtime-demo-upbit.json",
        "details": REPO_ROOT / "dashboard/demo-runtime-upbit",
        "priority": 6,
        "rotating": 18,
        "max_batch": 24,
    },
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    try:
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pick(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: source.get(key) for key in keys if key in source}


def _compact_fill(row: dict[str, Any]) -> dict[str, Any]:
    return _pick(
        row,
        (
            "id", "exchange", "strategy", "ts", "market", "symbol", "side", "price", "volume", "krw",
            "weight_pct", "realized_pnl", "return_pct", "reason",
        ),
    )


def _compact_feedback(row: dict[str, Any]) -> dict[str, Any]:
    result = _pick(
        row,
        ("id", "exchange", "strategy", "ts", "market", "outcome_return_pct", "realized_pnl", "holding_seconds", "note"),
    )
    before = row.get("profile_before") if isinstance(row.get("profile_before"), dict) else {}
    after = row.get("profile_after") if isinstance(row.get("profile_after"), dict) else {}
    profile_keys = (
        "regime_floor", "entry_floor", "exploration_floor", "base_weight_pct",
        "max_position_pct", "closed_trades", "wins", "ema_return_pct", "version",
    )
    result["profile_before"] = _pick(before, profile_keys)
    result["profile_after"] = _pick(after, profile_keys)
    return result


def _compact_memory(row: dict[str, Any]) -> dict[str, Any]:
    return _pick(
        row,
        (
            "ts", "signal_ts", "exchange", "strategy", "price", "change_24h_pct", "liquidity_score",
            "regime_score", "entry_score", "opportunity_score", "suggested_weight_pct", "trade_intent",
            "asset_return_pct", "pullback_pct", "volatility_pct", "orderbook_imbalance",
            "fib_retrace", "btc_return_pct", "eth_return_pct", "asset_vs_majors_pct",
            "price_delta_pct", "opportunity_delta", "regime_delta", "entry_delta",
        ),
    )


def _compact_detail(source: dict[str, Any]) -> dict[str, Any]:
    summary = source.get("summary") if isinstance(source.get("summary"), dict) else {}
    account = source.get("account") if isinstance(source.get("account"), dict) else {}
    profile = source.get("profile") if isinstance(source.get("profile"), dict) else {}
    signal = source.get("signal") if isinstance(source.get("signal"), dict) else {}
    signal_inner = signal.get("signal") if isinstance(signal.get("signal"), dict) else {}
    trade_plan = source.get("trade_plan") if isinstance(source.get("trade_plan"), dict) else {}
    position = source.get("position") if isinstance(source.get("position"), dict) else {}
    fills = source.get("fills") if isinstance(source.get("fills"), list) else []
    feedback = source.get("feedback") if isinstance(source.get("feedback"), list) else []
    equity = source.get("equity_history") if isinstance(source.get("equity_history"), list) else []
    memory = source.get("market_memory") if isinstance(source.get("market_memory"), list) else []

    signal_payload = _pick(
        signal,
        (
            "exchange", "strategy", "market", "symbol", "ts", "price", "turnover_24h", "change_24h_pct",
            "liquidity_score", "regime_score", "entry_score", "opportunity_score", "strategy_action",
            "trade_intent", "suggested_weight_pct", "reason",
        ),
    )
    signal_payload["diagnostics"] = _pick(
        signal_inner,
        (
            "asset_return_pct", "pullback_pct", "volatility_pct", "orderbook_imbalance",
            "fib_retrace", "btc_return_pct", "eth_return_pct", "asset_vs_majors_pct", "execution_note",
        ),
    )

    return {
        "version": 2,
        "state_class": source.get("state_class"),
        "state_label": source.get("state_label"),
        "summary": _pick(
            summary,
            (
                "key", "exchange", "strategy", "market", "symbol", "name", "equity_krw", "return_pct", "cash_krw",
                "position_value_krw", "position_cost_krw", "position_avg_price", "unrealized_pnl_krw",
                "realized_pnl_krw", "max_drawdown_pct", "closed_trades", "win_rate_pct", "ema_return_pct",
                "profile_version", "price", "opportunity_score", "regime_score", "entry_score",
                "suggested_weight_pct", "trade_intent", "signal_ts", "has_position", "state_class", "state_label",
            ),
        ),
        "account": _pick(
            account,
            (
                "exchange", "strategy", "market", "symbol", "name", "cash_krw", "volume", "avg_price", "realized_pnl",
                "peak_equity", "max_drawdown_pct", "peak_price", "last_buy_at", "last_trade_at", "entry_ts", "updated_ts",
            ),
        ),
        "profile": _pick(
            profile,
            (
                "exchange", "strategy", "market", "regime_floor", "entry_floor", "exploration_floor", "base_weight_pct",
                "max_position_pct", "closed_trades", "wins", "ema_return_pct", "version", "updated_ts",
            ),
        ),
        "signal": signal_payload,
        "trade_plan": trade_plan,
        "position": position,
        "fills": [_compact_fill(row) for row in fills[:30] if isinstance(row, dict)],
        "feedback": [_compact_feedback(row) for row in feedback[:12] if isinstance(row, dict)],
        "equity_history": [
            _pick(row, ("ts", "exchange", "strategy", "equity_krw", "return_pct", "cash_krw", "position_value_krw"))
            for row in equity[-120:] if isinstance(row, dict)
        ],
        "market_memory": [_compact_memory(row) for row in memory[-120:] if isinstance(row, dict)],
        "market_memory_count": int(source.get("market_memory_count") or len(memory)),
    }


def _encode_batch(details: list[dict[str, Any]]) -> bytes:
    return json.dumps({"details": details}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _split_batches(details: list[dict[str, Any]]) -> list[tuple[list[dict[str, Any]], bytes]]:
    batches: list[tuple[list[dict[str, Any]], bytes]] = []
    current: list[dict[str, Any]] = []
    current_body = b""
    for detail in details:
        single_body = _encode_batch([detail])
        if len(single_body) > MAX_SINGLE_DETAIL_BYTES:
            key = str(detail.get("key") or detail.get("market") or "unknown")
            raise RuntimeError(f"single market detail is too large: {key} {len(single_body)} bytes")
        candidate = [*current, detail]
        candidate_body = _encode_batch(candidate)
        if current and len(candidate_body) > MAX_BODY_BYTES:
            batches.append((current, current_body))
            current = [detail]
            current_body = single_body
        else:
            current = candidate
            current_body = candidate_body
    if current:
        batches.append((current, current_body))
    return batches


class CloudflareMarketDetailPublisher:
    """Publishes bounded Bithumb + Upbit PAPER details to the read-only viewer."""

    def __init__(self) -> None:
        load_dotenv(REPO_ROOT / ".env", override=True)

    @staticmethod
    def _endpoint() -> tuple[str, str]:
        load_dotenv(REPO_ROOT / ".env", override=True)
        ingest = os.getenv("CLOUDFLARE_VIEWER_INGEST_URL", "").strip()
        token = os.getenv("CLOUDFLARE_VIEWER_INGEST_TOKEN", "").strip()
        if not ingest or not token:
            return "", ""
        if ingest.endswith("/api/ingest"):
            return ingest[: -len("/api/ingest")] + "/api/ingest-market-details", token
        return ingest.rstrip("/") + "/api/ingest-market-details", token

    @staticmethod
    def _batch_markets(
        demo: dict[str, Any], *, cursor: int, priority_count: int, rotating_count: int, max_batch: int
    ) -> tuple[list[str], int]:
        leaderboard = [row for row in (demo.get("leaderboard") or []) if isinstance(row, dict) and row.get("market")]
        markets = [str(row["market"]) for row in leaderboard]
        if not markets:
            return [], 0
        opportunity = sorted(leaderboard, key=lambda row: _num(row.get("opportunity_score")), reverse=True)
        positioned = sorted(
            (row for row in leaderboard if row.get("has_position")),
            key=lambda row: abs(_num(row.get("unrealized_pnl_krw"))), reverse=True,
        )
        priority: list[str] = []
        left = max(1, priority_count // 2)
        for row in opportunity[:left] + positioned[: max(1, priority_count - left)]:
            market = str(row.get("market") or "")
            if market and market not in priority:
                priority.append(market)
        priority = priority[:priority_count]
        cursor = max(0, int(cursor)) % len(markets)
        rotating: list[str] = []
        for offset in range(min(rotating_count, len(markets))):
            market = markets[(cursor + offset) % len(markets)]
            if market not in priority and market not in rotating:
                rotating.append(market)
        next_cursor = (cursor + rotating_count) % len(markets)
        return (priority + rotating)[:max_batch], next_cursor

    def publish_once(self) -> dict[str, Any]:
        url, token = self._endpoint()
        if not url or not token:
            return {"status": "not_configured", "configured": False}

        state = _read_json(STATE_PATH)
        old_cursor = int(state.get("cursor") or 0)
        cursors = state.get("cursors") if isinstance(state.get("cursors"), dict) else {"bithumb": old_cursor}
        next_cursors = dict(cursors)
        details: list[dict[str, Any]] = []
        picked_by_exchange: dict[str, int] = {}

        for config in SOURCE_CONFIGS:
            exchange = str(config["exchange"])
            strategy = str(config["strategy"])
            demo = _read_json(Path(config["status"]))
            if not demo:
                picked_by_exchange[exchange] = 0
                continue
            markets, next_cursor = self._batch_markets(
                demo,
                cursor=int(cursors.get(exchange) or 0),
                priority_count=int(config["priority"]),
                rotating_count=int(config["rotating"]),
                max_batch=int(config["max_batch"]),
            )
            next_cursors[exchange] = next_cursor
            added = 0
            for market in markets:
                source = _read_json(Path(config["details"]) / f"{market.replace('/', '_')}.json")
                if not source:
                    continue
                compact = _compact_detail(source)
                summary = compact.get("summary") if isinstance(compact.get("summary"), dict) else {}
                source_ts = _num(summary.get("signal_ts")) or _num((compact.get("signal") or {}).get("ts"))
                details.append(
                    {
                        "key": f"{exchange}|{market}|{strategy}",
                        "exchange": exchange,
                        "market": market,
                        "strategy": strategy,
                        "source_ts": source_ts,
                        "detail": compact,
                    }
                )
                added += 1
            picked_by_exchange[exchange] = added

        if not details:
            return {"status": "waiting_for_detail_files", "configured": True, "published": 0, "by_exchange": picked_by_exchange}

        batches = _split_batches(details)
        total_bytes = 0
        total_stored = 0
        remote_results: list[dict[str, Any]] = []
        batch_sizes: list[int] = []
        stored_by_exchange = {name: 0 for name in picked_by_exchange}

        for batch_details, body in batches:
            response = requests.post(
                url,
                data=body,
                headers={
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json",
                    "User-Agent": "crypto-auto-trader-market-detail-publisher/2.0",
                },
                timeout=30,
            )
            response.raise_for_status()
            try:
                remote = response.json()
            except ValueError:
                remote = {"ok": True}
            remote_payload = remote if isinstance(remote, dict) else {}
            remote_results.append(remote_payload)
            total_stored += int(remote_payload.get("stored") or len(batch_details))
            for row in batch_details:
                exchange = str(row.get("exchange") or "")
                if exchange in stored_by_exchange:
                    stored_by_exchange[exchange] += 1
            total_bytes += len(body)
            batch_sizes.append(len(body))

        now = time.time()
        _write_json(
            STATE_PATH,
            {
                "version": 3,
                "cursors": next_cursors,
                "published_at": now,
                "published_keys": [row["key"] for row in details],
                "published": len(details),
                "published_by_exchange": picked_by_exchange,
                "stored": total_stored,
                "stored_by_exchange": stored_by_exchange,
                "requests": len(batches),
                "bytes": total_bytes,
                "batch_bytes": batch_sizes,
                "remote": remote_results,
            },
        )
        return {
            "status": "published", "configured": True, "published": len(details), "stored": total_stored,
            "published_by_exchange": picked_by_exchange, "stored_by_exchange": stored_by_exchange,
            "requests": len(batches), "bytes": total_bytes, "max_request_bytes": max(batch_sizes, default=0),
            "cursors": next_cursors,
        }


def main() -> None:
    print(json.dumps(CloudflareMarketDetailPublisher().publish_once(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
