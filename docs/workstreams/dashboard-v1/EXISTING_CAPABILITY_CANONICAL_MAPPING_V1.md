# CRYPTO EXISTING CAPABILITY → CANONICAL DESTINATION MAP v1

Status: PLANNING CANONICAL / NO SOURCE IMPLEMENTATION YET
Date: 2026-09-21
Parent IA: `PURPOSE_FEATURE_DATA_UI_MAP.md`

## 0. Rules

Primary user work is only:

- **실전매매** — choose a coin, see the strongest strategy, see split entry/exit/weight, run averaging/profit calculators, inspect evidence-backed rising candidates.
- **가상매매** — for one selected coin, inspect strategy-specific PAPER account/trades/performance, BTC/ETH-relative movement, and news/indicator/event reactions.

Everything else is secondary and must be classified under **탐색 / 연구·데이터 / 기록 / 운영**.

No implemented capability is deleted merely because it leaves a primary screen.

Treatment vocabulary:

- **KEEP_PRIMARY** — already close to the right place and remains primary.
- **MOVE_PRIMARY** — move an existing surface/data block into one of the two primary pages.
- **MERGE_PRIMARY** — combine currently separated features into one primary task surface.
- **SECONDARY** — keep accessible but remove from primary competition.
- **PROJECTION_GAP** — source/DB exists but the Viewer does not yet receive the evidence needed by the canonical page.
- **DERIVATION_GAP** — underlying metrics exist but a canonical summary such as “현재 우세 전략” is not yet defined/published.
- **LOCKED_FUTURE** — intentionally unavailable until a later safety/validation gate.

---

## 1. Capability mapping

| ID | Existing capability | Current source / route | Canonical destination | Treatment | Planning note / gap |
|---:|---|---|---|---|---|
| 001 | 빗썸/업비트 선택 | Research / Assets / PAPER route-local controls | 실전매매 + 가상매매 selector | MERGE_PRIMARY | Same semantic selector family; page owns current context. |
| 002 | 코인/티커 검색 | Research list, PAPER list | 실전매매 + 가상매매 selector | MERGE_PRIMARY | One compact selector pattern; preserve selection/search state. |
| 003 | 현재가 / 24h 변화 | Research live quote, Assets, PAPER | 실전매매 + 가상매매 header | MOVE_PRIMARY | Current price must be visible without opening a secondary panel. |
| 004 | 실제 보유 여부 / 실제 평가액 | Assets, Research selected coin | 실전매매 selected coin | MOVE_PRIMARY | Small inline position context, not a separate dashboard. |
| 005 | 실제 수량 / 평균단가 수정 | Assets holding mutation | 실전매매 utility | KEEP_PRIMARY | Needed for calculators; keep write boundary explicit. |
| 006 | 총 실제 자산 / 총 PnL | Home/Assets summary | 실전매매 secondary summary | SECONDARY | Useful context, but not the page’s dominant block. |
| 007 | 현재 판단 / 기회점수 / 시장점수 | Research, Dashboard | 실전매매 추천 근거 + 탐색 | SECONDARY | Do not present as competing score cards. |
| 008 | 현재 우세 전략 | Strategy/PAPER metrics are fragmented | 실전매매 | DERIVATION_GAP | Need one per-coin dominance result backed by strategy evidence; do not invent a winner if samples are weak. |
| 009 | 전략 검증 상태 | Strategy validation / current result | 실전매매 + 가상매매 | MOVE_PRIMARY | Show PASS / 검증 중 / 표본 부족 next to strategy. |
| 010 | 전략별 진입 타점 | PAPER current plan / strategy experiment plan | 실전매매 strategy matrix | MERGE_PRIMARY | Split entry rows must support N legs. |
| 011 | 전략별 진입 비중 | PAPER proposed weight / strategy plan | 실전매매 strategy matrix | MERGE_PRIMARY | Split allocation shown next to each entry leg. |
| 012 | 전략별 익절 타점 | PAPER plan / profit-protection data | 실전매매 strategy matrix | MERGE_PRIMARY | Split exits supported; no single-target-only UI. |
| 013 | 전략별 익절 비중 | strategy plan / profit protection | 실전매매 strategy matrix | MERGE_PRIMARY | Remaining quantity must be explicit. |
| 014 | 손절/중단 기준 | PAPER plan / holding-plan | 실전매매 strategy matrix | MOVE_PRIMARY | Low-frequency column/detail; not a separate card. |
| 015 | 물타기 계산기 | Assets `averaging.js` | 실전매매 | KEEP_PRIMARY | Selected coin inherits actual qty/avg when held. |
| 016 | 분할 예산 계획 | Assets `holding-plan.js` | 실전매매 물타기 | MERGE_PRIMARY | Treat as calculator mode, not independent page. |
| 017 | 익절/고점보호 계산 | Assets holding-plan/profit guidance | 실전매매 | KEEP_PRIMARY | Split exit calculator; retain trailing/high-point protection when data exists. |
| 018 | 실제 보유자산 이력 | Assets | 기록 → 실제자산 | SECONDARY | Historical audit, not trading primary. |
| 019 | 지금 볼 코인 / watch candidates | Dashboard `dashboardWatchList` | 실전매매 상승후보 | MOVE_PRIMARY | Becomes compact evidence-backed shortlist. |
| 020 | 추천 근거: 기회/시장/PAPER | Dashboard + Research + PAPER | 실전매매 상승후보 | MERGE_PRIMARY | Each recommendation must show why, not just a score. |
| 021 | 추천 근거: BTC/ETH 상대 움직임 | relative-strength research | 실전매매 상승후보 | PROJECTION_GAP | Need bounded per-coin relative evidence in Viewer. |
| 022 | 추천 근거: 최근 이벤트 반응 | intelligence/reaction memory | 실전매매 상승후보 | PROJECTION_GAP | Need compact latest reaction evidence; no unsupported recommendation. |
| 023 | 전체 PAPER 계좌 요약 | PAPER overall | 가상매매 overview | SECONDARY | One compact summary above coin selector or separate secondary view. |
| 024 | 거래소별 PAPER 계좌 | PAPER Bithumb/Upbit | 가상매매 overview | SECONDARY | Preserve; not primary when a coin is selected. |
| 025 | PAPER 코인 목록 | PAPER master list | 가상매매 selector | MOVE_PRIMARY | Use as coin selector/list evidence. |
| 026 | PAPER 코인 검색/필터/정렬 | PAPER controls | 가상매매 selector | KEEP_PRIMARY | Preserve current durable UI state. |
| 027 | 개별 코인 현재 PAPER 포지션 | PAPER detail | 가상매매 → 전략 탭 | MOVE_PRIMARY | Must be strategy-scoped where possible. |
| 028 | 현재 매매 계획 | PAPER detail | 가상매매 → 전략 탭 | MOVE_PRIMARY | Entry/exit/weight/remaining splits beside account state. |
| 029 | 가격·체결·가상계좌 | PAPER detail | 가상매매 → 전략 탭 | MERGE_PRIMARY | Account strip + current position + ledger. |
| 030 | 최근 PAPER 체결 | PAPER detail | 가상매매 → 전략 탭 | MOVE_PRIMARY | Full chronological table, not tiny recent-only summary. |
| 031 | PAPER 실현/미실현 PnL | PAPER detail | 가상매매 → 전략 탭 | MOVE_PRIMARY | Strategy/account scoped. |
| 032 | PAPER 완료 거래/승률 | PAPER detail | 가상매매 → 전략 탭 | MOVE_PRIMARY | Part of performance strip. |
| 033 | 전략 실험 계좌 | `strategy_lab_accounts` | 가상매매 → 전략 탭 | PROJECTION_GAP | DB/source exists; Viewer must receive per-strategy account state. |
| 034 | 전략별 체결 원장 | `strategy_lab_trades` | 가상매매 → 전략 탭 | PROJECTION_GAP | Current Strategy UI explicitly lacks experiment-level fills. Critical gap. |
| 035 | 전략별 학습 상태 | `strategy_lab_learning` | 가상매매 → 전략 탭 / 기록 | MOVE_PRIMARY | Current state near strategy; change history goes to 기록. |
| 036 | 전략별 성과 metrics | `strategy_lab_metrics`, Strategy page | 가상매매 → 전략 탭 | MOVE_PRIMARY | Trades, win rate, PnL, DD, expectancy where available. |
| 037 | 매매방법별 비교 | Strategy | 가상매매 → 전략 비교 | MERGE_PRIMARY | Comparison is local to selected coin; avoid separate top-level “매매방법”. |
| 038 | 코인별 매매방법 비교 | Strategy | 가상매매 | MERGE_PRIMARY | Selected coin stays in context while switching strategy. |
| 039 | 현재 실행 방식의 성적 | Strategy | 가상매매 | MERGE_PRIMARY | A strategy tab state, not top-level page. |
| 040 | 검증 흐름 / 기준 충족 | Strategy | 가상매매 → 검증상태 | MOVE_PRIMARY | Compact evidence state; details can disclose. |
| 041 | 전략 후보등록/검증/미충족 상태 | Strategy | 가상매매 → 검증상태 | MOVE_PRIMARY | Keep actual status and sample counts. |
| 042 | 같은 코인 거래소별 PAPER 결과 | PAPER | 가상매매 secondary comparison | SECONDARY | One-click comparison, not default view. |
| 043 | BTC 대비 상대강도 | `market_relative_strength.py` / market detail | 가상매매 → BTC/ETH | PROJECTION_GAP | Partial compact data exists; needs canonical historical/period view. |
| 044 | ETH 대비 상대강도 | relative-strength path | 가상매매 → BTC/ETH | PROJECTION_GAP | Same as BTC. |
| 045 | Multi-TF OHLCV | OHLCV collectors/stores | 가상매매 → BTC/ETH support / 연구·데이터 | SECONDARY | Chart evidence supports relative movement; raw tables stay secondary. |
| 046 | 국내/해외 가격차 | cross-exchange research | 연구·데이터 | SECONDARY | Optional evidence drill-down. |
| 047 | 국내 프리미엄 | domestic premium research | 연구·데이터 | SECONDARY | Optional evidence drill-down. |
| 048 | 공식 거시 이벤트 ingest | BLS/BEA/FOMC intelligence modules | 가상매매 → 이벤트 | PROJECTION_GAP | Normalize into selected-coin event timeline. |
| 049 | SEC/CFTC 공식 뉴스 ingest | intelligence official-news | 가상매매 → 이벤트 | PROJECTION_GAP | Selected coin relevance must be explicit; global feed stays secondary. |
| 050 | 이벤트 normalized store | `research_intelligence_events` | 가상매매 → 이벤트 | PROJECTION_GAP | Viewer needs event time/type/source. |
| 051 | 이벤트 가격반응 | intelligence event-response | 가상매매 → 이벤트 | PROJECTION_GAP | Need coin/BTC/ETH horizon reaction. |
| 052 | 코인별 reaction memory | `research_intelligence_reaction_memory` | 가상매매 → 이벤트 | PROJECTION_GAP | Critical user-requested function. |
| 053 | 이벤트 horizon 15m/1h/4h/1d | reaction memory/event response | 가상매매 → 이벤트 | PROJECTION_GAP | Must be one row/expandable evidence unit. |
| 054 | 거래소 공지 | market notice | 가상매매 → 이벤트 + 탐색 | MOVE_PRIMARY | Selected coin timeline + global explore list. |
| 055 | 상장/유의/거래종료 lifecycle | lifecycle modules / Theme | 가상매매 → 이벤트 + 탐색 | MOVE_PRIMARY | Same evidence, two contexts. |
| 056 | 상장 이력 연구 | Research secondary | 연구·데이터 + 가상매매 이벤트 detail | SECONDARY | Do not create another top-level page. |
| 057 | DEX launch/pre-listing research | DEX launch modules | 연구·데이터 | SECONDARY | Link into coin evidence only when relevant. |
| 058 | Flow collector | market-flow modules | 연구·데이터 | SECONDARY | Available for deep evidence; not primary requested surface. |
| 059 | CVD | flow store/analysis | 연구·데이터 | SECONDARY | Can support recommendation/strategy evidence later. |
| 060 | Orderbook stream/imbalance | orderbook stream store | 연구·데이터 | SECONDARY | Deep evidence only. |
| 061 | Absorption | flow absorption modules | 연구·데이터 | SECONDARY | Deep evidence only. |
| 062 | Price-flow divergence | divergence module | 연구·데이터 | SECONDARY | Deep evidence only. |
| 063 | Forward flow reaction | market flow reaction modules | 연구·데이터 | SECONDARY | Deep evidence only. |
| 064 | 코인 사업/프로젝트 설명 | Theme project profile | 탐색 → 코인/테마 detail | SECONDARY | Keep readable but out of trading primary. |
| 065 | 테마/섹터 순위 | Theme/Sectors | 탐색 | SECONDARY | Discovery only. |
| 066 | 테마 자금 집중 | Dashboard/Sectors | 탐색 | SECONDARY | Discovery only. |
| 067 | 전체 시장 상태/상승하락/거래대금 | Market dashboard | 탐색 | SECONDARY | Keep one coherent market page; fix broken grid during migration. |
| 068 | 시장 온도/매수 타이밍 | Dashboard | 탐색 | SECONDARY | Can feed rising-candidate evidence but not dominate live page. |
| 069 | 최근 중요 변화 | Dashboard | 기록 / 탐색 | SECONDARY | Chronology belongs in 기록; current anomalies can link from 탐색. |
| 070 | 실시간 관제 | Dashboard | 운영 | SECONDARY | Runtime/health state should not share trading canvas. |
| 071 | PAPER 전체 체결 기록 | Records/PAPER | 기록 → PAPER | SECONDARY | Full audit. |
| 072 | 전략 연구 체결 기록 | strategy lab DB | 기록 → 전략실험 | PROJECTION_GAP | Needed for cross-coin audit after primary per-coin ledger is delivered. |
| 073 | 판단 변경 | Records | 기록 → 판단 | SECONDARY | Keep chronology. |
| 074 | 학습 변경 | Records / PAPER recent learning | 기록 → 학습 | SECONDARY | Keep before/after evidence. |
| 075 | 이벤트 기록 | intelligence event store | 기록 → 이벤트 | PROJECTION_GAP | Global chronology, not primary coin timeline. |
| 076 | 오류/incident | Records/System | 기록 → 시스템 | SECONDARY | Audit only. |
| 077 | Research supervisor 상태 | System | 운영 → Runtime | SECONDARY | Operator-only. |
| 078 | PAPER runtime supervisor/liveness | System/source | 운영 → Runtime | SECONDARY | Surface liveness and last successful cycle. |
| 079 | Strategy Lab runtime | source/System | 운영 → Runtime | SECONDARY | Distinguish source-exists from actually running. |
| 080 | Phase 5 intelligence ingest runtime | source/System | 운영 → Runtime | SECONDARY | Show latest cycle, event count, freshness. |
| 081 | collector별 freshness | System/research node | 운영 → 수집 | SECONDARY | OHLCV/event/flow/listing etc. |
| 082 | SQLite DB 상태 | System | 운영 → Data | SECONDARY | Row/freshness detail. |
| 083 | Parquet 분석창고 | System | 운영 → Data | SECONDARY | Keep operator-only. |
| 084 | SQLite/Drive backup | System | 운영 → Backup | SECONDARY | Keep operator-only. |
| 085 | Cloudflare snapshot publish | System/publisher | 운영 → Projection | SECONDARY | Freshness + last publish. |
| 086 | Market detail publish | market-detail publisher | 운영 → Projection | SECONDARY | Projection coverage/freshness. |
| 087 | Git synchronization | System | 운영 → Deploy | SECONDARY | Operator-only. |
| 088 | GitHub Actions CI | System | 운영 → Deploy | SECONDARY | Operator-only. |
| 089 | Cloudflare Pages status | System | 운영 → Deploy | SECONDARY | Operator-only. |
| 090 | Telegram BUY_CANDIDATE alert | System | 운영 → Alerts | SECONDARY | Can deep-link to 실전매매 selected coin. |
| 091 | Remote access | System | 운영 → Access | SECONDARY | Operator-only. |
| 092 | Account / user invite | System | 운영 → Account | SECONDARY | Operator-only. |
| 093 | Safety contract / no real order | System | 운영 → Safety | SECONDARY | Keep visible to owner/admin. |
| 094 | 기본/상세 reader mode | global shell | Utility, not route | KEEP_PRIMARY | Do not let it create duplicate IA. |
| 095 | Light/Dark | global shell | Utility, not route | KEEP_PRIMARY | Preserve. |
| 096 | admin/owner/logout | global shell | Utility | KEEP_PRIMARY | Operations entry may live here. |
| 097 | Walk-forward / OOS | roadmap future | 가상매매 validation | LOCKED_FUTURE | Do not fabricate current results. |
| 098 | adaptive_intelligence_v2 parallel PAPER | roadmap future | 가상매매 strategy family | LOCKED_FUTURE | Later experiment family. |
| 099 | 소액 실전 테스트 | future safety workstream | 실전매매 | LOCKED_FUTURE | Explicit separate authorization required. |
| 100 | 실주문/자동 실전매매 | intentionally absent | none | LOCKED_FUTURE | Current product must not imply this is active. |

---

## 2. Current route disposition

| Current route | Decision |
|---|---|
| Home | retire as primary route; recommendation and useful summaries move to 실전매매, remaining market/status blocks to 탐색/운영 |
| Market / dashboard | keep capability, move to 탐색 |
| Research / Coin | split: primary selected-coin evidence moves to 가상매매; deep evidence moves to 연구·데이터 |
| Theme / Sectors | 탐색 |
| Assets | merge actual-position input + calculators into 실전매매; history goes to 기록 |
| PAPER | merge into 가상매매 |
| Strategy | merge into 가상매매 |
| Records | keep as 기록 |
| System | keep as 운영, reachable from utility/admin rather than competing with primary trading navigation |

---

## 3. Projection gaps that block the canonical UI

These are the only backend/projection gaps that directly block the requested primary screens.

1. **Per-coin dominant strategy projection**
   - Inputs already exist across PAPER/Strategy metrics.
   - Need a canonical, sample-aware summary. Weak sample => “검증 부족”, not a forced winner.

2. **Per-strategy account state**
   - `strategy_lab_accounts` exists.
   - Selected coin + selected strategy must receive account/equity/cash/position/PnL.

3. **Per-strategy trade ledger**
   - `strategy_lab_trades` exists.
   - Current Viewer explicitly lacks experiment-level fills.

4. **BTC/ETH-relative historical evidence**
   - Relative-strength source exists.
   - Need selected-coin horizons usable by the 가상매매 page.

5. **Selected-coin event timeline + reaction memory**
   - Event/reaction/reaction-memory sources exist.
   - Need bounded Viewer projection for event time/type/source and 15m/1h/4h/1d coin/BTC/ETH response.

6. **Recommendation evidence envelope**
   - Rising-candidate row must combine current price, dominant strategy, next entry, PAPER evidence, BTC/ETH-relative movement and recent event reaction.
   - No promotion when required evidence is stale/insufficient.

Everything else can remain secondary while these six are completed.

---

## 4. Reference rules used for the next Low-fi

### CODE1 Drive Harness — adopted as process/IA discipline

Read-only reference, not copied styling.

- Low-fi validates function, information hierarchy, user flow, state and recovery before High-fi.
- External Git references must not rewrite product purpose.
- High-frequency tasks use **flat scan**; do not default to accordion/card nesting.
- One grouping surface may contain flat rows; do not make every row a card.
- Semantic component family is fixed before radius/color/spacing tuning.
- Real values/state/actions outrank helper copy and decorative chrome.
- Preserve selected entity/search/filter/scroll context.
- Validate representative 390px and desktop containment before visual freeze.
- Avoid generic AI dashboard patterns, repeated helper subtitles and meaningless three-card grids.

### External Git — implementation/reference principles only

**openexch/trading-ui**
- Useful reference: one selected market context drives market stats, chart, order/action rail and order/history surfaces without route hopping.
- Adopt: task adjacency, persistent instrument context, fixed/compact data hierarchy.
- Do not adopt: live order submission semantics; CRYPTO remains PAPER/read-only unless separately authorized.

**rampstackco/swiss-style-theme**
- Useful reference: dense information carried by grid discipline, typography, alignment and hairlines rather than card sprawl.
- Adopt: visible grid logic, tabular scan, restrained accent, whitespace as hierarchy.

**davaded/frontend-art-direction**
- Useful reference: inspect content/data readiness first; real content over fake visual polish; display-size typography off by default; avoid mechanical card grids and decorative gradients/glow.

**carbon-design-system/carbon**
- Useful reference: dense data/state tables, consistent component/state semantics and accessibility.
- Do not import Carbon as a new project dependency; use it as read-only pattern evidence.

### GitHub Star-list note

The connected GitHub tool in this session exposes repositories/search but does **not** expose the authenticated user's starred-repository list endpoint. Therefore no repository is being claimed as “user-starred” without evidence. CODE1's curated Git reference registry plus public external repository research is used instead.

---

## 5. Gate

Mapping table is the authority for the next Low-fi.

No source/UI implementation before:
1. this map is accepted or corrected;
2. the two primary page Low-fi hierarchy is reviewed;
3. each primary component points to an existing capability or one of the six explicit projection gaps.
