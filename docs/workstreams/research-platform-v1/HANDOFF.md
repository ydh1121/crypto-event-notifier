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

Verified in the real Cloudflare account:

- Wrangler OAuth login
- Pages project creation/reuse
- D1 creation/binding/migrations
- Pages secrets
- `/api/health` returns `ok: true`
- first owner bootstrap and login
- 20-second PAPER snapshot delivery
- owner manual holdings display
- Windows Wrangler/Python UTF-8 and Pages config-path deployment issues fixed
- local Git auto-sync recovered and repeatedly verified
- Pages auto-deploy verified `healthy` / `up_to_date`
- per-market detail publisher runtime verified with 40 markets stored in 2 size-aware requests
- Research Supervisor self-healing and Windows atomic status-write collision fix verified in long-running logs

## Research supervisor

Managed periodic components:

- `warehouse-export` — 5 minutes
- `reference-version-watch` — 6 hours
- `cloudflare-snapshot-publish` — 20 seconds
- `cloudflare-market-detail-publish` — 30 seconds
- `cloudflare-pages-deploy` — 30-second viewer-code change check

Component failure remains isolated from the PAPER engine. Remote Pages users cannot change component state.

## Current Pages data contract

The global snapshot contains:

- aggregate PAPER capital/equity/cash/P&L
- scan progress and active-position count
- compact 477-market leaderboard
- per-market current price, account/equity state, average entry, unrealized P/L, trade count/win rate
- regime / entry / opportunity / suggested weight / current intent
- Research Supervisor component summary
- optional authenticated manual holdings
- bounded recent cross-market fills and completed-trade learning records for the Records workspace

A separate per-market detail path stores bounded detailed PAPER research by `exchange + market + strategy` without bloating the 20-second global snapshot.

Current detail payload contains:

- current PAPER position/account state
- next entry/add plan, target, hard stop and trailing state
- recent PAPER fills
- completed-trade feedback and profile-learning changes
- bounded equity history
- bounded market-memory / regime / entry / opportunity history
- selected signal diagnostics such as pullback, volatility, orderbook imbalance and BTC/ETH context

Current implementation uses `bithumb|KRW-XXX|adaptive`; the key shape is ready for Phase 3 Upbit and Phase 4 strategy variants.

The Windows detail publisher rotates through the market universe while prioritizing active/high-opportunity markets. Payloads are size-aware and automatically split into <=1.5 MB requests. Raw SQLite is never uploaded.

## Phase 2.5 UI architecture after full local-vs-Pages audit

The real current local dashboard was re-reviewed from its final runtime cascade rather than from conversation history. The relevant local load order includes base styles plus plain-language, portfolio tools, UX polish, Liquid navigation, PAPER research, research capital and research component layers.

The Pages viewer now intentionally uses focused owners instead of stacking many broad patch layers:

- `local-parity.js/css` — Liquid top/bottom navigation and desktop Results research split
- `asset-local-port.js/css` — Coin workspace, local-derived asset analysis, charts and browser-only averaging tools
- `records-port.js/css` — cross-market fills/learning Records timeline
- `viewer-shell-v2.js/css` — consolidated Home / Results / Settings composition, mobile Results master/detail and polling-state persistence

Older `viewer-best-port` and `mobile-qa` broad patch layers remain in source history but are no longer loaded by `index.html`.

### Home

Current composition:

- aggregate PAPER capital card
- compact permitted manual holdings with clickable coin rows
- actual top opportunity-score coins as quick cards
- actual market-average regime / entry / opportunity context
- scan progress
- research-service health

The old duplicate leader/node summary block is hidden once the consolidated shell is active.

### Coin

`asset-local-port` remains the canonical local-derived surface:

- Liquid coin chip rail
- large current-price hero
- actual permitted holding average price / current P&L
- plain-Korean current decision
- regime / entry / related-flow scores
- expandable diagnostics
- browser-only holding and averaging calculator; no PC/SQLite mutation
- shared 1H / 6H / 24H / 7D price/score range
- PAPER markers and bounded research history
- optional collapsed detailed PAPER plan/fills/learning section

### Results

Desktop:

- search / sort / status filters
- left all-market leaderboard
- right selected-market live PAPER detail
- current leader / aggregate state summary

Mobile:

- `코인 목록 / 선택 코인 상세` master-detail switch instead of stacking all 477 rows above detail
- selected-market detail has a sticky back-to-list control
- raw intent strings are normalized to Korean labels
- unavailable plan prices are represented as calculation state, never invented values
- persisted search / sort / filter / selected market / list scroll
- `content-visibility` is used to reduce long-list rendering cost

### Records

The old summary-only view is replaced by a cross-market timeline:

- cumulative fills / learning counts
- buy / sell / learning filters
- recent PAPER buy/sell records
- completed-trade profile-learning changes
- clicking a record opens that coin

The compact `recent_records` bridge reads only bounded fields from local PAPER research tables. Raw SQLite and full signal JSON remain local.

### Settings

The local `데이터 수집 · 연구 구성요소` experience is ported as read-only status:

- component label and description
- enabled/runtime status
- real interval
- recent successful run
- last result / error
- external reference-watch summary
- clear read-only permission status

Local `끄기`, `지금 실행`, strategy mutation, kill/pause/resume and other PC-control actions are intentionally not present on Pages.

Owner invite/account management remains available in Settings.

## Current next action

Finish the **Phase 2.5C runtime verification gate** against the consolidated viewer shell before starting Phase 3.

One consolidated verification pass should cover:

1. Windows auto-sync reaches the latest branch head and the Python snapshot publisher restarts cleanly after the `recent_records` change,
2. Pages auto-deploy records the same head and stays healthy,
3. one iPhone Safari sweep across Home / Coin / Results / Records / Settings confirms no clipping, blank oversized plan cards or bottom-nav overlap,
4. Results polling preserves search / sort / filter / selected coin / list scroll instead of jumping every 15 seconds,
5. the 477-market list remains responsive on mobile and desktop,
6. Records shows real cross-market fill/learning data after the new snapshot contract is live,
7. desktop 1280–1920 visual QA checks the consolidated shell against the local dashboard's useful information hierarchy.

After those checks pass, Phase 3 Upbit all-KRW PAPER can start. Further cosmetic polish can continue later, but state loss, mobile usability, 477-market responsiveness or data-bridge failures remain blockers.

## Parallel observations

These continue without blocking the roadmap:

- Chrome long-run responsiveness
- Git auto-sync long-run behavior
- Parquet growth/day and retention sizing
- negative permission test: invited viewer without holdings permission must not receive private holdings

## Later roadmap

- Phase 3: Upbit all-KRW PAPER via common exchange adapter
- Phase 4: Strategy Lab — conservative/balanced/aggressive/DCA/countertrend/swing and combinations
- Phase 5: on-chain + Korean/global community language + news + macro event-risk features
- Phase 6: local AI research service
- Phase 7: walk-forward/holdout/challenger validation
- Phase 8: robust live-candidate promotion research; real-money work remains a separate future workstream
