# Dashboard v1 workstream tasks

Status legend: `[ ]` pending · `[-]` active · `[x]` complete · `[>]` deferred to later workstream

## A. Continuity and permanent rules

- [x] Add restart-safe repository protocol in `AGENTS.md`
- [x] Add project-specific `DESIGN.md`
- [x] Record Photo-eBook as the primary approved UI baseline
- [x] Record external design/Korean-copy references as distilled guidance, not code/content to blindly copy
- [x] Make this workstream the continuation source for future chats/sessions

## B. Dashboard information architecture and visual redesign

- [x] Replace the single long page with responsive view navigation: 개요 / 자산 / 성과 / 활동 / 설정
- [x] Rebuild top shell, KPI hierarchy, cards, spacing, status chips, mobile safe-area behavior
- [x] Remove the current narrow-left-content / empty-right-space desktop feel
- [x] Group strategy settings by purpose instead of one dense matrix
- [x] Keep existing controls wired through the redesign
- [-] User visual QA on the live local dashboard; tune spacing/geometry only from actual screenshots

## C. Charts and analytics

- [x] Add asset price history API and chart with PAPER buy/sell markers
- [x] Add Regime + Entry score history chart
- [x] Add portfolio equity time series
- [x] Persist exposure/drawdown in portfolio history payloads
- [x] Add range selection (1H / 6H / 24H / 7D)
- [x] Add performance summary: total return, realized/unrealized PnL, closed trades, win rate, profit factor, MDD/current DD
- [x] Add condition diagnostics showing why an asset is WATCH / WAIT_PULLBACK / BUY_CANDIDATE / RISK_OFF
- [ ] Add condition-performance breakdown after enough completed fills exist to make it meaningful

## D. Forward-test durability

- [x] Persist portfolio snapshots to SQLite
- [x] Restore PAPER cash/positions from journal fills after app restart
- [x] Keep forward-test fills/history across code/server restarts
- [x] Add migration-safe journal/restore tests
- [ ] Preserve the exact same-day drawdown baseline across a restart instead of recalculating from restored cost basis

## E. Telegram operations

- [x] Telegram local secret configuration from dashboard
- [x] Test message works
- [x] Alert on important action changes with cooldown
- [x] Alert on PAPER fills and risk-off exits
- [x] Alert on risk blocks (spread/slippage/BTC flash) with anti-spam cooldown
- [x] Alert on engine/asset errors with anti-spam cooldown
- [x] Add daily PAPER performance summary

## F. Multi-asset workflow

- [x] Ticker-only asset addition starts generic analysis
- [x] Asset profiles support context mode + related markets
- [x] Improve asset detail UI to expose context basket and factor contribution
- [ ] Add per-asset analysis/profile notes for GPT-managed refinements
- [ ] Validate multi-asset portfolio limits with several simultaneous assets

## G. Backup and synchronization

- [x] GitHub code/control desired-state sync exists
- [x] Local SQLite is the authoritative runtime DB
- [x] Surface backup/sync status in the redesigned dashboard
- [ ] Finish one-time rclone Google Drive setup flow/documentation
- [ ] Verify consistent SQLite snapshot upload to `Crypto Auto Trader/backups`
- [ ] Mirror `control/` and `dashboard/` to Drive without secrets

## H. Phone / external access — current stopping point

- [x] Add network-access status API (LAN address + Tailscale installed/connected state)
- [x] Add phone-access panel in settings with copyable safe URL and token guidance
- [x] Add `scripts/setup-phone-access.ps1` to install/open Tailscale with user approval
- [ ] Verify same-Wi-Fi phone access on the user's device
- [ ] Verify Tailscale external phone access on the user's device
- [x] Keep remote clients behind Dashboard token authentication
- [x] Explicitly warn against public port-forwarding of 8765

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

- [x] Python tests pass in GitHub Actions
- [x] Python module compile check passes
- [x] Dashboard JS `node --check` passes
- [x] Dashboard structural smoke checks pass
- [x] Existing Cloudflare TypeScript check remains green

## Completion condition for this workstream

This workstream stops when the redesigned dashboard, analytics/graphs, durable PAPER forward test, Telegram operations, Git/Drive backup path, multi-asset views, and secure phone external access are usable and verified. Real-money trading remains deferred.
