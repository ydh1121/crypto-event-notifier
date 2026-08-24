# Dashboard v1 handoff

## Current phase

Phase 4 continuation: local multi-asset PAPER engine + beginner-friendly operational dashboard + secure phone access.

## User-approved scope

Proceed through dashboard redesign, charts/analytics, forward-test persistence, Telegram operational alerts, multi-asset context UI, Git/Drive backup flow, manually entered holdings/averaging tools, and phone external access.

Do **not** build real-money execution in this workstream. Live execution is a future separate Work/workstream.

## Runtime that already works

- Local FastAPI/Uvicorn server on port 8765
- secure launcher binds Uvicorn to `127.0.0.1`
- VPN-free Cloudflare Quick Tunnel HTTPS phone access works over mobile 5G
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
- local SQLite stores manually entered real holding quantity/average price and per-ticker averaging plans
- GitHub auto-sync on branch `b3-auto-trader-phase1`
- Telegram local configuration + successful alerts
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

## Current phone-access decision

- User does not want a phone VPN dependency and uninstalled Tailscale.
- Primary external phone path is Cloudflare Tunnel over HTTPS.
- `start-trader-secure.bat` launches the local trader on loopback and creates a temporary `https://*.trycloudflare.com` URL.
- User confirmed that the Cloudflare URL opens successfully on mobile 5G without VPN.
- Quick Tunnel URLs can change on restart. Stable named Cloudflare Tunnel is an optional later improvement, not required for current PAPER testing.
- Direct public-IP HTTP access is not approved and must be removed/disabled after verification.

## Current dashboard/tooling status

- Photo-eBook-inspired responsive shell: 개요 / 자산 / 성과 / 활동 / 설정
- price, score and portfolio charts
- beginner-facing plain-language decision copy
- Telegram important-event alerts, with GitHub sync/startup noise removed
- per-ticker manually entered holding quantity + average price
- per-ticker averaging-down calculator up to 20 rounds
- suggested entry amount + account percentage on BUY_CANDIDATE
- local SQLite runtime persistence
- GitHub desired-state sync and restart-safe workstream docs

## Git state

- The user's diverged local branch was successfully repaired against `origin/b3-auto-trader-phase1` while preserving local control/runtime data.
- `control/assets.json` may remain locally modified by design.
- Latest Cloudflare launcher fixes passed CI.

## Active task

`B. mobile/desktop visual QA + G. Google Drive backup + H. public exposure cleanup`

## Exact next action

1. While `start-trader-secure.bat` is running, verify the old public-IP `http://...:8765` address no longer opens from 5G.
2. If the public path still opens, inspect `Get-NetTCPConnection -LocalPort 8765 -State Listen` and remove any leftover old trader process; then disable any router port-forwarding/DMZ/UPnP exposure for TCP 8765.
3. Rotate the phone connection code from the local PC dashboard because an earlier code appeared in console/chat logs.
4. Continue screenshot-based mobile dashboard QA, prioritizing ordinary Korean copy and removing remaining technical labels from primary surfaces.
5. Verify the new `내 실제 보유분`, `물타기 계산기`, and recommended entry-size UI on phone and desktop.
6. Finish one-time rclone Google Drive setup and verify SQLite snapshot upload to `Crypto Auto Trader/backups`.
7. Add one or more additional tickers and validate multi-asset simultaneous limits/context behavior.
8. Leave real-money trading deferred to the separate future Work/workstream.

## Safety constraints

- Keep PAPER-only behavior.
- Keep `LIVE_TRADING_ENABLED=false` and do not add live order execution.
- Never commit local tokens/secrets or public IP addresses.
- Do not expose port 8765 directly to the public internet.
- Prefer VPN-free HTTPS Cloudflare Tunnel for phone access.
- Preserve remote bearer-token authentication.
- The local phone-code reveal/rotate endpoints must stay loopback-only.
- Manual real holdings are display/calculator inputs only; they must not trigger exchange orders in this workstream.

## Branch / PR

Work continues on `b3-auto-trader-phase1`, existing Draft PR #1. Do not merge unless the user explicitly requests it.
