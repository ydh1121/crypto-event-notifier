# Research Platform v1 tasks

Status legend: `[ ]` pending · `[-]` active · `[x]` complete · `[>]` deferred

## Phase 0 — current dashboard/PAPER stabilization gate

- [-] User acceptance of Photo-eBook top navigation on PC + iPhone
- [-] Verify Chrome remains responsive during full-market PAPER research; MutationObserver feedback-loop guards added, current Pages/browser verification pending
- [-] Verify GitHub -> local sync remains reliable during long-run operation
- [x] Preserve local SQLite/control state across restart
- [x] Keep live exchange execution out of this workstream

Phase 0 remains the release gate for calling the current dashboard stable, but it no longer blocks low-risk sidecar/viewer work. PAPER execution semantics remain unchanged.

## Phase 1 — 24시간 local data foundation

### 1A. Analytical warehouse

- [x] Add DuckDB runtime dependency
- [x] Add incremental SQLite -> Parquet exporter
- [x] Export append-heavy `research_market_memory`
- [x] Export PAPER fills
- [x] Export learning feedback
- [x] Export equity history
- [x] Partition Parquet by table + UTC date
- [x] Persist export checkpoints locally so restart does not duplicate old rows
- [x] Keep SQLite authoritative; Parquet remains secondary analytical history
- [ ] Add retention/compaction policy after real volume is measured
- [x] Add scoped multi-exchange/Upbit history partitions for Phase 3
- [ ] Add news/community/on-chain/macro partitions in Phase 5

Local root:

`b3_trader/data/research-warehouse/`

This path remains ignored by Git.

### 1B. 24/7 research component supervisor

- [x] Add separate non-trading research supervisor process
- [x] Start/stop supervisor with the normal Windows launcher
- [x] Keep supervisor alive across normal trader operation
- [x] Restart supervisor when Git/Python update requests exit code 75
- [x] Component failures are isolated and retried instead of stopping the trader
- [x] Persist component health/status locally
- [x] Persist bounded local supervisor log
- [x] Add dashboard component-health UI
- [x] Add safe per-component on/off controls
- [x] Add immediate per-component `지금 실행` control without restarting the trader
- [x] Apply control-file changes live in the research supervisor
- [x] Restrict component mutations to loopback/local PC; remote clients are read-only

Current managed components:

- `warehouse-export` — every 5 minutes
- `reference-version-watch` — every 6 hours
- `cloudflare-snapshot-publish` — every 20 seconds after Pages setup
- `cloudflare-market-detail-publish` — every 30 seconds after Pages setup
- `upbit-paper-research` — Phase 3 Upbit KRW PAPER; currently enabled at 180-second post-scan interval
- `strategy-lab-shadow` — Phase 4 six-style shadow PAPER comparison using existing market-memory rows
- `cloudflare-pages-deploy` — checks every 30 seconds after Pages setup; deploys only on viewer-code changes

Safety contract:

- cannot place orders
- cannot change active PAPER strategy profiles
- Strategy Lab uses dedicated shadow-PAPER tables and cannot mutate active adaptive accounts
- cannot auto-promote external code
- Pages viewer and Pages deployment remain read-only with respect to trading

### 1C. External repository registry/version watch

- [x] Add committed reference catalog at `control/reference-components.json`
- [x] Record purpose/category/restart requirement/update policy
- [x] Mark license review as pending instead of guessing
- [x] Observe default-branch commit versions from GitHub
- [x] Persist latest-seen SHA/status locally
- [x] No cloning/execution/update promotion from watcher
- [x] Optional local `REFERENCE_GITHUB_TOKEN` support only for API-rate headroom; not required
- [x] Show external-repo watch count/update/failure summary in the research component UI
- [ ] Review licenses before adopting code from any reference
- [ ] Add staged install directory and compatibility-test runner
- [ ] Add PAPER smoke test before promotion
- [ ] Add rollback version management
- [ ] Add manual promote action only after the staging/test/rollback chain exists

Initial catalog:

- Freqtrade
- Hummingbot
- NautilusTrader
- CCXT
- PyUpbit
- vectorbt
- Microsoft Qlib
- FinRL
- FinGPT
- Ollama
- llama.cpp
- OpenBB
- DefiLlama Adapters
- DuckDB
- Qdrant

## Phase 1 validation gate

- [x] CI: Python tests + compile, dashboard smoke and Cloudflare typecheck passed for the initial Phase 1 foundation
- [x] CI: component-control API/supervisor/dashboard slice passed Python tests + compile, dashboard smoke and Cloudflare typecheck
- [ ] Long-run observation remains useful for retention sizing, but no longer blocks later phases
- [ ] Measure storage growth/day before choosing retention and compaction

## Phase 2 — Cloudflare Pages viewer + invite users

### 2A. Viewer application

- [x] Separate `cloudflare-pages/` Pages/Functions viewer from the old Container experiment
- [x] Read-only mobile/desktop viewer UI
- [x] D1 schema for users, invites, sessions, snapshots and audit log
- [x] First-owner bootstrap flow
- [x] Owner/viewer login with secure session cookie
- [x] Owner-created invite links
- [x] Per-viewer `내 자산정보도 보이기` permission
- [x] Authenticated `/api/ingest` machine-to-cloud snapshot route
- [x] Authenticated latest snapshot API
- [x] Keep all remote trading/control endpoints out of the Pages viewer

### 2B. 24/7 PC bridge

- [x] Outbound local PAPER snapshot publisher
- [x] Compact authenticated manual-holdings snapshot; raw SQLite never uploads
- [x] Reload local `.env` at publish time so setup does not require trader restart
- [x] Local Pages deployer checks Git changes and deploys viewer-only code
- [x] Local deployer runs typecheck + D1 migrations + Pages health check before recording success
- [x] Add `cloudflare-pages-deploy` to Research Supervisor
- [x] Add one-command Windows setup script using Wrangler browser OAuth
- [x] Generate/store ingest + first-owner secrets without printing them
- [x] Enable snapshot publish + Pages deploy automatically after successful one-time setup
- [x] Harden Windows Wrangler invocation and UTF-8 subprocess handling
- [x] Fix Pages deploy config path handling
- [x] Prevent Pages npm install from dirtying the Git worktree with generated `package-lock.json`
- [x] Verify Git auto-sync can receive the fix and Pages auto-deploy remains healthy
- [x] Add bounded retry/backoff for transient Cloudflare 429/5xx/timeouts

### 2C. Deployment path

- [x] GitHub Actions viewer validation
- [x] Optional direct GitHub -> Pages deploy workflow when Cloudflare GitHub secrets exist
- [x] Missing GitHub Cloudflare secrets no longer block viewer validation; local Wrangler bridge is the default
- [x] One-time account-side provisioning on the user's Windows PC
- [x] Stable URL confirmed: `https://crypto-paper-viewer-ydh1121-cf36.pages.dev`
- [x] `/api/health` confirmed `ok: true`
- [x] First owner account created and logged in
- [x] 20-second PAPER snapshots confirmed in the browser
- [x] Owner manual holdings confirmed in the Pages viewer
- [ ] Confirm a viewer without holdings permission cannot see private holdings
- [x] Google Drive remains backup/export only

## Phase 2.5 — Pages/local dashboard information parity

Goal: keep the Windows PC and SQLite as the source of truth while making Pages the normal external/mobile read-only surface.

### 2.5A. Navigation and first read-only workspace slice

- [x] Add top-level `홈 / 코인 / 결과 / 기록 / 설정` navigation to Pages
- [x] Keep one authenticated session across all viewer workspaces
- [x] Add Home summary with PAPER capital, holdings, leader and research-node state
- [x] Add Coin workspace using current compact leaderboard scores/state
- [x] Add Results workspace with existing all-market search/filter/sort
- [x] Add first Records summary from current snapshot
- [x] Add read-only Settings/account/research-node workspace
- [x] Keep owner invite management in Settings
- [x] Preserve read-only remote contract; no pause/resume/strategy mutation endpoints

### 2.5B. Detailed research data bridge

- [x] Design compact per-market detail payload separate from the global snapshot
- [x] Publish current position, planned next entry/add, target/stop/trailing state
- [x] Publish recent PAPER fills per market
- [x] Publish completed-trade feedback and profile-learning history
- [x] Publish bounded equity history for charts
- [x] Publish bounded market-memory/score history for charts and diagnostics
- [x] Add D1/API storage that avoids resending every market's full history every 20 seconds
- [x] Add authenticated per-market detail endpoint
- [x] Add rotating detail publisher keyed by `exchange + market + strategy`
- [x] Add size-aware multi-request batching so growing history does not break the publisher
- [x] Runtime verify 40 markets stored successfully in two requests with max request < 1.5 MB

### 2.5C. Local-equivalent read-only UI

- [x] Verify real authenticated browser rendering of detailed Coin/Results data on desktop and iPhone
- [x] Complete page-by-page audit against the current local dashboard final CSS/JS cascade
- [x] Consolidate Home / Results / Settings into one final `viewer-shell-v3` owner
- [x] Keep `asset-local-port` as the canonical local-derived Coin workspace owner
- [x] Keep `records-port` as the cross-market activity owner
- [x] Add local-derived Liquid navigation and coin chip rail without remote control APIs
- [x] Add bounded equity chart to Coin detail
- [x] Add market-condition / buy-timing / opportunity history chart
- [x] Add recent fill/history list
- [x] Add learning/profile-change history
- [x] Add next planned buy/add and protection levels
- [x] Add browser-only manual holding / averaging calculator without PC or SQLite writes
- [x] Expand Home manual holdings into a dashboard with invested/value/P&L, best/worst holding and allocation view
- [x] Add Home opportunity quick cards using actual research scores
- [x] Add full read-only `데이터 수집 · 연구 구성요소` status view in Settings
- [x] Add compact recent cross-market fills/learning payload to the global snapshot
- [x] Expand Records into a cross-market fill/learning timeline
- [x] Rework desktop Results leaderboard into a wider compact row layout without the clipped dedicated holding column
- [x] Add mobile Results master/detail mode so 477 rows and selected detail are not vertically stacked
- [x] Move Coin charts ahead of manual tools on mobile and make tools single-column/touch-friendly
- [x] Normalize raw trade-intent labels and unavailable plan values without inventing prices
- [x] Persist result filter/sort/search/selected coin/list scroll in browser storage across polling
- [-] Refine plain-Korean decision/reason hierarchy aligned with `DESIGN.md`
- [-] Mobile Safari QA at 360–430 px — v3 page-wide mobile pass implemented; final real-device re-check remains useful
- [-] Desktop QA at 1280–1920 px — MutationObserver feedback-loop fix added; final Chrome re-check pending
- [-] Verify 477-market rendering remains responsive — `content-visibility` + mobile master/detail + observer-loop guards implemented; final Chrome observation pending
- [x] Runtime verify the global `recent_records` bridge after publisher restart

## Phase 3 — Upbit all-market PAPER

- [x] Implement common read-only public exchange adapter interface for Bithumb + Upbit
- [x] Add Upbit public quotation client using official market/ticker/orderbook/candle endpoints
- [x] Runtime verify complete public KRW universes: Bithumb 477/477 and Upbit 286/286
- [x] Introduce durable scoped identity `exchange + market + strategy` without destroying current legacy Bithumb history
- [x] Create isolated 10M PAPER account per scoped Upbit `exchange + market + strategy`
- [x] Add Upbit scan/scoring/PAPER loop using the common adapter
- [x] Runtime verify one full Upbit 286-market PAPER pass with Supervisor healthy and no engine error
- [x] Export scoped multi-exchange fills/feedback/equity/market-memory to the analytical warehouse
- [x] Add exchange dimension and Bithumb/Upbit payloads to the global viewer snapshot contract
- [x] Add Bithumb + Upbit per-market detail rotation using the existing D1 `exchange + market + strategy` key
- [x] Runtime verify latest multi-exchange snapshot/detail publisher contract after Windows auto-sync
- [-] Add `빗썸 / 업비트 / 거래소 비교` viewer selector and shared-market comparison workspace; implementation deployed, final Chrome/browser acceptance pending
- [-] Verify mobile exchange comparison UX without horizontal-table dependence
- [x] Promote Bithumb onto the scoped multi-exchange engine after legacy state migration/regression checks
- [x] Runtime verify Bithumb scoped cutover: 477/477, legacy frozen, Cloudflare scoped records live

## Phase 4 — strategy laboratory

Architecture: Strategy Lab reuses the same `research_market_memory_mx` rows already collected by Phase 3. It does not multiply exchange API calls. Lab tables are isolated from the active adaptive PAPER accounts.

- [-] 보수적 — implementation complete, Windows shadow-PAPER runtime verification pending
- [-] 균형 — implementation complete, Windows shadow-PAPER runtime verification pending
- [-] 공격적 — implementation complete, Windows shadow-PAPER runtime verification pending
- [-] 분할매수 — implementation complete, Windows shadow-PAPER runtime verification pending
- [-] 역추세 — implementation complete, Windows shadow-PAPER runtime verification pending
- [-] 스윙 — implementation complete, Windows shadow-PAPER runtime verification pending
- [-] isolated metrics/learning state per style — dedicated accounts/trades/learning/metrics tables implemented; live verification pending
- [-] read-only Strategy Lab summary in Pages — six-card Bithumb/Upbit comparison implemented; deploy/browser verification pending
- [x] include fee + slippage assumptions in shadow execution model
- [x] keep Strategy Lab unable to mutate the active adaptive PAPER account tables
- [ ] multi-style experiment launcher for user-created combinations
- [ ] per-market Strategy Lab drilldown / experiment history UI
- [ ] minimum-sample and stability gates before any strategy is considered a candidate

## Phase 5+ — context AI and promotion research

- [ ] on-chain feature collectors
- [ ] Korean/global community language features
- [ ] global news event objects
- [ ] FOMC/CPI/jobs/macro event-risk layer
- [ ] local AI inference service
- [ ] walk-forward/holdout strategy-improvement validation
- [ ] candidate promotion score using return + drawdown + sample size + stability + execution quality

Real-money execution stays deferred to a separate future workstream.
