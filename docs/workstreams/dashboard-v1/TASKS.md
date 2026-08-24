# Dashboard v1 workstream tasks

Status legend: `[ ]` pending · `[-]` active · `[x]` complete · `[>]` deferred to later workstream

## A. Continuity and permanent rules

- [x] Add restart-safe repository protocol in `AGENTS.md`
- [x] Add project-specific `DESIGN.md`
- [x] Record Photo-eBook as the primary approved UI baseline
- [x] Record external design/Korean-copy references as distilled guidance, not code/content to blindly copy
- [x] Make this workstream the continuation source for future chats/sessions

## B. Dashboard information architecture and visual redesign

- [-] Replace the single long page with responsive view navigation: 개요 / 자산 / 성과 / 활동 / 설정
- [ ] Rebuild top shell, KPI hierarchy, cards, spacing, status chips, mobile safe-area behavior
- [ ] Remove the current narrow-left-content / empty-right-space desktop feel
- [ ] Group strategy settings by purpose instead of one dense matrix
- [ ] Keep all existing controls functional through the redesign

## C. Charts and analytics

- [ ] Add asset price history API and chart with PAPER buy/sell markers
- [ ] Add Regime + Entry score history chart
- [ ] Add portfolio equity/exposure/drawdown time series
- [ ] Add range selection (1H / 6H / 24H / 7D where enough data exists)
- [ ] Add performance summary: total return, realized/unrealized PnL, closed trades, win rate, profit factor, MDD/current DD
- [ ] Add condition diagnostics showing why an asset is WATCH / WAIT_PULLBACK / BUY_CANDIDATE / RISK_OFF
- [ ] Add condition-performance breakdown once enough fills exist

## D. Forward-test durability

- [ ] Persist portfolio snapshots to SQLite
- [ ] Restore PAPER cash/positions from the journal after app restart
- [ ] Keep forward-test history across code/server restarts
- [ ] Add migration-safe tests for journal/restore behavior

## E. Telegram operations

- [x] Telegram local secret configuration from dashboard
- [x] Test message works
- [ ] Alert on important action changes only, with debounce/cooldown
- [ ] Alert on PAPER fills and risk-off exits
- [ ] Alert on risk blocks (spread/slippage/BTC flash) only when materially new
- [ ] Alert on engine/system errors with anti-spam cooldown
- [ ] Add daily PAPER performance summary

## F. Multi-asset workflow

- [x] Ticker-only asset addition starts generic analysis
- [x] Asset profiles support context mode + related markets
- [ ] Improve asset detail UI to expose context basket and factor contribution
- [ ] Add per-asset analysis/profile notes for GPT-managed refinements
- [ ] Validate multi-asset portfolio limits with several simultaneous assets

## G. Backup and synchronization

- [x] GitHub code/control desired-state sync exists
- [x] Local SQLite is the authoritative runtime DB
- [ ] Surface backup age/status clearly in dashboard
- [ ] Finish one-time rclone Google Drive setup flow/documentation
- [ ] Verify consistent SQLite snapshot upload to `Crypto Auto Trader/backups`
- [ ] Mirror `control/` and `dashboard/` to Drive without secrets

## H. Phone / external access — current stopping point

- [ ] Add network-access status API (LAN address + Tailscale installed/connected state)
- [ ] Add phone-access panel in settings with copyable safe URL and token guidance
- [ ] Add `scripts/setup-phone-access.ps1` to install/open Tailscale with user approval
- [ ] Verify same-Wi-Fi phone access
- [ ] Verify Tailscale external phone access
- [ ] Confirm remote clients still require Dashboard token
- [ ] Explicitly warn against public port-forwarding of 8765

## I. Real-money execution

- [>] **DEFERRED — separate future Work/workstream. Do not implement here.**
- [>] Exchange balance as source of truth
- [>] order idempotency/client order identifiers
- [>] partial-fill and open-order reconciliation
- [>] stale order cancellation
- [>] hard daily-loss kill / maximum exposure at exchange balance level
- [>] tightly capped live pilot
- [>] live-mode update/change-approval workflow

## Completion condition for this workstream

This workstream stops when the redesigned dashboard, analytics/graphs, durable PAPER forward test, Telegram operations, Git/Drive backup path, multi-asset views, and secure phone external access are usable and verified. Real-money trading remains deferred.
