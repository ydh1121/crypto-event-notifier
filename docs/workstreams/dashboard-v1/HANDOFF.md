# Dashboard v1 handoff

## Current phase

Local multi-asset PAPER monitor + beginner-facing dashboard + secure Cloudflare phone access + adaptive Bithumb-wide per-coin PAPER research.

## Hard boundary

This workstream remains **PAPER-only**. Use forward-test evidence to find robust candidates before any later live-trading work. Do not add real-money order execution here.

## Runtime / local state

- Windows local PC, FastAPI/Uvicorn on port 8765
- secure launcher binds to `127.0.0.1`
- Cloudflare HTTPS phone access; no phone VPN dependency
- manual holdings/average prices/averaging plans remain in local SQLite
- user-added assets in `control/assets.json` must be preserved
- Telegram automatic delivery remains fresh BUY_CANDIDATE-only
- PR #1 stays Draft and must not be merged without explicit request

## Permanent UI baseline — Photo-eBook is canonical

Before modifying navigation, read the current Photo-eBook sources:
- `docs/spec-v1/06-liquid-navigation.md`
- `UI_REGRESSION_SPEC.md`
- `public/assets/js/ui/liquid-controller.js`
- `public/assets/styles/ui/liquid-skin.css`
- `public/assets/styles/desktop/nav-corrections.css`

Required Liquid contract:
- **one rail = one moving indicator = one nested skin = one controller**
- actual glass material belongs to the rail; shell/wrapper stays visually transparent
- moving indicator is a **direct child of the rail**
- indicator geometry uses active button `offsetLeft`, `offsetTop`, `offsetWidth`, `offsetHeight`
- active button/icon/text remains the real clickable element at a higher z-layer; never clone its content into the indicator and never hide the active button with `opacity:0`
- selected button paints blue only as a first-paint fallback; after controller ready, only the moving indicator paints blue
- approved Breeze easing: `cubic-bezier(0.34, 1.56, 0.64, 1)`
- browser owns native horizontal momentum; no JS `scrollLeft`/`scrollIntoView` loop and no custom pointer/touch pan for the nav rail
- PC top rail is `width:max-content`, centered on the actual chip group; never stretch a grey/glass rail across the viewport
- mobile rail keeps native Safari scrolling and approved safe-area behavior
- do not add a second navigation controller or a second moving indicator

Current implementation files:
- `dashboard/navigation-v3.js`
- `dashboard/navigation-v3.css`
- build marker: `UI 2026.08.24-8`

## Chrome freeze root cause and fix

The experimental `research-capital.js` used a broad `MutationObserver` on `document.body`. A mutation inside `#demoResearch` triggered `renderAggregate()`, which wrote `innerHTML` back inside `#demoResearch`, which could trigger the same observer again. With the full Bithumb universe this could form a high-frequency self-triggering DOM loop and freeze Chrome.

Current rule:
- no broad body MutationObserver for research decoration
- `research-capital.js` uses bounded 15-second data polling plus explicit coin-selection refresh only
- only write aggregate/detail DOM when the rendered value signature changed
- research assets load directly from `dashboard/index.html`; navigation code does not dynamically own research loading

## Browser / Git synchronization ownership

Do **not** reintroduce multiple sync/reload owners.

Current architecture:
- **one Git sync owner:** Python `GitAutoSync`
- `scripts/run-local.ps1` forces `AUTO_GIT_SYNC=true`, `AUTO_GIT_PUSH_CONTROL=true`, 15-second polling
- local `control/assets.json` and `control/runtime.json` are preserved while remote application code updates
- unexpected local code edits still fail closed
- dashboard-only file updates do not require Uvicorn restart
- `b3_trader/*.py` updates trigger supervised exit code 75 and automatic Python restart
- secure Cloudflare launcher no longer starts the experimental external `git-sync-watch.ps1`
- browser no longer force-reloads itself on every Git commit; user refresh is allowed and preferred over reload loops
- `dashboard/runtime-build.json` remains ignored so a stale experimental file cannot dirty/block the worktree

## Adaptive all-market PAPER research

- every valid Bithumb KRW market gets its own independent **10,000,000 KRW virtual account**
- accounts are isolated
- public Bithumb data only; no private/order endpoint
- roughly 3-minute full-market sweep
- `AssetStrategy` remains an input, but bounded `explore` / `idle_explore` entries prevent waiting forever for one legacy threshold
- staged additions, adaptive sizing, spread/slippage/BTC flash guards
- hard stop, dynamic take profit, trailing protection, market weakness and time/opportunity decay exits
- per-market adaptive profile changes are bounded DB parameters; Python source never self-modifies

## Research dashboard

Home:
- coin-by-coin 10M research status
- current return leader
- market count / scan progress / active positions / freshness

Results:
- full Bithumb KRW universe, scrollable and searchable
- filters: all / holding / completed-waiting / untraded / profit / loss
- sorts include return, position value, unrealized P/L, trade count, win rate, drawdown, opportunity and current price

Per-coin detail prioritizes:
- current price
- average entry
- current position value / weight
- realized and unrealized P/L
- next planned entry/add
- expected buy rounds
- dynamic target / stop / trailing protection
- market-memory history for later AI analysis
- fills and bounded learning feedback

Generated data remains local/ignored:
- `b3_trader/data/auto_demo.sqlite3`
- `dashboard/demo-runtime/KRW-XXX.json`

## Immediate verification after 2026-08-24-8

Because the previous running launcher may still contain the retired external watchdog and the browser may already be frozen, do one clean bootstrap/restart once:

1. Close the frozen Chrome tab/window.
2. Stop the current secure launcher with `Ctrl+C`.
3. Run safe `repair-local-sync.ps1` from the latest remote branch, preserving control state.
4. Confirm local HEAD equals `origin/b3-auto-trader-phase1`.
5. Start `start-trader-secure.bat` once.
6. Confirm console says `GitHub sync: in-app single owner (15s, local coin settings preserved)`.
7. Confirm Settings shows only one build card: `UI 2026.08.24-8`.
8. Verify PC top nav is one compact centered glass capsule and mobile active icon/label remains visible above the moving Liquid skin.
9. Verify Chrome remains responsive while Results updates.

## Safety constraints

- PAPER-only
- no private Bithumb endpoints
- no live order placement
- manual real holdings remain display/calculator inputs only
- keep secrets/runtime DB/generated research data ignored/local
- no public direct exposure of port 8765
- live execution stays deferred to a separate future workstream
