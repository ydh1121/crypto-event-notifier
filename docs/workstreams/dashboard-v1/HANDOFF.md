# Dashboard v1 handoff

## Current phase

Phase 4 continuation: local multi-asset PAPER engine + beginner-facing dashboard + secure Cloudflare phone access + isolated Bithumb-wide auto PAPER demo.

## User-approved scope

Proceed through dashboard redesign, charts/analytics, forward-test persistence, quiet Telegram buy alerts, multi-asset context UI, Git/Drive backup flow, manually entered holdings/averaging tools, secure phone access, and a **real-market-data / fake-money** automatic trading demo before any real-order work.

Do **not** build real-money execution in this workstream. Live execution remains a future separate Work/workstream.

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
- Telegram is configured; automatic delivery is intentionally BUY_CANDIDATE-only

## Permanent UI/copy baseline

- Read repo `AGENTS.md` and `DESIGN.md` first.
- For Korean UI copy, apply the current Photo-eBook `docs/spec-v1/20-korean-copywriting-skill.md`.
- For mobile Safari/interaction regression work, apply the current Photo-eBook `UI_REGRESSION_SPEC.md`.
- For Liquid Glass selector work, use Photo-eBook `docs/spec-v1/06-liquid-navigation.md` plus the approved `interaction-liquid-taffy` reference.
- Primary comprehension target: Korean non-trader in their 60s.
- Put the user decision/action first; technical reasons stay behind `판단 근거 자세히 보기`.
- iOS focusable form controls must be >=16 px.
- button labels must not wrap at supported widths.
- repeated cards/panels keep stable geometry.
- 5-second polling must not reset deliberate UI state.

## Latest screenshot QA fixes — 2026-08-24

### 1. Averaging calculator layout

Observed on iPhone: the first averaging row collapsed into a narrow two-column shape, labels/inputs were vertically misaligned, and the remove control competed with the amount input.

Current fix in `dashboard/navigation-v3.css`:
- mobile `.avg-row` has one explicit geometry owner
- grid areas are `round/remove`, then full-width `price`, full-width `amount`, then `after`
- inputs are full-width, 50 px high, 16 px text
- action buttons and summary are separated by explicit spacing
- existing 20-round persistence/calculation behavior is unchanged

### 2. Average price and P/L readability

Observed on iPhone: saved average-price text was too small and current P/L was ellipsized, hiding the percentage/value.

Current fix:
- average-price value is roughly 24–25 px on phone
- current P/L gets more horizontal share at wider phone widths
- P/L amount and percentage are rendered as separate inline pieces and may wrap instead of disappearing
- <=430 px switches the two metrics to one column so neither value is sacrificed

### 3. Liquid Glass motion

The previous implementation mostly looked like a blue selected pill; it did not reproduce the approved spring/taffy feel.

Current implementation in `dashboard/navigation-v3.js` + `.css` follows the Photo-eBook contract:
- one rail = one moving indicator = one geometry/motion owner
- geometry comes from the active item's real `offsetLeft/Top/Width/Height`
- active button itself does not paint a second blue plate after indicator mount
- move animation uses stretch -> overshoot -> snap-back keyframes
- approved spring family includes `cubic-bezier(0.34, 1.56, 0.64, 1)`
- press interaction compresses the surface slightly
- native iOS horizontal scrolling remains native; no custom touch momentum is installed
- `prefers-reduced-motion` falls back to static/quiet motion

Photo-eBook's current contract explicitly says horizontal rails should keep native iOS scrolling and **must not** add custom touch/pointer momentum; the "rubber" character belongs to the moving Liquid indicator, not a JavaScript replacement for Safari scrolling.

### 4. Existing stability fixes retained

- `판단 근거 자세히 보기` open state survives 5-second rerenders
- mobile inputs avoid Safari focus zoom
- routine button labels stay one line
- ETH/BTC remains a built-in market reference, not a fake KRW asset
- Telegram remains BUY_CANDIDATE-only

## New isolated 10,000,000 KRW automatic PAPER demo

User requested a demo before real execution that automatically searches the full Bithumb KRW market and trades suitable coins with a 10,000,000 KRW virtual seed.

Implemented as `b3_trader/auto_demo.py` and intentionally isolated from the existing manual/watchlist PAPER portfolio.

Core rules:
- start capital: 10,000,000 KRW
- public Bithumb endpoints only; **no API key and no private/order endpoint calls**
- scans the current Bithumb KRW market list every ~3 minutes
- excludes BTC, ETH and major stablecoins from candidate trading
- filters out low-turnover assets and extreme 24h moves
- ranks the liquid universe using liquidity + momentum, then applies the existing `AssetStrategy` to top candidates
- entry requires existing `BUY_CANDIDATE` logic rather than a new unrelated signal model
- adaptive base order starts from 500,000 KRW and uses the existing regime/entry confidence sizing function
- max per-asset virtual position: 3,000,000 KRW
- max total virtual exposure: 6,000,000 KRW
- max simultaneous positions: 4
- existing execution-risk logic is reused for spread, estimated slippage, BTC flash-crash and order-rate limits
- the same asset can receive an additional PAPER buy only after cooldown while BUY_CANDIDATE still holds and caps permit it
- exit on hard PAPER stop at -8% or broad-regime score below 45
- sell fill uses order-book-estimated executable price when available

Persistence/UI:
- separate SQLite: `b3_trader/data/auto_demo.sqlite3`
- generated dashboard state: ignored `dashboard/runtime-demo.json`
- `scripts/run-local.ps1` starts the demo automatically unless local environment sets `AUTO_DEMO_ENABLED=false`
- if the demo process dies while the main launcher is alive, the launcher restarts it
- Home dashboard gets a `1,000만원 자동매매 데모` card showing virtual equity, cash, held symbols and current candidates
- this experiment never changes manually entered real holdings and never places real orders

## Current phone-access decision

- User does not want a phone VPN dependency and removed Tailscale.
- Primary path: Cloudflare HTTPS Tunnel.
- Best long-term workflow: one-time named Tunnel + fixed custom hostname, then always launch `start-trader-secure.bat`.
- Quick Tunnel remains the fallback.
- Do not reintroduce public port forwarding.

## Git/CI state

- Work continues on `b3-auto-trader-phase1`, Draft PR #1; do not merge without explicit request.
- Latest functional head before this handoff update: `6e1791ef0af1e80d8e7440babde760e7d415ead1`.
- GitHub Actions run for that functional head completed successfully: dashboard smoke, Python tests/compile, and Cloudflare typecheck all passed.
- Local `control/assets.json` may remain modified because the user added assets locally.
- Runtime data under `b3_trader/data/` and generated `dashboard/runtime-demo.json` remain ignored by Git.

## Active task

`B. iPhone screenshot QA + F. Bithumb-wide 10M PAPER forward test + G. Google Drive backup`

## Exact next action

1. Let the user's local auto-sync receive the new branch head, or restart `start-trader-secure.bat` once if the new demo process is not running yet.
2. On iPhone reload the current Cloudflare HTTPS page and verify:
   - averaging rows are stacked cleanly and no input/removal button overlaps
   - `내 평단` is clearly larger
   - `현재 손익` amount and percentage are both visible
   - moving blue Liquid selector visibly stretches/overshoots/springs when changing top navigation or coin chips
3. On Home verify `1,000만원 자동매매 데모` appears and updates independently of the main PAPER account.
4. Leave the demo running. Evaluate candidate quality, trade count, realized P/L, total return, drawdown and concentration before changing thresholds or discussing live execution.
5. Capture new Home/Coin screenshots after the branch is active; tune only observed regressions.
6. Finish rclone Google Drive backup verification after UI/demo validation.
7. Leave real-money trading deferred to the separate future Work/workstream.

## Safety constraints

- Keep all exchange execution PAPER-only.
- Keep `LIVE_TRADING_ENABLED=false`; do not add live order execution here.
- The isolated auto demo must use only public Bithumb market endpoints.
- Never commit local tokens/secrets, Cloudflare credentials, public IPs or runtime SQLite files.
- Do not expose port 8765 directly to the public internet.
- Preserve remote bearer-token authentication.
- Local phone-code reveal/rotate/onboarding generation stays loopback-only.
- Manual real holdings are display/calculator inputs only; they must not trigger exchange orders in this workstream.