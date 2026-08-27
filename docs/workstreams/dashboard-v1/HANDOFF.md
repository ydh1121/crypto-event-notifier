# Dashboard v1 handoff

## Current phase

Local multi-asset PAPER monitor + beginner-facing dashboard + secure Cloudflare phone access + adaptive Bithumb-wide per-coin PAPER research + Build 38 market lifecycle/notice/timing/return-window foundation.

## Program roadmap

The program-level source of truth is now:

- `docs/workstreams/dashboard-v1/MASTER_ROADMAP.md`
- Viewer omission/regression checklist: `docs/VIEWER_REBUILD_CHECKLIST.md`
- Existing dashboard-v1 continuity checklist: `docs/workstreams/dashboard-v1/TASKS.md`
- Permanent modular dependency rules: `docs/MODULAR_ARCHITECTURE.md`

The master roadmap merges the already-completed strategy analytics work with the remaining real-holdings history / records / CI / Phase 5~8 / mobile QA work and adds the market-intelligence program: automatic listing/delisting lifecycle, pre-KRW CEX/DEX history, D-5 returns, multi-facet sector/geography, flow/CVD, technical structure, news/macro/human/onchain intelligence, unified score v2, AI interpretation, PAPER v2, walk-forward and candidate promotion.

Do not jump directly from raw new features into the current PAPER strategy. Required promotion path is:

`collect → persist → quality/reaction validation → shadow score → parallel PAPER A/B → walk-forward → candidate`.

## Modular architecture — permanent rule

Dependency direction:

`collector/source → store/repository → feature/domain → score/decision → service/API → page/view`

Do not put reusable calculation, exchange fetch, SQL, scoring formula or long-lived cache into `pages/*`.
Do not put indicator/event/lifecycle formulas into supervisors. Supervisors only orchestrate modules.
If equivalent logic is needed twice, extract the shared owner before continuing.

UI continuity is owned by:
- `cloudflare-pages/public/modules/shared/ui-continuity.js`

No page-specific `scrollTop` copy/paste and no broad DOM `MutationObserver` continuity workaround.

## Current market-intelligence implementation status

Build 38 completed in source/CI:
- shared same-page UI continuity guard is installed at the Viewer app root
- same-route router rerenders preserve scroll/focus state through the shared owner
- `b3_trader/market_lifecycle.py` owns pure lifecycle classification and lifecycle PAPER entry policy
- `b3_trader/market_lifecycle_store.py` owns additive lifecycle SQLite tables/events
- first lifecycle observation is treated as baseline so all existing markets are not mislabeled as new listings
- a market appearing after baseline becomes `NEW_LISTING`
- exchange warning/caution maps to `CAUTION`
- market disappearance requires 3 accepted observations before `TERMINATED`
- a severely incomplete/empty market-list response is rejected before it can increment missing counters
- `b3_trader/market_notice_sources.py` owns Bithumb/Upbit official notice adapters
- `b3_trader/market_notice_timing.py` owns pure structured timing extraction
- `b3_trader/market_notice_store.py` owns notice/event state persistence and additive timing columns
- structured timing fields are `announcement_at`, `deposit_at`, `trade_open_at`, `termination_at`; date-only wording does not invent midnight
- `b3_trader/market_notice_audit.py` provides compact read-only live-source/timing coverage inspection
- `b3_trader/market_lifecycle_service.py` composes market-list state with official notice state and owns the lifecycle entry-policy service boundary
- `market-notice-watch` runs as a separate supervisor sidecar and cannot place orders
- lifecycle state and `notice_only` announced listings are projected through the bounded Cloudflare snapshot
- the sector Viewer renders a modular lifecycle panel for listing-announced/new/caution/termination states and structured schedule times
- lifecycle panel refreshes only its own DOM on snapshot polling; it does not rerender the whole page
- D-5..D-1 completed prior-day return windows reuse `research_market_memory_mx`; no duplicate per-widget exchange calls
- all active KRW markets are already seeded through the existing all-market PAPER account/profile path; newly discovered markets therefore bootstrap their account/profile before scoring and begin market-memory collection on scan
- `TERMINATION_SCHEDULED` and `TERMINATED` now block new/additional PAPER buys while existing positions can still be sold/managed and historical performance remains stored
- CAUTION and NEW_LISTING remain shadow information in the current adaptive strategy; broader lifecycle scoring stays deferred to Unified Score v2/PAPER v2

Validation:
- Build 38 lifecycle/notice/timing/return-window/entry-policy tests PASS
- dedicated Build 38 CI PASS
- full B3 trader CI PASS after preserving legacy trade-plan construction compatibility
- Python compile PASS
- Cloudflare typecheck PASS
- Pages typecheck + JS syntax PASS
- dashboard smoke PASS

Immediate next action:
1. sync/deploy/restart the current Build 38 source on the Windows runtime
2. run the real Bithumb/Upbit official notice collector and `market_notice_audit --rows 4`; one source may be partial, but all-source failure must be investigated
3. verify `market-notice-watch`, Cloudflare snapshot publisher and Viewer lifecycle panel are healthy after restart
4. verify sector scroll continuity and D-5..24H columns on desktop + phone; only then mark the active QA items complete
5. verify an actual newly listed market traverses account/profile research/sector-facet/history owners end-to-end when the next listing occurs
6. start pre-KRW CEX/DEX listing-history collector/store/feature work; identity must be contract/chain/provider-backed rather than ticker-only

## Hard boundary

This workstream remains **PAPER-only**. Use forward-test evidence to find robust candidates before any later live-trading work. Do not add real-money order execution here.

## Runtime / local state

- Windows local PC, FastAPI/Uvicorn on port 8765
- secure launcher binds to `127.0.0.1`
- Cloudflare HTTPS phone access; no phone VPN dependency
- manual holdings/average prices/averaging plans remain in local SQLite
- user-added assets in `control/assets.json` must be preserved
- Telegram automatic delivery remains fresh BUY_CANDIDATE-only
- PR #1 stays Draft and must not be merged without explicit request

## Permanent UI baseline — Photo-eBook is canonical

Before modifying navigation, read the current Photo-eBook sources:
- `docs/spec-v1/06-liquid-navigation.md`
- `UI_REGRESSION_SPEC.md`
- `public/assets/js/ui/liquid-controller.js`
- `public/assets/styles/ui/liquid-skin.css`
- `public/assets/styles/desktop/nav-corrections.css`

Required Liquid contract:
- **one rail = one moving indicator = one nested skin = one controller**
- actual glass material belongs to the rail; shell/wrapper stays visually transparent
- moving indicator is a **direct child of the rail**
- indicator geometry uses active button `offsetLeft`, `offsetTop`, `offsetWidth`, `offsetHeight`
- active button/icon/text remains the real clickable element at a higher z-layer; never clone its content into the indicator and never hide the active button with `opacity:0`
- selected button paints blue only as a first-paint fallback; after controller ready, only the moving indicator paints blue
- approved Breeze easing: `cubic-bezier(0.34, 1.56, 0.64, 1)`
- browser owns native horizontal momentum; no JS `scrollLeft`/`scrollIntoView` loop and no custom pointer/touch pan for the nav rail
- PC top rail is `width:max-content`, centered on the actual chip group; never stretch a grey/glass rail across the viewport
- mobile rail keeps native Safari scrolling and approved safe-area behavior
- do not add a second navigation controller or a second moving indicator

Current implementation files:
- `dashboard/navigation-v3.js`
- `dashboard/navigation-v3.css`
- build marker: `UI 2026.08.24-8`

## Chrome freeze root cause and fix

The experimental `research-capital.js` used a broad `MutationObserver` on `document.body`. A mutation inside `#demoResearch` triggered `renderAggregate()`, which wrote `innerHTML` back inside `#demoResearch`, which could trigger the same observer again. With the full Bithumb universe this could form a high-frequency self-triggering DOM loop and freeze Chrome.

Current rule:
- no broad body MutationObserver for research decoration
- `research-capital.js` uses bounded 15-second data polling plus explicit coin-selection refresh only
- only write aggregate/detail DOM when the rendered value signature changed
- research assets load directly from `dashboard/index.html`; navigation code does not dynamically own research loading

## Browser / Git synchronization ownership

Do **not** reintroduce multiple sync/reload owners.

Current architecture:
- **one Git sync owner:** Python `GitAutoSync`
- `scripts/run-local.ps1` forces `AUTO_GIT_SYNC=true`, `AUTO_GIT_PUSH_CONTROL=true`, 15-second polling
- local `control/assets.json` and `control/runtime.json` are preserved while remote application code updates
- unexpected local code edits still fail closed
- dashboard-only file updates do not require Uvicorn restart
- `b3_trader/*.py` updates trigger supervised exit code 75 and automatic Python restart
- secure Cloudflare launcher no longer starts the experimental external `git-sync-watch.ps1`
- browser no longer force-reloads itself on every Git commit; user refresh is allowed and preferred over reload loops
- `dashboard/runtime-build.json` remains ignored so a stale experimental file cannot dirty/block the worktree

## Adaptive all-market PAPER research

- every valid Bithumb KRW market gets its own independent **10,000,000 KRW virtual account**
- accounts are isolated
- public Bithumb data only; no private/order endpoint
- roughly 3-minute full-market sweep
- `AssetStrategy` remains an input, but bounded `explore` / `idle_explore` entries prevent waiting forever for one legacy threshold
- staged additions, adaptive sizing, spread/slippage/BTC flash guards
- hard stop, dynamic take profit, trailing protection, market weakness and time/opportunity decay exits
- per-market adaptive profile changes are bounded DB parameters; Python source never self-modifies

## Research dashboard

Home:
- coin-by-coin 10M research status
- current return leader
- market count / scan progress / active positions / freshness

Results:
- full Bithumb KRW universe, scrollable and searchable
- filters: all / holding / completed-waiting / untraded / profit / loss
- sorts include return, position value, unrealized P/L, trade count, win rate, drawdown, opportunity and current price

Per-coin detail prioritizes:
- current price
- average entry
- current position value / weight
- realized and unrealized P/L
- next planned entry/add
- expected buy rounds
- dynamic target / stop / trailing protection
- market-memory history for later AI analysis
- fills and bounded learning feedback

Generated data remains local/ignored:
- `b3_trader/data/auto_demo.sqlite3`
- `dashboard/demo-runtime/KRW-XXX.json`

## Current verified viewer/publisher state

- Cloudflare snapshot/detail publisher recovered after D1 retention pressure.
- Snapshot retention is bounded and health exposes snapshot age/count.
- Viewer project-research completion count uses the same definition for numerator and unresolved count.
- Build 38 source/CI including termination-only PAPER gate is complete; local runtime/Pages/live-notice verification is the next operational step.
- Current work must preserve PAPER scanning and publisher health while adding new features.

## Safety constraints

- PAPER-only
- no private Bithumb endpoints
- no live order placement
- manual real holdings remain display/calculator inputs only
- keep secrets/runtime DB/generated research data ignored/local
- no public direct exposure of port 8765
- live execution stays deferred to a separate future workstream
