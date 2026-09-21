# CRYPTO SIMPLIFIED TRADING LOW-FI SPEC v1

Status: PLANNING / USER REVIEW REQUIRED
Date: 2026-09-21
Input: user-defined trading workflow + `EXISTING_CAPABILITY_CANONICAL_MAPPING_V1.md`

This spec intentionally designs only two primary pages.

---

# 0. Global shell

Desktop primary navigation candidate:

`실전매매 | 가상매매 | 탐색 | 기록`

Utility area:

`기본/상세 | 밝게/어둡게 | 운영(관리자) | 로그아웃`

Rules:
- 운영 is not a primary trading destination.
- No separate top-level “매매방법” route.
- No separate top-level “자산” route.
- Selected exchange/coin context is page-local and sticky.
- No generic Home dashboard is required.

Mobile candidate:
- primary navigation must keep the same four destinations;
- exact control pattern is NOT_FROZEN until low-fi review.

---

# 1. 실전매매 Low-fi

## 1.1 Purpose

One page answers:

1. 무슨 코인을 볼까?
2. 지금 어떤 전략이 우세한가?
3. 어디서 몇 % 살까?
4. 어디서 몇 % 팔까?
5. 실제 보유 중이면 물타기/익절 계산 결과는 어떻게 되는가?

No general market dashboard inside this page.

## 1.2 Desktop hierarchy

```
┌─────────────────────────────────────────────────────────────────────┐
│ [빗썸|업비트] [티커/코인 검색________________] 현재가 0.0000원     │
│ 실제보유: 수량 · 평단 · 평가액 · 손익 (보유하지 않으면 숨김)        │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────┬──────────────────────────────────────────────┐
│ 상승 가능성 후보     │ 선택 코인 전략 계획                         │
│                      │                                              │
│ TICKER  현재가       │ [우세 전략 / 검증 상태 / PAPER 표본]        │
│ 우세전략 · 다음진입  │                                              │
│ 근거 1~2줄           │ 전략 | 진입 타점/비중 | 익절 타점/비중      │
│ [보기]               │ ──────────────────────────────────────────── │
│                      │ 전략A  1차/2차/...   1차/2차/...             │
│ ...                  │ 전략B  1차/2차/...   1차/2차/...             │
│                      │ 전략C  표본부족                              │
│                      │                                              │
│                      │ 선택 전략 상세 근거는 한 줄/Disclosure      │
└──────────────────────┴──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ [물타기 계산] [익절 계산]                                           │
│                                                                     │
│ 선택된 계산기만 표시.                                               │
│ 입력 → 분할 회차 결과를 flat rows/table로 표시.                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 1.3 상승 가능성 후보 row

Only actionable information:

- 거래소
- 티커
- 현재가
- 우세 전략
- 다음 진입가
- 최근 PAPER 근거
- BTC/ETH 대비 요약
- 최근 이벤트 반응 요약

No score-wall. Scores may be secondary metadata.

Selecting a row changes the selected coin in the right workspace without route change.

## 1.4 Strategy plan matrix

Primary dense table, not a grid of cards.

Columns:
- 전략
- 검증 상태
- PAPER 표본
- 진입 1차 / 비중
- 진입 2차 / 비중
- 진입 3차+ / 비중
- 익절 1차 / 비중
- 익절 2차 / 비중
- 익절 3차+ / 비중
- 손절/중단
- 현재 조건

If sample is insufficient:
- show `검증 부족`;
- do not fabricate entry/exit authority.

## 1.5 Calculator treatment

One grouping surface with two local modes:

`물타기 | 익절`

Do not render both as large simultaneous cards.

### 물타기
Inputs:
- actual quantity / avg price when held
- additional budget
- number of splits
- per-leg buy price / allocation

Output:
- per-leg amount/quantity
- resulting avg price
- total invested

### 익절
Inputs:
- quantity / avg price
- split count
- per-leg target / allocation

Output:
- per-leg realized PnL
- remaining quantity
- total expected PnL / return

## 1.6 Mobile

Order of information:
1. exchange + coin + current price
2. dominant strategy / next action
3. strategy plan horizontal/stacked rows
4. calculator
5. rising candidates

Candidate list moves below selected-coin task flow on small screens so discovery does not push the active trade plan off-screen.

---

# 2. 가상매매 Low-fi

## 2.1 Purpose

One selected coin answers:

1. 어떤 전략이 이 코인에서 잘 작동했는가?
2. 각 전략 계좌에서 실제로 어떤 PAPER 거래가 일어났는가?
3. BTC/ETH와 비교하면 어떻게 움직였는가?
4. 뉴스·지표·거래소 이벤트 때 어떻게 반응했는가?

## 2.2 Desktop hierarchy

```
┌─────────────────────────────────────────────────────────────────────┐
│ [빗썸|업비트] [티커/코인 검색________________] 현재가 · PAPER 상태 │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ [전략] [BTC/ETH 대비] [이벤트 반응]                                │
└─────────────────────────────────────────────────────────────────────┘
```

### 전략 mode

```
┌──────────────┬──────────────────────────────────────────────────────┐
│ 전략 목록    │ [공격적] [균형] [보수적] [분할] [역추세] [스윙] ... │
│              │                                                      │
│ 성과순       │ 계좌 현황 strip                                     │
│ 검증상태     │ 시작금 | 평가액 | 현금 | 포지션 | PnL | DD          │
│              │                                                      │
│              │ 현재 계획                                           │
│              │ 다음 진입/비중 | 다음 익절/비중 | 중단 기준         │
│              │                                                      │
│              │ 매매 내역 table                                     │
│              │ 시각 | 매수/매도 | 가격 | 수량 | 비중 | PnL | 근거  │
│              │                                                      │
│              │ 성과 strip                                          │
│              │ 거래수 | 승률 | 평균손익 | 기대값 | DD | 검증상태   │
└──────────────┴──────────────────────────────────────────────────────┘
```

Rules:
- Strategy tab changes content in-place; selected coin never disappears.
- Account/trades/performance belong to the same strategy view.
- No separate route for “매매방법”.
- The trade ledger is a critical projection gap, not an optional enhancement.

### BTC/ETH 대비 mode

One main comparison surface.

- selected coin vs BTC
- selected coin vs ETH
- 15m / 1h / 4h / 1d
- relative return / direction / co-movement
- concise historical table beneath chart/summary

No generic technical-indicator dashboard here.

### 이벤트 반응 mode

Event timeline/table.

Columns/rows:
- event time
- type/source
- event title
- coin 15m / 1h / 4h / 1d
- BTC 15m / 1h / 4h / 1d
- ETH 15m / 1h / 4h / 1d
- historical same-type sample count / average
- disclosure for source/provenance

Filters:
- 거시지표
- FOMC
- 규제/공식뉴스
- 거래소 공지
- 상장/유의/종료
- 코인 개별

The page explains the selected coin; it is not a general news portal.

## 2.3 Mobile

Order:
1. selected exchange/coin
2. mode tabs: 전략 / BTC·ETH / 이벤트
3. in Strategy mode, strategy tabs become a horizontal rail
4. account strip
5. current plan
6. trade ledger
7. performance

No three-pane desktop master/detail layout is carried into mobile.

---

# 3. Secondary destinations

## 탐색

Purpose: find something worth opening, not decide a trade.

Keep:
- overall market state
- rising/falling/volume
- themes/sectors
- lifecycle/listing notices
- project/business description
- market context

Every coin row should deep-link into either 실전매매 or 가상매매 with the coin selected.

## 기록

Purpose: chronology/audit.

Keep:
- PAPER fills
- strategy-lab fills
- decisions
- learning changes
- event records
- incidents

## 운영

Purpose: owner/admin only.

Keep:
- runtime
- collectors
- DB/warehouse
- projection
- backup
- Git/CI/Pages
- alerts
- access/account
- safety contract

## 연구·데이터

Not necessarily a top navigation item.

Reach from 탐색/coin detail when deep evidence is needed:
- Flow/CVD
- orderbook
- absorption
- divergence
- listing history
- DEX research
- raw provenance

---

# 4. Visual/layout reference translation

This is pattern translation, not style copying.

## From CODE1 Drive Harness

Use:
- function/IA before visual styling;
- high-frequency flat scan;
- one grouping surface + flat rows instead of card-inside-card;
- semantic family before token tuning;
- real value/state/action over helper copy;
- preserve selected context and return state;
- validate 390px + desktop containment before High-fi.

Do not import:
- CODE1 commerce-specific navigation, brand or component styling.

## From openexch/trading-ui

Use:
- one persistent selected instrument context;
- adjacent task surfaces rather than route hopping;
- dense numeric scan;
- desktop terminal composition that keeps market/action/history in one context;
- mobile mode switch rather than squeezing desktop three-column layout.

Do not use:
- live order entry behavior;
- order-submission semantics;
- its decorative visual effects.

## From swiss-style-theme

Use:
- grid/alignment discipline;
- tabular dense information;
- whitespace and hairlines instead of repeated cards;
- restrained accent.

## From frontend-art-direction

Use:
- real data readiness first;
- display-size typography off by default;
- no mechanical card grids;
- no decorative gradient/glow as a substitute for hierarchy.

## From Carbon

Use:
- dense table/state readability;
- component/state consistency;
- keyboard/accessibility patterns.

No external UI library is added to CRYPTO by this planning document.

---

# 5. Low-fi acceptance gate

Before source implementation:

- [ ] User accepts/corrects the two primary page hierarchies.
- [ ] Every visible block maps to an existing capability or an explicit projection gap.
- [ ] No extra primary dashboard is introduced.
- [ ] No feature is deleted; secondary capabilities have a known destination.
- [ ] 실전매매 can answer “coin / strategy / buy / sell” without route hopping.
- [ ] 가상매매 can answer “strategy result / BTC-ETH / event reaction” without route hopping.
- [ ] Desktop grouping does not rely on equal-card grids.
- [ ] Mobile does not inherit a compressed desktop three-pane layout.
