from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def normalize_market(value: str) -> str:
    market = value.strip().upper()
    if not market:
        raise ValueError("ticker/market is required")
    if "-" not in market:
        market = f"KRW-{market}"
    quote, symbol = market.split("-", 1)
    if quote != "KRW" or not symbol:
        raise ValueError("only Bithumb KRW markets are supported for now")
    return f"KRW-{symbol}"


@dataclass(frozen=True)
class AssetProfile:
    market: str
    symbol: str
    enabled: bool = True
    context_mode: str = "generic_alt"
    related_markets: tuple[str, ...] = ()
    order_krw: float | None = None
    max_position_krw: float | None = None
    min_regime_score: float | None = None
    min_entry_score: float | None = None
    news_modifier: float = 0.0
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AssetProfile":
        market = normalize_market(str(raw.get("market") or raw.get("ticker") or ""))
        symbol = market.split("-", 1)[1]
        related = tuple(
            normalize_market(str(value))
            for value in (raw.get("related_markets") or [])
            if str(value).strip()
        )
        return cls(
            market=market,
            symbol=str(raw.get("symbol") or symbol).upper(),
            enabled=bool(raw.get("enabled", True)),
            context_mode=str(raw.get("context_mode") or "generic_alt"),
            related_markets=related,
            order_krw=float(raw["order_krw"]) if raw.get("order_krw") is not None else None,
            max_position_krw=float(raw["max_position_krw"]) if raw.get("max_position_krw") is not None else None,
            min_regime_score=float(raw["min_regime_score"]) if raw.get("min_regime_score") is not None else None,
            min_entry_score=float(raw["min_entry_score"]) if raw.get("min_entry_score") is not None else None,
            news_modifier=float(raw.get("news_modifier") or 0.0),
            notes=str(raw.get("notes") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["related_markets"] = list(self.related_markets)
        return payload


def default_profile(ticker: str) -> AssetProfile:
    market = normalize_market(ticker)
    symbol = market.split("-", 1)[1]
    if symbol == "B3":
        return AssetProfile(
            market=market,
            symbol=symbol,
            context_mode="base_gaming",
            related_markets=("KRW-AERO", "KRW-VIRTUAL", "KRW-DEGEN", "KRW-IMX", "KRW-AXS", "KRW-GALA", "KRW-BEAM"),
            notes="B3 Base/gaming context profile",
        )
    return AssetProfile(
        market=market,
        symbol=symbol,
        context_mode="generic_alt",
        notes="Generic profile. Ask GPT to refine sector/ecosystem context.",
    )


class AssetRegistry:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._mtime_ns = -1
        self._assets: dict[str, AssetProfile] = {}
        if not self.path.exists():
            self._assets = {"KRW-B3": default_profile("B3")}
            self.save()
        else:
            self.reload(force=True)

    def reload(self, force: bool = False) -> bool:
        with self._lock:
            try:
                mtime_ns = self.path.stat().st_mtime_ns
            except FileNotFoundError:
                return False
            if not force and mtime_ns == self._mtime_ns:
                return False
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            rows = raw.get("assets", raw if isinstance(raw, list) else [])
            assets = {profile.market: profile for profile in (AssetProfile.from_dict(row) for row in rows)}
            if not assets:
                assets["KRW-B3"] = default_profile("B3")
            self._assets = assets
            self._mtime_ns = mtime_ns
            return True

    def list(self, enabled_only: bool = False) -> list[AssetProfile]:
        self.reload()
        with self._lock:
            values = list(self._assets.values())
        if enabled_only:
            values = [row for row in values if row.enabled]
        return sorted(values, key=lambda row: row.market)

    def get(self, market: str) -> AssetProfile | None:
        self.reload()
        market = normalize_market(market)
        with self._lock:
            return self._assets.get(market)

    def upsert(self, profile: AssetProfile) -> None:
        with self._lock:
            self._assets[profile.market] = profile
            self.save()

    def add_generic(self, ticker: str) -> AssetProfile:
        profile = default_profile(ticker)
        self.upsert(profile)
        return profile

    def remove(self, market: str) -> bool:
        market = normalize_market(market)
        with self._lock:
            existed = self._assets.pop(market, None) is not None
            if existed:
                self.save()
            return existed

    def save(self) -> None:
        with self._lock:
            payload = {"schema_version": 1, "assets": [row.to_dict() for row in sorted(self._assets.values(), key=lambda x: x.market)]}
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)
            self._mtime_ns = self.path.stat().st_mtime_ns
