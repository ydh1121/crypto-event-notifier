from __future__ import annotations

import json
from typing import Any

# Keep enough reserved space for the next compact research projections (for
# example DEX launch/pool history) without ever sending raw research rows.
MAX_BODY_BYTES = 1_800_000
TARGET_BODY_BYTES = 1_400_000
RESERVED_HEADROOM_BYTES = MAX_BODY_BYTES - TARGET_BODY_BYTES
MAX_PROJECTED_MARKETS_PER_EXCHANGE = 600


def snapshot_bytes(snapshot: dict[str, Any]) -> int:
    return len(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _trim_tail(value: Any, limit: int) -> list[Any]:
    rows = _list(value)
    if limit <= 0:
        return []
    return rows[-limit:]


def _cap_leaderboards(public: dict[str, Any]) -> dict[str, int]:
    trimmed: dict[str, int] = {}
    root = _list(public.get("leaderboard"))
    if len(root) > MAX_PROJECTED_MARKETS_PER_EXCHANGE:
        trimmed["bithumb"] = len(root) - MAX_PROJECTED_MARKETS_PER_EXCHANGE
        public["leaderboard"] = root[:MAX_PROJECTED_MARKETS_PER_EXCHANGE]

    exchanges = _dict(public.get("exchanges"))
    upbit = _dict(exchanges.get("upbit"))
    rows = _list(upbit.get("leaderboard"))
    if len(rows) > MAX_PROJECTED_MARKETS_PER_EXCHANGE:
        trimmed["upbit"] = len(rows) - MAX_PROJECTED_MARKETS_PER_EXCHANGE
        upbit["leaderboard"] = rows[:MAX_PROJECTED_MARKETS_PER_EXCHANGE]
    return trimmed


def _deduplicate_bithumb(public: dict[str, Any]) -> dict[str, bool]:
    """Remove copies that can be inherited from the canonical Bithumb root.

    The Viewer selector merges ``public`` with the selected exchange payload.
    Therefore Bithumb does not need a second copy of its leaderboard, best
    market, lifecycle block or recent records. Aggregate per-exchange totals
    remain in ``exchanges.bithumb`` for combined-paper calculations.
    """

    result = {
        "leaderboard": False,
        "best_market": False,
        "market_lifecycle": False,
        "recent_records": False,
    }
    exchanges = _dict(public.get("exchanges"))
    bithumb = _dict(exchanges.get("bithumb"))
    if bithumb:
        for key in ("leaderboard", "best_market", "market_lifecycle"):
            if key in bithumb:
                bithumb.pop(key, None)
                result[key] = True
        bithumb["projection_inherits_root"] = True

    exchange_records = _dict(public.get("exchange_records"))
    if "bithumb" in exchange_records:
        exchange_records.pop("bithumb", None)
        result["recent_records"] = True
    return result


def _trim_strategy_history(public: dict[str, Any], limit: int) -> None:
    lab = _dict(public.get("strategy_lab"))
    histories = _dict(lab.get("strategy_equity_history"))
    for key, rows in list(histories.items()):
        histories[key] = _trim_tail(rows, limit)
    paper = _dict(lab.get("paper_history"))
    for key, rows in list(paper.items()):
        paper[key] = _trim_tail(rows, limit)


def _trim_recent_records(public: dict[str, Any], fills: int, feedback: int) -> None:
    blocks: list[dict[str, Any]] = []
    recent = _dict(public.get("recent_records"))
    if recent:
        blocks.append(recent)
    for value in _dict(public.get("exchange_records")).values():
        block = _dict(value)
        if block:
            blocks.append(block)
    for block in blocks:
        block["fills"] = _trim_tail(block.get("fills"), fills)
        block["feedback"] = _trim_tail(block.get("feedback"), feedback)


def _visible_market_sets(public: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {"bithumb": set(), "upbit": set()}
    for row in _list(public.get("leaderboard")):
        if isinstance(row, dict) and row.get("market"):
            out["bithumb"].add(str(row.get("market")))
    upbit = _dict(_dict(public.get("exchanges")).get("upbit"))
    for row in _list(upbit.get("leaderboard")):
        if isinstance(row, dict) and row.get("market"):
            out["upbit"].add(str(row.get("market")))
    return out


def _trim_coin_matrix_to_visible(public: dict[str, Any]) -> None:
    lab = _dict(public.get("strategy_lab"))
    matrix = _dict(lab.get("coin_matrix"))
    visible = _visible_market_sets(public)
    for exchange in ("bithumb", "upbit"):
        allowed = visible[exchange]
        if not allowed:
            continue
        matrix[exchange] = [
            row for row in _list(matrix.get(exchange))
            if isinstance(row, dict) and str(row.get("market") or "") in allowed
        ]


def _write_budget_metadata(
    snapshot: dict[str, Any],
    *,
    before: int,
    deduplicated: dict[str, bool],
    trimmed_markets: dict[str, int],
    compact_level: str,
) -> dict[str, Any]:
    public = _dict(snapshot.get("public"))
    metadata = {
        "version": 1,
        "max_body_bytes": MAX_BODY_BYTES,
        "target_body_bytes": TARGET_BODY_BYTES,
        "reserved_headroom_bytes": RESERVED_HEADROOM_BYTES,
        "max_projected_markets_per_exchange": MAX_PROJECTED_MARKETS_PER_EXCHANGE,
        "bytes_before": before,
        "bytes_after": 0,
        "headroom_bytes": 0,
        "within_target": False,
        "within_hard_limit": False,
        "compact_level": compact_level,
        "deduplicated_bithumb": deduplicated,
        "trimmed_markets": trimmed_markets,
        "raw_rows_added": False,
    }
    public["snapshot_budget"] = metadata
    # Iterate because writing the byte count changes the JSON length by a few
    # bytes. This converges immediately once the digit widths are stable.
    for _ in range(3):
        size = snapshot_bytes(snapshot)
        metadata["bytes_after"] = size
        metadata["headroom_bytes"] = max(0, MAX_BODY_BYTES - size)
        metadata["within_target"] = size <= TARGET_BODY_BYTES
        metadata["within_hard_limit"] = size <= MAX_BODY_BYTES
    return metadata


def apply_snapshot_budget(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Bound the existing Viewer snapshot without changing local research data.

    Core market rows remain available. The first savings come from removing
    backward-compatible Bithumb duplicates. Only if the payload remains above
    the target do we progressively reduce time-series display density and recent
    record tails. The hard 1.8 MB publisher limit remains fail-closed.
    """

    public = _dict(snapshot.get("public"))
    if not public:
        return snapshot

    before = snapshot_bytes(snapshot)
    trimmed_markets = _cap_leaderboards(public)
    deduplicated = _deduplicate_bithumb(public)
    _trim_coin_matrix_to_visible(public)
    compact_level = "dedupe"

    size = snapshot_bytes(snapshot)
    if size > TARGET_BODY_BYTES:
        _trim_strategy_history(public, 384)
        _trim_recent_records(public, 60, 40)
        compact_level = "history_384"
        size = snapshot_bytes(snapshot)
    if size > TARGET_BODY_BYTES:
        _trim_strategy_history(public, 288)
        _trim_recent_records(public, 40, 30)
        compact_level = "history_288"
        size = snapshot_bytes(snapshot)
    if size > TARGET_BODY_BYTES:
        _trim_strategy_history(public, 144)
        _trim_recent_records(public, 24, 16)
        compact_level = "history_144"

    _write_budget_metadata(
        snapshot,
        before=before,
        deduplicated=deduplicated,
        trimmed_markets=trimmed_markets,
        compact_level=compact_level,
    )
    return snapshot
