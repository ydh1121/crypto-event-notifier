# Dashboard v1 workstream tasks

Status legend: `[ ]` pending · `[-]` active · `[x]` complete · `[>]` deferred to later workstream

## A. Continuity and permanent rules

- [x] Add restart-safe repository protocol in `AGENTS.md`
- [x] Add project-specific `DESIGN.md`
- [x] Record Photo-eBook as the primary approved UI baseline
- [x] Make Photo-eBook Korean copy contract + UI regression rules required references for relevant dashboard edits
- [x] Make this workstream the continuation source for future chats/sessions
- [x] Make non-trader/older-adult comprehension a permanent dashboard + Telegram copy requirement

## B. Dashboard information architecture and visual redesign

- [x] Responsive navigation: 홈 / 코인 / 결과 / 기록 / 설정
- [x] Rebuild top shell, KPI hierarchy, cards, spacing, status chips and mobile safe-area behavior
- [x] Group strategy settings by purpose and hide advanced controls by default
- [x] Add beginner-facing copy layer replacing primary Regime/Entry/Context/RISK_OFF/PAPER jargon
- [x] Add plain-language 0–100 meanings
- [x] Show manually entered holdings/average price/P&L prominently
- [x] Preserve `판단 근거 자세히 보기` open/closed state across 5-second polling rerenders
- [x] Prevent iOS focus zoom by enforcing >=16px focusable form text on mobile
- [x] Prevent routine button-label wrapping and normalize mobile action geometry
- [x] Stabilize repeated asset/panel heights when optional holding data is missing
- [x] Remove conflicting legacy mobile calculator grid and leave `navigation-v3.css` as the single mobile `.avg-row` geometry owner
- [x] Use full-width stacked mobile `매수가` / `매수금액` inputs with separate delete control and result row
- [x] Make saved average-price text materially larger on mobile
- [x] Stop P/L from ellipsizing out of view; allow amount + percentage to wrap and stack metrics on narrow phones
- [x] Rebuild Liquid Glass motion from current Photo-eBook contract: one rail/one moving indicator, measured geometry, stretch/overshoot/snap-back spring motion, press response and reduced-motion fallback
- [x] Move selected Liquid indicators to outer overlay hosts; coin selector uses enough bleed to cross the inner rail boundary
- [x] Add static asset cache-bust versions + no-store/no-cache headers for reliable UI update delivery
- [-] User screenshot QA on current desktop + iPhone UI; tune only observed spacing/geometry/copy regressions

## C. Charts and analytics

- [x] Asset price history with PAPER buy/sell markers
- [x] Market-condition + buy-timing history
- [x] Portfolio equity time series
- [x] Range selection: 1H / 6H / 24H / 7D
- [x] Performance summary and per-asset results
- [x] Hide technical factor detail behind `판단 근거 자세히 보기`
- [x] Add ETH/BTC market-reference data derived from ETH-KRW and BTC-KRW
- [ ] Add condition-performance breakdown after enough completed fills exist

## D. Forward-test durability

- [x] Persist portfolio snapshots to SQLite
- [x] Restore PAPER cash/positions from journal fills after restart
- [x] Keep forward-test history across restarts
- [x] Add migration-safe journal/restore tests
- [ ] Preserve the exact same-day drawdown baseline across restart instead of recalculating from restored cost basis

## E. Telegram operations

- [x] Local secret configuration + test message
- [x] Plain-language Telegram copy
- [x] Include suggested entry amount and account percentage on BUY_CANDIDATE
- [x] Remove GitHub sync / start-stop noise
- [x] User policy changed to **automatic BUY_CANDIDATE alerts only**
- [x] Suppress WAIT/RISK_OFF/fill/risk-block/error/daily-summary automatic Telegram noise while retaining dashboard/journal records
- [x] Add tests for the buy-candidate-only policy

## F. Multi-asset workflow

- [x] Ticker-only asset addition starts generic analysis
- [x] Asset profiles support context mode + related markets
- [x] Manually entered holding quantity/average price per ticker in local SQLite
- [x] Per-ticker averaging-down calculator up to 20 rounds
- [x] Suggested entry sizing on BUY_CANDIDATE
- [x] Treat ETH/BTC as a built-in market reference instead of an unsupported KRW asset
- [x] Add isolated 10,000,000 KRW PAPER auto-trading demo scanning Bithumb KRW markets without private credentials
- [x] Demo universe ranking uses liquidity + momentum and existing `AssetStrategy`
- [x] Demo reuses spread/slippage/BTC-flash/order-rate execution guards
- [x] Demo supports adaptive sizing, per-asset cap, total exposure cap, max positions, cooldown averaging and emergency exits
- [x] Demo persists separately in ignored `b3_trader/data/auto_demo.sqlite3`
- [x] Move demo lifecycle inside FastAPI so Git-synced Python runtime updates can start it automatically without a manual launcher restart
- [x] Add authenticated `/api/demo` and Home `1,000만원 자동매매 데모` card
- [ ] Add per-asset analysis/profile notes for GPT-managed refinements
- [-] Run Bithumb-wide PAPER demo long enough to evaluate trade frequency, P/L, drawdown and candidate quality before live execution
- [-] Validate simultaneous multi-asset portfolio limits/context behavior using the user's already-added assets

## G. Backup and synchronization

- [x] GitHub code/control desired-state sync exists
- [x] Local SQLite is the authoritative runtime DB
- [x] Surface backup/sync status
- [x] Control-only Git divergence reconciliation + one-time repair script
- [x] Default GitHub poll reduced to 15 seconds
- [x] Dashboard-only Git commits update local static files without restarting Uvicorn
- [x] Browser watcher reloads dashboard changes for updated/published/reconciled sync states
- [x] Python runtime changes automatically request exit code 75 and the running PowerShell supervisor restarts the app
- [ ] Finish one-time rclone Google Drive setup/documentation
- [ ] Verify consistent SQLite snapshot upload to `Crypto Auto Trader/backups`
- [ ] Mirror non-secret `control/` and `dashboard/` to Drive

## H. Phone / external access

- [x] VPN-free Cloudflare Quick Tunnel launcher: `start-trader-secure.bat`
- [x] Bind local app to `127.0.0.1` in secure mode
- [x] User verified HTTPS Cloudflare access from phone over 5G without VPN
- [x] User verified old public-IP HTTP access is blocked
- [x] Tailscale removed; do not make it the primary path
- [x] Add one-time `scripts/setup-stable-cloudflare.ps1` for persistent named Tunnel + custom hostname
- [x] Secure launcher automatically uses named Tunnel when local stable config exists; otherwise falls back to Quick Tunnel
- [x] Stable hostname preserves browser origin so saved phone connection code persists across server restarts
- [x] Add loopback-only one-tap phone link for Quick Tunnel onboarding using a URL fragment that is immediately cleared after import
- [ ] User runs named-Tunnel setup if a Cloudflare-managed domain is available and verifies fixed URL across restart
- [ ] Rotate phone connection code after stable access is verified because an older code appeared in chat/console logs

## I. Real-money execution

- [>] **DEFERRED — separate future Work/workstream. Do not implement here.**
- [>] Exchange balance as source of truth
- [>] order idempotency/client order identifiers
- [>] partial-fill and open-order reconciliation
- [>] stale order cancellation
- [>] hard daily-loss kill / maximum exposure at exchange balance level
- [>] tightly capped live pilot
- [>] live-mode update/change-approval workflow

## Validation status

- [x] Latest Python tests pass
- [x] Python module compile check passes, including `b3_trader.auto_demo`
- [x] Dashboard JS syntax/smoke checks pass, including final `navigation-v3.js` Liquid overlay layer
- [x] Existing Cloudflare TypeScript check passes
- [-] Re-check latest post-QA branch head after final calculator/Liquid/cache-bust commits

## Completion condition for this workstream

Stop when the redesigned dashboard is user-approved on PC + phone, the isolated 10,000,000 KRW Bithumb-wide PAPER demo has accumulated enough forward-test evidence to judge the strategy, multi-asset PAPER behavior is validated, Google Drive backup is verified, and secure phone access is convenient enough for normal use. Real-money execution remains deferred.