# Viewer UX / UI / User-Journey State Audit — 2026-09-03

## Review persona

Primary simulation persona: a Korean coin trader in their 60s who can use an exchange app but is not a developer or technical trader.

The audit follows three layers together:

1. User journey — what the user expects after a click.
2. UX state — which selection/filter is allowed to affect which screen.
3. UI state — whether the selected control is visible, highlighted, and located next to the content it changes.

## Deterministic journey simulation

| Scenario | Previous behavior | Expected behavior | Status target |
| --- | --- | --- | --- |
| Main nav → 섹터 | 섹터 route could highlight `코인 찾기` because router still mapped `sectors -> research` | `섹터` alone is active | FIX |
| 전략 전체에서 전략 B 선택 → 코인별 성과 | hidden overview selection silently changed the next tab | coin-performance tab owns its own visible strategy selector | FIX |
| 코인별 성과에서 전략 C 선택 → 전략 전체 | overview selection should not change | each tab keeps independent selection scope | FIX |
| 전략 전체 → 가상매매 | stale `strategyCoinMarket` could leak from an older matrix visit | no hidden market handoff from overview | FIX |
| 코인별 전략 비교에서 BTC 선택 → 가상매매 | BTC is an explicit visible selection | carry BTC intentionally | KEEP |
| 홈에서 보유 BTC가 selected → 내 코인 상세 | header button could open an older `assetMarket` | carry the visible selected holding | FIX |
| 가상매매 코인별 목록 | strategy is shown in rows but not filterable | show an explicit execution-strategy filter | FIX |
| 가상매매 strategy filter | must not mix Shadow research strategies | only strategies actually present in execution PAPER rows are filter options | CONTRACT |
| 전략 비교 non-overview tabs | global Shadow KPI strip stayed above unrelated tab content | show global experiment KPIs only on `전략 전체` | FIX |
| 선택 전략 코인 results | sorted by absolute return, mixing biggest losses with best winners | default to return-highest and expose sort control | FIX |
| 섹터 table sort | arrow changed but selected sort was not visibly active | active style + aria-pressed on current sort | FIX |
| Mobile 390/430 main navigation | 6 buttons required undisclosed horizontal scrolling | show all six in a 3 x 2 grid | FIX |

## Control ownership rules

- Main navigation owns route selection only.
- Journey navigation owns workspace selection (`가상매매` vs `전략 비교`).
- Page tabs own view mode only.
- Overview strategy row selection affects only overview detail.
- Coin-performance strategy selection affects only the coin-performance table.
- Matrix coin selection affects only the matrix, except an intentional route handoff when the user leaves the matrix for execution PAPER.
- Execution PAPER strategy filters may only use strategies present in execution PAPER rows. Shadow experiment strategies never appear as execution-PAPER filter options.
- Search/sort/filter controls must sit immediately above the content they change.
- A hidden stale state must not change another page.

## Button/selection inventory

### Main navigation
- 홈: visible active state
- 코인 찾기: visible active state
- 섹터: visible active state, independent route
- 내 코인: visible active state
- 매매 성적: visible active state; remains active while inside 전략 비교 workspace
- 기록: visible active state
- 시스템: utility button, intentionally not a primary navigation item

### Home
- candidate rows: click carries visible exchange + market to 코인 찾기
- holding rows: selected row visibly highlighted
- 내 코인 상세: must carry the same selected holding shown on Home
- secondary links: 섹터 / 전략 비교 / 상세 현황 are explicit destinations, not hidden tab changes

### 코인 찾기
- exchange segmented control: active state visible
- decision chips: active state visible
- market row: selected state visible
- research history remains secondary to current decision workspace

### 섹터
- exchange segmented control: active state visible
- filter chips: active state visible
- sector row: selected state visible
- coin row: selected state visible
- sort: current sort must have an active state in addition to arrow direction

### 내 코인
- selected holding row: visible
- calculators are scoped to the selected holding
- history is supporting content after the main holding/action workspace

### 매매 성적 / 가상매매
- workspace navigation: `가상매매` active
- internal tabs: summary / coin / exchange selection visible
- execution-strategy filter: visible next to coin list controls
- strategy filter options are execution-only

### 전략 비교
- workspace navigation: `전략 비교` active
- overview row: affects only overview detail
- coin-performance strategy: separate explicit selector
- coin-performance sort: explicit selector
- matrix coin: selected state visible
- current execution benchmark: independent from Shadow selections

### 기록
- exchange segmented control: active state visible
- record type chips: active state visible
- strategy/period selects display their current values
- reset returns every visible filter to its default

## Remaining visual QA after source/state contract

Source-level state simulation and CI contracts do not replace pixel-level browser QA. After live auto-sync, 390px, 430px, tablet, and desktop should still be checked for clipping, tap-target spacing, sticky-header overlap, and scroll position continuity.
