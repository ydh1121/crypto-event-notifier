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

## Research supervisor

Managed periodic components:

- `warehouse-export` — 5 minutes
- `reference-version-watch` — 6 hours
- `cloudflare-snapshot-publish` — 20 seconds
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

Raw SQLite is never uploaded.

## Phase 2.5 implementation started

The Pages viewer now has the same top-level information architecture as the local dashboard:

- `홈`
- `코인`
- `결과`
- `기록`
- `설정`

First slice added:

- Home: aggregate PAPER state, permitted manual holdings, leader, research-node summary
- Coin: current per-market account state and plain-Korean regime/entry/opportunity scores from the compact snapshot
- Results: all-market search/filter/sort; rows open Coin detail
- Records: current snapshot/trade-count summary
- Settings: read-only account/research-node state plus owner invite management

Remote contract remains read-only. There are no Pages endpoints for pause/resume, kill switch, strategy changes, asset mutation, or order execution.

## Current next action

Proceed with **Phase 2.5B — detailed research data bridge**.

Do not put all historical data into the 20-second global snapshot. Design a separate bounded per-market detail path so 477 markets do not resend full history continuously.

Next implementation order:

1. define compact per-market detail payload from the existing local PAPER detail data,
2. add D1 storage/API for latest per-market detail,
3. publish only changed/recent selected detail slices on a slower cadence,
4. expose current trade plan / next add / target / stop / trailing state,
5. expose recent fills and completed-trade feedback,
6. expose bounded equity + market-memory history for charts,
7. build the Pages Coin/Records detailed views on that API,
8. mobile/desktop QA and polling-state preservation.

After the Phase 2.5 data contract is stable, Phase 3 Upbit adapter work can begin while UI polish continues.

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
