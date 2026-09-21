# CRYPTO PURPOSE → FEATURE → DATA → UI CANONICAL MAP

Status: CANONICAL REBASELINE
Date: 2026-09-21
Authority: actual source + durable roadmap. A source file alone is never treated as a completed capability.

## 1. Product mission

The product exists to close one evidence loop:

1. Accumulate per-coin behavior against BTC/ETH plus internal/external news, macro, lifecycle and market events.
2. Run strategy-specific PAPER trading per coin, accumulate fills and outcomes, and verify which entry/exit methods repeatedly work for that coin.
3. For actually held assets, combine the validated research/PAPER evidence with averaging and profit-protection calculators, then use only a separately authorized small live test when readiness gates are met.
4. Only after the small-test gate succeeds may a future live-trading workstream be considered. Current runtime remains PAPER/read-only and must not auto-promote.

A UI is valid only when it makes this loop easier to inspect. Generic dashboard polish is not a product goal.

## 2. Completion vocabulary

Every capability must be tracked independently across five layers.

- SOURCE: implementation exists and has tests/contracts.
- RUNTIME: it is actually scheduled/running in the intended local process.
- DB: authoritative SQLite evidence is accumulating with timestamps/provenance.
- PROJECTION: the required bounded data is published to the Viewer.
- UI: the capability is visible in the page where the product mission says it belongs.

No capability may be called complete merely because SOURCE is present.

## 3. Purpose 1 — per-coin intelligence and reaction memory

### 3.1 Implemented source families

| Capability | SOURCE evidence | Runtime/DB intent | Current Viewer state |
|---|---|---|---|
| Coin identity / business / sector research | `coin_profile_*`, research supervisor `coin-profile-enrichment` | scheduled profile enrichment | Theme page exposes profile/business evidence |
| Listing/caution/termination lifecycle | `market_notice_*`, `market_lifecycle_*` | scheduled `market-notice-watch`; local DB | Theme lifecycle panel exists |
| Multi-timeframe OHLCV | `market_ohlcv_*` | scheduled `market-ohlcv-history`; SQLite | only selected derived price windows are surfaced |
| BTC/ETH relative strength | `market_relative_strength.py` | SQLite feature path | compact market-detail projection exists, but it is not a first-class per-coin evidence section |
| Cross-exchange gap / domestic premium | `market_cross_exchange_gap.py`, `market_domestic_premium.py` | SQLite feature path | not organized as a per-coin research narrative |
| Trade flow / CVD / orderbook | `market_flow_collector.py`, stream/store/orderbook modules | source/store exists; runtime ownership must be audited separately | no canonical Viewer surface |
| Price-flow divergence / absorption | `market_price_flow_divergence.py`, `market_flow_absorption_*` | research evidence tables | no canonical Viewer surface |
| Flow forward reaction | `market_flow_reaction.py`, due/reliability modules | forward research tables | no canonical Viewer surface |
| Official macro/news ingest | `intelligence_ingest_cycle.py` | supervisor component `phase5-intelligence-ingest` | System can show component status, but research pages do not expose the evidence |
| BLS / BEA / FOMC events | `intelligence_bls_*`, `intelligence_bea_*`, `intelligence_fomc_calendar.py` | normalized `research_intelligence_events` | not surfaced as a per-coin event timeline |
| SEC / CFTC official news | `intelligence_official_news.py` | normalized event store | not surfaced as a per-coin event timeline |
| Crypto response to events | `intelligence_event_response.py` | event-response research tables | not surfaced |
| U.S. market sensitivity | `intelligence_event_response_us_sensitivity.py` | descriptive research table | not surfaced |
| Per-coin reaction memory | `intelligence_reaction_memory.py` | `research_intelligence_reaction_memory`, keyed by event_type + market + horizon + provider/exchange | not surfaced |
| Listing-history reaction | `listing_history_*` | scheduled listing-history research | Research page has a compact listing-history section |
| DEX launch / pre-listing reaction | `dex_launch_*` | scheduled/bounded research path | compact feature support exists but is not part of one unified coin evidence timeline |

### 3.2 Critical disconnect

The backend already contains the beginnings of the user's first objective, including a normalized event store and a per-coin reaction-memory table, but `cloudflare_snapshot_publisher.py` does not publish the intelligence/reaction evidence as a first-class Viewer domain. Current Viewer pages therefore cannot answer a basic question such as:

> “When CPI/FOMC/SEC/lifecycle/flow events happened before, how did this coin react versus BTC and ETH at 15m/1h/4h/1d?”

That is a product-level missing surface, not a cosmetic defect.

## 4. Purpose 2 — coin-specific strategy PAPER validation

| Capability | SOURCE/DB evidence | Current state |
|---|---|---|
| Active adaptive PAPER | `multi_exchange_paper.py`, `paper_runtime_supervisor.py`, scoped PAPER store | Bithumb runtime owner exists; actual liveness must be read from local runtime, not inferred from source |
| Upbit PAPER | research supervisor `upbit-paper-research` | component exists but default is disabled in `research_control.py`; local actual state must be audited |
| Per-coin market memory | active PAPER market-memory tables | accumulated and used by current detail projections |
| Strategy lab | `strategy_lab.py` | independent experiment/accounts/learning/trades/metrics tables exist |
| Strategy experiments | conservative / balanced / aggressive / DCA / contrarian / swing family | strategy page exposes aggregate and coin breakdown |
| Per-strategy fills | `strategy_lab_trades` | DB exists, but current Strategy UI explicitly says experiment-level fills are not supplied in Snapshot |
| Per-coin × strategy comparison | strategy lab metrics + market detail | UI has partial matrix/breakdown |
| Validation gates | candidate/warming/rejected + strategy validation views | UI exists but is split away from the coin evidence loop |
| Walk-forward / OOS | roadmap Phase 7 | not implemented |
| intelligence-v2 parallel PAPER | roadmap `adaptive_intelligence_v2` | not implemented |

### 4.1 Critical disconnect

The product should let the user open one coin and move directly through:

`coin evidence → strategy candidates → actual PAPER fills → per-strategy PnL/DD/win-rate/expectancy → validation status`.

Today this path is split between Research, PAPER and Strategy, and the Strategy page cannot display its own experiment trade ledger because the projection is missing. This prevents the second product objective from being inspected end-to-end.

## 5. Purpose 3 — actual holdings and decision bridge

| Capability | SOURCE/DB evidence | Current Viewer state |
|---|---|---|
| Actual holdings / valuation / PnL | holdings + portfolio/history paths | Assets page exposes current value/PnL/history |
| Holdings mutation | V16 holding mutation service/consumer | owner-write path exists under explicit safety boundary |
| Averaging calculator | `shared/averaging.js`, Assets page | implemented |
| Budget-by-round planner | `holding-plan.js`, Assets page | implemented |
| Profit-protection / target reference | holding-plan/profit guidance | implemented |
| PAPER reference beside real holding | Assets detail uses Bithumb/Upbit PAPER plan | implemented, but evidence lineage is shallow |
| Validated strategy evidence for held coin | strategy lab + PAPER metrics | not unified into Assets decision bridge |
| Historical event-reaction evidence for held coin | reaction memory | not unified into Assets |
| Small live test | future boundary | not implemented / not authorized |

### 5.1 Critical disconnect

The calculators exist, but the Assets page does not yet answer:

- Which strategy has actually been validated for this exact coin?
- How many PAPER trades support that conclusion?
- What happened to this coin in prior BTC/ETH/macro/news/lifecycle regimes?
- Is the suggested averaging/exit reference backed by a validated method or merely the current adaptive PAPER plan?

Until those links exist, the Assets page is a calculator plus PAPER reference, not the intended evidence bridge to real capital.

## 6. Purpose 4 — future live transition

Current source intentionally remains PAPER-only/read-only. `b3_trader/main.py` warns that even armed credentials do not submit live orders, and the roadmap requires separate live safeguards and explicit authorization.

This is correct. The missing work is not “turn live on”; it is finishing objectives 1–3 and producing enough forward/OOS evidence to justify a later small-test workstream.

## 7. Current Viewer IA diagnosis

### Existing top-level structure
`Home / Market / Assets / PAPER / Strategy / Records` (+ System)

Problems:
1. It is feature-origin based, not mission based.
2. Market/Research/Theme split the same coin evidence across multiple routes.
3. PAPER and Strategy split execution from validation.
4. Event/reaction memory has no first-class destination.
5. Flow/CVD/orderbook/absorption evidence has no first-class destination.
6. Assets cannot see the complete validation lineage.
7. Records mixes user evidence, learning and operations rather than serving as an audit trail of the research→validation loop.
8. Home/dashboard emphasizes cards and status summaries rather than progress through the four product objectives.
9. Large empty/imbalanced desktop regions and clipped master rails are symptoms of composition being designed before the canonical capability map.

## 8. Target mission-driven IA

### 8.1 Home — “What is ready to act on?”
Not a generic dashboard.

Required sections:
- Data accumulation health: event/OHLCV/flow/reaction freshness and coverage.
- Coins with enough reaction evidence.
- Coins with enough strategy PAPER evidence.
- Held assets requiring review.
- Validation blockers: missing samples, stale sources, disabled runtimes.
- No strategy/coin is promoted solely by headline return.

### 8.2 Research — one evidence model
Local navigation:
- Market context
- Coins
- Events
- Themes / lifecycle

#### Coin detail canonical tabs
1. Summary
2. Price vs BTC/ETH
3. Event reactions
4. Flow / CVD / orderbook
5. Technical / structure
6. Listing / lifecycle
7. Strategy evidence
8. Raw evidence / provenance

The user should never need to leave the coin context merely to discover how that coin reacted to CPI/FOMC/BTC/ETH or which strategy worked on it.

### 8.3 Validation — PAPER + strategy lab in one workspace
Local navigation:
- Active PAPER
- Coin × strategy
- Strategy × coin
- Trade ledger
- Validation gates
- Walk-forward / OOS

This replaces the conceptual split between “모의투자” and “매매방법”. They are two views of one validation system.

### 8.4 Portfolio — actual capital decision bridge
Local navigation:
- Holdings
- Averaging
- Profit protection
- Evidence for held coin
- Small-test gate (LOCKED until separately authorized)

Each held coin must show:
- actual position,
- current plan/calculators,
- validated strategy sample,
- latest PAPER fills/performance,
- historical event-reaction profile,
- explicit evidence insufficiency when data is weak.

### 8.5 Journal — audit trail
Local navigation:
- Research events
- PAPER fills
- Strategy-lab fills
- Learning changes
- Decision changes
- Operational incidents

Journal is evidence chronology, not another dashboard.

### 8.6 Operations
- component runtime health,
- source freshness/rate limits,
- SQLite/warehouse/backup,
- projection/deployment,
- CI,
- account/access.

Operations must not compete with trading/research information.

## 9. Current page disposition

| Current route | Disposition |
|---|---|
| Home/dashboard | rebuild around mission readiness; keep useful data, drop card-centric composition |
| Research/Coin | becomes canonical Coin Research workspace |
| Market dashboard | demote into Research → Market context |
| Theme/Sectors | merge into Research → Themes/lifecycle |
| PAPER | merge into Validation → Active PAPER |
| Strategy | merge into Validation → strategy/coin comparison + ledger + gates |
| Assets | retain as Portfolio, enrich with validated evidence lineage |
| Records | become Journal with explicit evidence classes |
| System | retain as Operations |

No capability is deleted by this IA change.

## 10. Development order from this rebaseline

### Gate A — actual-runtime truth first
Read-only audit on the user's local machine:
- which supervisor components are running,
- Phase 5 latest successful cycle / event counts,
- reaction/reaction-memory row counts and latest timestamps,
- Bithumb/Upbit PAPER liveness and last fill time,
- strategy-lab experiment/trade/metric counts,
- market-flow/CVD/orderbook/reaction table counts,
- snapshot projection coverage.

This audit determines what is “implemented but dormant” versus actually accumulating.

### Gate B — complete the data loop
Priority:
1. event/reaction/reaction-memory accumulation,
2. BTC/ETH-relative + flow reaction continuity,
3. source freshness/coverage,
4. required Viewer projection.

### Gate C — complete the validation loop
Priority:
1. guarantee active PAPER liveness,
2. publish strategy-lab trade ledger,
3. unify coin × strategy evidence,
4. establish sample/readiness gates,
5. only then build `adaptive_intelligence_v2` and walk-forward.

### Gate D — rebuild Viewer from the canonical feature map
Do not continue page-by-page cosmetic repair.
First implement the target route/page skeleton and map every existing capability to one canonical location, then migrate surfaces without deleting data.

### Gate E — actual capital
Only after Gates B–D have measurable evidence:
- Portfolio evidence bridge,
- separately authorized small-test design,
- future live workstream.

## 11. Immediate defects observed during the current QA

These are real but not the top-level workstream:
- Research/Coin master rail clips/hides at least one lower item near the viewport boundary.
- Market dashboard composition breaks into an unbalanced half-width/empty-right layout at the supplied desktop viewport.

Record them as known UI defects. Repair them during the IA migration unless they block runtime auditing.

## 12. Stop rules

Until the feature inventory/runtime audit is complete:
- no new cosmetic page-polish work order,
- no Production deploy,
- no page-specific height/scroll patch unless it blocks access to required evidence,
- no declaring a feature complete from source/tests alone,
- no live-order implementation.
