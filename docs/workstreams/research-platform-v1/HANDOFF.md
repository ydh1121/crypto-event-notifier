# Research Platform v1 handoff

## Active state

This is the active top-level expansion workstream. `dashboard-v1` remains the local UI stabilization sub-workstream.

Hard boundary: **PAPER-only**. No live exchange execution, private exchange order endpoints, remote strategy mutation, or automatic promotion of external code.

## Current verified runtime

Windows PC is the 24/7 research server.

- local SQLite: authoritative PAPER/runtime state
- Parquet + DuckDB: secondary analytical warehouse
- Research Supervisor: non-trading sidecar
- private GitHub: source/spec/reference registry
- Google Drive: backup/export only
- Cloudflare Pages + Functions + D1: authenticated external/mobile read-only viewer

Verified Pages URL:

`https://crypto-paper-viewer-ydh1121-cf36.pages.dev`

Already runtime verified:

- Wrangler OAuth / Pages / D1 / secrets / health
- first owner bootstrap/login
- 20-second compact PAPER snapshots
- owner manual holdings
- per-market detail publisher with size-aware request splitting
- Windows Git auto-sync + Pages auto-deploy
- Research Supervisor self-healing and Windows atomic-status write hardening

## Research supervisor

Managed components:

- `warehouse-export` — 5 minutes
- `reference-version-watch` — 6 hours
- `cloudflare-snapshot-publish` — 20 seconds
- `cloudflare-market-detail-publish` — 30 seconds
- `cloudflare-pages-deploy` — 30-second viewer-code change check

Remote Pages users cannot mutate component state or trading/PAPER strategy state.

## Current Pages data contract

The global snapshot contains aggregate PAPER capital/equity/cash/P&L, scan progress, compact all-market leaderboard, current per-market PAPER state/scores, Research Supervisor status, optional permitted manual holdings, and bounded cross-market fill/learning records.

A separate detail path stores bounded research keyed by `exchange + market + strategy`. Current Bithumb identity is `bithumb|KRW-XXX|adaptive` and already carries position, trade plan, target/stop/trailing state, recent fills, learning/profile changes, equity history and market-memory/score history.

Raw SQLite is never uploaded.

## Final Pages UI ownership after local-vs-Pages audit

The current viewer intentionally avoids multiple broad patch layers fighting over the same screen.

- `local-parity.js/css` — Liquid navigation and desktop Results research split
- `asset-local-port.js/css` — Coin workspace and browser-only averaging tools
- `records-port.js/css` — cross-market activity timeline
- `viewer-shell-v3.js/css` — final Home / Results / Settings composition, holdings dashboard, mobile QA and polling-state persistence

`viewer-shell-v2`, `viewer-best-port` and `mobile-qa` remain only in source history and are not loaded by the current index.

### Home

- aggregate PAPER capital
- full permitted manual-holdings dashboard with invested/current value/P&L
- best/worst current holding and allocation view
- clickable per-asset holdings rows
- actual top opportunity-score quick cards
- market-average regime/entry/opportunity context
- scan progress and research-service health

### Coin

- Liquid coin chip rail
- large current-price hero
- actual permitted holding average price/current P&L
- plain-Korean current decision
- regime/entry/related-flow scores
- expandable diagnostics
- shared 1H/6H/24H/7D price and score range
- browser-only holding/averaging calculator; no PC/SQLite write
- on mobile charts are shown before manual tools to reduce scrolling friction

### Results

Desktop:

- wider left ranking panel
- compact row hierarchy: rank / coin+state / current price+average / return+holding/P&L context
- no dedicated clipped holding column
- right selected-market PAPER detail

Mobile:

- `코인 목록 / 선택 코인 상세` master-detail switch
- sticky return-to-list control
- touch-sized search/sort/filter controls
- raw trade-intent normalization
- unavailable prices shown as calculation state rather than invented numbers
- saved search/sort/filter/selected market/list scroll across polling
- long-list `content-visibility`

### Records

Cross-market timeline with buy/sell/learning filters. Clicking a record opens the corresponding coin.

### Settings

Read-only `데이터 수집 · 연구 구성요소` status showing component description, state, interval, recent success/result/error and external-reference status. Local control buttons are intentionally excluded.

## Phase 2.5 remaining observations

Implementation is no longer blocking Phase 3. Continue observing:

- iPhone Safari 360–430 px real-device usability after v3
- desktop 1280–1920 layout after wider Results/holdings dashboard
- long-run 477-market responsiveness
- `recent_records` runtime after the publisher restart
- invited viewer negative permission test for private holdings

These are verification/polish items, not blockers for the Phase 3 data architecture.

## Phase 3 — started

The first Phase 3 slice is now implemented without changing the current Bithumb PAPER execution path.

Added:

- `b3_trader/upbit_client.py` — read-only Upbit quotation client
- `b3_trader/exchange_public.py` — common public Bithumb/Upbit adapter interface
- `scripts/check-phase3-public.py` — Bithumb/Upbit KRW market/ticker coverage smoke check

Upbit public collection uses the official trading-pair list, quote-currency ticker list, orderbook and minute-candle APIs. No Upbit API key or private order endpoint is introduced.

Next Phase 3 engineering order:

1. runtime-smoke the Upbit KRW market/ticker collector on Windows,
2. introduce durable local identity `exchange + market + strategy` while preserving existing Bithumb history,
3. create isolated 10M PAPER account per identity,
4. add Upbit scan/scoring loop via the common public adapter,
5. add exchange dimension to warehouse/Pages snapshot rows,
6. add Bithumb vs Upbit cross-venue comparison,
7. promote the multi-exchange engine only after Bithumb regression/PAPER smoke passes.

## Parallel observations

- Chrome long-run responsiveness
- Git auto-sync long-run behavior
- Parquet growth/day and retention sizing
- private-holdings negative permission test

## Later roadmap

- Phase 4: Strategy Lab — conservative/balanced/aggressive/DCA/countertrend/swing
- Phase 5: on-chain + community language + news + macro event-risk
- Phase 6: local AI research service
- Phase 7: walk-forward/holdout/challenger validation
- Phase 8: robust live-candidate promotion research; real-money work remains a separate future workstream
