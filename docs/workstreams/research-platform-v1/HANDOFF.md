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

Verified in the real Cloudflare account on 2026-08-24:

- Wrangler OAuth login
- Pages project creation/reuse
- D1 creation/binding/migrations
- Pages secrets
- initial deploy
- `/api/health` returns `ok: true`
- first owner bootstrap and login
- 20-second PAPER snapshot delivery
- owner-only manual holdings display
- Windows Wrangler/Python UTF-8 and Pages config-path deployment issues fixed
- local Git auto-sync recovered and verified after the generated npm lockfile blocker was removed
- Pages auto-deploy verified `healthy` and `up_to_date` against the current branch head

## Research supervisor

Managed periodic components:

- `warehouse-export` — 5 minutes
- `reference-version-watch` — 6 hours
- `cloudflare-snapshot-publish` — 20 seconds
- `cloudflare-market-detail-publish` — 30 seconds
- `cloudflare-pages-deploy` — 30-second viewer-code change check

Component failure remains isolated from the PAPER engine. Remote Pages users cannot change component state.

## Current Pages data contract

The global snapshot currently contains:

- aggregate PAPER capital/equity/cash/P&L
- scan progress and active-position count
- compact all-market leaderboard
- per-market current price, account/equity state, average entry, unrealized P/L, trade count/win rate
- regime / entry / opportunity / suggested weight / current intent
- Research Supervisor summary
- optional authenticated manual holdings

A separate per-market detail path now stores bounded detailed PAPER research by `exchange + market + strategy` without bloating the 20-second global snapshot.

Current detail payload contains:

- current PAPER position/account state
- next entry/add plan, target, hard stop and trailing state
- recent PAPER fills
- completed-trade feedback and profile-learning changes
- bounded equity history
- bounded market-memory / regime / entry / opportunity history
- selected signal diagnostics such as pullback, volatility, orderbook imbalance and BTC/ETH context

Current implementation uses `bithumb|KRW-XXX|adaptive`; the key shape is ready for Phase 3 Upbit and Phase 4 strategy variants.

The Windows detail publisher rotates through the market universe while prioritizing active/high-opportunity markets. Payloads are size-aware and automatically split into <=1.5 MB requests. Real runtime verification stored 40 markets in two requests (22 + 18) with no lost rows.

Raw SQLite is never uploaded.

## Phase 2.5 status

The Pages viewer has the same top-level information architecture as the local dashboard:

- `홈`
- `코인`
- `결과`
- `기록`
- `설정`

Implemented viewer slices:

- Home: aggregate PAPER state, permitted manual holdings, leader, research-node summary
- Coin: current per-market account state and plain-Korean regime/entry/opportunity scores
- Coin detail: next trade plan, bounded charts, recent fills and learning history from the authenticated per-market detail API
- Results: all-market search/filter/sort; rows open Coin detail
- Records: current snapshot/trade-count summary
- Settings: read-only account/research-node state plus owner invite management

Remote contract remains read-only. There are no Pages endpoints for pause/resume, kill switch, strategy changes, asset mutation, or order execution.

## Current next action

Proceed with **Phase 2.5C — browser/UI verification and parity polish**.

Immediate order:

1. verify a known published market such as BTC/XRP/ETH renders the detailed Coin cards in the authenticated Pages viewer,
2. fix any client-side/API rendering issue found by that real browser check,
3. improve chart ranges/labels and plain-Korean trade-decision hierarchy,
4. expand Records into a useful cross-market fill/learning view instead of only a summary,
5. verify polling preserves selected tab/coin/filter/scroll state,
6. mobile Safari QA at 360–430 px,
7. desktop QA at 1280–1920 px,
8. verify 477-market rendering remains responsive.

After the Phase 2.5 data contract and browser rendering are stable, Phase 3 Upbit adapter work can begin while UI polish continues.

## Parallel observations

These continue without blocking the roadmap:

- local dashboard Photo-eBook navigation acceptance on PC/iPhone
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
