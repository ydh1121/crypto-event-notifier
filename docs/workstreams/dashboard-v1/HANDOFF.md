# Dashboard v1 handoff

## Current phase

Local multi-asset PAPER monitor + beginner-facing dashboard + secure Cloudflare phone access + adaptive Bithumb-wide per-coin PAPER research + verified Build 38 market lifecycle foundation + Build 39 pre-KRW CEX listing-history foundation + Build 65~71 DEX v2 forward-only validation track + Build 48 senior-default Viewer UX pass.

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

## Build 48 senior-default Viewer UX pass

Primary target user is a Korean crypto buyer/seller in their 60s who is not expected to interpret developer, quant or internal research terminology.

Completed in the current Build 48 pass:
- `cloudflare-pages/public/index.html` enables `data-reader-baseline="senior"` and loads `senior-default.css` last so older density rules cannot shrink the default interface again
- common body/menu/meta copy is raised toward a 13~16px hierarchy; routine controls target at least 44px and key inputs 48px
- existing `content-priority.css` remains authoritative for visual order; it already pushes coin-finder listing research, holdings history and sector research material behind the primary user task flow even when source render order is older
- combined and per-exchange current PAPER results present a normalized 10,000,000 KRW comparison instead of leading with the sum of many independent virtual accounts
- strategy detail uses the same 10,000,000 KRW normalized comparison basis while underlying strategy/PAPER source calculations remain unchanged
- numeric strategy ranking was removed from the default list; `수익률 높은 순` is explicitly described as a sort order rather than a recommendation rank
- experiment IDs were removed from the default strategy list/detail summary; research IDs remain only in deeper evidence/comparison surfaces
- `shared/holding-plan.js` converts the existing PAPER `trade_plan` into ordinary-language holding guidance without creating new trade logic
- the default holdings flow now answers `지금 물타기해도 될까?` first, then shows next review price, remaining/total rounds, stop-adding level, target reference and current PAPER suggested weight
- because actual holding exchange is not yet stored, the Viewer requires an explicit Bithumb/Upbit reference selection before presenting holding-plan prices rather than guessing an exchange
- the user can enter a total additional-buy budget; the first round uses the current real PAPER `next_add_price`, later rows are explicitly labeled estimates based on the current `add_step_pct`, and no row is generated at/below the PAPER hard stop
- the holding plan states stop conditions: no remaining rounds, sell/error state, hard-stop boundary, or weakened conditions on the next strategy recalculation
- profit protection is shown as three price/condition stages using existing PAPER fields only: first protection activation, dynamic target, and trailing high-water protection; no arbitrary 30/30/40 partial-sell ratio is invented
- a persistent global `간편 보기 / 상세 보기` mode is implemented. `간편 보기` is the default and hides specialist research scores, deep charts, secondary calculators and internal evidence while `상세 보기` restores the existing surfaces without deleting data
- Records now defaults to `내 매매·판단` with buy/sell/decision changes only; `시스템·학습` is a separate persisted scope for learning adjustments, errors and safety blocks
- high-frequency holding/Records copy has been moved toward ordinary Korean while technical evidence remains available in detail/internal views

Still open in this UX pass:
- material US macro schedule / major US market index / material news must consume the existing Phase 5 calendar/news data contract; do not create a Viewer-only collector or fake current-event placeholders
- persist actual holding exchange in local holdings data so the reference exchange can be preselected automatically
- staged profit protection deliberately has no partial-sell percentages until a real allocation/execution policy is defined
- complete remaining terminology cleanup where it does not damage technical accuracy
- add consistent non-color state cues (`▲/▼`, 수익/손실, explicit status text)
- desktop and current-phone screenshot/interaction QA remains required

Validation note:
- Build 48 source changes remain Viewer-only and do not alter PAPER order logic, strategy selection logic, DEX forward-validation rules or live-trading boundaries
- commit `8686fb8` completed 28 GitHub Actions with no failure/queued/in-progress result
- the newer simple/detail + Records split head must complete its own Actions before Build 48 code validation is marked closed

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
- Build 69 now also owns a dedicated 15-minute scheduled process. `run-local.ps1` starts, restart-cycles and stops it with the normal server; server-off means zero scheduled network/DB work
- normal launcher sets `DEX_FORWARD_PIPELINE_DEDICATED_MODE=true`, which forces the generic `listing-history-research` and `dex-launch-research` components off without mutating local control state
- the scheduler, generic listing/DEX owners and `market-notice-watch` share a cross-process nonblocking work lock. Lock contention is a network-0/DB-0 deferred no-op, and a separate process lock prevents duplicate schedulers
- each scheduled result is re-audited against the Build 69 one-intake/one-enrichment/one-score/max-one-case, pre-cutoff, Build 47, PAPER/order/Cloudflare/fitting safety envelope
- Build 70 counts event and asset-dedup p1h/p6h/p24h label coverage and keeps statistical validation blocked until every core window has at least 30 event labels and 20 unique-asset labels
- Build 71 is implemented as a read-only preregistered validator and reuses the exact Build 66 score snapshot passed through Build 70
- before Build 70 readiness, Build 71 returns `waiting_for_forward_sample`, `validation_statistics_calculated=false` and `statistics=null`; correlation/spread/late-half functions are not called
- after readiness, Build 71 calculates only the preregistered event/asset-dedup Spearman, top/bottom quartile spread, asset-dedup chronological late-half and strong-negative core checks
- the Build 65 primary level is `asset_dedup`; Build 72 is allowed only when every frozen criterion passes
- Build 71 remains PAPER/shadow/read-only. It does not fit weights, select a trade threshold, mutate the DB, publish Cloudflare data, change strategy/position sizing, wire PAPER A/B or place orders
- Windows HEAD `4f65082`에서 Build 71 contract/runtime PASS. Build 70은 0 event/0 unique asset, Build 71은 `waiting_for_forward_sample`, `validation_statistics_calculated=false`, `statistics=null`로 확인됨

Validation:
- Build 38 dedicated CI PASS
- Build 38 Windows runtime/PAPER self-heal/live official notice/Cloudflare publisher verification PASS
- Build 39 listing-history tests PASS
- Build 39 modular contract PASS
- Build 39 Cloudflare Pages typecheck PASS
- full B3 trader push and PR CI PASS with Build 39 source/supervisor changes
- Build 71 local full Python suite 255 tests, compileall, Build 65~71 contract chain and workflow YAML validation PASS
- Build 71 code commit `5c8081d` dedicated forward-validation CI PASS
- Build 71 code commit `5c8081d` full B3 trader CI PASS
- Build 71 Windows runtime at HEAD `4f65082`: contract PASS, Build 70 ledger PASS, Build 71 runtime PASS with no early statistics
- Build 69 scheduler local full Python suite 266 tests, server-off verifier, scheduler contract, Build 39/43 supervisor regression and Build 65~71 contract chain PASS
- Build 69 scheduler Windows runtime remains explicitly pending because the server is off; no process or network call was started for source validation
- Build 48 baseline through `8686fb8`: 28 GitHub Actions completed with no failure/queued/in-progress result
- Build 48 simple/detail + Records split latest-head CI/visual validation remains pending
- PR #1 remains Draft/unmerged

Immediate next action:
1. finish GitHub Actions for the latest Build 48 head, then perform desktop + phone screenshot QA of senior typography, holding plan, simple/detail toggle and Records split
2. add consistent non-color state cues after visual QA identifies the high-frequency surfaces that still rely on red/green alone
3. persist actual holding exchange in local holdings data; until then keep explicit user reference-exchange selection fail-safe
4. connect US macro/index/news context only through the existing Phase 5 data contract
5. leave the normal server on to let the 15-minute Build 69 process accumulate new official KRW listing samples automatically; manual Build 67 → 68 → 66 invocations are no longer the normal path
6. while Build 70 remains below 30 event/20 unique asset labels per core window, require Build 71 to stay `waiting_for_forward_sample` with no validation statistics
7. only a real Build 71 forward PASS may open Build 72 implementation; a FAIL means retire v2 or preregister a new hypothesis with a new forward cutoff, not tune v2 on the consumed validation sample

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
- Build 69/70 Windows runtime is verified at 0 forward cases, and Build 71 source/CI/Windows runtime validation is complete; actual forward sample readiness is the current DEX v2 operational gate.
- Build 69 scheduled process is source-validated but its always-on Windows heartbeat is pending the next server start. Until then, the server-off verifier correctly reports `server_offline_runtime_pending` with network/DB 0.
- Current work must preserve PAPER scanning and publisher health while adding new features.

## Safety constraints

- PAPER-only
- no private Bithumb endpoints
- no live order placement
- manual real holdings remain display/calculator inputs only
- keep secrets/runtime DB/generated research data ignored/local
- no public direct exposure of port 8765
- live execution stays deferred to a separate future workstream


## Single-chat UI system audit checkpoint — CRYPTO-WO-20260921-001

Status: AUDIT COMPLETE / IMPLEMENTATION NOT STARTED.

Actual local recovery baseline supplied from the Windows checkout before documentation updates:
- branch: `b3-auto-trader-phase1`
- HEAD: `e9318be6c47877013e408d10479ea7f3e83f6506`
- tracked diff: clean
- staged diff: clean
- untracked: none
- upstream: `origin/b3-auto-trader-phase1`
- ahead/behind: `0 / 0`

The same code HEAD had already been deployed to Production Pages and the user confirmed the V17 asset changes appeared applied. GitHub CI readback for `e9318be6...` shows `B3 trader tests` and the returned Build 51~71 workflow set completed successfully. PR #1 remains Draft/open.

### UI system audit result

The primary problem is not missing features. It is propagation debt and competing information architecture:
- active shell exposes 6 top-level buttons plus system/account behind the user menu, while the permanent/product docs use several different conceptual groupings;
- Research, Assets, PAPER, Strategy, Sectors and Records each evolved their own search/filter/tab/master-detail grammar;
- `index.html` currently loads 37 CSS stylesheets. The loaded set totals about 260,399 CSS characters, 2,124 rule blocks, 100 media blocks and 1,874 `!important` declarations;
- late override ownership is concentrated in `strategy-native-v5.css`, `interaction-layout-v4.css`, `mainstream-v4.css`, `layout-fixes-v4.css`, plus subsequent viewport/compact/V17 layers;
- broad observer debt remains in `shared/rail-controls-v16.js`, which installs a document-root subtree `MutationObserver` contrary to AGENTS/MODULAR_ARCHITECTURE;
- the global simple/detail mechanism is directionally correct but is mainly CSS visibility gating, not yet a semantic per-page Primary/Supporting/Advanced composition contract.

Stable exemplar candidates to preserve:
- Strategy V5 master rail + selected-strategy workspace + internal views;
- Records audience split: `내 매매·판단` vs `시스템·학습`;
- Research master/detail with local live patches;
- Assets V17 position hero → facts → holdings editor handoff;
- `shared/ui-continuity.js` and scoped V16 live-patch ownership;
- `shared/viewport-handoff-v4.js` explicit mobile return-to-list behavior.

Target IA for the next design-system waves, with no capability deletion:
- global: `홈 / 코인 / 내 자산 / 모의투자 / 기록 / 더보기`;
- Coin local navigation: `코인 / 시장현황 / 테마`;
- Paper local navigation: overall performance / per-coin / method-strategy comparison / current execution;
- More: system / account / operations.

Target disclosure order on primary operational pages:
`지금 무엇을 해야 하는가 → 현재 가격·보유·손익 → 왜 그런 판단인가 → 다음 행동 → 고급 분석·근거`.

### External read-only skill evidence used in the audit

- `hueyexe/frontend-agent-skills@2841c079dd8a9c634882227194dc42e25227710d`, MIT: IA/navigation, usability, design-system architecture, interaction patterns, visual hierarchy, accessibility. Adopted task-first IA, labels-as-promises, progressive disclosure, low-specificity token/component ownership, stable wayfinding, semantic/native accessibility. Overridden where project-native DESIGN/TASTES require denser financial presentation and localStorage-based private Viewer state instead of URL-shareable state.
- `educlopez/ui-craft@ceecc8e1fb0c2befda73da996435900d6dd0c1ac`, MIT: audit/system extraction and dense-dashboard anti-slop. Adopted tabular numerals, operator-density, no decorative chart/card grid. Did not adopt its generic style as a theme.
- `emilkowalski/skills@85e8e2363b713506e1d5b6e07a0eb2da66be1bc3`, MIT: mobile-native checks. Adopted 16px focused input minimum, safe-area, capability media queries, touch feedback, real-device QA. Design-engineering polish is deferred until structure stabilizes.
- `microsoft/skills@14655200e871a89c013803b3aa4d88202cb03fc1`, MIT: used only as final review rubric for frictionless action, craft, accessibility and trustworthy errors. Creative-font/gradient/background guidance is rejected where it conflicts with CRYPTO DESIGN/TASTES/system-font/no-decoration rules.

### Exact next gate

Do not begin a broad rewrite. Review/approve the audit, then create/activate `CRYPTO-WO-20260921-002` with a bounded foundation scope:
1. remove the broad `rail-controls-v16.js` MutationObserver and move enhancements to explicit render/ui:refresh ownership;
2. establish one canonical token/control/master-detail foundation and regression contract;
3. migrate only the shared shell/high-frequency primitives first;
4. no trading/data/PAPER semantic change, no feature deletion, no Production deploy until visual/regression QA passes.

Because this HANDOFF/TASKS update is a documentation-only Git mutation performed through GitHub after the local readback, the user's local checkout will need a fast-forward before the next implementation work begins.


## CRYPTO-WO-20260921-002 UI foundation consolidation — VERIFY

Current implementation HEAD: `3e15a8d8a1959a99f7a2a8c5ff7196d83571c7a9`.

Implementation/verification result:
- broad document-root rail `MutationObserver` removed;
- rail controls use explicit root-scoped render/`ui:refresh` lifecycle;
- canonical UI geometry tokens live in `tokens.css`;
- shell/components/interaction layer consume the canonical tokens;
- additive shared composition primitives and `UI_FOUNDATION_CONTRACT.md` added;
- V18 regression checker is part of `npm run typecheck`;
- no trading/data/PAPER/SQLite/real-money semantic change;
- no Production deployment.

Actual local readback at `3e15a8d...`:
- branch `b3-auto-trader-phase1`;
- tracked/staged/untracked = 0/0/0;
- upstream aligned = 0/0;
- full `npm run typecheck` PASS through `V16_HOLDINGS_WRITE=PASS` and `[PASS] CRYPTO WO-002 LOCAL FOUNDATION VERIFY`.

Latest GitHub CI at the same HEAD:
- B3 trader tests run 2750 = SUCCESS;
- python-test = SUCCESS;
- cloudflare-typecheck = SUCCESS;
- cloudflare-pages-viewer = SUCCESS, including Viewer baseline source contract;
- dashboard-smoke = SUCCESS;
- returned Build 51~71 workflow set = SUCCESS.

Next gate is visual QA only. Use a non-Production preview deployment of this exact HEAD, then verify representative desktop/tablet/phone widths, light/dark, keyboard/focus, simple/detail reader mode, selection/search/sort continuity, and live-polling continuity. Do not deploy Production until this gate is accepted.


### WO-002 preview deployment checkpoint

Preview source: `7e19da175c34fc4e6b172581ebf2831bd5426a67` (implementation `3e15a8d...` plus docs-only durable commits).

Preview URLs:
- deployment: `https://1072960d.crypto-paper-viewer-ydh1121-cf36.pages.dev`
- alias: `https://qa-v18-ui-foundation.crypto-paper-viewer-ydh1121-cf36.pages.dev`

Production was not deployed. Visual QA must use this preview only and must avoid holdings/runtime write actions. Start with 1440px dark on Home / Coin / Assets / Paper / Strategy / Records, then 390px dark on Coin / Assets / Paper, followed by light mode, keyboard/focus, simple/detail, selection/search/sort, and live-polling continuity.


### WO-002 partial desktop visual-QA handoff — 2026-09-21

User stopped screenshot submission after the current desktop sweep; implementation/QA work continues. Treat the supplied screenshots as a durable partial-QA checkpoint, not acceptance.

Observed preserve candidates:
- Assets V17 hierarchy remains the clearest operational page.
- Strategy master/detail selection rail and internal tabs remain intact.
- Records keeps the useful user-vs-system audience split.
- Research/market selection rails and scoped detail surfaces remain functional in the screenshots.

Observed repair candidates for later bounded waves:
1. Market overview/dashboard still has card-soup pressure and competing visual prominence.
2. Theme/Sectors has excessive simultaneous density (ranking rail + coin table + evidence panel) and small scanning text.
3. PAPER/Strategy tabs show large empty detail areas when content is sparse, causing inconsistent vertical rhythm.
4. Sticky global/local header stack needs explicit scroll/focus visibility QA; long-page screenshots show content tight to the sticky boundary.
5. System is operationally useful but visually flat: many equal-weight sections/status rows with weak prioritization.

Continue bounded WO-002 QA/foundation repair from these findings. Production remains prohibited; page-level redesign beyond WO-002 foundation scope belongs to a later bounded work order.


### WO-002 bounded desktop foundation repair

Work continues after the desktop screenshot sweep. Two foundation-level issues were repaired without changing page semantics:

1. Sticky-shell focus/anchor visibility: `viewport-first-v9.css` now sets document `scroll-padding-top` from the responsive `--shell-header-offset`, with regression coverage.
2. System desktop hierarchy: retired the old `mainstream-v4.css` one-column override so `records-system.css` again owns the intended 3/2/1 responsive operations grid and 2/1 system summary grid.

These are override/foundation repairs, not the later page-level hierarchy redesign for Market/Theme/PAPER/Strategy. Latest regression verification and Preview re-deploy are still required. Production remains unchanged.


## CRYPTO-WO-20260921-003 Market + Theme page hierarchy — IMPLEMENTED / VERIFY

The V18 foundation wave is no longer being expanded. WO-003 uses the user's supplied desktop screenshots as the page-level evidence source and touches only Market dashboard + Theme/Sectors hierarchy.

Implemented:
- Market dashboard now has deliberate prominence: market state is primary; actual-assets/PAPER are supporting; watch list is primary intelligence; sector/strategy are supporting.
- Theme/Sectors no longer presents rank + coin table + project profile as three simultaneous desktop rails. Rank + selected-theme detail remain primary, while project evidence moves below the table behind native progressive disclosure and automatically opens on explicit coin selection.
- No new cards/tabs/chips were added. Data selectors, market/sector data, PAPER/trading logic, SQLite semantics and real-money boundary are unchanged.
- A dedicated V19 regression contract protects cache lineage, dashboard prominence, two-pane Theme ownership, and project-evidence accessibility.

Source implementation lineage through `ff9253e2c174a8cc5c2f6d77618568c7c5185a89`; documentation commits follow on the same branch. Next gate is exact latest-head CI, then actual local fast-forward/typecheck, then Preview-only redeploy. Production remains prohibited.


### WO-003 exact-head remote CI gate

Remote HEAD `deb3c30385cdcf86604a62a9357c490a6071b522` is unchanged and exact-head CI is green:
- B3 trader tests #2800 = SUCCESS
- dashboard-smoke = SUCCESS
- cloudflare-typecheck = SUCCESS
- python-test = SUCCESS
- cloudflare-pages-viewer = SUCCESS
- returned Build 51~71 workflow set = SUCCESS

Next gate is actual local fast-forward to this exact HEAD, clean/aligned readback, full `npm run typecheck`, then Preview-only redeploy/readback on `qa-v18-ui-foundation`. Production remains prohibited.
