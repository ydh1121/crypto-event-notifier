# Autonomous PAPER demo

Status: experimental, PAPER-only. This is a pre-live validation track and must never place real Bithumb orders.

## Purpose

Run the currently implemented regime/entry strategy against a broader Bithumb KRW universe before any live-execution work. The demo uses a completely separate virtual account so it cannot alter the user's manually entered holdings or the existing PAPER portfolio history.

## Account and risk

- Start equity: 10,000,000 KRW
- Base order: 500,000 KRW with the existing adaptive sizing function (0.60x–1.25x)
- Maximum value per coin: 3,000,000 KRW
- Maximum total exposure: 6,000,000 KRW
- Maximum simultaneously open coins: 4
- Re-entry/add-on cooldown per coin: 30 minutes
- Hard PAPER stop: -8% per position
- Market-weakness exit: regime score below 45
- Existing execution checks are reused: spread <= 45 bps, estimated slippage <= 35 bps, BTC flash-crash guard, order-rate guard

## Universe selection

Every scan starts from Bithumb's full KRW market list and public ticker snapshot. Stablecoin-like quote substitutes are excluded from trade candidates. The remaining markets are filtered for 24-hour turnover >= 3 billion KRW and extreme 24-hour moves (>32% absolute) are skipped. Liquidity and momentum rank the shortlist, then the existing `AssetStrategy` evaluates 5-minute candles, BTC/ETH regime inputs, alt breadth, orderbook imbalance, pullback, Fibonacci location, momentum and volatility.

Only `BUY_CANDIDATE` results can create a virtual buy. The strategy thresholds remain the existing regime >= 65 and entry >= 68.

## Isolation and persistence

- Demo database: `b3_trader/data/auto_demo.sqlite3`
- Dashboard runtime status: `dashboard/runtime-demo.json` (generated/ignored)
- Existing user holdings, averaging plans, and main PAPER fills are not modified.
- No Bithumb private API key is needed or used.
- No Telegram demo-trade spam is emitted.

## Runtime

`scripts/run-local.ps1` launches `python -m b3_trader.auto_demo` alongside the local trader. The scanner repeats roughly every 180 seconds and persists its fills so the experiment survives restarts.

The Home dashboard contains a `1,000만원 자동매매 데모` summary showing virtual equity, cash, open positions, and current candidates.

## Evaluation before live trading

Do not use a short winning streak as evidence that the strategy is ready for live execution. Review at least trade count, win rate, payoff ratio, drawdown, turnover, spread/slippage blocks, behavior during market regime changes, and whether the universe-selection step systematically chases already-extended coins. Live execution remains a separate workstream even if this demo performs well.
