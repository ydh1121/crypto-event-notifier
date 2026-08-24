# Dashboard v1 handoff

## Current phase

Phase 4 continuation: local multi-asset PAPER engine + beginner-facing dashboard + secure Cloudflare phone access + isolated Bithumb-wide 10M KRW automatic PAPER demo.

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

Observed on iPhone/Chrome device emulation: the first averaging row still collapsed into an awkward multi-column legacy layout.

Final fix:
- removed the conflicting mobile `.avg-row` grid from `portfolio-tools.css`; that file now explicitly leaves mobile calculator geometry to `navigation-v3.css`
- mobile `.avg-row` is forced to **flex-column**
- round number sits at top-left
- delete button is absolutely positioned top-right
- `매수가` and `매수금액` each get a full-width 52 px input on their own row
- input text is 16 px
- calculated after-average message gets a separate full-width block
- action buttons use two columns; `계획 비우기` gets its own full row

### 2. Average price and P/L readability

- saved average-price value is about 26–27 px on phone
- P/L amount and percentage are separate inline pieces and may wrap instead of ellipsizing
- <=430 px puts average-price and P/L tiles in one column so neither value is sacrificed

### 3. Liquid Glass selector now floats outside the rail

- scrollable rail remains the native iOS scrollport
- moving indicator is mounted in an **outer overlay host** (`.view-rail` for primary tabs and `.asset-chip-shell` for coin chips)
- geometry is translated from `getBoundingClientRect()` into host coordinates
- primary tab indicator uses a small outer bleed
- coin-chip indicator uses an 11 px bleed, enough to cross the inner rail padding/border and visibly float outside it
- horizontal scroll updates overlay position while Safari momentum remains native
- motion is stretch -> overshoot -> snap-back with the approved spring family
- press interaction compresses the liquid skin slightly
- `prefers-reduced-motion` remains supported

### 4. GitHub -> local automatic synchronization

- default remote polling interval is 15 seconds
- static `dashboard/*.js|css|html` commits fast-forward locally without restarting Uvicorn
- dashboard watcher reloads for `updated`, `published`, and `reconciled` sync paths
- `b3_trader/*.py` runtime changes request exit code 75 and the already-running PowerShell supervisor restarts the Python app automatically
- user should not normally stop/re-run `start-trader-secure.bat` for GitHub commits
- control-only local state remains preserved/reconciled
- unexpected non-control local code changes block auto-update instead of being destroyed
- `index.html` uses v5/v2 cache-busts for final navigation/calculator files; static headers request no-store/no-cache

### 5. Existing stability fixes retained

- `판단 근거 자세히 보기` state survives polling rerenders
- mobile inputs avoid Safari focus zoom
- routine button labels stay one line
- ETH/BTC remains a built-in market reference, not a fake KRW asset
- Telegram remains BUY_CANDIDATE-only

## Isolated 10,000,000 KRW automatic PAPER demo

The demo is owned by the **FastAPI app lifecycle**, not by a one-time child process created only when the shell launcher starts.

Core rules:
- start capital: 10,000,000 KRW
- public Bithumb endpoints only; no private/order endpoints and no API key required
- scans Bithumb KRW markets roughly every 3 minutes
- excludes BTC, ETH and major stablecoins from candidate trading
- filters low turnover and extreme 24h moves
- ranks liquidity + momentum, then applies existing `AssetStrategy`
- entry still requires existing `BUY_CANDIDATE`
- adaptive entry sizing from 500,000 KRW base
- max per asset 3,000,000 KRW
- max total exposure 6,000,000 KRW
- max simultaneous positions 4
- reuses spread/slippage/BTC flash-crash/order-rate guards
- additional PAPER buys only after cooldown while BUY_CANDIDATE persists and caps permit
- exit on -8% hard PAPER stop or regime score below 45
- sell uses order-book-estimated executable price when available

Lifecycle/persistence/UI:
- separate ignored SQLite: `b3_trader/data/auto_demo.sqlite3`
- generated ignored runtime status: `dashboard/runtime-demo.json`
- local app starts/supervises the demo thread when `AUTO_DEMO_ENABLED` is not false
- `/api/demo` exposes authenticated demo status
- Home always mounts `1,000만원 자동매매 데모`, showing virtual equity, cash, held symbols and current candidates
- demo never contaminates the main PAPER portfolio or manually entered real holdings

## Current phone-access decision

- User does not want a phone VPN dependency and removed Tailscale.
- Primary path: Cloudflare HTTPS Tunnel.
- Best long-term workflow: one-time named Tunnel + fixed custom hostname, then always launch `start-trader-secure.bat`.
- Quick Tunnel remains fallback.
- Do not reintroduce public port forwarding.

## Git/CI state

- Work continues on `b3-auto-trader-phase1`, Draft PR #1; do not merge without explicit request.
- `b433747f4c6db916d869b08de849a3250e1663a4` passed dashboard smoke, Python tests/compile and Cloudflare typecheck.
- Later functional QA commits remove conflicting calculator CSS, increase Liquid bleed and bump cache versions; re-check latest head CI before declaring the visual fix complete.
- Local `control/assets.json` may remain modified because the user added assets locally.
- Runtime data under `b3_trader/data/` and generated `dashboard/runtime-demo.json` remain ignored by Git.

## Active task

`B. iPhone screenshot QA + F. Bithumb-wide 10M PAPER forward test + G. Google Drive backup`

## Exact next action

1. Let the running local app receive the bootstrap update. Python changes should auto-exit with code 75 and be restarted by the already-running supervisor; do not manually restart the launcher unless this fails.
2. Refresh an already-open browser once after that bootstrap runtime restart. Future dashboard-only commits should self-reload.
3. Verify Home shows `1,000만원 자동매매 데모` and `/api/demo` updates.
4. Verify Coin: full-width stacked averaging inputs, larger avg price, visible P/L, coin Liquid selector crossing the rail and springing.
5. Leave the demo running to collect trade count, P/L, drawdown, concentration and candidate-quality evidence.
6. Finish Google Drive/rclone backup after UI/demo validation.
7. Keep real-money trading deferred.

## Safety constraints

- Keep all exchange execution PAPER-only.
- Keep `LIVE_TRADING_ENABLED=false`.
- Auto demo uses only public Bithumb market endpoints.
- Never commit local tokens/secrets, Cloudflare credentials, public IPs or runtime SQLite files.
- Do not expose port 8765 publicly.
- Preserve remote bearer-token authentication.
- Local phone-code reveal/rotate/onboarding stays loopback-only.
- Manual real holdings are display/calculator inputs only.