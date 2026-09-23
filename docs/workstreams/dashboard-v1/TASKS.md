# Dashboard v1 workstream tasks

## Successor CURRENT — CRYPTO-WO-20260921-RECOVERY-001

**Status: IMPLEMENTED_REVIEW_PENDING. V22 / WO-008 remains rejected.**
This block supersedes older visual-acceptance and BLOCKED_LOCAL_EVIDENCE checkpoints below.

### Authority and actual evidence

- Actual Windows evidence: user-supplied `CRYPTO_LOCAL_CURRENT_20260921T233738Z(1).json`, observed 2026-09-21 23:37:38–23:41:55 UTC. Clean local `b3-auto-trader-phase1@ba3c59a50962ae1a5bdc41053a75f9e6bf9e1ec7`; execution-source hashes align with remote `56b9361f352eedce2e543b3baca36952b2397d76` (later documentation changes).
- Canonical `b3_trader/data/auto_demo.sqlite3`: 3,081,179,136 bytes; WAL present. Latest relevant activity around 06:23 UTC, about 17 hours old at observation. T0/T1 did not grow; relevant process discovery returned no items. Historical healthy badges are not current liveness proof. Cause and present runtime still need actual-PC investigation.
- Actual counts: PAPER accounts 775 / fills 23,134; Strategy Lab accounts 4,650 / trades 7,007; market memory 347,777; OHLCV 1,639,206; trade flow 2,863,417; intelligence events 70 / responses 10. Responses cover one event and BTC/ETH only, with no 1d or altcoin samples.
- Bithumb/B3/aggressive: 5 fills, 2 closed trades, 1 win. Full diagnostic replay matches cash 9,003,349.466550918, quantity 1,242,359.8884979396, average 0.7942143087, realized -9,950.53344908182; no replay differences. Global aggressive 1,039 closed trades is a separate scope. Stored maximum drawdown is not reproducible from fills alone.
- `manual_holdings` is absent in this DB; source owns holdings through `Settings.journal_db` (default `b3_trader/data/crypto_trader.sqlite3`). That other actual DB has not been inventoried. Do not invent holdings loss or initialize new tables.
- Implementation checkout: isolated `agent/crypto-product-data-recovery-20260921`, based on recovery checkpoint `368d4d9`. It is not the user's Windows runtime. No canonical DB write, runtime restart, Production deployment, real order, automatic merge or holdings mutation occurred.

### Implemented vertical slice

- Read-only consistent coin/exchange account projection now includes quantity, full precision, complete per-experiment ledger, fee-aware replay, scoped wins/return and revision identity. Removed the old shared 80-fill truncation/latest-only gap.
- Existing execution predicates and sizing are shared with the plan projection, preserving strategy/PAPER behavior. Plan exposes next entry, weight, conditional later rounds, actual full-position take-profit and stop rules; no invented partial-sale strategy.
- Existing D1 detail transport can store complete immutable ledger chunks. Authenticated API paginates by experiment and revision; changed revisions return 409 instead of mixing account and old fills. Pending rotations retain their place under existing write budgets.
- Paper route now keeps coin fixed across strategy tabs, account, price/fill chart, complete ledger and fee-inclusive split calculator. BTC/ETH comparisons use aligned stored 1h closes; events show only actual selected-coin responses. Missing observations stay missing. Old aggregate/basic-strategy pages remain reachable in the full Viewer.
- New view has one owned Shadow DOM stylesheet; preserves draft, focus and disclosure state during polling and follows the existing theme. Cross-exchange holding fallback and ticker localization corruption are corrected. No global strategy sample is presented as coin validation.
- Standalone stdlib review server opens the same projection/UI against the existing PC DB in read-only mode. Bind is loopback only; mutation routes, foreign origins and nonlocal hosts are rejected. `scripts/build-strategy-review.py` packages it with `RUN_REVIEW.cmd`; no DB, secrets, seeded data, Python dependencies or installer are included.

### Verification and limits

- New Python projection/journal/context/HTTP tests: 8 passed; existing affected Strategy Lab/custom/candidate/write-budget tests: 10 passed.
- Pre/post execution differential: 5,000 randomized cases matched fills, balances and learning (excluding wallclock metadata). Shared-rule extraction does not authorize strategy changes.
- JavaScript API/model/DOM tests: 12 passed, covering complete pagination, revision/chunk integrity, fee/quantity conservation, exchange/quote isolation, polling continuity, theme, identifier fidelity and preservation of original account pages.
- TypeScript and all existing Viewer static gates passed; changed Python modules compile. Extracted archive runs with Python `-S`, serves every packaged asset and reconciles a fixture account with unchanged DB hash. Static gates and DOM tests are not visual acceptance.
- Browser local navigation was blocked by this session's browser policy. Desktop/mobile visual acceptance and actual Windows DB → new Viewer numeric comparison remain pending. No screenshots or visual PASS are claimed.
- Remaining data gaps: stopped/stale collection diagnosis; altcoin event reactions / 1d horizons / historical same-type samples; real-holdings workflow redesign and small-live comparison. The rejected live-trading page is not declared redesigned or accepted.
- Transport limit: a single coin whose complete chunks exceed its per-run write budget fails explicitly; no silent truncation. Future chunk retention and very large journals need a separate bounded storage plan.

### Event reaction continuation — source complete, PC verification pending

- Parent for this unit: `a8c3545`. No new Windows review result was supplied or found; the actual-runtime evidence above has not advanced. This unit changes source, not the currently running PC or Production.
- Default event-response targets now include KRW markets from both REST and WebSocket registries; older DBs can discover observed raw markets. Explicit benchmark lists remain exact. No new source feed, network request, score or order path is added.
- A validated previously captured reaction supplies the same baseline for later horizons after raw-trade pruning. Conflicting/revised event clocks or corrupt saved samples fail closed; existing rows are not rewritten. Future ticks cannot satisfy a present target. No schema change or canonical DB mutation is required for this source change.
- Event projection groups by captured event clock and joins the same exchange, provider, source and horizon. It exposes baseline/target prices and exact timestamps for the coin, BTC and ETH, plus relative percentage-point movement. Invalid observations stay nonnumeric and are flagged.
- Historical samples use the same coin/exchange/source/event type/provider over the preceding year and only results captured before the selected event. Future events and late backfills cannot inflate that historical comparison. Counts, mean, median and positive counts remain separate from any recommendation probability.
- The event tab now selects one event and connects reaction numbers, original publication link, historical samples and actual price/time evidence. Selection and disclosures survive polling, including arrival of a newer event.
- Verification: 21 Python collection/journal/context tests + 13 ingest/check/downstream-sensitivity tests passed; latest changed collector tests 6/6 passed. JS/API/DOM 13/13 passed; all existing Viewer type/static gates and changed Python compilation passed. Extracted stdlib archive returned the same stored event prices/returns through HTTP and the local report, served every asset, and left the fixture DB hash unchanged.
- The existing review archive now also emits one explicitly scoped event sample. It uses B3 if present, otherwise labels a BTC sample separately; no BTC observation becomes B3 evidence.
- Limits remain: first capture still needs a real baseline and target inside existing raw retention; this does not reconstruct never-recorded prices or repair a stopped process. Unsupported event feeds, actual PC application, live accumulation and visual acceptance remain pending. New schema/pinned-price storage would require a separate additive change with actual DB backup/readback first.

### Runtime supervision continuation — source complete, PC verification pending

- Parent for this unit: `c3f828c`. No new actual-PC review result was received or found. The Windows runtime/DB evidence above has not advanced; no process was restarted or canonical data changed.
- Found in source: the launcher printed ON immediately after starting hidden sidecars, then blocked on the app and did not observe sidecar exits. Sidecars only restarted during app code-update exit 75. This source defect is not an established cause of the historical whole-PC outage.
- `local_process_host.py` now owns the existing launcher session and exact sidecar modules/arguments. It holds a per-checkout OS lock, records child exit codes and bounded rotating logs, retries failed collection/PAPER processes after five seconds, and observes app shutdown before retrying children. App exit 75 cleans up and returns to PowerShell so the updated host module is reloaded. Normal app exit or a stop request ends the session. Cleanup failure returns a non-retry exit instead of duplicating unresolved children.
- Holding-consumer startup arguments and its app-update/shutdown lifecycle are preserved; no new automatic retry policy is added. This source change grants no permission to run it on the actual PC. Strategy/PAPER execution predicates, control flags and databases are unchanged.
- `runtime_review.py` reads scoped Windows process identities, saved component/exit metadata and bounded error classifications. It does not export raw command lines, log bodies, environment values or credentials. A failed process lookup or ambiguous checkout remains unknown. Stored healthy labels never become live-process proof.
- The same read-only review archive now records T0/T1 DB activity 30 seconds apart, alongside the existing account/ledger/event evidence. Unchanged timestamps are an observation, not proof of collection failure; slow/missing queries stay unknown. The archive includes no process host or collector executable and cannot apply the recovery code.
- Verification: 25 distinct affected Python tests passed (including real fixture subprocess crash/retry, app-only restart, code-update cleanup of all owned roles, duplicate-host exclusion, stop cancellation, cleanup-failure non-retry, and read-only evidence). Build 69 ownership/static contract and changed-module compilation passed. Extracted 32-file archive ran with Python `-B -S`, reconciled the same fixture account over HTTP, completed both observations, kept unsupported process checks unknown and left the fixture DB hash unchanged.
- Native Windows/PowerShell execution and actual-PC DB-to-Viewer acceptance remain NOT_RUN. Existing GUI tests were not repeated because the Viewer source did not change. No visual acceptance, collector-growth proof, new actual outage cause, primary merge or deployment is claimed.

### Exact next action

1. Run the provided `CRYPTO_STRATEGY_REVIEW.zip` outside the actual checkout via `RUN_REVIEW.cmd`. Keep it open for at least 30 seconds. It reads the existing canonical DB and emits private `CRYPTO_B3_REVIEW_RESULT.json` with account/event/runtime T0/T1 evidence; do not commit or publicly upload this report.
2. Compare the real B3 account, all fills, current rules and calculation result in the new screen; complete desktop/mobile visual review. The archive is a review build, not a site deployment or production acceptance.
3. Investigate current Windows collector/supervisor exit evidence without treating persisted badges as liveness or restarting blindly. Restore accumulation only from actual process/log evidence and existing operating rules.
4. After actual review, carry this source through the existing Preview workflow. Primary branch, PR #1 and Production stay unmerged/unchanged unless separately authorized.


Status legend: `[ ]` pending · `[-]` active · `[x]` complete · `[>]` deferred to later workstream

Program-level roadmap: `docs/workstreams/dashboard-v1/MASTER_ROADMAP.md`

Viewer omission contract: `docs/VIEWER_REBUILD_CHECKLIST.md`

새로운 시장지능/상장생애주기/수급/기술분석/Phase 5~8/PAPER v2 작업의 세부 순서와 체크 상태는 `MASTER_ROADMAP.md`를 우선한다. 이 파일은 dashboard-v1 기존 작업의 연속성 상태를 유지한다.

## A. Continuity and permanent rules

- [x] Add restart-safe repository protocol in `AGENTS.md`
- [x] Add project-specific `DESIGN.md`
- [x] Record Photo-eBook as the primary approved UI baseline
- [x] Apply Photo-eBook Korean copy + mobile regression rules to dashboard work
- [x] Keep primary comprehension suitable for a Korean non-trader in their 60s
- [x] Add `MASTER_ROADMAP.md` as the program-level checklist for market intelligence, scoring, PAPER v2, Phase 5~8 and final QA
- [x] Add `docs/MODULAR_ARCHITECTURE.md` and make collector/store/feature/score/service/page dependency direction a permanent repository rule
- [x] Add shared `ui-continuity.js`; do not duplicate page-specific scroll/focus restoration or use broad MutationObserver loops

## B. Dashboard UI / mobile UX

- [x] Responsive navigation: 홈 / 코인 / 결과 / 기록 / 설정
- [x] Preserve `판단 근거 자세히 보기` state across polling rerenders
- [x] Prevent iOS input-focus zoom with >=16px focusable text
- [x] Prevent routine button-label wrapping
- [x] Rebuild mobile averaging calculator as full-width stacked rows
- [x] Increase average-price readability and prevent P/L ellipsis loss
- [x] Use one measured Liquid indicator with stretch/overshoot/snap-back motion
- [x] Preserve native iOS horizontal rail momentum
- [x] Fix detached/covering Liquid bug by moving rail glass/background to a lower visual layer and keeping labels/icons above the moving indicator
- [x] Use separate horizontal/vertical Liquid bleed so the selector only slightly protrudes outside the rail instead of becoming an oversized blob
- [-] Verify shared same-page continuity guard fixes sector/master-detail selection scroll reset without interfering with intentional route scroll-to-top
- [-] User screenshot QA on current iPhone + desktop

## C. Main multi-asset monitor

- [x] B3-style generalized live analysis for user-selected Bithumb KRW assets
- [x] ETH/BTC built-in reference
- [x] Manual holdings / average price / P&L in local SQLite
- [x] Per-ticker averaging-down plans up to 20 rounds
- [x] Suggested entry amount and account percentage on BUY_CANDIDATE
- [x] Telegram automatic alerts reduced to fresh BUY_CANDIDATE only
- [x] Reject malformed configured markets such as `KRW-ETH/BTC` at registry/API boundaries while preserving valid configured assets

## D. Adaptive all-market PAPER research

- [x] Replace old shared 10M demo portfolio with **one independent 10,000,000 KRW PAPER account per Bithumb KRW market**
- [x] Create/maintain accounts for every valid KRW market rather than filtering to a small candidate basket
- [x] Scan public Bithumb KRW markets roughly every 3 minutes
- [x] Reuse `AssetStrategy` scoring but do not require legacy BUY_CANDIDATE for every PAPER entry
- [x] Add bounded `explore` and `idle_explore` entries with smaller weights when opportunity is constructive but old fixed thresholds are not met
- [x] Keep spread / estimated-slippage / BTC flash-crash PAPER execution guards
- [x] Position sizing is percentage-based from each coin's own 10M account
- [x] Add hard stop, take-profit, trailing giveback, market-weakness and time/opportunity exits
- [x] Persist independent cash, position, realized P/L, drawdown and equity history
- [x] Rank markets by current PAPER return and expose current best performer
- [x] Add dedicated restart-safe `paper_runtime_supervisor` as the normal launcher owner; constructor errors, runtime exceptions and unexpected clean returns all retry without taking down the dashboard/research sidecar
- [x] Centralize PAPER freshness/PID liveness so stale or reused PIDs cannot suppress recovery; direct `local_app` runs retain the embedded-worker fallback
- [x] Verify PAPER self-heal on Windows after full launcher restart: external supervisor PID alive, PAPER `running/fresh`, zero restart/error, PAPER-only safety preserved
- [-] Leave engine running long enough to collect meaningful trade-frequency / P&L / drawdown / win-rate evidence

## E. Per-coin feedback DB / bounded learning

- [x] Persist per-market profile thresholds and base position weight in SQLite
- [x] Store current signal / opportunity / intent per market
- [x] Store every PAPER fill with timing, amount, weight, reason and signal snapshot
- [x] Store completed-trade feedback: result, holding time, entry signal, profile before and profile after
- [x] Update only the affected coin's PAPER profile after each closed trade
- [x] Winning entries can relax toward their successful entry conditions
- [x] Losing entries make the profile more selective and reduce base weight
- [x] Bound adaptive thresholds and position weights to avoid runaway self-tuning
- [x] Learning is DB-driven only; it does not rewrite Python source or enable live trading
- [ ] After enough samples, add out-of-sample / holdout validation before promoting any profile as a live-trading candidate

## F. PAPER research dashboard

- [x] Home summary: number of markets, scan progress, active positions and current return leader
- [x] Results workspace: `전체 코인 자동매매 연구`
- [x] Ranking rows: return, trade count, win rate and current intent
- [x] Per-coin detail: opportunity/regime/entry, suggested weight, adaptive profile version/thresholds
- [x] Per-coin equity curve
- [x] Per-coin trade history with time, side, virtual order amount, weight and result
- [x] Per-coin learning history showing profile before/after changes
- [x] Generate ignored per-market detail JSON under `dashboard/demo-runtime/`
- [x] Allow direct ticker lookup for markets outside the visible top ranking
- [-] User visual QA of the new research workspace

## G. GitHub / local synchronization

- [x] GitHub branch remains `b3-auto-trader-phase1`
- [x] Local SQLite remains authoritative runtime data
- [x] Control-only divergence repair preserves `control/assets.json` and `control/runtime.json`
- [x] Normal launcher forces Git auto-sync and control publishing on
- [x] Normal launcher forces 15-second polling even if an older `.env` still contains the old template value
- [x] Startup can safely preserve local control changes while realigning app code
- [x] Startup prints local/remote Git sync state
- [x] Dashboard-only changes avoid Uvicorn restart
- [x] Python runtime changes use supervised exit code 75 and automatic restart
- [ ] Finish rclone Google Drive setup and verify backups/mirrors

## H. Phone access

- [x] Cloudflare HTTPS tunnel without phone VPN requirement
- [x] Secure launcher binds app to `127.0.0.1`
- [x] Public direct port path remains disabled
- [x] Quick Tunnel fallback
- [ ] Complete named/stable Cloudflare hostname setup if user wants a fixed URL
- [ ] Rotate old exposed phone connection code after stable access is finalized

## I. Real-money execution

- [>] **DEFERRED — separate future Work/workstream. Do not implement here.**
- [>] Select live candidates from PAPER evidence, not from one-off score snapshots
- [>] Add exchange-balance source of truth, idempotency, partial-fill/open-order reconciliation and stale-order cancellation
- [>] Add exchange-level hard exposure/daily-loss limits
- [>] Run a tightly capped live pilot only after adequate forward-test and holdout evidence

## J. Program roadmap continuity

- [x] Merge the already-completed strategy equity/coin performance/coin×strategy/overall PAPER equity+drawdown work into the master roadmap as completed baseline
- [x] Preserve existing pending items: real-holdings history, record strategy/state/system filters, GitHub Actions Viewer status, Phase 5, Phase 6, Phase 7, Phase 8, final 390/430 QA
- [x] Add new listing/pre-listing CEX/DEX history, caution/delist lifecycle, D-5 price columns, scroll-position preservation, geography/facet taxonomy, news/macro/human/onchain intelligence, order-flow/CVD, technical structure engine and PAPER v2 sequence
- [x] Implement lifecycle domain + additive local SQLite registry with baseline-safe NEW_LISTING detection, CAUTION mapping, 3-observation termination confirmation and partial-market-response rejection
- [x] Add official Bithumb/Upbit notice adapters, notice DB, lifecycle notice overlay and independent `market-notice-watch` supervisor sidecar
- [x] Structure official notice timing into `announcement_at`, `deposit_at`, `trade_open_at`, `termination_at` with fail-closed date-only handling and compact `market_notice_audit`
- [x] Publish lifecycle/notice-only state to Cloudflare Viewer and add modular 상장예정/유의/거래종료 panel + ticker state styling
- [x] Add D-5 return-window feature from existing shared `research_market_memory_mx`; no separate exchange call per UI feature
- [x] Add termination-only PAPER safety gate: `TERMINATION_SCHEDULED`/`TERMINATED` blocks new/additional PAPER buys while existing position exits/history stay available; CAUTION/NEW_LISTING remain shadow in current adaptive
- [x] Add dedicated PAPER runtime self-heal ownership and shared liveness policy after live QA exposed a stale/dead PID + stopped worker condition
- [x] Stabilize Cloudflare D1 write budget after live 503: snapshot 60s, detail 300s, bounded detail batches, unchanged-row skip, quota-aware error handling; Windows runtime publishers verified healthy
- [-] Existing all-KRW account/profile seeding + market-memory/profile backlog provide automatic new-market bootstrap; verify full profile/sector/facet path on an actual new listing
- [x] Verify Build 38 runtime/Pages/live official notice timing/PAPER self-heal after sync/restart; publishers healthy, PAPER fresh, asset registry valid, Viewer snapshot current
- [-] Build 39 pre-KRW CEX foundation: official KRW listing planner, verified profile identity bridge, exact CoinGecko venue-pair verification, Binance/OKX/Bybit adapters, domestic opening-price resolver, additive SQLite store, T-7d~T-1h + post-7d features, bounded 15-minute sidecar, audit CLI and dedicated CI are implemented; live Windows data audit remains
- [-] Execute the remaining work in `MASTER_ROADMAP.md` dependency order; next after CEX live QA is compact Viewer projection, DEX-first history, then multi-facet/flow-CVD work
- [x] Build 65~70 forward-only DEX v2 preregistration/scorer/intake/enrichment/orchestration/sample-ledger 구현. pre-cutoff와 Build 47 historical cursor는 격리하고 30 event/20 unique asset gate를 고정
- [x] Build 71 preregistered forward validation 구현: Build 70 readiness 전 통계 미계산, 준비 후 event/asset-dedup Spearman·quartile spread·chronological late-half·strong-negative 기준만 계산
- [x] Build 69 forward scheduler 구현: 별도 15분 process, 회당 Build 69 1회/최대 1 case, OS process/work lock, launcher start/restart/stop, server-off no-work, generic listing/DEX historical component 강제 비활성
- [x] Build 69 scheduler Windows runtime verified: fresh heartbeat/process lock, 900s interval, 2 pages/exchange, first bounded cycle success, generic listing/DEX historical components disabled by dedicated mode, zero safety violations
- [-] 실제 신규 KRW 상장 forward 표본 누적. 현재 Build 70은 0 event / 0 unique asset이며 Build 71은 `waiting_for_forward_sample`이 정상 상태
- [ ] 실제 표본에서 Build 71 PASS 후에만 Build 72 parallel PAPER A/B를 구현하고 기존 PAPER 신호/주문/position sizing은 그대로 유지

## K. Build 48 senior-default UX pass

Target user: a Korean crypto buyer/seller in their 60s who is not a developer, quant or professional technical analyst.

- [x] Add a final `senior-default.css` readability layer and make it the default Viewer baseline
- [x] Raise primary body/menu/control/meta text toward a 13~16px minimum hierarchy and make routine controls/inputs 44~48px high
- [x] Preserve the existing content-priority layer that already moves coin-finder listing history, holdings history and sector research material behind the primary task flow
- [x] Replace combined PAPER headline totals with a 10,000,000 KRW normalized result while preserving the underlying independent-account calculations
- [x] Normalize per-exchange PAPER KPI money and selected-strategy evaluation money to a 10,000,000 KRW comparison basis
- [x] Remove numeric strategy ranking from the default strategy list and state explicitly that the current order is a return sort, not a recommendation rank
- [x] Remove experiment ID from the default strategy list/detail summary; retain research identifiers only where advanced comparison evidence needs them
- [ ] Add user-facing US macro schedule / major US market index / material-news context without inventing or stale-caching event data; consume the existing Phase 5 data contract rather than creating a Viewer-only collector
- [x] Turn averaging-down from a calculator into a bounded decision plan: wait/buy/stop state, next review price, remaining/max rounds, user-entered remaining budget, per-round amount, first PAPER review price, explicitly estimated later prices and stop-adding conditions
- [-] Add staged profit-taking guidance: first profit-protection level, dynamic PAPER target and final trailing protection are shown; do not invent partial-sell percentages until a real execution/allocation policy exists
- [x] Require the user to select Bithumb/Upbit reference before holding-specific plan prices because actual holding exchange is not yet persisted
- [ ] Persist the actual holding exchange in local holdings data so the Viewer can preselect it instead of asking every session/coin
- [x] Add global simple/detail mode; default simple mode hides specialist research scores, deep charts, internal evidence and secondary calculators without deleting data, and detailed mode restores the existing surfaces
- [x] Separate user trade/decision history from system/learning logs in the default Records view; `내 매매·판단` is the default and `시스템·학습` is a separate persisted scope
- [-] Continue copy cleanup from PAPER/research/sector/opportunity/regime/entry/drawdown terminology to ordinary Korean where it does not damage technical accuracy; holding-plan and Records high-frequency copy has been converted
- [ ] Add non-color state cues consistently (`▲/▼`, 수익/손실, 상태 text) and complete screenshot QA on desktop + phone

## Validation status

- [x] Current adaptive research implementation passed Python tests + module compile
- [x] Current Liquid/research dashboard implementation passed Node dashboard smoke checks
- [x] Current branch passed Cloudflare typecheck
- [x] Build 38 lifecycle/notice/return-window/timing/entry-policy/PAPER-liveness unit tests pass in GitHub Actions
- [x] Build 38 dedicated CI passes including Pages typecheck and modular source contract
- [x] Full B3 trader CI passes after PAPER self-heal and malformed-asset fail-closed fixes
- [x] Cloudflare Pages JS syntax/typecheck passes with shared continuity/lifecycle modules
- [x] Build 39 dedicated CI passes: listing-history compile/tests, modular contract and Cloudflare Pages typecheck
- [x] Full B3 trader CI passes with Build 39 source/supervisor additions
- [x] Build 69/70 Windows runtime: 공식 공지 조회 정상, 신규 forward 0건, enrichment/DB mutation 0건, sample readiness false 확인
- [x] Build 71 local compile/unit/contract/Build 63·65~70 regression PASS; commit `5c8081d`의 전용 Build 71 CI와 전체 B3 trader CI 모두 PASS; Windows HEAD `4f65082`에서 Build 71 contract/runtime PASS 및 통계 미실행 대기 상태 확인
- [x] Build 69 scheduler local source validation: full Python suite 266 tests, scheduler/server-off contract, Build 39/43 supervisor regressions, Build 65~71 contract chain PASS
- [x] Build 69 scheduler Windows live runtime PASS: scheduler running/fresh, process lock acquired, PAPER/shadow-only, order/PAPER-A-B/live unwired, research supervisor fresh, generic historical listing/DEX disabled, first cycle `attempts=1 / successes=1 / failures=0`, no safety violations
- [x] Build 48 senior-default baseline through commit `8686fb8`: 28 GitHub Actions completed with no failure/queued/in-progress result
- [-] Build 48 simple/detail + Records split latest-head CI and desktop/phone visual regression validation in progress
- [x] PR #1 remains Draft and unmerged

## Completion condition

Finish this workstream when mobile/dashboard UX is approved, adaptive per-coin PAPER research has accumulated enough evidence to identify robust candidates rather than lucky short-term winners, backup is verified, phone access is convenient, and the program-level items tracked in `MASTER_ROADMAP.md` have either completed or been explicitly moved to a successor workstream. Real-money execution stays deferred.


## L. CRYPTO-WO-20260921-001 single-chat UI system recovery / audit

- [x] Actual Windows checkout reconciled: `b3-auto-trader-phase1` / `e9318be6c47877013e408d10479ea7f3e83f6506`; tracked, staged and untracked state all clean; upstream `origin/b3-auto-trader-phase1`; ahead/behind `0/0`.
- [x] Production Viewer release at the same code HEAD was already deployed and read back healthy before this audit; latest GitHub `B3 trader tests` and Build 51~71 workflow set are green; PR #1 remains Draft/open.
- [x] Activated the single-chat Drive harness and reconciled READ FIRST / CURRENT SNAPSHOT / CURRENT BATON / Work Order Ledger with actual Git state.
- [x] Audited the active Viewer entry graph: 9 current routes (`dashboard`, `dashboard-detail`, `research`, `assets`, `paper`, `strategy`, `sectors`, `records`, `system`) plus global reader/theme/account controls.
- [x] Completed page / feature / component-family inventory and mapped duplicate entry points, master-detail patterns, global simple/detail behavior, chart/table/filter/search interactions, responsive handoff, accessibility contracts, and live-polling continuity.
- [x] CSS propagation audit: the current `index.html` loads 37 stylesheets. Across those loaded files there are ~260,399 CSS characters, 2,124 rule blocks, 100 media blocks and 1,874 `!important` declarations. Largest override layers include `strategy-native-v5.css` (448), `interaction-layout-v4.css` (400), `mainstream-v4.css` (146), and `layout-fixes-v4.css` (142).
- [x] Identified a permanent-contract violation in `shared/rail-controls-v16.js`: a broad document-root `MutationObserver({childList:true,subtree:true})` is still installed even though AGENTS/MODULAR_ARCHITECTURE prohibit broad observer continuity/enhancement loops. No code change was made during the audit.
- [x] Stable exemplar candidates recorded: Strategy V5 master/detail workspace, Records user-vs-system audience split, Research master/detail + live patch path, V17 Assets position hero/facts/editor handoff, `ui-continuity.js`, scoped live-patch modules, and `viewport-handoff-v4.js` mobile return pattern.
- [x] Target IA proposed without deleting capability: global `홈 / 코인 / 내 자산 / 모의투자 / 기록 / 더보기`; `코인` local views = `코인 / 시장현황 / 테마`; `모의투자` owns performance + coin view + method/strategy comparison + current execution; `더보기` owns system/account/operations.
- [x] Target component model proposed: foundations/tokens → primitives → navigation/controls → master-detail/data-view components → page compositions. Page-specific late override CSS is to be reduced incrementally rather than replaced by a big-bang rewrite.
- [x] Simple/detail model proposed as semantic Primary / Supporting / Advanced disclosure per page; feature access remains preserved and selected object/tab/filter/scroll/focus must survive mode change and polling.
- [x] QA model fixed for future waves: desktop 1280/1440/1920, tablet 768/900/1024, phone 360/390/430 plus real iPhone Safari; light/dark, keyboard/focus, 200% zoom/reflow, safe-area, touch targets, no page overflow, and polling continuity are required.
- [ ] NEXT GATE — proposed `CRYPTO-WO-20260921-002`: bounded UI foundation consolidation only. Remove the broad rail MutationObserver, establish canonical shell/control/master-detail tokens/components, add propagation/regression checks, and preserve current page functionality/IA while reducing override ownership. Do not start until WO-001 audit review/approval.


## M. CRYPTO-WO-20260921-002 UI foundation consolidation verify

- [x] Actual local parent verified at `c5b1c893b25e45b69f3fe2de68ff9a48847d7a98`, clean/aligned 0/0 before implementation.
- [x] Removed the broad document-root `MutationObserver` from `shared/rail-controls-v16.js`; rail enhancement is now scoped to `#pageRoot` and explicit `ui:refresh` lifecycle.
- [x] Established canonical shared UI geometry tokens in `tokens.css` and consumed them from shell/components/interaction layers.
- [x] Added additive composition primitives and `UI_FOUNDATION_CONTRACT.md`; no new late CSS layer was added.
- [x] Added `check-ui-foundation-v18.mjs` and wired it into `npm run typecheck`.
- [x] Refreshed stale V4/V8/V16 regression assertions to the canonical V18 token/build lineage without weakening functional checks.
- [x] Actual local verification PASS at `3e15a8d8a1959a99f7a2a8c5ff7196d83571c7a9`; worktree clean/aligned and every Viewer contract PASS including `UI_FOUNDATION_V18` and `V16_HOLDINGS_WRITE`.
- [x] GitHub `B3 trader tests` run 2750 PASS: python-test, cloudflare-typecheck, cloudflare-pages-viewer, dashboard-smoke all SUCCESS; returned Build 51~71 set SUCCESS.
- [ ] VISUAL QA GATE — preview-only deployment/readback, then desktop 1280/1440/1920, tablet 768/900/1024, phone 360/390/430, light/dark, keyboard/focus, reader-mode, selection/sort/search and live polling continuity.
- [ ] Production deployment remains prohibited until visual QA is accepted.


### WO-002 preview visual-QA checkpoint

- [x] Non-Production Pages preview deployed from actual local `7e19da175c34fc4e6b172581ebf2831bd5426a67`.
- [x] Deployment URL: `https://1072960d.crypto-paper-viewer-ydh1121-cf36.pages.dev`.
- [x] Stable preview alias: `https://qa-v18-ui-foundation.crypto-paper-viewer-ydh1121-cf36.pages.dev`.
- [x] Wrangler explicitly used preview branch `qa-v18-ui-foundation`; Production branch was not deployed.
- [ ] Visual QA pending: desktop 1440 dark first, then representative phone 390 dark, then light/keyboard/focus/reader-mode/search/sort/polling continuity.
- [ ] No write-action testing against holdings/PAPER/runtime mutation endpoints during visual QA.


### WO-002 partial desktop visual-QA evidence — 2026-09-21

User supplied a broad 1440px-class dark-mode screenshot sweep from the V18 preview covering Home, Coin/Research, Market overview, Theme/Sectors, Assets, PAPER, Strategy/Method comparison, Records, and System surfaces.

Partial findings only — NOT final visual acceptance:
- [x] No obvious global horizontal overflow or catastrophic shell collapse is visible in the supplied desktop screenshots.
- [x] Global header/nav, local market nav, major master/detail rails, tables and status colors render consistently enough to continue QA.
- [x] Assets V17 remains the strongest stable exemplar: hierarchy from portfolio summary → selected holding → PnL/facts → holdings editor → planning is comparatively clear.
- [x] Strategy master/detail and Records audience split remain structurally intact.
- [ ] REPAIR candidate: Market overview/dashboard remains card-dense with several blocks competing at similar visual weight.
- [ ] REPAIR candidate: Theme/Sectors is information-dense; left ranking + central table + project evidence creates small text and weak scan hierarchy at desktop scale.
- [ ] REPAIR candidate: PAPER/Strategy detail views have large unused vertical areas when selected content is short, producing inconsistent density between tabs.
- [ ] REPAIR candidate: sticky global/local headers occupy substantial vertical space; during long-page scroll several screenshots show content beginning directly beneath/behind the sticky stack. Verify scroll-margin/anchor/focus visibility before acceptance.
- [ ] REPAIR candidate: System page is operationally complete but visually reads as a long stack of equal-weight cards/rows; status/priority grouping needs later component migration, not a WO-002 foundation rewrite.
- [ ] Screenshot intake stops at the supplied desktop set for now; work continues. Phone/light/keyboard/focus/polling checks remain pending and are not interpreted as cancelled.
- [ ] Production remains prohibited.


### WO-002 desktop evidence bounded foundation repair

- [x] Corrected the earlier interpretation: screenshot intake stopped, work did not pause.
- [x] Added dynamic shell `scroll-padding-top` derived from `--shell-header-offset` so anchor/focus navigation does not land beneath the sticky header stack.
- [x] Bumped `viewport-first-v9.css` cache key and added a V18 regression assertion for sticky-shell scroll/focus visibility.
- [x] Removed legacy `mainstream-v4.css` rules that forced `.operations-grid` and `.system-grid` to one column at all desktop widths.
- [x] Restored canonical System responsive ownership from `records-system.css`: operations 3 columns desktop / 2 below 1180 / 1 below 620; system summary 2 columns desktop / 1 below 820.
- [x] Added V18 ownership regression checks and refreshed the mainstream cache contract.
- [ ] Remote/local regression verification pending at latest repair HEAD.
- [ ] Re-deploy Preview only after regression verification; Production remains prohibited.


## N. CRYPTO-WO-20260921-003 Market + Theme page hierarchy

Parent verified by actual local readback before source mutation:
- branch `b3-auto-trader-phase1`
- HEAD `0316ab2a0c542d2ce2c8c14ede9842ab7b63eedb`
- tracked/staged/untracked = 0/0/0
- upstream = 0/0
- full Viewer contract PASS
- Preview repair deployment/readback PASS; Production unchanged

Scope is intentionally bounded to the desktop evidence already supplied:
- [x] Market dashboard: reweighted the overview into one primary market surface with actual-assets and PAPER as supporting surfaces instead of three equal cards.
- [x] Market dashboard: made “지금 볼 코인” the primary intelligence surface; sector flow and strategy validity are supporting stacked surfaces.
- [x] Responsive fallback: market overview becomes full-width above account/PAPER at <=1100; all surfaces become single-column at <=720.
- [x] Theme/Sectors: converted the four top summary cards into one fact-strip treatment.
- [x] Theme/Sectors: retained sector-rank + detail as the two primary panes while removing the permanent third project-info rail.
- [x] Theme/Sectors: project business/evidence is now native `details/summary` progressive disclosure below the coin table; selecting a coin opens the disclosure explicitly.
- [x] Theme/Sectors: increased table/rank scan readability and removed the decorative overview gradient.
- [x] Preserved sector table, sorting, selected coin, project evidence, official links, and research jump.
- [x] Added `check-page-hierarchy-v19.mjs` and wired it into `npm run typecheck`.
- [x] Exact latest-head GitHub CI verification PASS at `deb3c30385cdcf86604a62a9357c490a6071b522`: B3 trader tests #2800 SUCCESS; dashboard-smoke, cloudflare-typecheck, python-test, cloudflare-pages-viewer all SUCCESS; returned Build 51~71 workflow set SUCCESS.
- [x] Actual local/current readback PASS at `7e29f78a7a20009fe741b35756cf38d2cdc96fef`: branch `b3-auto-trader-phase1`, tracked/staged/untracked `0/0/0`, upstream `0/0`; full `npm run typecheck` PASS including `PAGE_HIERARCHY_V19=PASS`.
- [x] Preview-only V19 redeploy/readback PASS: deployment `14c1a46b`, alias `qa-v18-ui-foundation`; `dashboard.css?v=4`, `sectors.css?v=3`, `main.js?v=100.0` live. Production not deployed.
- [x] WO-003 ACCEPTED. Market + Theme page-hierarchy scope closed; remaining PAPER/Strategy sparse-detail work moves to a new bounded WO.


## O. CRYPTO-WO-20260921-004 PAPER + Strategy sparse-detail hierarchy

Scope is bounded to PAPER + Strategy composition only.

- [x] PAPER workspace no longer forces `min-height: calc(100vh - 265px)`; detail height follows actual content.
- [x] PAPER master rail remains independently bounded/sticky, but uses responsive `--shell-header-offset` and `max-height` rather than forcing the workspace/detail height.
- [x] PAPER list owns its own bounded scroll area without imposing viewport height on the detail pane.
- [x] Strategy detail shell no longer owns a fixed `440px` minimum or viewport max-height; it is content-height driven.
- [x] Strategy detail panels no longer create a nested vertical scroll container; document flow remains canonical.
- [x] Existing strategy tabs, strategy selection rail, PAPER filters/search/sort, selected market, trade plan, fills, charts and evidence remain available.
- [x] Added `check-sparse-detail-v20.mjs` and wired it into `npm run typecheck`.
- [x] CI PASS for the exact current code at durable head `9f598c70bd3a18c5af2160dc05a721504d01e1fd` (code identical to implementation head `c8c13dfa4...`; only TASKS/HANDOFF docs differ): B3 trader tests #2819 SUCCESS and returned Build 51~71 set SUCCESS.
- [x] Actual local/current readback PASS at `b72ef6424121431562d53bd0c1e5351b184db90a`: branch `b3-auto-trader-phase1`, tracked/staged/untracked `0/0/0`, upstream `0/0`; full `npm run typecheck` PASS including `PAGE_HIERARCHY_V19=PASS` and `SPARSE_DETAIL_V20=PASS`.
- [x] Preview-only WO-004 redeploy/readback PASS: deployment `9d55cef5`, alias `qa-v18-ui-foundation`; PAPER content-height repair LIVE; Strategy sparse-detail repair LIVE. Production not deployed.
- [x] WO-004 ACCEPTED.


## P. CRYPTO-WO-20260921-005 Mobile & interaction continuity

Scope is bounded to 360/390/430 safe-area, touch geometry and interaction continuity.

- [x] Added shell-side `safe-area-inset-left/right/top/bottom` handling while preserving `viewport-fit=cover`.
- [x] App shell/auth use dynamic viewport height fallback (`100vh` + `100dvh`).
- [x] Compact global navigation uses `repeat(3,minmax(0,1fr))`, bounded text overflow and canonical `--control-touch-h`.
- [x] Compact main-nav / segmented / reader-mode / chips / theme controls are forced to canonical touch height at <=620px.
- [x] Auth theme toggle and horizontal journey navigation respect notch-side safe areas.
- [x] Existing coarse-pointer 16px form-input rule and native zoom remain preserved.
- [x] Existing viewport return bar remains >=44px.
- [x] Added `check-mobile-interaction-v21.mjs` to guard focus/selection/scroll/polling continuity contracts without introducing a new render owner.
- [x] Foundation contract updated with safe-area/touch ownership.
- [x] Exact code-head CI PASS at `3acfe9367629d3ed69bec48b069bfcb7211c4c17`: B3 trader tests #2853 SUCCESS; cloudflare-pages-viewer, cloudflare-typecheck, python-test and dashboard-smoke all SUCCESS; returned Build 51~71 set SUCCESS.
- [x] Actual local/current readback PASS at `c841bf49bda6b8ddb7fa7d46ca3a147324e0bbb3`: branch `b3-auto-trader-phase1`, tracked/staged/untracked `0/0/0`, upstream `0/0`; full `npm run typecheck` PASS including `MOBILE_INTERACTION_V21=PASS`.
- [x] Preview-only WO-005 redeploy/readback PASS: deployment `c476bcbe`, alias `qa-v18-ui-foundation`; safe-area and mobile touch geometry assets LIVE. Production not deployed.
- [x] WO-005 ACCEPTED.

### V21 stale-contract repair / debt guard

- [x] Updated `INFORMATION_ARCHITECTURE_V10` to recognize the safe-area-aware shared content padding contract instead of the retired literal padding string.
- [x] Kept `interaction-layout-v4.css` at the audited 400 `!important` ceiling: compact touch sizing now flows through `--control-h: var(--control-touch-h)` and owning theme/journey rules instead of six new late overrides.
- [x] Updated `UI_FOUNDATION_V18` ordering check to be cache-version agnostic while preserving stylesheet-order and debt caps.
- [x] Updated mainstream dark-mode cache assertion for `theme-dark-v4.css?v=2`.


## Q. CRYPTO-WO-20260921-006 Final device interaction QA

TYPE = DEVICE_QA / RELEASE_GATE
STATUS = ACTIVE
PARENT = WO-005 accepted preview state

No source mutation is authorized until a reproducible device defect is observed.

- [ ] 390px concentrated QA
- [ ] 430px concentrated QA
- [ ] 360px minimum-width overflow sanity
- [ ] iOS Safari focus zoom / keyboard / safe-area
- [ ] horizontal rail native momentum
- [ ] master-detail selection → scroll/focus continuity
- [ ] live polling preserves selection/search/filter/scroll/open disclosure
- [ ] light/dark toggle at compact width
- [ ] simple/detail reader-mode continuity at compact width
- [ ] 1280–1920 desktop regression sanity after mobile source changes
- [ ] Production deployment remains prohibited until device gate is accepted.


## R. CRYPTO-WO-20260921-007 Simplified trading IA rebaseline

STATUS = ACTIVE

- [x] Supersede WO-006 device QA as current WIP; device QA remains a later release gate.
- [x] Replace the oversized purpose/page tree with a simplified canonical structure centered on `실전매매` and `가상매매`.
- [x] Primary live-trading page requirements fixed: exchange, ticker, current price, dominant strategy, split entries, split exits, split allocation, averaging calculator, profit-taking calculator, evidence-backed likely-riser recommendations.
- [x] Primary PAPER coin page requirements fixed: per-strategy account/trade history, BTC/ETH-relative movement, news/indicator/event reactions.
- [x] All other existing features demoted to 탐색 / 연구·데이터 / 기록 / 운영.
- [ ] Build one exhaustive existing-capability → canonical-destination mapping table before any further page coding.
- [ ] Produce low-fidelity wireframe/page component hierarchy only after the mapping table is accepted.
- [ ] No Production deploy.


### WO-007 planning artifacts

- [x] Created exhaustive 100-row capability map: `EXISTING_CAPABILITY_CANONICAL_MAPPING_V1.md`.
- [x] Created two-primary-page Low-fi: `SIMPLIFIED_TRADING_LOWFI_SPEC_V1.md`.
- [x] Primary pages remain only `실전매매` and `가상매매`; 탐색/기록/운영/연구·데이터 are secondary.
- [x] Identified six primary projection/derivation gaps only: dominant strategy, strategy account state, strategy trade ledger, BTC/ETH-relative history, selected-coin event/reaction memory, recommendation evidence envelope.
- [x] Reused CODE1 Drive Harness principles: IA/flow before High-fi, flat-scan high-frequency tasks, grouping surface + flat rows, semantic family before tokens, real state/value over helper copy, context preservation, 390px + desktop containment review.
- [x] Reviewed public Git references read-only: `openexch/trading-ui`, `rampstackco/swiss-style-theme`, `davaded/frontend-art-direction`, `carbon-design-system/carbon`.
- [x] External references are pattern evidence only; no new UI dependency/library is introduced.
- [x] Current GitHub connector does not expose authenticated starred-repository enumeration; no repo is falsely labeled as user-starred.
- [x] USER CONTINUATION accepted as approval to proceed from the mapping + Low-fi hierarchy.
- [x] Planning gate released; source mutation still requires fresh actual-local parent verification.
- [ ] Production deploy remains prohibited.


## S. CRYPTO-WO-20260921-008 Primary shell + 실전매매 composition v1

STATUS = VERIFY_LOCAL_AND_PREVIEW

PARENT REMOTE = current durable branch head after WO-007 acceptance docs

- [x] WO-007 planning accepted; migration order fixed in `SIMPLIFIED_TRADING_MIGRATION_PLAN_V1.md`.
- [x] Fresh actual-local parent verification PASS at `fd527d7b026c7c483ae9dd152eef836808db6392`: branch `b3-auto-trader-phase1`, tracked/staged/untracked `0/0/0`, upstream `0/0`.
- [x] Implemented new primary `실전매매` composition at code head `169ca445ef4a93103fc548f642bacc5de675a77b`; all legacy routes/modules remain wired.
- [x] Primary visible navigation is now `실전매매 / 가상매매 / 탐색 / 기록`; 운영 remains owner/account utility.
- [x] Live page reuses actual holdings/current quote/watch candidates/PAPER detail/strategy-lab results plus canonical averaging and profit-protection utilities.
- [x] Dominant-strategy UI is evidence-safe: one Gate candidate may be shown only as `우세 후보`; multiple/absent candidates show compare/insufficient state; no return-only winner is invented.
- [x] PAPER/strategy/holdings-write/data semantics preserved; `live` is a patch route with page-owned `snapshot-live` refresh, calculator inputs are not overwritten by polling.
- [x] Added `SIMPLIFIED_TRADING_V22` contract and refreshed stale IA/viewport/mobile/build-lineage contracts without deleting prior gates.
- [x] Exact code-head CI PASS at `169ca445ef4a93103fc548f642bacc5de675a77b`: B3 trader tests #2925 SUCCESS; cloudflare-pages-viewer/cloudflare-typecheck/python-test/dashboard-smoke SUCCESS; returned Build 51~71 set SUCCESS.
- [x] Preview-only deployment/readback PASS: deployment `f18a2c1a`, alias `qa-v18-ui-foundation`; UTF-8 raw-byte readback confirmed all V22 live-trading markers. Production not deployed.
- [ ] Production prohibited.

### WO-008 implementation notes

- New route: `live`.
- Desktop primary composition: exchange/ticker/current price/holding context → observation candidates → strategy evidence/plan → one-mode-at-a-time averaging/profit calculator.
- Candidate block is explicitly `상승 관찰 후보`, not final recommendation; BTC·ETH/event evidence envelope remains WO-011.
- Strategy-specific entry/exit projections that do not exist in Snapshot display `projection 대기` / `비중 미제공`; no synthetic targets are generated.
- Current PAPER 24h label no longer falls back to cumulative PAPER return; missing 24h data displays `-`.
- Old Assets/PAPER/Strategy/Market pages remain reachable through secondary journeys during migration.
- [x] Actual local/current readback PASS at `ba3c59a50962ae1a5bdc41053a75f9e6bf9e1ec7`: branch `b3-auto-trader-phase1`, tracked/staged/untracked `0/0/0`, upstream `0/0`; full `npm run typecheck` PASS including `SIMPLIFIED_TRADING_V22=PASS`.
- [x] Preview-only deployment/readback PASS at `f18a2c1a` and stable alias; first PowerShell text readback was a Windows charset false negative, raw UTF-8 byte decoding passed both immutable deployment and alias.
- [ ] Focused visual QA pending: one desktop screenshot + one 390px screenshot of the new `실전매매` page only.
- [ ] Production prohibited.
