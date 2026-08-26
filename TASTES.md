# TASTES.md

## REJECT
- Do not change the approved information architecture just to make a screen look newer.
- Do not use black filled pills for routine selected filters.
- Do not stack border + shadow + tinted background on every container.
- Do not let financial values wrap onto two lines; reduce dense KPI type before breaking the number.
- Do not use decorative gradients, glow, oversized gauges, or dashboard ornament that does not improve a trading decision.
- Do not shrink desktop metadata below 11px or focused mobile form controls below 16px.

## REQUIRE
- Use Apple system typography and Korean system fallbacks; financial figures use tabular lining numerals.
- Default palette: ink `#1D1D1F`, grouped canvas `#F5F5F7`, white surfaces, one action blue `#0066CC`, restrained semantic green/red.
- Use an 8/12/16/20/24 spacing rhythm with small optical corrections only when needed.
- Prefer hairline dividers and grouped surfaces over visible card chrome; shadows must be subtle.
- Use compact 8–10px-radius segmented controls and filter chips with neutral default / blue-tinted selected state.
- Every interactive control needs clear hover, pressed and keyboard-focus feedback; press scale stays subtle and fast.
- Preserve inputs, selected ranges and scroll position during live polling.
- Keep the existing master/detail and page structure unless the user explicitly asks to change it.

## WHEN AMBIGUOUS
- Subtract before adding.
- Prefer Apple HIG restraint plus Coinbase-like institutional financial density over generic SaaS dashboard styling.
- Optimize first-glance scanability: decision, price, average price, P/L, recommended level, then supporting detail.
