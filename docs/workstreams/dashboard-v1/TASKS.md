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
- [-] User screenshot QA on current iPhone + desktop

## C. Main multi-asset monitor

- [x] B3-style generalized live analysis for user-selected Bithumb KRW assets
- [x] ETH/BTC built-in reference
- [x] Manual holdings / average price / P&L in local SQLite
- [x] Per-ticker averaging-down plans up to 20 rounds
- [x] Suggested entry amount and account percentage on BUY_CANDIDATE
- [x] Telegram automatic alerts reduced to fresh BUY_CANDIDATE only

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
- [ ] Execute the pending work in `MASTER_ROADMAP.md` dependency order; do not jump directly to PAPER v2 before feature collection/shadow validation

## Validation status

- [x] Current adaptive research implementation passed Python tests + module compile
- [x] Current Liquid/research dashboard implementation passed Node dashboard smoke checks
- [x] Current branch passed Cloudflare typecheck
- [x] PR #1 remains Draft and unmerged

## Completion condition

Finish this workstream when mobile/dashboard UX is approved, adaptive per-coin PAPER research has accumulated enough evidence to identify robust candidates rather than lucky short-term winners, backup is verified, phone access is convenient, and the program-level items tracked in `MASTER_ROADMAP.md` have either completed or been explicitly moved to a successor workstream. Real-money execution stays deferred.