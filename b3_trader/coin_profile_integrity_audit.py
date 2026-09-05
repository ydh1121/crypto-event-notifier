from __future__ import annotations

import argparse
import json
import os

import requests
from dotenv import load_dotenv


def _endpoint() -> tuple[str, str]:
    load_dotenv(override=True)
    ingest = os.getenv("CLOUDFLARE_VIEWER_INGEST_URL", "").strip()
    token = os.getenv("CLOUDFLARE_VIEWER_INGEST_TOKEN", "").strip()
    if not ingest or not token:
        return "", ""
    root = ingest[: -len("/api/ingest")] if ingest.endswith("/api/ingest") else ingest.rstrip("/")
    return root + "/api/coin-profile-integrity-audit", token


def run() -> dict:
    url, token = _endpoint()
    if not url or not token:
        return {"ok": False, "configured": False, "error": "Cloudflare ingest is not configured"}
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "configured": True, "error": f"{type(exc).__name__}: {exc}"}
    return payload if isinstance(payload, dict) else {"ok": False, "configured": True, "error": "invalid response"}


def compact(payload: dict, row_limit: int = 30) -> dict:
    if not payload.get("ok"):
        return payload
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    limit = max(0, min(120, int(row_limit)))
    return {
        "ok": True,
        "audited_at": payload.get("audited_at"),
        "market_scope": payload.get("market_scope") or payload.get("audit_scope") or {},
        "cached_scope": payload.get("cached_scope") or {},
        "ready_total": payload.get("ready_total"),
        "total": payload.get("total", len(rows)),
        "identity_total": payload.get("identity_total"),
        "incomplete_total": payload.get("incomplete_total"),
        "by_exchange": payload.get("by_exchange") or {},
        "reasons": payload.get("reasons") or {},
        "sample_count": min(limit, len(rows)),
        "sample_rows": rows[:limit],
        "rows_truncated": bool(payload.get("rows_truncated")) or len(rows) > limit,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit all listed coin profiles while keeping console output bounded.")
    parser.add_argument("--rows", type=int, default=30, help="problem rows to print; full market audit still runs")
    parser.add_argument("--full", action="store_true", help="print the full API payload")
    args = parser.parse_args()
    payload = run()
    print(json.dumps(payload if args.full else compact(payload, args.rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()