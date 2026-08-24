# Dashboard v1 handoff

## Current phase

Phase 4 continuation: local multi-asset PAPER engine + beginner-friendly operational dashboard + secure phone access.

## User-approved scope

Proceed through dashboard redesign, charts/analytics, forward-test persistence, Telegram operational alerts, multi-asset context UI, Git/Drive backup flow, manually entered holdings/averaging tools, and phone external access.

Do **not** build real-money execution in this workstream. Live execution is a future separate Work/workstream.

## Runtime that already works

- Local FastAPI/Uvicorn server on port 8765
- loopback dashboard authentication without stale-token lockout
- remote/LAN clients require Dashboard token internally
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
   - engine now calculates suggested entry KRW amount and percentage of current PAPER account equity
   - BUY_CANDIDATE Telegram messages include recommended percentage + amount
   - asset payload includes `suggested_entry`

4. Telegram noise reduction
   - GitHub sync notifications removed
   - routine engine start/stop notifications removed
   - trading/risk/error/daily-summary notifications remain

5. Tailscale fix
   - PC setup succeeded and Tailscale IPv4 was `100.87.132.38` during user test
   - MagicDNS/`ts.net` name failed on the iPhone over 5G
   - dashboard/network API now prefers direct `http://100.x.x.x:8765`
   - setup script can add a Windows Firewall inbound rule limited to Tailscale `100.64.0.0/10` when run as Administrator
   - user must verify direct 100.x URL with the iPhone Tailscale VPN switch enabled

6. Public-IP warning
   - user showed that a public address `182.212.253.183` could open the dashboard over 5G HTTP
   - this is not an approved access path because the bearer/phone code would travel over unencrypted HTTP
   - once Tailscale works, disable any router port-forwarding/DMZ/UPnP rule that exposes TCP 8765 publicly
   - rotate the phone connection code after discontinuing the public path

7. Git divergence repair
   - user's local branch and GitHub branch diverged because local control commits and GPT remote commits happened concurrently
   - `GitAutoSync` now reconciles control-only divergence instead of failing `merge --ff-only`
   - `scripts/repair-local-sync.ps1` safely realigns code to remote while preserving `control/assets.json` and `control/runtime.json`
   - `.env`, local SQLite, dashboard token, Telegram settings and other ignored local runtime files are not removed by that repair

## Design baseline

Primary approved reference: `ydh1121/Photo-eBook` current UI and its `AGENTS.md`, `UI_REGRESSION_SPEC.md`, core tokens/layout/components.

Permanent dashboard design rules live in root `DESIGN.md`. Restart/session rules live in root `AGENTS.md`.

## Active task

`B. User visual QA + H. phone access verification + G. local Git repair verification`

## Exact next action

1. Check CI for the holdings/calculator/sync/Tailscale commit set.
2. User stops the currently running local app.
3. Because the user's local branch is already diverged, preserve the two `control/*.json` files, reset code to `origin/b3-auto-trader-phase1`, restore those control files, then start the app. After the new code is present, future control-only divergence should self-reconcile.
4. User opens dashboard with Ctrl+F5 and verifies:
   - beginner copy on 개요/자산/성과/설정
   - 자산 → 내 실제 보유분
   - 자산 → 물타기 계산기
   - BUY_CANDIDATE sizing guidance
   - 설정 → 휴대폰에서 보기
5. On the iPhone, open Tailscale, verify the VPN switch is ON and the PC appears in the tailnet.
6. Open direct `http://100.87.132.38:8765` (or the current 100.x address shown by the dashboard), not the `ts.net` hostname.
7. If direct 100.x still fails, rerun `scripts/setup-phone-access.ps1` once in Administrator PowerShell to add the Tailscale-only Windows Firewall rule.
8. After Tailscale succeeds, disable any public 8765 exposure and rotate the phone connection code from the PC dashboard.
9. Finish/verify local rclone Google Drive upload path before closing this workstream.

## Safety constraints

- Keep PAPER-only behavior.
- Keep `LIVE_TRADING_ENABLED=false` and do not add live order execution.
- Never commit local tokens/secrets.
- Do not expose port 8765 publicly; Tailscale/LAN only.
- Preserve remote bearer-token authentication.
- The local phone-code reveal/rotate endpoints must stay loopback-only.
- Manual real holdings are display/calculator inputs only; they must not trigger exchange orders in this workstream.

## Branch / PR

Work continues on `b3-auto-trader-phase1`, existing Draft PR #1. Do not merge unless the user explicitly requests it.
