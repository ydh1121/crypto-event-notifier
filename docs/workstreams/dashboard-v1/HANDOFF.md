# Dashboard v1 handoff

## Current phase

Phase 4 continuation: local multi-asset PAPER engine + beginner-friendly operational dashboard + secure phone access.

## User-approved scope

Proceed through dashboard redesign, charts/analytics, forward-test persistence, Telegram operational alerts, multi-asset context UI, Git/Drive backup flow, and phone external access.

Do **not** build real-money execution in this workstream. Live execution is a future separate Work/workstream.

## Runtime that already works

- Local FastAPI/Uvicorn server on port 8765
- loopback dashboard authentication without stale-token lockout
- remote/LAN clients require Dashboard token internally
- user-facing name for that secret is now `휴대폰 연결 코드`
- local-PC-only `/api/local/phone-code` can reveal/copy the code; remote clients receive 403
- B3 live market analysis in PAPER mode
- Regime/Entry/context scoring internally
- Bithumb/OKX public market inputs
- PAPER buy/risk-off paths and execution guards
- SQLite journal + portfolio restoration
- GitHub auto-sync on branch `b3-auto-trader-phase1`
- Telegram local configuration + successful test message
- ticker-based multi-asset registry

## Beginner-language rule added 2026-08-24

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

Scores must include both the number and meaning: 0–39 매우 나쁨, 40–54 좋지 않음, 55–64 보통, 65–74 좋음, 75–100 매우 좋음.

`dashboard/plain-language.js` is the current compatibility layer over the redesigned dashboard. `b3_trader/user_language.py` performs centralized Telegram wording conversion before delivery. Permanent rules are in `DESIGN.md` and `AGENTS.md`.

## Design baseline

Primary approved reference: `ydh1121/Photo-eBook` current UI and its `AGENTS.md`, `UI_REGRESSION_SPEC.md`, core tokens/layout/components.

Permanent dashboard design rules live in root `DESIGN.md`. Restart/session rules live in root `AGENTS.md`.

## Current files added/changed for plain language

- `b3_trader/user_language.py`
- `b3_trader/telegram_notify.py`
- `b3_trader/local_app.py`
- `b3_trader/tests/test_user_language.py`
- `dashboard/plain-language.js`
- `dashboard/plain-language.css`
- `dashboard/index.html`
- `.github/workflows/b3-trader-tests.yml`
- `AGENTS.md`
- `DESIGN.md`

## Active task

`B. User visual QA + H. phone access verification`

## Exact next action

1. Wait for/check CI for the plain-language commit set.
2. User pulls `b3-auto-trader-phase1` and restarts local app.
3. User opens dashboard with Ctrl+F5 and checks beginner copy on 개요/자산/성과/설정.
4. Confirm Settings → 휴대폰에서 보기 exposes the local `휴대폰 연결 코드` with 보기/복사 only on 127.0.0.1.
5. Verify same-Wi-Fi phone access using LAN URL + connection code.
6. Run `scripts/setup-phone-access.ps1`, sign in on PC + phone, then verify Tailscale external access.
7. Continue actual screenshot-based spacing/copy QA; keep technical metrics under details.
8. Finish/verify local rclone Google Drive upload path if desired before closing this workstream.

## Safety constraints

- Keep PAPER-only behavior.
- Keep `LIVE_TRADING_ENABLED=false` and do not add live order execution.
- Never commit local tokens/secrets.
- Do not expose port 8765 publicly; Tailscale/LAN only.
- Preserve remote bearer-token authentication.
- The local phone-code reveal endpoint must stay loopback-only.

## Branch / PR

Work continues on `b3-auto-trader-phase1`, existing Draft PR #1. Do not merge unless the user explicitly requests it.
