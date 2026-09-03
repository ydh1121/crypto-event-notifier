# Dashboard v1 workstream tasks

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
