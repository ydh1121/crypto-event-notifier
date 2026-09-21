# Viewer Build 29 work contract

Build 29 keeps the approved information architecture and changes density, hierarchy, live behavior and sector research only.

## 1. Common component polish

- Replace colored filter pills with quiet Apple-style text chips.
- Selected filters use white surface + hairline + one small blue indicator instead of a filled blue/black capsule.
- Buy/sell/learning record badges use neutral surfaces; semantic color is reduced to a small dot.
- Financial figures remain tabular and non-wrapping.

## 2. Records and comparison density

- Records feed is constrained to a readable width and gets a compact right-side summary rail on desktop.
- PAPER exchange comparison is constrained to a narrower table width.
- Search/filter controls remain above the feed and keep focus during background polling.

## 3. PAPER selected-coin hierarchy

Primary values:
1. average buy price
2. current holding value
3. realized P/L
4. win rate
5. next entry/add price
6. target price
7. hard stop
8. suggested weight

Cash, unrealized P/L, split progress and remaining split count stay visible but secondary.

## 4. Main dashboard hierarchy

The dashboard must show these surfaces before long lists:

1. actual asset allocation donut + total P/L rate
2. Bithumb/Upbit market-state summary with visual score hierarchy
3. total PAPER P/L + exchange PAPER P/L
4. scrollable watch candidates
5. sector money-concentration summary
6. strategy validity summary
7. compact recent changes feed

`전략 유효성` means PAPER experiments that pass the current sample/risk/performance gates. It is not automatic live-strategy promotion.

## 5. Sector research

Add a dedicated `섹터` page.

- Aggregate Bithumb/Upbit market-detail data by sector.
- Use 24h turnover, rising-coin turnover share, turnover-weighted change, opportunity score and PAPER position concentration.
- The money-flow indicator is explicitly a trading-concentration proxy, not exchange deposit/withdrawal net flow.
- Persist sector snapshots in Cloudflare D1 so later strategy research can use accumulated history.
- Show sector ranking, selected-sector history and top constituent coins.

## 6. Live row insertion

- Records polling must not rebuild the search box or steal focus.
- New records are inserted at the top only.
- New dashboard activity rows and record rows receive a short translate/fade animation.
- Existing rows do not replay the animation on every poll.
- Respect `prefers-reduced-motion` through the global token contract.

## 7. Local sync runtime temp files

Generated atomic temp names such as `dashboard/runtime-demo-upbit.json.tmp` are runtime files, not user code changes.

- Ignore them in Git.
- Treat `dashboard/runtime-demo*.tmp` as safe in `repair-local-sync.ps1`.
- Do not broaden the exemption to arbitrary source files.

## 8. Next bundle

After Build 29 browser QA passes, continue with:

1. strategy equity curve
2. per-strategy coin performance
3. coin × strategy comparison
4. total PAPER equity / drawdown
