from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
FEATURE_VERSION = 1

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
    """Versioned, forward-only transaction fee catalog and local profile selection.

    Current public fee information is never retroactively applied to historical
    reactions. Each catalog row becomes effective only when first verified in the
    local database. Bithumb has account-specific coupon state, so no profile is
    selected automatically; callers fail closed until a local profile is chosen.
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
            """
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
        with self.conn:
            self.conn.execute(
                """INSERT INTO research_market_fee_profile_mx(
                       exchange,market_prefix,profile,source,updated_at,schema_version
                   ) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(exchange,market_prefix) DO UPDATE SET
                       profile=excluded.profile,source=excluded.source,
                       updated_at=excluded.updated_at,schema_version=excluded.schema_version""",
                (exchange_name,prefix,profile_name,str(source),stamp,SCHEMA_VERSION),
            )

    def active_profile(self, exchange: str, market_prefix: str) -> tuple[str | None, str]:
        exchange_name = str(exchange).lower()
        prefix = str(market_prefix).upper()
        row = self.conn.execute(
            "SELECT profile,source FROM research_market_fee_profile_mx WHERE exchange=? AND market_prefix=?",
            (exchange_name, prefix),
        ).fetchone()
        if row:
            return str(row["profile"]), str(row["source"])
        env_name = f"B3_{exchange_name.upper()}_FEE_PROFILE"
        env_profile = str(os.getenv(env_name) or "").strip()
        if env_profile:
            exists = self.conn.execute(
                """SELECT 1 FROM research_market_fee_schedule_mx
                   WHERE exchange=? AND market_prefix=? AND profile=? LIMIT 1""",
                (exchange_name, prefix, env_profile),
            ).fetchone()
            if exists:
                return env_profile, f"env:{env_name}"
            return None, f"invalid_env:{env_name}"
        if exchange_name == "upbit" and prefix == "KRW":
            return "standard", "built_in_default_upbit_krw"
        return None, "profile_unselected"

    @staticmethod
    def _market_prefix(market: str) -> str:
        return str(market).split("-", 1)[0].upper()

    def resolve_taker_fee(self, exchange: str, market: str, at_ts: float) -> dict[str, Any] | None:
        exchange_name = str(exchange).lower()
        prefix = self._market_prefix(market)
        profile, profile_source = self.active_profile(exchange_name, prefix)
        if not profile:
            return None
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
        result["profile_source"] = profile_source
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
        invalid = sum(
            1 for row in rows
            if float(row["maker_fee_bps"]) < 0 or float(row["taker_fee_bps"]) < 0
            or not str(row["source_url"]).startswith("https://")
        )
        upbit_profile, upbit_source = self.active_profile("upbit", "KRW")
        bithumb_profile, bithumb_source = self.active_profile("bithumb", "KRW")
        return {
            "ok": invalid == 0 and len(rows) >= len(CURRENT_CATALOG),
            "status": "ready" if rows else "waiting_for_catalog_seed",
            "catalog_rows": len(rows),
            "invalid_catalog_rows": invalid,
            "rows": rows,
            "selected_profiles": profiles,
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
