# Dashboard v1 handoff

## Current phase

Phase 4 continuation: local multi-asset PAPER engine + very simple beginner-facing dashboard + VPN-free secure phone access.

## User-approved scope

Proceed through dashboard redesign, charts/analytics, forward-test persistence, Telegram operational alerts, multi-asset context UI, Git/Drive backup flow, manually entered holdings/averaging tools, and phone external access.

Do **not** build real-money execution in this workstream. Live execution is a future separate Work/workstream.

## Runtime that already works

- Local FastAPI/Uvicorn server on port 8765
- secure launcher binds Uvicorn to `127.0.0.1`
- VPN-free Cloudflare Quick Tunnel HTTPS phone access works over mobile 5G
- old direct public-IP HTTP access was verified blocked while secure mode is active
- loopback dashboard authentication without stale-token lockout
- remote clients require Dashboard token internally
- user-facing name for that secret is `휴대폰 연결 코드`
- local-PC-only phone-code reveal/rotate endpoints
- B3-style live analysis generalized to multiple Bithumb KRW tickers
- Regime/Entry/context scoring remains internal
- Bithumb/OKX public market inputs
- PAPER buy/risk-off paths and execution guards
- SQLite journal + portfolio restoration
- local SQLite stores manually entered real holding quantity/average price and per-ticker averaging plans
- user has already added multiple assets and entered average prices locally; do not overwrite local control/runtime/SQLite state
- GitHub auto-sync on branch `b3-auto-trader-phase1`
- Telegram local configuration + successful alerts

## User-facing language rule

The primary UI and Telegram messages must make sense to a Korean non-trader in their 60s.

Internal vocabulary remains valid in code/logs, but primary surfaces use:

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
- User confirmed the Cloudflare URL opens successfully on mobile 5G without VPN.
- User confirmed the old public-IP HTTP path is blocked in secure mode.
- Quick Tunnel URLs can change on restart. Stable named Cloudflare Tunnel is an optional later improvement.

## Latest dashboard simplification pass

`dashboard/plain-language.js` and `dashboard/plain-language.css` were rewritten to make the product decision-first and much less technical.

Key changes:

- top-level tabs shown as `홈 / 코인 / 결과 / 기록 / 설정`
- mobile uses a fixed five-item bottom navigation
- product title simplified to `코인 상태판`
- home hero explains only the core question: buy now or wait
- engine pause/resume/emergency controls moved out of Home and into Settings → safety controls
- strategy/risk numeric settings collapsed behind `고급 설정 보기`
- actual saved holdings are summarized on Home using the local `/api/holdings` data
- each holding row shows ticker, average price, value and current return, and opens that coin directly
- watchlist cards are decision-first: `매수 후보 / 기다림 / 지켜보기 / 지금은 매수하지 않음`
- saved average price and unrealized PnL appear directly on asset cards when present
- score detail is reduced to compact market/timing summaries on cards
- asset detail shows current price, saved average price, actual unrealized PnL, decision sentence, then three plain-language score blocks
- technical factors remain under `왜 이렇게 판단했는지 자세히 보기`
- cards/shadows/spacing were reduced for a calmer Photo-eBook-like grouped layout
- mobile KPI cards are compact 2x2 instead of tall full-width cards
- charts remain available but no longer dominate the first screen

## Git state

- The user's diverged local branch was repaired against `origin/b3-auto-trader-phase1` while preserving local data.
- `control/assets.json` may remain locally modified by design.
- Secure-launcher and latest simplified-dashboard changes both passed CI.

## Active task

`B. screenshot-based simplified UI QA + G. Google Drive backup + F. multi-asset validation`

## Exact next action

1. Let the local secure launcher auto-sync or pull the latest branch, then restart if required.
2. Open PC and phone dashboards and verify the new `홈 / 코인 / 결과 / 기록 / 설정` UI.
3. On Home, verify `내 코인 현황` correctly reflects all locally saved holdings/average prices and current PnL without mixing tickers.
4. On Coin, verify each selected ticker loads its own saved holding and averaging-down plan.
5. Send screenshots of Home, Coin detail, and the averaging calculator; tune geometry/copy only from those screenshots.
6. Rotate the phone connection code because an earlier code appeared in console/chat logs.
7. Finish one-time rclone Google Drive setup and verify SQLite snapshot upload to `Crypto Auto Trader/backups`.
8. Validate simultaneous multi-asset limits/context behavior using the already-added local assets.
9. Leave real-money trading deferred to the separate future Work/workstream.

## Safety constraints

- Keep PAPER-only behavior.
- Keep `LIVE_TRADING_ENABLED=false` and do not add live order execution.
- Never commit local tokens/secrets or public IP addresses.
- Do not expose port 8765 directly to the public internet.
- Prefer VPN-free HTTPS Cloudflare Tunnel for phone access.
- Preserve remote bearer-token authentication.
- Local phone-code reveal/rotate endpoints must stay loopback-only.
- Manual real holdings are display/calculator inputs only; they must not trigger exchange orders in this workstream.

## Branch / PR

Work continues on `b3-auto-trader-phase1`, existing Draft PR #1. Do not merge unless the user explicitly requests it.