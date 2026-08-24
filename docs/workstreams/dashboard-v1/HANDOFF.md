# Dashboard v1 handoff

## Current phase

Phase 4 continuation: local multi-asset PAPER engine + beginner-friendly operational dashboard + secure phone access.

## User-approved scope

Proceed through dashboard redesign, charts/analytics, forward-test persistence, Telegram operational alerts, multi-asset context UI, Git/Drive backup flow, manually entered holdings/averaging tools, and phone external access.

Do **not** build real-money execution in this workstream. Live execution is a future separate Work/workstream.

## Runtime that already works

- Local FastAPI/Uvicorn server on port 8765
- loopback dashboard authentication without stale-token lockout
- remote clients require Dashboard token internally
- user-facing name for that secret is `휴대폰 연결 코드`
- local-PC-only `/api/local/phone-code` can reveal/copy the code; remote clients receive 403
- local-PC-only phone-code rotation endpoint can replace an exposed/old code without deleting other local data
- B3 live market analysis in PAPER mode
- Regime/Entry/context scoring internally
- Bithumb/OKX public market inputs
- PAPER buy/risk-off paths and execution guards
- SQLite journal + portfolio restoration
- local SQLite also stores manually entered real holding quantity/average price and per-ticker averaging plans
- GitHub auto-sync on branch `b3-auto-trader-phase1`
- Telegram local configuration + successful test message
- ticker-based multi-asset registry

## User-facing language rule

Primary UI and Telegram messages must make sense to a Korean non-trader in their 60s.

Internal vocabulary remains valid in code/logs, but the primary mapping is:

- Regime → `전체 시장 분위기`
- Entry → `지금 매수 타이밍`
- Context → `비슷한 코인들의 흐름`
- RISK_OFF → `지금은 매수하지 않음`
- WAIT_PULLBACK → `가격이 내려오길 기다림`
- WATCH → `조금 더 지켜보기`
- PAPER → `가상매매`
- DD → `하락폭`
- realized PnL → `확정 손익`
- Profit Factor → `번 돈 ÷ 잃은 돈`

Scores include both number and meaning: 0–39 매우 나쁨, 40–54 좋지 않음, 55–64 보통, 65–74 좋음, 75–100 매우 좋음.

## Changes added after user phone/Telegram QA on 2026-08-24

1. `b3_trader/user_tools.py`
   - manual holding quantity + average price per market
   - averaging-down plans saved per market, up to 20 rows
   - calculations are stored in the same local SQLite database so normal DB backup includes them
   - no exchange-account connection; these are manual records only

2. `dashboard/portfolio-tools.js` + `dashboard/portfolio-tools.css`
   - `내 실제 보유분` panel in the asset view
   - holding cost/current value/unrealized PnL
   - saved averaging calculator with round-by-round expected average price
   - BUY_CANDIDATE sizing guide
   - public HTTP/WAN access warning
   - local phone-code rotation control

3. Entry sizing
   - engine calculates suggested entry KRW amount and percentage of current PAPER account equity
   - BUY_CANDIDATE Telegram messages include recommended percentage + amount
   - asset payload includes `suggested_entry`

4. Telegram noise reduction
   - GitHub sync notifications removed
   - routine engine start/stop notifications removed
   - trading/risk/error/daily-summary notifications remain

5. Phone-access decision
   - Tailscale setup on the PC succeeded, but the user does not want to depend on a phone VPN client.
   - a `100.x` Tailscale address is expected to be unreachable from the phone when the Tailscale VPN switch is off.
   - Tailscale remains an optional path only; it is no longer the primary recommendation.
   - primary VPN-free path is now Cloudflare Tunnel over HTTPS.
   - `scripts/run-local-cloudflare.ps1` and `start-trader-secure.bat` start the local trader bound to `127.0.0.1` and a Cloudflare Quick Tunnel to that loopback service.
   - the generated `https://*.trycloudflare.com` URL is written to `b3_trader/data/cloudflare-tunnel-url.txt` while the secure launcher is running and is surfaced by `/api/network`.
   - Quick Tunnel URLs are temporary and can change on restart. They are acceptable for current PAPER/mobile verification; a stable named Cloudflare Tunnel can be configured later if desired.
   - the phone dashboard UI now treats VPN-free Cloudflare HTTPS as the primary external-access method and leaves Tailscale under optional alternatives.

6. Public-IP exposure
   - the user verified over 5G that the dashboard is still reachable through a public-IP HTTP path.
   - this is not an approved access path because the bearer/phone code can travel over unencrypted HTTP and TCP 8765 is exposed inbound.
   - do not record the user's public IP in repository documentation.
   - the secure Cloudflare launcher overrides `DASHBOARD_HOST=127.0.0.1`, so even if a router forwarding rule still exists the trader itself does not listen on LAN/WAN interfaces during secure mode.
   - after secure mode is verified, remove any router port-forwarding/DMZ/UPnP exposure for TCP 8765 and rotate the phone connection code.

7. Git divergence repair
   - user's local branch and GitHub branch diverged because local control commits and GPT remote commits happened concurrently
   - `GitAutoSync` reconciles control-only divergence instead of repeatedly failing `merge --ff-only`
   - `scripts/repair-local-sync.ps1` safely realigns code to remote while preserving `control/assets.json` and `control/runtime.json`
   - `.env`, local SQLite, dashboard token, Telegram settings and other ignored local runtime files are not removed by that repair

## Design baseline

Primary approved reference: `ydh1121/Photo-eBook` current UI and its `AGENTS.md`, `UI_REGRESSION_SPEC.md`, core tokens/layout/components.

Permanent dashboard design rules live in root `DESIGN.md`. Restart/session rules live in root `AGENTS.md`.

## Active task

`B. User visual QA + H. VPN-free phone access verification + G. local Git repair verification`

## Exact next action

1. User stops the currently running `start-trader.bat` process with Ctrl+C.
2. Because the local branch has diverged, fetch the latest `scripts/repair-local-sync.ps1`, run it once, and verify code matches `origin/b3-auto-trader-phase1` while preserving local control/data.
3. Start with `start-trader-secure.bat`, not the normal launcher.
4. Verify the PowerShell output shows a generated `https://*.trycloudflare.com` address.
5. Open that HTTPS address on the iPhone over 5G without a VPN and enter the phone connection code.
6. Confirm the old public-IP `http://...:8765` path no longer opens while secure mode is running. If it still opens, inspect which process/interface is listening on 8765 before changing router settings.
7. Once HTTPS phone access works, remove any router port-forwarding/DMZ/UPnP exposure for TCP 8765 and rotate the phone connection code.
8. Continue screenshot-based mobile dashboard QA and finish/verify local rclone Google Drive upload path before closing this workstream.

## Safety constraints

- Keep PAPER-only behavior.
- Keep `LIVE_TRADING_ENABLED=false` and do not add live order execution.
- Never commit local tokens/secrets or public IP addresses.
- Do not expose port 8765 directly to the public internet.
- Prefer VPN-free HTTPS Cloudflare Tunnel for current phone access; Tailscale is optional only.
- Preserve remote bearer-token authentication.
- The local phone-code reveal/rotate endpoints must stay loopback-only.
- Manual real holdings are display/calculator inputs only; they must not trigger exchange orders in this workstream.

## Branch / PR

Work continues on `b3-auto-trader-phase1`, existing Draft PR #1. Do not merge unless the user explicitly requests it.
