from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
CURRENT_PYTHON = Path(sys.executable).resolve()

if VENV_PYTHON.exists() and CURRENT_PYTHON != VENV_PYTHON.resolve():
    result = subprocess.run(
        [str(VENV_PYTHON), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(REPO_ROOT),
        check=False,
    )
    raise SystemExit(result.returncode)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    print(f"python={sys.executable}")
    print(json.dumps({name: check(name) for name in ("bithumb", "upbit")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
