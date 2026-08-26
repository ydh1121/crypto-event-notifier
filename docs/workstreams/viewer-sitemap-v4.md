# Crypto Research Viewer — Sitemap v4

## Global navigation

Primary navigation has exactly four destinations.

1. Dashboard (`home`)
2. Research (`coin`)
3. PAPER (`results`)
4. Assets (`assets`)

System status is a utility destination opened from the freshness/status control. It is not a primary navigation item.

## Dashboard

Question answered: **What requires my attention now?**

Order of regions:

1. Alerts / opportunities
2. Actual-asset summary
3. Market-state summary
4. Combined Bithumb + Upbit PAPER PnL
5. PAPER active-position count
6. Research candidates
7. Exchange-level PAPER summary

Rules:
- No full holding table.
- No strategy table.
- No long trade history.
- Dashboard must fit the main monitoring information in one desktop viewport where practical.

## Research

Question answered: **Which coin deserves attention, and what is the current judgement?**

Desktop layout:

- Left rail
  1. Exchange scope
  2. Market-state metrics
  3. Search
  4. Priority watchlist
- Main workspace
  1. Current judgement
  2. Selected coin / current price
  3. Regime / entry / opportunity scores
  4. Decision evidence and diagnostics
  5. Supporting chart/context
  6. Compact PAPER reference for the selected coin

Rules:
- Do not show the full Strategy Lab.
- Do not show portfolio management tools by default.
- Selecting a research candidate stays inside Research.
- PAPER navigation must be explicit, never automatic.

## PAPER

Question answered: **Is the research system performing well in simulated trading?**

Secondary navigation:

1. Summary — default
2. Coin performance
3. Strategy comparison
4. Trade records
5. Exchange comparison

### PAPER / Summary

1. Combined Bithumb + Upbit PnL
2. Combined return
3. Combined equity / starting research capital
4. Combined active positions
5. Strategy validation status
6. Bithumb summary
7. Upbit summary

### PAPER / Coin performance

1. Exchange selector
2. Current-exchange PnL summary
3. Search / sort / status filters
4. Master list
5. Selected-coin detail

`전체` is the default filter. Filtering never replaces the PAPER summary destination.

### PAPER / Strategy comparison

1. Exchange selector
2. Comparison table
3. Optional selected-strategy details

Use a table, not repeated large cards.

### PAPER / Trade records

1. Exchange selector
2. Record summary
3. Buy / sell / learning filter
4. Chronological record list

Clicking a record must not automatically leave PAPER.

### PAPER / Exchange comparison

1. Common-market summary
2. Search / sorting
3. Sticky-header comparison table
4. Selected-market comparison details

## Assets

Question answered: **What is the status of my actual holdings?**

Order of regions:

1. Current valuation
2. PnL / return
3. Invested capital
4. Holding count
5. Allocation
6. Holding table

Rules:
- Actual holdings and PAPER accounts are never mixed.
- Clicking a holding does not automatically navigate away.
- Research navigation, if offered, must be an explicit action.

## System utility

Question answered: **Is the node/account healthy?**

Contains only:
- Research node health
- Freshness
- Account/permission information
- Owner invite controls

System must not contain trading-performance or portfolio content.

## Component semantics

- Primary navigation: text tabs in the app header
- Secondary navigation: text tabs inside PAPER
- Scope selector: segmented control
- Filter: compact chips
- Status: non-clickable badge
- Primary action: solid button only when an actual action exists
- Repeated comparable data: table/list, not cards
- Summary data: compact KPI row
