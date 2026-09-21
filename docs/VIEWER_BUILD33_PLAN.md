# Viewer Build 33 — Strategy / PAPER Performance Analytics

Build 33 keeps the approved navigation and page structure intact. It extends the existing Strategy Research page with real Shadow PAPER performance analytics derived from the authoritative SQLite research database.

## Scope

1. Strategy equity curve
   - Capture each strategy experiment's aggregate PAPER equity at five-minute buckets.
   - Derive portfolio drawdown from observed aggregate equity peaks.
   - Store only PAPER research history; this does not place or modify real orders.
   - Viewer ranges: 1H / 6H / 24H / 7D / all available history.

2. Strategy-by-coin performance
   - Use `strategy_lab_accounts` as the source of truth.
   - Show per-coin return, realized PnL, unrealized PnL, account drawdown, closed trades, win rate, and whether the strategy currently holds the coin.

3. Coin × strategy comparison
   - For one KRW market, compare all running/paused strategy experiments using the same market-memory source.
   - Do not manufacture backtest results or interpolate missing trades.

4. Overall adaptive PAPER equity / drawdown
   - Aggregate `research_accounts_mx` for Bithumb and Upbit adaptive PAPER accounts.
   - Capture five-minute portfolio history by exchange.
   - Expose Bithumb, Upbit, and combined curves as a benchmark inside Strategy Research.

## Storage / performance

- `strategy_lab_equity_history`: local SQLite, five-minute experiment snapshots.
- `paper_portfolio_history`: local SQLite, five-minute exchange-level adaptive PAPER snapshots.
- Retain fourteen days locally; publish at most seven days / 2,016 points per series to keep the Cloudflare snapshot bounded.
- Coin × strategy data is published in a compact matrix rather than verbose repeated objects.

## UI

Strategy Research gains four internal tabs without changing the main navigation:

- 전략 성과
- 코인별 성과
- 코인 × 전략
- 전체 PAPER

The existing strategy Gate / candidate validation remains unchanged.

## Safety

- PAPER only.
- No real exchange order APIs.
- No automatic strategy promotion.
- No mutation of the active adaptive strategy configuration.
