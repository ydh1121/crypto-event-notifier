# Viewer Build 36 — Sector identity audit and mobile discovery

Build 36 is a focused sector-research quality pass. It does not change the approved information architecture.

## Project identity integrity

- Audit every cached Bithumb and Upbit KRW profile against the exchange's current official English project name.
- Never treat a ticker alone as sufficient identity evidence.
- CoinMarketCap and CoinGecko candidates must match the exchange project name before their description, logo, categories or links can be used.
- Bithumb manual PDFs must contain the target Korean/English project identity before the PDF is accepted.
- Existing cache rows with an identity mismatch are the highest-priority precision-research backlog.
- Precision repair may replace/clear stale identity-sensitive metadata so a previous wrong description cannot survive through non-empty-field preservation.
- Until repair completes, the Viewer hides a mismatched profile instead of showing another project's business description.

## Sector discovery UX

- Add a global sector/coin search field supporting Korean name, English name, ticker and market.
- Add filter chips: all, researched, needs research, up, down, unclassified.
- Preserve 24H turnover/change/opportunity sorting.
- Mobile <=760px must not use a forced 650px-wide coin table. Coin rows become stacked metric cards with no horizontal clipping.
- Project business copy remains Korean-first; English text is not used as the primary fallback.

## Safety

- PAPER/read-only boundaries are unchanged.
- Community sources remain corroboration only.
- When identity evidence is uncertain, prefer unresolved/pending over a confident but incorrect profile.
