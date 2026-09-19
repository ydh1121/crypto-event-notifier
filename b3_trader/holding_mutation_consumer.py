from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from .cloudflare_snapshot_publisher import CloudflareSnapshotPublisher
from .config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
VALID_EXCHANGES = {"bithumb", "upbit"}
HOLDING_MARKET_PATTERN = re.compile(r"^KRW-[A-Z0-9]+(?:/[A-Z0-9]+)?$")


def _quote_currency(market: str) -> str:
    pair = market.split("-", 1)[1] if "-" in market else market
    return pair.split("/", 1)[1] if "/" in pair else "KRW"


def _fee_profile(exchange: str, market: str) -> tuple[float, str] | None:
    quote = _quote_currency(market)
    if exchange == "bithumb" and quote == "BTC":
        return 0.0, "bithumb_btc_free"
    if exchange == "bithumb" and quote == "KRW":
        return 0.0004, "bithumb_coupon_0.04pct"
    if exchange == "upbit" and quote == "KRW":
        return 0.0005, "upbit_krw_0.05pct"
    return None


class MutationRejected(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _runtime_url(ingest_url: str) -> str:
    parts = urlsplit(ingest_url)
    if not parts.scheme or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme, parts.netloc, "/api/holding-mutations-runtime", "", ""))


def _journal_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _request_json(url: str, token: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "crypto-auto-trader-holding-consumer/1.0",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
            code = str(data.get("error", {}).get("code") or f"HTTP_{exc.code}")
            message = str(data.get("error", {}).get("message") or raw or exc.reason)
        except (TypeError, json.JSONDecodeError):
            code, message = f"HTTP_{exc.code}", raw or str(exc.reason)
        raise MutationRejected(code, message) from exc
    except URLError as exc:
        raise MutationRejected("RUNTIME_ENDPOINT_UNAVAILABLE", str(exc.reason)) from exc
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise MutationRejected("INVALID_RUNTIME_RESPONSE", "런타임 큐 응답이 JSON이 아닙니다.") from exc
    return data if isinstance(data, dict) else {}


def _holding_row(conn: sqlite3.Connection, market: str) -> tuple[dict[str, Any], set[str]]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='manual_holdings' LIMIT 1"
    ).fetchone()
    if not exists:
        raise MutationRejected("MANUAL_HOLDINGS_TABLE_MISSING", "manual_holdings 테이블이 없습니다.")
    columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(manual_holdings)").fetchall()}
    required = {"market", "volume", "avg_price", "updated_ts"}
    if not required.issubset(columns):
        raise MutationRejected("MANUAL_HOLDINGS_SCHEMA_MISMATCH", "manual_holdings 스키마가 예상과 다릅니다.")
    exchange_select = "exchange" if "exchange" in columns else "NULL AS exchange"
    row = conn.execute(
        f"SELECT market,volume,avg_price,{exchange_select},updated_ts FROM manual_holdings WHERE market=? LIMIT 1",
        (market,),
    ).fetchone()
    if not row:
        raise MutationRejected("HOLDING_NOT_FOUND", "현재 보유자산 행을 찾을 수 없습니다.")
    return dict(row), columns


def _positive_number(value: Any, *, code: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MutationRejected(code, "0보다 큰 숫자가 필요합니다.") from exc
    if not (number > 0.0):
        raise MutationRejected(code, "0보다 큰 숫자가 필요합니다.")
    return number


def _receipt_result(conn: sqlite3.Connection, mutation_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT result_json FROM holding_mutation_receipts WHERE mutation_id=? LIMIT 1",
        (mutation_id,),
    ).fetchone()
    if not row:
        return None
    try:
        value = json.loads(str(row["result_json"] or "{}"))
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def apply_mutation(journal_db: str, mutation: dict[str, Any]) -> dict[str, Any]:
    mutation_id = str(mutation.get("id") or "")
    exchange = str(mutation.get("exchange") or "").lower()
    market = str(mutation.get("market") or "").upper()
    action = str(mutation.get("action") or "")
    expected_revision = float(mutation.get("expected_revision") or 0.0)
    payload = mutation.get("payload") if isinstance(mutation.get("payload"), dict) else {}

    if not mutation_id or exchange not in VALID_EXCHANGES or not HOLDING_MARKET_PATTERN.fullmatch(market):
        raise MutationRejected("INVALID_MUTATION", "반영 요청 식별값이 올바르지 않습니다.")
    if action not in {"set_holding", "apply_averaging"}:
        raise MutationRejected("INVALID_MUTATION_ACTION", "지원하지 않는 보유자산 반영 종류입니다.")
    fee_profile = _fee_profile(exchange, market)
    if fee_profile is None:
        raise MutationRejected("UNSUPPORTED_EXCHANGE_MARKET", "현재 지원하지 않는 거래소·마켓 조합입니다.")
    if action == "apply_averaging" and _quote_currency(market) != "KRW":
        raise MutationRejected("QUOTE_AWARE_AVERAGING_REQUIRED", "BTC 마켓 물타기 실제 반영은 BTC 단위 계산기 전환 후 지원합니다.")

    path = _journal_path(journal_db)
    if not path.exists():
        raise MutationRejected("JOURNAL_DB_MISSING", f"journal DB가 없습니다: {path}")

    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            # Local receipt is in the same canonical DB transaction as the holding update.
            # If Cloudflare ACK is lost, reclaiming the same mutation returns this result
            # instead of applying the averaging rounds twice.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS holding_mutation_receipts (
                    mutation_id TEXT PRIMARY KEY,
                    applied_ts REAL NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )
            existing = _receipt_result(conn, mutation_id)
            if existing is not None:
                return existing

            row, columns = _holding_row(conn, market)
            current_revision = float(row.get("updated_ts") or 0.0)
            if expected_revision > 0 and abs(current_revision - expected_revision) > 0.000001:
                raise MutationRejected("REVISION_CONFLICT", "화면을 연 뒤 보유정보가 변경되었습니다. 최신값을 다시 확인하세요.")

            stored_exchange = str(row.get("exchange") or "").strip().lower()
            if stored_exchange and stored_exchange not in VALID_EXCHANGES:
                raise MutationRejected("EXCHANGE_INVALID", "저장된 거래소 값이 올바르지 않습니다.")
            if stored_exchange in VALID_EXCHANGES and stored_exchange != exchange:
                raise MutationRejected("EXCHANGE_CONFLICT", "저장된 거래소와 반영 요청 거래소가 다릅니다.")
            exchange_backfilled = "exchange" in columns and not stored_exchange

            before_volume = max(0.0, float(row.get("volume") or 0.0))
            before_avg = max(0.0, float(row.get("avg_price") or 0.0))
            buy_gross = 0.0

            if action == "set_holding":
                final_volume = _positive_number(payload.get("volume"), code="INVALID_VOLUME")
                final_avg = _positive_number(payload.get("avg_price"), code="INVALID_AVG_PRICE")
                applied_rounds: list[dict[str, float]] = []
            else:
                rows = payload.get("rounds") if isinstance(payload.get("rounds"), list) else []
                if not rows:
                    raise MutationRejected("AVERAGING_ROUNDS_REQUIRED", "실제 반영할 물타기 회차가 없습니다.")
                total_volume = before_volume
                total_cost = before_volume * before_avg
                applied_rounds = []
                for source in rows[:20]:
                    if not isinstance(source, dict):
                        continue
                    price = _positive_number(source.get("price"), code="INVALID_AVERAGING_PRICE")
                    amount = _positive_number(source.get("amount_krw"), code="INVALID_AVERAGING_AMOUNT")
                    quantity = amount / price
                    total_volume += quantity
                    total_cost += amount
                    buy_gross += amount
                    applied_rounds.append({"price": price, "amount_krw": amount, "volume": quantity})
                if not applied_rounds:
                    raise MutationRejected("AVERAGING_ROUNDS_REQUIRED", "유효한 물타기 회차가 없습니다.")
                final_volume = total_volume
                final_avg = total_cost / total_volume if total_volume > 0 else 0.0

            updated_ts = time.time()
            rate, fee_policy = fee_profile
            result = {
                "mutation_id": mutation_id,
                "market": market,
                "exchange": exchange,
                "exchange_backfilled": exchange_backfilled,
                "action": action,
                "before_volume": before_volume,
                "before_avg_price": before_avg,
                "final_volume": final_volume,
                "final_avg_price": final_avg,
                "applied_rounds": applied_rounds,
                "buy_gross_krw": buy_gross,
                "buy_fee_krw": buy_gross * rate,
                "fee_rate": rate,
                "fee_policy": fee_policy,
                "quote_currency": _quote_currency(market),
                "updated_ts": updated_ts,
            }
            if exchange_backfilled:
                conn.execute(
                    "UPDATE manual_holdings SET volume=?,avg_price=?,exchange=?,updated_ts=? WHERE market=?",
                    (final_volume, final_avg, exchange, updated_ts, market),
                )
            else:
                conn.execute(
                    "UPDATE manual_holdings SET volume=?,avg_price=?,updated_ts=? WHERE market=?",
                    (final_volume, final_avg, updated_ts, market),
                )
            conn.execute(
                "INSERT INTO holding_mutation_receipts(mutation_id,applied_ts,result_json) VALUES(?,?,?)",
                (mutation_id, updated_ts, json.dumps(result, ensure_ascii=False, separators=(",", ":"))),
            )
        return result
    finally:
        conn.close()


def _publish_after_mutation(result: dict[str, Any]) -> dict[str, Any]:
    try:
        publication = CloudflareSnapshotPublisher().publish_once()
        result["snapshot_publish_status"] = str(publication.get("status") or "unknown")
        result["snapshot_private_holdings_enabled"] = bool(publication.get("private_holdings_enabled"))
    except Exception as exc:
        # The canonical SQLite write is already committed. Do not roll it back because
        # the viewer publisher is temporarily unavailable; normal publisher cycles can
        # still deliver the canonical row later.
        result["snapshot_publish_status"] = "error"
        result["snapshot_publish_error"] = str(exc)[:240]
    return result


def process_once(settings: Settings | None = None) -> dict[str, Any]:
    load_dotenv(REPO_ROOT / ".env", override=True)
    settings = settings or Settings()
    ingest_url = os.getenv("CLOUDFLARE_VIEWER_INGEST_URL", "").strip()
    token = os.getenv("CLOUDFLARE_VIEWER_INGEST_TOKEN", "").strip()
    runtime_url = _runtime_url(ingest_url)
    if not runtime_url or not token:
        return {"status": "not_configured", "processed": False}

    try:
        claimed = _request_json(runtime_url, token)
    except MutationRejected as exc:
        return {"status": "queue_unavailable", "processed": False, "error_code": exc.code, "error": exc.message}
    mutation = claimed.get("mutation")
    if not isinstance(mutation, dict):
        return {"status": "idle", "processed": False}

    mutation_id = str(mutation.get("id") or "")
    try:
        result = apply_mutation(settings.journal_db, mutation)
    except MutationRejected as exc:
        try:
            _request_json(runtime_url, token, method="POST", payload={
                "id": mutation_id,
                "status": "rejected",
                "result": {},
                "error_code": exc.code,
                "error_message": exc.message,
            })
        except MutationRejected:
            pass
        return {"status": "rejected", "processed": True, "id": mutation_id, "error_code": exc.code, "error": exc.message}
    except (sqlite3.Error, OSError, ValueError) as exc:
        code, message = "LOCAL_DB_ERROR", str(exc)
        try:
            _request_json(runtime_url, token, method="POST", payload={
                "id": mutation_id,
                "status": "rejected",
                "result": {},
                "error_code": code,
                "error_message": message,
            })
        except MutationRejected:
            pass
        return {"status": "rejected", "processed": True, "id": mutation_id, "error_code": code, "error": message}

    result = _publish_after_mutation(result)
    try:
        _request_json(runtime_url, token, method="POST", payload={"id": mutation_id, "status": "applied", "result": result})
    except MutationRejected as exc:
        # Local SQLite is already canonical. The receipt makes a reclaimed request
        # idempotent, so a later retry can ACK the same result without a second write.
        return {"status": "applied_ack_pending", "processed": True, "id": mutation_id, "result": result, "error_code": exc.code}
    return {"status": "applied", "processed": True, "id": mutation_id, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply queued owner holding mutations to canonical local SQLite.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued mutation and exit.")
    parser.add_argument("--interval", type=float, default=5.0, help="Polling seconds in continuous mode.")
    args = parser.parse_args()
    if args.once:
        print(json.dumps(process_once(), ensure_ascii=False))
        return 0
    interval = max(1.0, float(args.interval))
    while True:
        result = process_once()
        if result.get("processed") or result.get("status") not in {"idle", "not_configured"}:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
