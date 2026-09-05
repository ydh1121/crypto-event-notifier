from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def _same_path(a: str, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except OSError:
        return False


if os.name == "nt" and VENV_PYTHON.exists() and not _same_path(sys.executable, VENV_PYTHON):
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]])

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from b3_trader.cloudflare_snapshot_publisher import CloudflareSnapshotPublisher
from b3_trader.multi_exchange_store import BITHUMB_CUTOVER_MIGRATION

DB_PATH = REPO_ROOT / "b3_trader/data/auto_demo.sqlite3"
BITHUMB_STATUS = REPO_ROOT / "dashboard/runtime-demo.json"
UPBIT_STATUS = REPO_ROOT / "dashboard/runtime-demo-upbit.json"


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def scalar(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> float:
    row = conn.execute(sql, args).fetchone()
    return float(row[0] or 0) if row else 0.0


def main() -> None:
    print(f"python={sys.executable}")
    if not DB_PATH.exists():
        print("ERROR: auto_demo.sqlite3 missing")
        print("PHASE3_CUTOVER=FAIL")
        raise SystemExit(1)

    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        migration_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_store_migrations'"
        ).fetchone()
        marker = None
        if migration_table:
            marker = conn.execute(
                "SELECT name,applied_ts,details_json FROM research_store_migrations WHERE name=?",
                (BITHUMB_CUTOVER_MIGRATION,),
            ).fetchone()
        applied_ts = float(marker["applied_ts"] or 0) if marker else 0.0
        details = {}
        if marker:
            try:
                parsed = json.loads(str(marker["details_json"] or "{}"))
                details = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                details = {}

        bithumb_accounts = int(scalar(
            conn,
            "SELECT COUNT(*) FROM research_accounts_mx WHERE exchange='bithumb' AND strategy='adaptive'",
        ))
        upbit_accounts = int(scalar(
            conn,
            "SELECT COUNT(*) FROM research_accounts_mx WHERE exchange='upbit' AND strategy='adaptive'",
        ))
        bithumb_signal_ts = scalar(
            conn,
            "SELECT MAX(ts) FROM research_signals_mx WHERE exchange='bithumb' AND strategy='adaptive'",
        )
        upbit_signal_ts = scalar(
            conn,
            "SELECT MAX(ts) FROM research_signals_mx WHERE exchange='upbit' AND strategy='adaptive'",
        )
        legacy_signal_ts = scalar(conn, "SELECT MAX(ts) FROM research_signals") if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_signals'"
        ).fetchone() else 0.0
        scoped_fills = int(scalar(
            conn,
            "SELECT COUNT(*) FROM research_fills_mx WHERE exchange='bithumb' AND strategy='adaptive'",
        ))
        legacy_fills = int(scalar(conn, "SELECT COUNT(*) FROM research_fills")) if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_fills'"
        ).fetchone() else 0
    finally:
        conn.close()

    bithumb = read_json(BITHUMB_STATUS)
    upbit = read_json(UPBIT_STATUS)
    snapshot = CloudflareSnapshotPublisher().build_snapshot()
    public = snapshot.get("public") if isinstance(snapshot.get("public"), dict) else {}
    records = public.get("exchange_records") if isinstance(public.get("exchange_records"), dict) else {}
    bithumb_records = records.get("bithumb") if isinstance(records.get("bithumb"), dict) else {}

    stored_verification = details.get("verification") if isinstance(details.get("verification"), dict) else {}
    result = {
        "cutover_marker": bool(marker),
        "cutover_applied_ts": applied_ts,
        "stored_cutover_verification_ok": bool(stored_verification.get("ok")),
        "bithumb_scoped_accounts": bithumb_accounts,
        "upbit_scoped_accounts": upbit_accounts,
        "bithumb_scoped_signal_after_cutover": bool(applied_ts and bithumb_signal_ts > applied_ts),
        "legacy_signal_stopped_before_cutover": bool(applied_ts and legacy_signal_ts <= applied_ts),
        "bithumb_scoped_fills": scoped_fills,
        "legacy_fills_at_cutover_source": legacy_fills,
        "bithumb_runtime_exchange": bithumb.get("exchange"),
        "bithumb_runtime_identity": bithumb.get("identity"),
        "bithumb_scan": f"{int(bithumb.get('scanned_count') or 0)}/{int(bithumb.get('scan_total') or 0)}",
        "upbit_scan": f"{int(upbit.get('scanned_count') or 0)}/{int(upbit.get('scan_total') or 0)}",
        "cloudflare_bithumb_record_fill_count": int(bithumb_records.get("fill_count") or 0),
        "cloudflare_bithumb_record_feedback_count": int(bithumb_records.get("feedback_count") or 0),
        "upbit_signal_present": upbit_signal_ts > 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    errors: list[str] = []
    pending: list[str] = []
    if not marker:
        pending.append("Bithumb scoped cutover marker not written yet")
    elif not stored_verification.get("ok"):
        errors.append("stored Bithumb migration verification is not OK")
    if bithumb_accounts < 400:
        pending.append("Bithumb scoped accounts are not fully seeded yet")
    if upbit_accounts < 200:
        errors.append("Upbit scoped accounts disappeared")
    if marker and not (bithumb_signal_ts > applied_ts):
        pending.append("first post-cutover Bithumb scoped scan has not completed yet")
    if marker and legacy_signal_ts > applied_ts:
        errors.append("legacy Bithumb signal table is still being written after cutover")
    if bithumb.get("exchange") != "bithumb" or bithumb.get("identity") != "exchange+market+strategy":
        pending.append("runtime-demo.json is still from the legacy engine")
    if int(bithumb.get("scan_total") or 0) > 0 and int(bithumb.get("scanned_count") or 0) != int(bithumb.get("scan_total") or 0):
        pending.append("Bithumb first scoped full scan still running")
    if int(upbit.get("scan_total") or 0) > 0 and int(upbit.get("scanned_count") or 0) != int(upbit.get("scan_total") or 0):
        errors.append("Upbit full scan is no longer complete")
    if marker and int(bithumb_records.get("fill_count") or 0) != scoped_fills:
        errors.append("Cloudflare Bithumb records are not reading scoped fills")

    print("\n=== RESULT ===")
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        print("PHASE3_CUTOVER=FAIL")
        raise SystemExit(1)
    if pending:
        for item in pending:
            print(f"PENDING: {item}")
        print("PHASE3_CUTOVER=WARMING")
        return
    print("PHASE3_CUTOVER=PASS")


if __name__ == "__main__":
    main()
