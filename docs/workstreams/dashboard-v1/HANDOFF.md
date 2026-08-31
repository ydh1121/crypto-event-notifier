# Dashboard v1 handoff

## Current phase

Local multi-asset PAPER monitor + beginner-facing dashboard + secure Cloudflare phone access + adaptive Bithumb-wide per-coin PAPER research + verified Build 38 market lifecycle foundation + Build 39 pre-KRW CEX listing-history foundation + Build 65~71 DEX v2 forward-only validation track.

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

Build 38 completed and live-verified:
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
- `TERMINATION_SCHEDULED` and `TERMINATED` block new/additional PAPER buys while existing positions can still be sold/managed and historical performance remains stored
- CAUTION and NEW_LISTING remain shadow information in the current adaptive strategy; broader lifecycle scoring stays deferred to Unified Score v2/PAPER v2
- normal launcher owns Bithumb PAPER through `paper_runtime_supervisor`; stale/dead/reused PID cannot suppress recovery
- Cloudflare D1 writes are bounded at snapshot 60s / detail 300s with capped detail batches and unchanged-row skipping
- Windows live verification confirmed notice/snapshot/detail components healthy, PAPER `running/fresh`, valid asset registry and current Viewer snapshot

Build 39 pre-KRW CEX foundation completed in source/CI, live data QA pending:
- `listing_identity.py` owns the fail-closed identity gate; ticker-only matching is forbidden
- `/api/coin-profile-identity` reuses verified/corroborated `coin_profile_cache` identity via INGEST bearer authentication rather than duplicating project research
- existing CoinGecko evidence is surfaced as a stable `coingecko_id`; multi-source/CMC provider ids are not assumed to be CoinGecko ids
- `listing_venue_verifier.py` requires exact CoinGecko coin-id + venue identifier + base/target pair before foreign candles are accepted
- initial public CEX adapters are Binance, OKX and Bybit; each normalizes to the shared `ListingCandle` domain
- `listing_history_planner.py` seeds only official KRW listing notices and rejects Upbit USDT-only notices as KRW cases
- listing case keys use stable domestic notice id when available; changed trade-open schedules update the same case
- `domestic_listing_price.py` resolves the domestic listing start price from public 1-minute candles around `trade_open_at`, not from current ticker price
- additive local SQLite owns `listing_history_cases`, `listing_history_sources`, `listing_history_candles`, `listing_history_features`
- prelisting windows are T-7d/T-5d/T-3d/T-1d/T-6h/T-1h; postlisting tracking is +5m/+1h/+6h/+24h/+3d/+7d
- unknown foreign launch time/first price stays null; the first candle of the bounded T-8d research window is never treated as a historical CEX launch price
- when a venue exposes a launch timestamp, first price is resolved only from a narrow launch-time candle window; Binance may use its explicit first historical kline path
- `tracking_postlisting` remains active until 7-day reaction data can mature
- `listing-history-research` is an independent 15-minute supervisor component, processes at most 3 cases per run, and has no PAPER score/order authority
- `listing_history_audit.py` provides read-only case/status/identity/source/candle/feature audit output
- `scripts/check-listing-build39.py` and dedicated `B3 listing Build 39` workflow enforce the modular/ticker-safety/PAPER-unwired contract
- `scripts/verify-build39-runtime.ps1` performs contract → Pages deploy → one bounded live cycle → audit; `-StatusOnly` checks the supervisor component and accumulated DB state

Build 65~71 DEX v2 forward validation track:
- Build 65 retired the failed retrospective v1 hypothesis and froze v2 components, 0.60/0.40 weights, directions, `2026-08-31T00:00:00Z` cutoff and forward validation criteria before scoring
- Build 66 scores only usable post-cutoff cases and never back-scores pre-cutoff cases as v2
- Build 67 ingests current official Bithumb/Upbit KRW listing notices; Build 68 enriches at most one post-cutoff case per run
- Build 69 composes one Build 67 intake, one bounded Build 68 enrichment and one Build 66 audit; it does not reactivate generic historical supervisors or Build 47 cursors
- Build 70 counts event and asset-dedup p1h/p6h/p24h label coverage and keeps statistical validation blocked until every core window has at least 30 event labels and 20 unique-asset labels
- Build 71 is implemented as a read-only preregistered validator and reuses the exact Build 66 score snapshot passed through Build 70
- before Build 70 readiness, Build 71 returns `waiting_for_forward_sample`, `validation_statistics_calculated=false` and `statistics=null`; correlation/spread/late-half functions are not called
- after readiness, Build 71 calculates only the preregistered event/asset-dedup Spearman, top/bottom quartile spread, asset-dedup chronological late-half and strong-negative core checks
- the Build 65 primary level is `asset_dedup`; Build 72 is allowed only when every frozen criterion passes
- Build 71 remains PAPER/shadow/read-only. It does not fit weights, select a trade threshold, mutate the DB, publish Cloudflare data, change strategy/position sizing, wire PAPER A/B or place orders
- the latest Windows Build 69/70 runtime found 0 new notices, 0 forward cases and 0 labels; waiting is the correct current state

Validation:
- Build 38 dedicated CI PASS
- Build 38 Windows runtime/PAPER self-heal/live official notice/Cloudflare publisher verification PASS
- Build 39 listing-history tests PASS
- Build 39 modular contract PASS
- Build 39 Cloudflare Pages typecheck PASS
- full B3 trader push and PR CI PASS with Build 39 source/supervisor changes
- PR #1 remains Draft/unmerged

Immediate next action:
1. sync the final Build 71 HEAD on the Windows runtime and run the Build 71 contract plus runtime verifier once
2. while Build 70 remains below 30 event/20 unique asset labels per core window, require Build 71 to stay `waiting_for_forward_sample` with no validation statistics
3. when a new official KRW listing appears, run the bounded Build 69 pipeline once; Build 67 → Build 68 → Build 66 must remain one intake/maximum one enrichment/one score audit per invocation
4. rerun Build 70 and Build 71 after labels mature; do not inspect or fit forward statistics before the frozen readiness gate opens
5. only a real Build 71 forward PASS may open Build 72 implementation. A FAIL means retire v2 or preregister a new hypothesis with a new forward cutoff, not tune v2 on the consumed validation sample
6. preserve the still-open Build 39 live CEX data QA, Viewer visual QA and actual-new-listing end-to-end profile/facet QA as parallel operational debt

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

- Cloudflare snapshot/detail publishers are healthy after D1 retention/write-budget fixes.
- Snapshot retention is bounded and health exposes snapshot age/count.
- Current cadence is snapshot 60 seconds and market detail 300 seconds; unchanged detail rows are skipped and bounded batches protect D1 write budget.
- Viewer project-research completion count uses the same definition for numerator and unresolved count.
- Build 38 lifecycle/notice/timing/termination PAPER gate and PAPER self-heal are live-verified.
- Build 39 CEX listing-history foundation is source/CI complete; Windows live CEX data audit remains open.
- Build 69/70 Windows runtime is verified at 0 forward cases, and Build 71 source/local validation is complete; actual forward sample readiness is the current DEX v2 operational gate.
- Current work must preserve PAPER scanning and publisher health while adding new features.

## Safety constraints

- PAPER-only
- no private Bithumb endpoints
- no live order placement
- manual real holdings remain display/calculator inputs only
- keep secrets/runtime DB/generated research data ignored/local
- no public direct exposure of port 8765
- live execution stays deferred to a separate future workstream
