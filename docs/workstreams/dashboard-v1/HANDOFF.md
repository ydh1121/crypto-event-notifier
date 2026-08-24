# Dashboard v1 handoff

## Current phase

Local multi-asset PAPER monitor + beginner-facing dashboard + secure Cloudflare phone access + adaptive Bithumb-wide per-coin PAPER research.

## Hard boundary

This workstream remains **PAPER-only**. The goal is to use forward-test evidence to find robust candidates before any later live-trading work. Do not add real-money order execution here.

## Runtime / local state

- Windows local PC, FastAPI/Uvicorn on port 8765
- secure launcher binds to `127.0.0.1`
- Cloudflare HTTPS phone access, no phone VPN dependency
- manual holdings/average prices/averaging plans remain in local SQLite
- user-added assets in `control/assets.json` must be preserved
- Telegram automatic delivery remains fresh BUY_CANDIDATE-only
- PR #1 stays Draft and must not be merged without explicit request

## Permanent UI baseline

Use repo `AGENTS.md`, `DESIGN.md`, current Photo-eBook Korean copy rules, mobile regression rules and Liquid navigation reference.

Primary requirements:
- Korean non-trader in their 60s must understand primary surfaces
- decision/action first; technical detail behind secondary disclosure
- iOS focusable controls >=16px
- buttons do not wrap
- native iOS horizontal momentum stays native
- polling must not reset deliberate UI state

## Latest mobile Liquid fix

User screenshot showed two related bugs:
- active top-navigation glass covered the active icon/label, leaving a blank blue pill
- coin selector sometimes appeared as a detached blue circle / oversized blob at the left edge

Current fix:
- visual rail background lives on the outer host/pseudo layer
- moving Liquid indicator is an outer-host sibling at a lower z-layer
- tab/chip label and icon content stays above the Liquid layer
- geometry uses separate horizontal/vertical bleed instead of one oversized 11px value
- top nav uses small bleed; coin chip uses modest horizontal bleed and slightly larger vertical bleed
- active indicator still slightly crosses the rail boundary but should remain visually attached to its chip
- native Safari rail scrolling remains untouched

Files:
- `dashboard/navigation-v3.js`
- `dashboard/navigation-v3.css`

## Adaptive all-market PAPER research

The old model used one shared 10M portfolio and only traded a filtered top-candidate basket. That is no longer the target.

Current model:
- every valid Bithumb KRW market gets its own independent **10,000,000 KRW virtual account**
- all accounts are isolated from one another
- public Bithumb market data only; no API key and no private/order endpoint
- roughly 3-minute full-market sweep
- `AssetStrategy` scores remain inputs, but PAPER trading no longer freezes until legacy BUY_CANDIDATE appears

### Entry behavior

Per market, the engine computes:
- regime score
- entry score
- liquidity score
- opportunity score
- adaptive profile thresholds

Entry intents:
- `buy`: normal/adaptive threshold pass
- `explore`: bounded smaller entry when opportunity is constructive but old fixed threshold is not met
- `idle_explore`: after long inactivity, permit a smaller PAPER probe if risk/opportunity are still acceptable
- `add`: additional PAPER buy after cooldown when opportunity improves

Exploration is intentionally smaller than normal entries. It does not mean forcing trades into poor conditions; very weak opportunity/risk remains `wait`.

### Exits

- hard PAPER stop
- take profit
- trailing giveback after profit is armed
- market-weakness exit
- time/opportunity-decay exit

### Position size

- percentage of that coin's own 10M account
- adaptive base weight, bounded 3–15%
- max position percentage bounded per market
- spread, estimated slippage and BTC flash-crash guards remain active

## Feedback DB / bounded automatic improvement

Database: ignored local `b3_trader/data/auto_demo.sqlite3`.

New research tables persist:
- per-market accounts
- per-market adaptive profiles
- signals / current intent
- fills
- completed-trade feedback
- equity history

After a completed trade the engine stores:
- entry signal snapshot
- holding duration
- realized P/L and return
- profile before update
- profile after update
- learning note/version

Bounded learning behavior:
- winning entry conditions can move that coin's PAPER thresholds toward the successful conditions
- losing entry conditions make that coin's profile more selective
- base PAPER position weight can rise/fall within bounds
- only DB profile parameters change
- Python source code is **not** self-modified
- live trading is never enabled by this learning loop

Future promotion to live trading must use enough samples plus holdout/out-of-sample validation so a short lucky streak is not treated as a robust edge.

## Research dashboard

Generated market detail files: ignored `dashboard/demo-runtime/KRW-XXX.json`.

Home:
- coin-by-coin 10M research status
- current return leader
- market count
- sweep progress
- active PAPER positions

Results:
- `전체 코인 자동매매 연구`
- ranking with return / completed trades / win rate / current intent
- search field
- visible top ranking for quick comparison
- direct ticker + Enter lookup for any scanned KRW market outside the visible top ranking

Per-coin detail:
- current return
- opportunity / regime / entry
- suggested weight
- adaptive profile version and thresholds
- max drawdown
- equity curve
- trade time / side / virtual amount / weight / return / reason
- learning-feedback records with before → after parameters

Files:
- `dashboard/demo-research.js`
- `dashboard/demo-research.css`
- dynamically loaded by `dashboard/navigation-v3.js`

## GitHub -> local auto-sync

The earlier failure mode was: local `control/assets.json` was dirty, so the old startup script skipped all Git updates and the server remained on an old commit.

Current behavior:
- `scripts/run-local.ps1` forces `AUTO_GIT_SYNC=true`
- forces `AUTO_GIT_PUSH_CONTROL=true`
- forces 15-second polling in process environment even if old `.env` has the original value
- if only `control/assets.json` / `control/runtime.json` are dirty, startup runs safe control-preserving repair instead of skipping the update
- unexpected local code changes are still protected from destructive overwrite
- startup prints `GitHub sync: latest (<sha>)` when local and remote match
- dashboard-only changes do not require Uvicorn restart
- `b3_trader/*.py` changes trigger supervised exit code 75 and automatic Python restart

## Validation

Current adaptive research + UI branch updates passed:
- Python tests
- Python module compile
- dashboard Node syntax/smoke checks
- Cloudflare typecheck

## Next verification on the user's machine

1. Wait for running local app to auto-sync current branch; the `auto_demo.py` Python change should trigger the supervised restart automatically.
2. Confirm console reports latest Git sync rather than `Local Git working tree has changes. Startup update was skipped`.
3. On iPhone verify:
   - active top tab shows icon + label over the blue glass
   - coin chip glass remains attached to the selected chip
   - no detached blue circle
4. Home should show `코인별 1,000만원 가상매매`.
5. Results should show `전체 코인 자동매매 연구`.
6. Let the engine complete at least one full Bithumb KRW sweep; per-market detail files appear progressively during the sweep.
7. Leave research running to accumulate trades/profile versions before judging which markets are actually robust.
8. Finish Google Drive/rclone backup verification afterward.

## Safety constraints

- PAPER-only
- no private Bithumb endpoints
- no live order placement
- manual real holdings remain display/calculator inputs only
- keep secrets/runtime DB/generated research data ignored/local
- no public direct exposure of port 8765
- live execution stays deferred to a separate future workstream