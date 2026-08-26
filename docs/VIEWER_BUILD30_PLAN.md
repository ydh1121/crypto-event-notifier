# VIEWER BUILD 30 PLAN

## Scope
Build 30 keeps the approved information architecture and changes dashboard interaction behavior to feel like a live exchange UI.

## Confirmed defects
1. The sector route existed in navigation and `main.js`, but `core/router.js` did not allow the `sectors` route. Clicking Sector therefore fell back to Dashboard.
2. Dashboard watchlist rows were display-only. They need direct navigation into Research with the matching exchange and market already selected.
3. Dashboard subscribed to each snapshot by calling the full `render()` path. This replaced the dashboard DOM even when only a price, score, PnL or sector value changed.
4. Sector flow was rebuilt as part of the full dashboard render and then fetched again.
5. Recent activity was still visually too wide for the amount of information shown.

## Live refresh audit
- Header freshness/status: already patches text only. Keep.
- Records feed: already inserts new rows in-place with `feed.prepend`. Keep.
- Dashboard asset allocation: change only value text, donut background and keyed legend rows.
- Dashboard exchange market state: change only score text, meters and counts.
- Dashboard PAPER summary: change only PnL/return/account values.
- Dashboard watchlist: reconcile keyed market rows; keep existing DOM nodes and reorder only when ranking changes.
- Dashboard sector flow: reconcile keyed sector rows; do not replace the whole card.
- Dashboard strategy validity: change only candidate/warming/rejected values.
- Dashboard recent activity: reconcile keyed event rows and animate only new rows.
- Sector detail page: user-driven renders remain acceptable; no periodic whole-page refresh is introduced in this build.

## Navigation behavior
- Add `sectors` to the router allow-list.
- Dashboard watchlist row -> set `researchExchange`, `researchMarket`, clear search/filter -> Research.
- Dashboard recent activity row -> same direct Research jump.
- Dashboard sector row -> set `sectorExchange`, `sectorSelected` -> Sector detail.
- Sector coin row -> matching Research detail.

## Recent activity density
- Reduce the activity area to a compact two-column bottom workspace.
- Left: recent events.
- Right: live summary rail with 1H event count, buy/sell count, learning count, best opportunity and top sector.
- Show short clock time in rows; full local timestamp is retained in the title tooltip.

## Update feedback
Only changed numeric values receive a short restrained highlight (`value-tick`). The card itself does not flash or remount.

## Next bundle
After Build 30 browser QA passes:
1. strategy equity curve
2. strategy-by-coin performance
3. coin × strategy comparison
4. total PAPER equity / drawdown
