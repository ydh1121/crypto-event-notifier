from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH, START_KRW
from .strategy_lab import STYLE_SPECS, StyleSpec, StrategyLabStore, _num

CUSTOM_PREFIX = "custom_"
MAX_CUSTOM_TOTAL = 12
MAX_CUSTOM_PER_EXCHANGE = 6
_ALLOWED_EXCHANGES = {"bithumb", "upbit"}
_NUMERIC_FIELDS = {
    "entry_regime": (35.0, 90.0),
    "entry_score": (35.0, 90.0),
    "opportunity": (35.0, 95.0),
    "base_weight_pct": (1.0, 25.0),
    "max_position_pct": (5.0, 70.0),
    "max_buys": (1, 12),
    "add_drop_pct": (0.5, 15.0),
    "take_profit_pct": (2.0, 40.0),
    "stop_loss_pct": (-30.0, -1.0),
    "exit_regime": (25.0, 80.0),
    "min_hold_seconds": (0.0, 86400.0),
    "max_volatility_pct": (1.0, 20.0),
}
_REGISTERED_CUSTOM_KEYS: set[str] = set()


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS strategy_lab_custom_specs (
            experiment_id TEXT PRIMARY KEY,
            exchange TEXT NOT NULL,
            style_key TEXT NOT NULL UNIQUE,
            primary_style TEXT NOT NULL,
            secondary_style TEXT NOT NULL,
            mix_ratio REAL NOT NULL,
            spec_json TEXT NOT NULL,
            created_ts REAL NOT NULL,
            updated_ts REAL NOT NULL
        )"""
    )
    conn.commit()


def _blend_spec(primary: str, secondary: str, mix_ratio: float, overrides: dict[str, Any] | None = None) -> StyleSpec:
    if primary not in STYLE_SPECS or primary.startswith(CUSTOM_PREFIX):
        raise ValueError("invalid primary style")
    if secondary not in STYLE_SPECS or secondary.startswith(CUSTOM_PREFIX):
        raise ValueError("invalid secondary style")
    ratio = min(1.0, max(0.0, float(mix_ratio)))
    a = STYLE_SPECS[primary]
    b = STYLE_SPECS[secondary]
    payload = asdict(a)
    for field in _NUMERIC_FIELDS:
        av = getattr(a, field)
        bv = getattr(b, field)
        value = float(av) * ratio + float(bv) * (1.0 - ratio)
        payload[field] = int(round(value)) if field == "max_buys" else value
    # The custom dictionary key is unique, while spec.key deliberately preserves
    # the primary style's special entry behavior (DCA/contrarian/swing/etc.).
    payload["key"] = primary
    payload["label"] = f"{a.label} + {b.label}"
    payload["description"] = f"{a.label} {ratio * 100:.0f}%와 {b.label} {(1.0-ratio) * 100:.0f}% 기준을 혼합한 사용자 실험입니다."
    for field, raw in (overrides or {}).items():
        if field not in _NUMERIC_FIELDS:
            continue
        low, high = _NUMERIC_FIELDS[field]
        value = float(raw)
        if value < float(low) or value > float(high):
            raise ValueError(f"{field} out of range")
        payload[field] = int(round(value)) if field == "max_buys" else value
    if float(payload["base_weight_pct"]) > float(payload["max_position_pct"]):
        raise ValueError("base weight cannot exceed max position")
    return StyleSpec(**payload)


def _unregister_custom_specs() -> None:
    for key in tuple(_REGISTERED_CUSTOM_KEYS):
        STYLE_SPECS.pop(key, None)
    _REGISTERED_CUSTOM_KEYS.clear()


def register_custom_specs(path: Path = DB_PATH) -> int:
    _unregister_custom_specs()
    if not path.exists():
        return 0
    conn = _connect(path)
    try:
        rows = conn.execute(
            """SELECT c.style_key,c.spec_json
               FROM strategy_lab_custom_specs c
               JOIN strategy_lab_experiments e USING(experiment_id)
               WHERE e.status='running' ORDER BY c.created_ts"""
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(str(row["spec_json"] or "{}"))
                spec = StyleSpec(**payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            key = str(row["style_key"])
            STYLE_SPECS[key] = spec
            _REGISTERED_CUSTOM_KEYS.add(key)
        return len(_REGISTERED_CUSTOM_KEYS)
    finally:
        conn.close()


def _seed_accounts(conn: sqlite3.Connection, experiment: str, exchange: str) -> int:
    latest = conn.execute(
        """SELECT m.market,m.price,m.id
           FROM research_market_memory_mx m
           JOIN (
             SELECT market,MAX(id) AS max_id FROM research_market_memory_mx
             WHERE exchange=? AND strategy='adaptive' GROUP BY market
           ) x ON x.max_id=m.id
           ORDER BY m.market""",
        (exchange,),
    ).fetchall()
    now = time.time()
    for row in latest:
        price = max(0.0, _num(row["price"]))
        conn.execute(
            """INSERT OR IGNORE INTO strategy_lab_accounts(
                experiment_id,exchange,market,cash_krw,volume,avg_price,realized_pnl,peak_equity,
                max_drawdown_pct,buy_count,entry_ts,last_price,closed_trades,wins,gross_profit,
                gross_loss,sum_return_pct,last_memory_id,updated_ts
            ) VALUES(?,?,?, ?,0,0,0,?,0,0,0,?,0,0,0,0,0,?,?)""",
            (experiment, exchange, str(row["market"]), START_KRW, START_KRW, price, int(row["id"]), now),
        )
    return len(latest)


def create_custom_experiment(
    *,
    exchange: str,
    label: str,
    primary_style: str,
    secondary_style: str,
    mix_ratio: float = 0.5,
    overrides: dict[str, Any] | None = None,
    path: Path = DB_PATH,
) -> dict[str, Any]:
    exchange = exchange.strip().lower()
    if exchange not in _ALLOWED_EXCHANGES:
        raise ValueError("invalid exchange")
    clean_label = " ".join(str(label or "").split())[:48]
    if len(clean_label) < 2:
        raise ValueError("label is too short")
    _unregister_custom_specs()
    spec = _blend_spec(primary_style, secondary_style, mix_ratio, overrides)
    conn = _connect(path)
    try:
        # Ensure default Strategy Lab tables exist while only the six built-ins are
        # registered. This prevents a custom style from being bootstrapped onto the
        # other exchange by StrategyLabStore._ensure_default_experiments().
        bootstrap = StrategyLabStore(path)
        bootstrap.close()
        total = int(conn.execute("SELECT COUNT(*) FROM strategy_lab_custom_specs").fetchone()[0])
        per_exchange = int(conn.execute(
            "SELECT COUNT(*) FROM strategy_lab_custom_specs WHERE exchange=?", (exchange,)
        ).fetchone()[0])
        if total >= MAX_CUSTOM_TOTAL or per_exchange >= MAX_CUSTOM_PER_EXCHANGE:
            raise ValueError("custom experiment limit reached")
        suffix = uuid.uuid4().hex[:10]
        style_key = f"{CUSTOM_PREFIX}{suffix}"
        exp_id = f"{exchange}|{style_key}|v1"
        now = time.time()
        description = spec.description
        with conn:
            conn.execute(
                """INSERT INTO strategy_lab_experiments(
                    experiment_id,exchange,style,strategy_key,label,description,status,initial_krw,created_ts,updated_ts
                ) VALUES(?,?,?,?,?,?,'running',?,?,?)""",
                (exp_id, exchange, style_key, f"lab:{style_key}:v1", clean_label, description, START_KRW, now, now),
            )
            conn.execute(
                """INSERT INTO strategy_lab_custom_specs(
                    experiment_id,exchange,style_key,primary_style,secondary_style,mix_ratio,spec_json,created_ts,updated_ts
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    exp_id, exchange, style_key, primary_style, secondary_style,
                    min(1.0, max(0.0, float(mix_ratio))), json.dumps(asdict(spec), ensure_ascii=False), now, now,
                ),
            )
            seeded = _seed_accounts(conn, exp_id, exchange)
        return {
            "experiment_id": exp_id,
            "exchange": exchange,
            "style": style_key,
            "label": clean_label,
            "primary_style": primary_style,
            "secondary_style": secondary_style,
            "mix_ratio": min(1.0, max(0.0, float(mix_ratio))),
            "seeded_markets": seeded,
            "status": "running",
            "paper_only": True,
        }
    finally:
        conn.close()
        _unregister_custom_specs()


def set_custom_experiment_status(experiment: str, status: str, path: Path = DB_PATH) -> dict[str, Any]:
    if status not in {"running", "paused"}:
        raise ValueError("invalid status")
    conn = _connect(path)
    try:
        row = conn.execute(
            """SELECT c.experiment_id,c.style_key,e.exchange,e.label,e.status
               FROM strategy_lab_custom_specs c JOIN strategy_lab_experiments e USING(experiment_id)
               WHERE c.experiment_id=?""",
            (experiment,),
        ).fetchone()
        if not row:
            raise KeyError(experiment)
        now = time.time()
        with conn:
            conn.execute(
                "UPDATE strategy_lab_experiments SET status=?,updated_ts=? WHERE experiment_id=?",
                (status, now, experiment),
            )
            conn.execute(
                "UPDATE strategy_lab_custom_specs SET updated_ts=? WHERE experiment_id=?",
                (now, experiment),
            )
        return {
            "experiment_id": experiment,
            "exchange": row["exchange"],
            "label": row["label"],
            "status": status,
            "paper_only": True,
        }
    finally:
        conn.close()
        _unregister_custom_specs()


def custom_experiments(path: Path = DB_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    conn = _connect(path)
    try:
        rows = conn.execute(
            """SELECT c.experiment_id,c.exchange,c.style_key,c.primary_style,c.secondary_style,c.mix_ratio,
                      c.spec_json,c.created_ts,c.updated_ts,e.label,e.description,e.status,
                      COALESCE(m.markets,0) AS markets,COALESCE(m.active_positions,0) AS active_positions,
                      COALESCE(m.return_pct,0) AS return_pct,COALESCE(m.max_drawdown_pct,0) AS max_drawdown_pct,
                      COALESCE(m.closed_trades,0) AS closed_trades,COALESCE(m.win_rate_pct,0) AS win_rate_pct,
                      COALESCE(m.expectancy_pct,0) AS expectancy_pct,COALESCE(m.profit_factor,0) AS profit_factor
               FROM strategy_lab_custom_specs c
               JOIN strategy_lab_experiments e USING(experiment_id)
               LEFT JOIN strategy_lab_metrics m USING(experiment_id)
               ORDER BY c.created_ts DESC"""
        ).fetchall()
        result: list[dict[str, Any]] = []
        for source in rows:
            row = dict(source)
            try:
                row["spec"] = json.loads(str(row.pop("spec_json") or "{}"))
            except json.JSONDecodeError:
                row["spec"] = {}
            result.append(row)
        return result
    finally:
        conn.close()


class ConfiguredStrategyLabRunner:
    """Strategy Lab runner that loads persisted local custom style specs safely."""

    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path

    def run_once(self) -> dict[str, Any]:
        # Construct the base store with built-ins only, then expose saved custom
        # specs strictly for this processing window.
        _unregister_custom_specs()
        store = StrategyLabStore(self.path)
        try:
            custom_count = register_custom_specs(self.path)
            results = [store.process_exchange(exchange) for exchange in ("bithumb", "upbit")]
            snapshot = store.snapshot()
            experiments = snapshot.get("experiments") or []
            leaders: dict[str, dict[str, Any] | None] = {}
            for exchange in ("bithumb", "upbit"):
                candidates = [row for row in experiments if row.get("exchange") == exchange and row.get("status") == "running"]
                candidates.sort(
                    key=lambda row: (_num(row.get("return_pct")), -abs(_num(row.get("max_drawdown_pct")))),
                    reverse=True,
                )
                leaders[exchange] = candidates[0] if candidates else None
            return {
                "status": "processed",
                "paper_only": True,
                "source_rows": sum(int(row.get("source_rows") or 0) for row in results),
                "trades": sum(int(row.get("trades") or 0) for row in results),
                "experiment_count": len(experiments),
                "custom_experiment_count": custom_count,
                "leaders": leaders,
                "by_exchange": results,
            }
        finally:
            store.close()
            _unregister_custom_specs()
