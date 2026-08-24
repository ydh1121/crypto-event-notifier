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
   - `dashboard/ux-stability.js` remembers disclosure state per selected market in localStorage and restores it after rerender.

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
   - automatic Telegram delivery is BUY_CANDIDATE-only.
   - WAIT/RISK_OFF/fills/risk blocks/errors/daily summaries remain in journal/dashboard and do not generate Telegram noise.
   - manual Telegram test still calls direct `send()` and remains available.

5. Phone restart convenience
   - Quick Tunnel still works as fallback but changes URL on restart.
   - one-time `scripts/setup-stable-cloudflare.ps1` configures a persistent named Cloudflare Tunnel using a hostname on a domain already managed by the user's Cloudflare account.
   - `start-trader-secure.bat` / `run-local-cloudflare.ps1` automatically use the stable named Tunnel when local stable config exists; otherwise Quick Tunnel is used.
   - stable config/credentials live under ignored `b3_trader/data/` paths only.
   - stable hostname keeps the same browser origin, so the saved phone connection code remains in localStorage across server restarts.
   - for Quick Tunnel fallback, loopback PC UI can generate a one-tap phone link with `#connect=<code>`; the remote page imports it then immediately removes the URL fragment.

6. Dashboard UX v2 — current visual baseline
   - user rejected the previous large-card/mobile-tab presentation as too bulky and generic.
   - mobile navigation is now a floating bottom dock, not the large icon row at the top.
   - navigation uses one consistent inline-SVG line icon family; emoji/glyph-style icons are removed.
   - mobile header is reduced to a small `코인 상태판` row plus connection state.
   - desktop navigation is a compact segmented control rather than a full-width heavy rail.
   - asset detail is price-first: `현재 가격` is the dominant number (roughly 41–44 px mobile, larger desktop), followed by 24h change, saved average price and current P/L.
   - watch cards also promote current price to a primary 24–26 px number rather than small metadata.
   - Telegram/backup/phone/system English micro-kickers are hidden on mobile; developer status strings such as `blocked_dirty_worktree`, `idle`, and `PAPER` are translated to ordinary Korean.
   - remote phone settings no longer show the long active Cloudflare URL as a large block; a connected phone sees a compact `외부 연결 정상` summary.
   - calculator summary values are nowrap/ellipsis-protected to avoid splitting long numbers across multiple lines.
   - chart range buttons use one quiet segmented-control style; cards use softer borders/shadows and less redundant decoration.
   - this v2 pass is implemented in the final-loaded `dashboard/ux-polish.css` and `dashboard/ux-stability.js`, so trading-engine behavior is unchanged.

## Current phone-access decision

- User does not want a phone VPN dependency and uninstalled Tailscale.
- Primary path: Cloudflare HTTPS Tunnel.
- Best long-term local-PC workflow: one-time named Tunnel + fixed custom hostname, then always launch `start-trader-secure.bat`.
- If no Cloudflare-managed domain is available, continue Quick Tunnel and use the PC-generated one-tap link to avoid manually typing the connection code.
- Do not reintroduce public port forwarding.

## Git/CI state

- Work continues on `b3-auto-trader-phase1`, Draft PR #1; do not merge without explicit request.
- Local `control/assets.json` may remain modified because the user added assets locally.
- Current change set includes the dashboard UX v2 in `ux-stability.js` + `ux-polish.css`, BUY-only Telegram policy, ETH/BTC factor details, stable Cloudflare setup/launcher/status, tests, CI checks, and permanent repo rules.
- Check the workflow for the latest branch head before calling the unit complete.

## Active task

`B. screenshot-based UX v2 QA + F. multi-asset validation + G. Google Drive backup`

## Exact next action

1. Check latest GitHub Actions for the current branch and fix any failures.
2. User updates local code safely while preserving locally added assets/holdings and restarts `start-trader-secure.bat`.
3. On iPhone verify the UX v2 specifically:
   - navigation appears as the floating bottom dock, not a large row at the top
   - `코인` detail shows a much larger current price
   - current price on watch cards is clearly readable
   - settings no longer exposes `blocked_dirty_worktree`, `idle`, `PAPER`, or long Cloudflare URL blocks
   - calculator numbers/buttons do not wrap awkwardly and form focus does not zoom
   - disclosure stays open across 5-second refreshes
4. Capture Home, Coin, and Settings screenshots and tune only observed spacing/geometry issues.
5. If the user has a Cloudflare-managed domain, run `scripts/setup-stable-cloudflare.ps1` once and verify the same HTTPS URL survives restart.
6. Rotate the phone connection code after access is stable because an older code appeared in console/chat logs.
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
