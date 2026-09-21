from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 2
FEATURE_VERSION = 2

UPBIT_FEE_SOURCE = "https://support.upbit.com/hc/ko/articles/900006143046"
BITHUMB_FEE_SOURCE = "https://support.bithumb.com/hc/ko/articles/51131554420377"
BITHUMB_COUPON_SOURCE = "https://support.bithumb.com/hc/ko/articles/51131586657689"

CURRENT_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "schedule_id": "upbit-krw-standard-current-v1",
        "exchange": "upbit",
        "market_prefix": "KRW",
        "profile": "standard",
        "maker_fee_bps": 5.0,
        "taker_fee_bps": 5.0,
        "source_url": UPBIT_FEE_SOURCE,
        "source_note": "Official Upbit KRW trading fee currently 0.05%; event fees may differ.",
    },
    {
        "schedule_id": "bithumb-krw-standard-current-v1",
        "exchange": "bithumb",
        "market_prefix": "KRW",
        "profile": "standard",
        "maker_fee_bps": 25.0,
        "taker_fee_bps": 25.0,
        "source_url": BITHUMB_FEE_SOURCE,
        "source_note": "Official Bithumb base KRW fee 0.25%; account coupon/event discounts are separate profiles.",
    },
    {
        "schedule_id": "bithumb-krw-coupon-0.04-current-v1",
        "exchange": "bithumb",
        "market_prefix": "KRW",
        "profile": "coupon_0_04",
        "maker_fee_bps": 4.0,
        "taker_fee_bps": 4.0,
        "source_url": BITHUMB_COUPON_SOURCE,
        "source_note": "Official Bithumb 0.04% coupon profile; only valid when the account has registered the coupon.",
    },
)


class MarketFeeScheduleStore:
    """Versioned, forward-only transaction fee catalog and local profile history.

    Public fee catalog rows become effective only when first verified locally.
    Account-specific profile choices are separately time-versioned. Selecting a
    Bithumb profile now never applies it to an earlier reaction timestamp. This
    keeps transaction-cost research forward-only and reproducible.
    """

    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_fee_schedule_mx(
                schedule_id TEXT PRIMARY KEY,
                exchange TEXT NOT NULL,
                market_prefix TEXT NOT NULL,
                profile TEXT NOT NULL,
                maker_fee_bps REAL NOT NULL,
                taker_fee_bps REAL NOT NULL,
                effective_from REAL NOT NULL,
                effective_to REAL,
                source_url TEXT NOT NULL,
                source_note TEXT NOT NULL,
                verified_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_market_fee_schedule_lookup
            ON research_market_fee_schedule_mx(exchange,market_prefix,profile,effective_from DESC);

            CREATE TABLE IF NOT EXISTS research_market_fee_profile_mx(
                exchange TEXT NOT NULL,
                market_prefix TEXT NOT NULL,
                profile TEXT NOT NULL,
                source TEXT NOT NULL,
                updated_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market_prefix)
            );

            CREATE TABLE IF NOT EXISTS research_market_fee_profile_history_mx(
                exchange TEXT NOT NULL,
                market_prefix TEXT NOT NULL,
                profile TEXT NOT NULL,
                source TEXT NOT NULL,
                effective_from REAL NOT NULL,
                effective_to REAL,
                recorded_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 2,
                PRIMARY KEY(exchange,market_prefix,effective_from)
            );
            CREATE INDEX IF NOT EXISTS idx_market_fee_profile_history_lookup
            ON research_market_fee_profile_history_mx(
                exchange,market_prefix,effective_from DESC,effective_to
            );
            """
        )
        # Migrate any pre-v2 explicit selection from its recorded updated_at.
        # This does not infer history before the actual local selection timestamp.
        self.conn.execute(
            """INSERT OR IGNORE INTO research_market_fee_profile_history_mx(
                   exchange,market_prefix,profile,source,effective_from,effective_to,
                   recorded_at,schema_version
               )
               SELECT exchange,market_prefix,profile,source,updated_at,NULL,updated_at,2
               FROM research_market_fee_profile_mx"""
        )
        self.conn.commit()

    def ensure_current_catalog(self, *, now: float | None = None) -> int:
        stamp = float(now or time.time())
        inserted = 0
        with self.conn:
            for row in CURRENT_CATALOG:
                cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO research_market_fee_schedule_mx(
                           schedule_id,exchange,market_prefix,profile,maker_fee_bps,taker_fee_bps,
                           effective_from,effective_to,source_url,source_note,verified_at,
                           feature_version,schema_version
                       ) VALUES(?,?,?,?,?,?,?,NULL,?,?,?,?,?)""",
                    (
                        row["schedule_id"],row["exchange"],row["market_prefix"],row["profile"],
                        row["maker_fee_bps"],row["taker_fee_bps"],stamp,row["source_url"],
                        row["source_note"],stamp,FEATURE_VERSION,SCHEMA_VERSION,
                    ),
                )
                inserted += int(cursor.rowcount > 0)
        return inserted

    def set_active_profile(
        self,
        exchange: str,
        market_prefix: str,
        profile: str,
        *,
        source: str = "manual_local",
        now: float | None = None,
    ) -> None:
        exchange_name = str(exchange).lower()
        prefix = str(market_prefix).upper()
        profile_name = str(profile)
        exists = self.conn.execute(
            """SELECT 1 FROM research_market_fee_schedule_mx
               WHERE exchange=? AND market_prefix=? AND profile=? LIMIT 1""",
            (exchange_name, prefix, profile_name),
        ).fetchone()
        if not exists:
            raise ValueError(f"unknown fee profile: {exchange_name}/{prefix}/{profile_name}")

        stamp = float(now or time.time())
        latest = self.conn.execute(
            """SELECT * FROM research_market_fee_profile_history_mx
               WHERE exchange=? AND market_prefix=?
               ORDER BY effective_from DESC LIMIT 1""",
            (exchange_name, prefix),
        ).fetchone()
        if latest and stamp < float(latest["effective_from"]):
            raise ValueError("fee profile activation cannot move backward in time")

        with self.conn:
            open_row = self.conn.execute(
                """SELECT * FROM research_market_fee_profile_history_mx
                   WHERE exchange=? AND market_prefix=? AND effective_to IS NULL
                   ORDER BY effective_from DESC LIMIT 1""",
                (exchange_name, prefix),
            ).fetchone()

            if open_row is None:
                self.conn.execute(
                    """INSERT INTO research_market_fee_profile_history_mx(
                           exchange,market_prefix,profile,source,effective_from,effective_to,
                           recorded_at,schema_version
                       ) VALUES(?,?,?,?,?,NULL,?,?)""",
                    (exchange_name,prefix,profile_name,str(source),stamp,stamp,SCHEMA_VERSION),
                )
            elif str(open_row["profile"]) != profile_name:
                open_from = float(open_row["effective_from"])
                if stamp <= open_from:
                    raise ValueError("fee profile switch must occur after current interval start")
                self.conn.execute(
                    """UPDATE research_market_fee_profile_history_mx
                       SET effective_to=?
                       WHERE exchange=? AND market_prefix=? AND effective_from=?""",
                    (stamp,exchange_name,prefix,open_from),
                )
                self.conn.execute(
                    """INSERT INTO research_market_fee_profile_history_mx(
                           exchange,market_prefix,profile,source,effective_from,effective_to,
                           recorded_at,schema_version
                       ) VALUES(?,?,?,?,?,NULL,?,?)""",
                    (exchange_name,prefix,profile_name,str(source),stamp,stamp,SCHEMA_VERSION),
                )

            self.conn.execute(
                """INSERT INTO research_market_fee_profile_mx(
                       exchange,market_prefix,profile,source,updated_at,schema_version
                   ) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(exchange,market_prefix) DO UPDATE SET
                       profile=excluded.profile,source=excluded.source,
                       updated_at=excluded.updated_at,schema_version=excluded.schema_version""",
                (exchange_name,prefix,profile_name,str(source),stamp,SCHEMA_VERSION),
            )

    def _catalog_profile_exists(self, exchange: str, prefix: str, profile: str) -> bool:
        return bool(self.conn.execute(
            """SELECT 1 FROM research_market_fee_schedule_mx
               WHERE exchange=? AND market_prefix=? AND profile=? LIMIT 1""",
            (exchange,prefix,profile),
        ).fetchone())

    def _env_profile(self, exchange: str, prefix: str) -> tuple[str | None, str, float | None]:
        env_name = f"B3_{exchange.upper()}_FEE_PROFILE"
        env_profile = str(os.getenv(env_name) or "").strip()
        if not env_profile:
            return None, "env_unset", None
        if not self._catalog_profile_exists(exchange, prefix, env_profile):
            return None, f"invalid_env:{env_name}", None
        effective_name = f"{env_name}_EFFECTIVE_FROM"
        raw_effective = str(os.getenv(effective_name) or "").strip()
        if not raw_effective:
            return env_profile, f"env_without_effective_from:{env_name}", None
        try:
            effective_from = float(raw_effective)
        except ValueError:
            return None, f"invalid_env:{effective_name}", None
        return env_profile, f"env:{env_name}+{effective_name}", effective_from

    def active_profile(self, exchange: str, market_prefix: str) -> tuple[str | None, str]:
        exchange_name = str(exchange).lower()
        prefix = str(market_prefix).upper()
        row = self.conn.execute(
            """SELECT profile,source FROM research_market_fee_profile_history_mx
               WHERE exchange=? AND market_prefix=? AND effective_to IS NULL
               ORDER BY effective_from DESC LIMIT 1""",
            (exchange_name, prefix),
        ).fetchone()
        if row:
            return str(row["profile"]), str(row["source"])

        env_profile, env_source, _ = self._env_profile(exchange_name, prefix)
        if env_profile:
            return env_profile, env_source
        if env_source.startswith("invalid_env"):
            return None, env_source

        if exchange_name == "upbit" and prefix == "KRW":
            return "standard", "built_in_default_upbit_krw"
        return None, "profile_unselected"

    def profile_at(self, exchange: str, market_prefix: str, at_ts: float) -> dict[str, Any] | None:
        exchange_name = str(exchange).lower()
        prefix = str(market_prefix).upper()
        ts = float(at_ts)
        row = self.conn.execute(
            """SELECT profile,source,effective_from,effective_to
               FROM research_market_fee_profile_history_mx
               WHERE exchange=? AND market_prefix=?
                 AND effective_from<=?
                 AND (effective_to IS NULL OR effective_to>?)
               ORDER BY effective_from DESC LIMIT 1""",
            (exchange_name,prefix,ts,ts),
        ).fetchone()
        if row:
            return {
                "profile": str(row["profile"]),
                "source": str(row["source"]),
                "effective_from": float(row["effective_from"]),
                "effective_to": None if row["effective_to"] is None else float(row["effective_to"]),
            }

        env_profile, env_source, env_effective_from = self._env_profile(exchange_name, prefix)
        if env_profile and env_effective_from is not None and env_effective_from <= ts:
            return {
                "profile": env_profile,
                "source": env_source,
                "effective_from": env_effective_from,
                "effective_to": None,
            }

        if exchange_name == "upbit" and prefix == "KRW":
            schedule = self.conn.execute(
                """SELECT effective_from,effective_to FROM research_market_fee_schedule_mx
                   WHERE exchange='upbit' AND market_prefix='KRW' AND profile='standard'
                     AND effective_from<=?
                     AND (effective_to IS NULL OR effective_to>?)
                   ORDER BY effective_from DESC LIMIT 1""",
                (ts,ts),
            ).fetchone()
            if schedule:
                return {
                    "profile": "standard",
                    "source": "built_in_default_upbit_krw",
                    "effective_from": float(schedule["effective_from"]),
                    "effective_to": None if schedule["effective_to"] is None else float(schedule["effective_to"]),
                }
        return None

    @staticmethod
    def _market_prefix(market: str) -> str:
        return str(market).split("-", 1)[0].upper()

    def resolve_taker_fee(self, exchange: str, market: str, at_ts: float) -> dict[str, Any] | None:
        exchange_name = str(exchange).lower()
        prefix = self._market_prefix(market)
        profile_record = self.profile_at(exchange_name, prefix, float(at_ts))
        if not profile_record:
            return None
        profile = str(profile_record["profile"])
        row = self.conn.execute(
            """SELECT * FROM research_market_fee_schedule_mx
               WHERE exchange=? AND market_prefix=? AND profile=?
                 AND effective_from<=?
                 AND (effective_to IS NULL OR effective_to>?)
               ORDER BY effective_from DESC LIMIT 1""",
            (exchange_name,prefix,profile,float(at_ts),float(at_ts)),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["profile_source"] = profile_record["source"]
        result["profile_effective_from"] = profile_record["effective_from"]
        result["profile_effective_to"] = profile_record["effective_to"]
        return result

    def audit(self) -> dict[str, Any]:
        rows = [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM research_market_fee_schedule_mx ORDER BY exchange,market_prefix,profile"
            ).fetchall()
        ]
        profiles = [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM research_market_fee_profile_mx ORDER BY exchange,market_prefix"
            ).fetchall()
        ]
        history = [
            dict(row)
            for row in self.conn.execute(
                """SELECT * FROM research_market_fee_profile_history_mx
                   ORDER BY exchange,market_prefix,effective_from"""
            ).fetchall()
        ]
        invalid = sum(
            1 for row in rows
            if float(row["maker_fee_bps"]) < 0 or float(row["taker_fee_bps"]) < 0
            or not str(row["source_url"]).startswith("https://")
        )
        overlap_violations = int(self.conn.execute(
            """SELECT COUNT(*)
               FROM research_market_fee_profile_history_mx a
               JOIN research_market_fee_profile_history_mx b
                 ON a.rowid < b.rowid
                AND a.exchange=b.exchange
                AND a.market_prefix=b.market_prefix
                AND a.effective_from < COALESCE(b.effective_to, 1e100)
                AND b.effective_from < COALESCE(a.effective_to, 1e100)"""
        ).fetchone()[0])
        open_interval_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM (
                   SELECT exchange,market_prefix,COUNT(*) AS n
                   FROM research_market_fee_profile_history_mx
                   WHERE effective_to IS NULL
                   GROUP BY exchange,market_prefix
                   HAVING COUNT(*) > 1
               )"""
        ).fetchone()[0])
        upbit_profile, upbit_source = self.active_profile("upbit", "KRW")
        bithumb_profile, bithumb_source = self.active_profile("bithumb", "KRW")
        ok = (
            invalid == 0
            and len(rows) >= len(CURRENT_CATALOG)
            and overlap_violations == 0
            and open_interval_violations == 0
        )
        return {
            "ok": ok,
            "status": "ready" if rows else "waiting_for_catalog_seed",
            "catalog_rows": len(rows),
            "invalid_catalog_rows": invalid,
            "rows": rows,
            "selected_profiles": profiles,
            "profile_history": history,
            "profile_history_rows": len(history),
            "profile_history_overlap_violations": overlap_violations,
            "profile_history_open_interval_violations": open_interval_violations,
            "profile_resolution_by_at_ts": True,
            "profile_selection_retroactive": False,
            "upbit_krw_profile": upbit_profile,
            "upbit_krw_profile_source": upbit_source,
            "bithumb_krw_profile": bithumb_profile,
            "bithumb_krw_profile_source": bithumb_source,
            "bithumb_profile_required_for_full_cost": True,
            "forward_only_effective_from_first_local_verification": True,
            "historical_fee_backfill": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
