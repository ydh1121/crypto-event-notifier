# VIEWER BUILD 31 PLAN

## Goal
Turn the sector page from a shallow category table into a research surface that covers every available market detail row, explains sectors and projects, supports sorting, and preserves exchange-like live behavior.

## Requirements
1. Remove the 14-coin cap. A selected sector must expose every coin currently available in `market_details`.
2. Use the exchange public market list for official Korean and English names. Korean is visually primary.
3. Replace generic `기타` with a canonical taxonomy and an explicit `미분류 검토` bucket when evidence is insufficient.
4. Reference external category systems rather than inventing labels. CoinGecko and CoinMarketCap categories are used as taxonomy references. Because one asset can belong to multiple external categories, the viewer normalizes them to one representative sector for comparison.
5. Add sector overview and business-model explanations.
6. Add per-coin project profiles. CoinGecko metadata is fetched on demand and cached in D1; exchange metadata remains the fallback.
7. Add sortable 24H turnover, 24H change and opportunity-score columns with ascending/descending toggles.
8. Keep the full sector coin list in a bounded scrolling workspace with a project profile rail so the page does not become excessively tall.
9. Preserve explicit `리서치에서 보기` navigation from the selected coin profile.
10. Prevent the Dashboard `전략 연구` action from wrapping.
11. Make Dashboard `최근 중요 변화 + 실시간 관제` use the same 1320px visual width as the major dashboard blocks. Explain what the live metrics mean and widen the live rail.

## External taxonomy references
- CoinMarketCap categories: https://coinmarketcap.com/cryptocurrency-category/
- CoinGecko categories: https://www.coingecko.com/en/categories
- CoinGecko category methodology / usage: https://www.coingecko.com/learn/coingecko-categories

## Exchange name sources
- Bithumb public market list: `GET https://api.bithumb.com/v1/market/all?isDetails=false`
- Upbit public market list: `GET https://api.upbit.com/v1/market/all?is_details=false`

## Privacy and safety
- External project metadata contains no user holdings or user identifiers.
- Coin profile cache stores only public project metadata keyed by exchange + market.
- This remains READ ONLY PAPER; no order action is added.

## Next bundle after Build 31 QA
- strategy equity curve
- strategy-by-coin performance
- coin × strategy comparison
- total PAPER equity / drawdown
