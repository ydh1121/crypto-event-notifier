# Dashboard v1 handoff

## Current phase

Phase 4 continuation: local multi-asset PAPER engine + very simple beginner-facing dashboard + VPN-free secure phone access.

## User-approved scope

Proceed through dashboard redesign, charts/analytics, forward-test persistence, quiet Telegram buy alerts, multi-asset context UI, Git/Drive backup flow, manually entered holdings/averaging tools, and phone external access.

Do **not** build real-money execution in this workstream. Live execution is a future separate Work/workstream.

## Runtime that already works

- Local FastAPI/Uvicorn server on port 8765
- secure launcher binds Uvicorn to `127.0.0.1`
- VPN-free Cloudflare HTTPS phone access works over mobile 5G
- old direct public-IP HTTP access was verified blocked while secure mode is active
- loopback dashboard authentication without stale-token lockout
- remote clients require Dashboard token internally; user-facing name is `휴대폰 연결 코드`
- local-PC-only phone-code reveal/rotate endpoints
- B3-style live analysis generalized to multiple Bithumb KRW tickers
- Bithumb/OKX public market inputs
- PAPER buy/risk-off paths and execution guards
- SQLite journal + portfolio restoration
- local SQLite stores manually entered real holding quantity/average price and per-ticker averaging plans
- user has already added multiple assets and entered average prices locally; do not overwrite local control/runtime/SQLite state
- GitHub auto-sync on branch `b3-auto-trader-phase1`
- Telegram is configured and test messages work

## Permanent UI/copy baseline

- Read repo `AGENTS.md` and `DESIGN.md` first.
- For Korean UI copy, apply the current Photo-eBook `docs/spec-v1/20-korean-copywriting-skill.md`.
- For mobile Safari/interaction regression work, apply the current Photo-eBook `UI_REGRESSION_SPEC.md`.
- Primary comprehension target: Korean non-trader in their 60s.
- Put the user decision/action first; technical reasons stay behind `판단 근거 자세히 보기`.
- iOS focusable form controls must be >=16 px.
- button labels must not wrap at supported widths.
- repeated cards/panels keep stable geometry.
- 5-second polling must not reset deliberate UI state.

## Latest UX fixes — 2026-08-24

1. Live-refresh disclosure stability
   - problem: `판단 근거 자세히 보기` collapsed every 5 seconds because `refreshState()` rebuilt `renderSelectedAsset()`.
   - `dashboard/ux-stability.js` now remembers disclosure state per selected market in localStorage and restores it after rerender.

2. iPhone input zoom + button geometry
   - `dashboard/ux-polish.css` is loaded last.
   - mobile focusable inputs/selects/textareas are >=16 px to prevent Safari focus zoom.
   - routine button/copy/tab labels are nowrap with consistent 46 px control height.
   - calculator/action button groups reflow as grids instead of wrapping text.
   - asset cards reserve consistent rows when holding data is absent.

3. ETH/BTC
   - do not register ETH/BTC as a KRW asset.
   - `b3_trader/factors.py` derives ETH/BTC ratio from ETH-KRW / BTC-KRW prices and derives 24h relative change from ETH/BTC returns.
   - Home market summary shows ETH/BTC in plain language (`ETH가 더 강함`, `BTC가 더 강함`, `비슷한 흐름`).
   - entering ETH/BTC in the ticker box explains that it is already monitored as a market reference.

4. Telegram policy
   - automatic Telegram delivery is now BUY_CANDIDATE-only.
   - WAIT/RISK_OFF/fills/risk blocks/errors/daily summaries remain in journal/dashboard and do not generate Telegram noise.
   - manual Telegram test still calls direct `send()` and remains available.

5. Phone restart convenience
   - Quick Tunnel still works as fallback but changes URL on restart.
   - new one-time `scripts/setup-stable-cloudflare.ps1` configures a persistent named Cloudflare Tunnel using a hostname on a domain already managed by the user's Cloudflare account.
   - `start-trader-secure.bat` / `run-local-cloudflare.ps1` automatically use the stable named Tunnel when local stable config exists; otherwise Quick Tunnel is used.
   - stable config/credentials live under ignored `b3_trader/data/` paths only.
   - stable hostname keeps the same browser origin, so the saved phone connection code remains in localStorage across server restarts.
   - for Quick Tunnel fallback, loopback PC UI can generate a one-tap phone link with `#connect=<code>`; the remote page imports it then immediately removes the URL fragment.

## Current phone-access decision

- User does not want a phone VPN dependency and uninstalled Tailscale.
- Primary path: Cloudflare HTTPS Tunnel.
- Best long-term local-PC workflow: one-time named Tunnel + fixed custom hostname, then always launch `start-trader-secure.bat`.
- If no Cloudflare-managed domain is available, continue Quick Tunnel and use the PC-generated one-tap link to avoid manually typing the connection code.
- Do not reintroduce public port forwarding.

## Git/CI state

- Work continues on `b3-auto-trader-phase1`, Draft PR #1; do not merge without explicit request.
- Local `control/assets.json` may remain modified because the user added assets locally.
- Current change set adds/updates: `ux-stability.js`, `ux-polish.css`, dashboard index wiring, BUY-only Telegram policy, ETH/BTC factor details, stable Cloudflare setup/launcher/status, tests, CI checks, and permanent repo rules.
- Latest CI must be checked after the final commits before calling this unit complete.

## Active task

`B. screenshot-based UX QA + F. multi-asset validation + G. Google Drive backup`

## Exact next action

1. Check latest GitHub Actions for the current branch and fix any failures.
2. User updates local code safely while preserving locally added assets/holdings, restarts `start-trader-secure.bat`, and verifies:
   - disclosure stays open across 5-second refreshes
   - averaging inputs no longer zoom on iPhone
   - buttons remain one line
   - asset cards/sections look geometrically consistent
   - Home shows ETH/BTC reference
   - Telegram stays quiet unless a coin newly becomes BUY_CANDIDATE
3. If the user has a Cloudflare-managed domain, run `scripts/setup-stable-cloudflare.ps1` once, then restart and verify the same HTTPS URL works after another restart without re-entering the phone connection code.
4. If no domain is available, verify the Quick Tunnel `휴대폰용 링크 복사` convenience from the loopback PC settings.
5. Rotate the phone connection code after access is stable because an older code appeared in console/chat logs.
6. Continue screenshot-based mobile/desktop QA.
7. Finish rclone Google Drive backup and validate simultaneous multi-asset portfolio/context behavior.
8. Leave real-money trading deferred to the separate future Work/workstream.

## Safety constraints

- Keep PAPER-only behavior.
- Keep `LIVE_TRADING_ENABLED=false` and do not add live order execution.
- Never commit local tokens/secrets, Cloudflare credentials, or public IP addresses.
- Do not expose port 8765 directly to the public internet.
- Preserve remote bearer-token authentication.
- Local phone-code reveal/rotate/onboarding generation stays loopback-only.
- Manual real holdings are display/calculator inputs only; they must not trigger exchange orders in this workstream.
