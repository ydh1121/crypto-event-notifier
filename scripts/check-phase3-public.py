from __future__ import annotations

import json

from b3_trader.exchange_public import public_exchange


def check(name: str) -> dict[str, object]:
    adapter = public_exchange(name)
    markets = adapter.krw_markets()
    tickers = adapter.krw_tickers()
    ticker_markets = {str(row.get("market") or "") for row in tickers}
    sample = markets[0].market if markets else ""
    return {
        "exchange": name,
        "krw_markets": len(markets),
        "tickers": len(tickers),
        "ticker_coverage": sum(1 for row in markets if row.market in ticker_markets),
        "warning_markets": sum(1 for row in markets if row.warning),
        "sample_market": sample,
    }


def main() -> None:
    print(json.dumps({name: check(name) for name in ("bithumb", "upbit")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
