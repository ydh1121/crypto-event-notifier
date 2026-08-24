# Dashboard v1 workstream tasks

Status legend: `[ ]` pending · `[-]` active · `[x]` complete · `[>]` deferred to later workstream

## A. Continuity and permanent rules

- [x] Add restart-safe repository protocol in `AGENTS.md`
- [x] Add project-specific `DESIGN.md`
- [x] Record Photo-eBook as the primary approved UI baseline
- [x] Record external design/Korean-copy references as distilled guidance, not code/content to blindly copy
- [x] Make this workstream the continuation source for future chats/sessions
- [x] Make non-trader/older-adult comprehension a permanent dashboard + Telegram copy requirement

## B. Dashboard information architecture and visual redesign

- [x] Replace the single long page with responsive view navigation: 개요 / 자산 / 성과 / 활동 / 설정
- [x] Rebuild top shell, KPI hierarchy, cards, spacing, status chips, mobile safe-area behavior
- [x] Remove the current narrow-left-content / empty-right-space desktop feel
- [x] Group strategy settings by purpose instead of one dense matrix
- [x] Keep existing controls wired through the redesign
- [x] Add a beginner-facing copy layer that replaces Regime/Entry/Context/RISK_OFF/PAPER/DD/Profit Factor on primary surfaces
- [x] Add plain-language 0–100 score meanings: 매우 나쁨 / 좋지 않음 / 보통 / 좋음 / 매우 좋음
- [-] User visual QA on the live local dashboard; tune spacing/geometry/copy only from actual screenshots

## C. Charts and analytics

- [x] Add asset price history API and chart with PAPER buy/sell markers
- [x] Add Regime + Entry score history chart
- [x] Add portfolio equity time series
- [x] Persist exposure/drawdown in portfolio history payloads
- [x] Add range selection (1H / 6H / 24H / 7D)
- [x] Add performance summary: total return, realized/unrealized PnL, closed trades, win rate, profit factor, MDD/current DD
- [x] Add condition diagnostics showing why an asset is WATCH / WAIT_PULLBACK / BUY_CANDIDATE / RISK_OFF
- [x] Hide technical factor detail behind `왜 이렇게 판단했는지 자세히 보기` while keeping the primary decision plain
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
- [x] Translate outgoing trading jargon into ordinary Korean before delivery
- [x] Include suggested entry amount and account percentage on BUY_CANDIDATE alerts
- [x] Remove GitHub-sync and routine engine start/stop Telegram noise
- [x] Add tests for score meaning and Telegram jargon translation

## F. Multi-asset workflow

- [x] Ticker-only asset addition starts generic analysis
- [x] Asset profiles support context mode + related markets
- [x] Improve asset detail UI to expose context basket and factor contribution
- [x] Add manually entered real holding quantity/average-price records per ticker in local SQLite
- [x] Add per-ticker averaging-down calculator with up to 20 saved rounds
- [x] Show current-value/unrealized-PnL summary for manually entered holdings
- [x] Show suggested entry sizing on the asset screen when a BUY_CANDIDATE appears
- [ ] Add per-asset analysis/profile notes for GPT-managed refinements
- [ ] Validate multi-asset portfolio limits with several simultaneous assets

## G. Backup and synchronization

- [x] GitHub code/control desired-state sync exists
- [x] Local SQLite is the authoritative runtime DB
- [x] Surface backup/sync status in the redesigned dashboard
- [x] Add control-only divergence reconciliation so dashboard-generated Git commits do not permanently break auto-sync
- [x] Add `scripts/repair-local-sync.ps1` for safe one-time branch repair while preserving control files
- [ ] Finish one-time rclone Google Drive setup flow/documentation
- [ ] Verify consistent SQLite snapshot upload to `Crypto Auto Trader/backups`
- [ ] Mirror `control/` and `dashboard/` to Drive without secrets

## H. Phone / external access — current stopping point

- [x] Add network-access status API
- [x] Add phone-access panel with connection-code guidance
- [x] Rename Dashboard token to user-facing `휴대폰 연결 코드`
- [x] Add loopback-only reveal/rotate endpoints for the phone connection code
- [x] Add Tailscale setup as an optional path
- [x] Confirm Tailscale 100.x requires the phone VPN switch to be ON
- [x] User declined VPN-dependent phone access as the primary path and uninstalled Tailscale
- [x] Add VPN-free Cloudflare Quick Tunnel launcher: `start-trader-secure.bat`
- [x] Bind the trader to 127.0.0.1 in secure launcher mode so router forwarding cannot directly reach the app
- [x] Surface current `https://*.trycloudflare.com` URL through `/api/network`
- [x] Make VPN-free HTTPS Cloudflare access the primary phone-access UI
- [x] Keep public HTTP/WAN access warning visible
- [x] Repair the user's diverged local branch and pull the secure launcher
- [x] Verify `start-trader-secure.bat` generates an HTTPS Quick Tunnel URL
- [x] Verify iPhone/phone 5G access to the Cloudflare HTTPS URL with no VPN
- [ ] Verify old public-IP `http://...:8765` access stops while secure launcher is active
- [ ] Remove router port-forwarding/DMZ/UPnP exposure after the HTTPS path works
- [ ] Rotate the phone connection code after public exposure is removed
- [ ] Decide whether to keep temporary Quick Tunnel URLs or configure a stable named Cloudflare Tunnel later

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

- [x] Holdings/calculator/sync baseline CI green
- [x] VPN-free Cloudflare tunnel changes CI green
- [x] Python module compile check passes
- [x] Dashboard JavaScript checks pass
- [x] Existing Cloudflare TypeScript check remains green

## Completion condition for this workstream

This workstream stops when the redesigned dashboard, analytics/graphs, durable PAPER forward test, Telegram operations, Git/Drive backup path, multi-asset views, VPN-free secure phone external access, and user-facing holdings/averaging tools are usable and verified. Real-money trading remains deferred.
