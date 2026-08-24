# Dashboard v1 handoff

## Current phase

Local multi-asset PAPER forward-test console: redesigned dashboard + analytics + secure phone access preparation.

## User-approved scope

Proceed through dashboard redesign, charts/analytics, forward-test persistence, Telegram operational alerts, multi-asset context UI, Git/Drive backup flow, and phone external access.

Do **not** build real-money execution in this workstream. Live execution is a future separate Work/workstream.

## Implemented and validated

- Local FastAPI/Uvicorn server on port 8765
- loopback dashboard authentication without stale-token lockout
- remote/LAN/Tailscale clients still require Dashboard token
- B3 and ticker-added multi-asset PAPER analysis
- Regime / Entry / asset-context diagnostics
- Bithumb + OKX public market inputs
- PAPER buy/risk-off paths and risk guards
- SQLite asset snapshots, fills, events, and portfolio snapshots
- PAPER cash/open-position restoration from persisted fills after restart
- performance analytics: total/realized/unrealized PnL, return, closed trades, win rate, Profit Factor, MDD/current DD
- asset price history + PAPER buy/sell markers
- Regime/Entry history chart
- portfolio equity chart
- 1H / 6H / 24H / 7D chart ranges
- Telegram local configuration + successful test message
- Telegram action/fill/risk-block/error notifications with cooldowns
- 21:00 local PAPER daily summary
- GitHub auto-sync on `b3-auto-trader-phase1`
- responsive 5-view dashboard: 개요 / 자산 / 성과 / 활동 / 설정
- network status API for LAN and Tailscale
- phone-access settings panel with safe URL copy controls
- `scripts/setup-phone-access.ps1` for Tailscale install/sign-in setup
- explicit no-public-port-forwarding rule
- restart-safe `AGENTS.md`, `DESIGN.md`, `TASKS.md`, `HANDOFF.md`

GitHub Actions is green after these changes: Python tests/compile, dashboard JS syntax + smoke, existing Cloudflare TypeScript check.

## Design baseline

Primary approved reference: `ydh1121/Photo-eBook` current UI and its `AGENTS.md`, `UI_REGRESSION_SPEC.md`, core tokens/layout/components.

Permanent dashboard design rules live in root `DESIGN.md`. Restart/session rules live in root `AGENTS.md`.

Reference principles were distilled from the user-supplied public design/Korean-copy repositories. Do not copy third-party identity or large source passages; use the project-specific rules.

## Current active task

User-device verification and visual tuning.

## Exact next action in the current chat

1. Let the running local app auto-pull/restart, or manually run:
   - `git pull --ff-only origin b3-auto-trader-phase1`
   - `.\start-trader.bat`
2. Hard-refresh `http://127.0.0.1:8765` and visually inspect all five views.
3. Fix any screenshot-based spacing/geometry issues without regressing mobile.
4. In Settings > Phone access, verify the same-Wi-Fi URL from a phone.
5. For outside-Wi-Fi access, run `.\scripts\setup-phone-access.ps1`, sign in to Tailscale on PC + phone with the same account, then use the Tailscale URL shown by the dashboard and enter the Dashboard token.
6. Do not router-port-forward 8765.
7. After phone access is confirmed, finish/verify the Google Drive rclone backup path if still desired, then close this workstream at the agreed stopping point.

## Remaining known items before workstream closure

- visual QA from the actual local dashboard screenshots
- exact same-day DD baseline preservation across a restart (current positions/cash/history restore; daily DD baseline may restart from restored cost basis)
- condition-performance breakdown only after enough completed PAPER trades exist
- per-asset GPT research/profile notes
- Google Drive rclone one-time local setup + real upload verification
- same-Wi-Fi phone access verification
- Tailscale external phone access verification

## Safety constraints

- PAPER-only.
- `LIVE_TRADING_ENABLED=false`.
- No live order code in this workstream.
- Never commit local tokens/secrets.
- No public exposure of port 8765.
- Preserve remote bearer-token authentication.

## Branch / PR

Work continues on `b3-auto-trader-phase1`, existing Draft PR #1. Do not merge unless the user explicitly requests it.
