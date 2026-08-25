from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from b3_trader.exchange_public import public_exchange
from b3_trader.multi_exchange_paper import MultiExchangePaperDemo
from b3_trader.multi_exchange_store import MultiExchangeStore


def main() -> None:
    print("=== PHASE 3 PUBLIC ADAPTERS ===")
    for exchange in ("bithumb", "upbit"):
        adapter = public_exchange(exchange)
        markets = adapter.krw_markets()
        tickers = adapter.krw_tickers()
        ticker_markets = {str(row.get("market") or "") for row in tickers}
        warning = sum(1 for row in markets if row.warning)
        print(
            f"{exchange}: markets={len(markets)} tickers={len(tickers)} "
            f"coverage={sum(1 for row in markets if row.market in ticker_markets)}/{len(markets)} "
            f"warning={warning}"
        )

    print("\n=== PHASE 3 STORAGE BEFORE SCAN ===")
    store = MultiExchangeStore()
    print(json.dumps({"counts": store.counts(), "scopes": store.scope_counts()}, ensure_ascii=False, indent=2))
    store.close()

    print("\n=== UPBIT PAPER SMOKE: TOP 3 ===")
    demo = MultiExchangePaperDemo("upbit", "adaptive", market_limit=3)
    demo.run_once()
    status_path = REPO_ROOT / "dashboard/runtime-demo-upbit.json"
    if not status_path.exists():
        raise RuntimeError("Upbit PAPER status file was not created")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "exchange": status.get("exchange"),
                "strategy": status.get("strategy"),
                "market_count": status.get("market_count"),
                "scan_total": status.get("scan_total"),
                "scanned_count": status.get("scanned_count"),
                "active_positions": status.get("active_positions"),
                "warning_markets": status.get("warning_markets"),
                "best_market": (status.get("best_market") or {}).get("market"),
                "error": status.get("error"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if status.get("exchange") != "upbit" or status.get("strategy") != "adaptive":
        raise RuntimeError("Upbit PAPER status identity mismatch")
    if int(status.get("market_count") or 0) <= 0:
        raise RuntimeError("No Upbit scoped PAPER accounts were created")
    if int(status.get("scanned_count") or 0) != 3:
        raise RuntimeError("Upbit top-3 PAPER smoke did not complete")
    if status.get("error"):
        raise RuntimeError(f"Upbit PAPER smoke reported error: {status['error']}")

    print("\n=== PHASE 3 STORAGE AFTER SCAN ===")
    store = MultiExchangeStore()
    print(json.dumps({"counts": store.counts(), "scopes": store.scope_counts()}, ensure_ascii=False, indent=2))
    upbit_accounts = [
        row
        for row in store.scope_counts()
        if row.get("exchange") == "upbit" and row.get("strategy") == "adaptive"
    ]
    if not upbit_accounts or int(upbit_accounts[0].get("accounts") or 0) <= 0:
        raise RuntimeError("Upbit exchange+market+strategy accounts are missing")
    store.close()

    print("\nPHASE3_SMOKE=PASS")


if __name__ == "__main__":
    main()
