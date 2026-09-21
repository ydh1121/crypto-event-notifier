# UX Information Architecture V10

## 1. Product goal

The viewer is not a feature catalogue. Its primary job is to help one user move through one decision loop with minimum search cost:

**시장 파악 → 코인 판단 → 내 자산 확인 → 모의 실행 → 전략 평가 → 결과 회고**

Every screen must have one primary question. Existing functions are mapped under that question after the hierarchy is fixed. A function does not earn first-screen placement merely because it exists.

## 2. Global interaction rules

1. One shared content width for header, page title and page body.
2. Scroll ownership is explicit. The document owns long-form result/detail reading. A bounded master selection rail may own its own vertical scroll when the list must remain usable beside a long detail pane.
3. Result panes, cards and arbitrary content blocks do not get independent vertical scroll containers.
4. Horizontal scrolling is allowed for data tables that cannot reasonably collapse.
5. The shell header is sticky. On desktop master-detail screens, the selection rail may also be sticky so the user can continue changing the selected item while reading a long detail pane.
6. Every page has one first-priority answer above secondary evidence.
7. Navigation uses user goals, not implementation names.
8. A selected coin must expose its current price immediately in the first detail block.
9. Controls have three roles only: navigation tabs, selection controls, primary/secondary actions.
10. Historical evidence, diagnostics and specialist research are secondary layers and must not compete with the primary decision.
11. Source order must match visual order. CSS `order` is not used to repair information architecture.

### Scroll ownership rule

Use bounded vertical scrolling only where it solves an actual navigation problem:

- Research coin list: bounded selection rail.
- Assets holdings list/rail: bounded selection rail.
- Paper market list: bounded selection rail.
- Strategy experiment list: bounded selection rail.
- Large comparison/trade tables: horizontal scrolling as needed.
- Selected result/detail content: document scrolling, not an internal height trap.

Desktop master-detail behavior is therefore **sticky bounded rail + document-flow detail**. Mobile behavior is **bounded list + explicit list-to-detail handoff**.

## 3. Functional hierarchy

### A. Observe / Discover
- Home attention summary
- BTC / ETH and market regime
- Market breadth and status
- Themes / sectors
- Coin discovery and search
- Selected coin current price

### B. Decide
- Current coin decision
- Entry / add / stop / target plan
- Risk and market context
- BTC / ETH comparison context
- Supporting research and historical evidence

### C. Manage
- Portfolio total value and PnL
- Holdings and allocation
- Selected holding current price, average price and PnL
- Budget / averaging tools
- Holding history

### D. Simulate / Execute
- Paper balance and equity
- Selected coin paper position
- Order sizing and action
- Open orders / fills / order events
- Current paper strategy context

### E. Evaluate
- Strategy experiment comparison
- Selected strategy summary
- Per-coin strategy performance
- Strategy-specific virtual trade ledger
- Equity / drawdown evidence
- Candidate criteria and experiment settings

### F. Audit / Operate
- All paper fills and feedback
- Decision / system journal
- Diagnostics
- Account and viewer settings

## 4. Primary navigation

Top-level navigation is task-based and fixed to six destinations:

1. 홈
2. 시장
3. 자산
4. 모의투자
5. 전략
6. 기록

`더보기` is not a primary task. Diagnostics and settings remain reachable from the account control.

Market has one secondary navigation group:
- 코인
- 시장현황
- 테마

Paper and Strategy are separate first-class destinations. They are not hidden under a shared secondary group because their user questions are different.

## 5. Screen responsibility and priority

### 홈 — “지금 무엇을 먼저 봐야 하나?”
1. Items that need attention now
2. Portfolio / risk snapshot
3. Market regime snapshot
4. Recent meaningful execution
5. Shortcuts to the responsible screen

The home screen must not duplicate full tables from Market, Assets, Paper or Strategy.

### 시장 / 코인 — “이 코인을 지금 어떻게 봐야 하나?”
1. Selected coin identity + **current price**
2. Current decision / conclusion
3. Actionable trade plan
4. Why: market / momentum / volume / BTC context
5. My holding and paper context
6. Historical charts, fills, listing study and specialist research

Current price is not evidence. It is instrument identity and must be visible without searching.

### 시장 / 시장현황 — “전체 시장은 어떤 상태인가?”
1. BTC / ETH
2. Market regime and breadth
3. Exchange / universe status
4. Supporting metrics

### 시장 / 테마 — “어디에 움직임이 모이고 있나?”
1. Theme ranking
2. Theme constituents
3. Coin drill-down

### 자산 — “내 돈이 지금 어디에 있고 무엇을 해야 하나?”
1. Total value / PnL
2. Holdings list + selected holding
3. Selected holding current price / average price / PnL / weight
4. Decision reference and budget tools
5. Averaging calculators
6. Holding history

### 모의투자 — “현재 가상 포지션과 다음 행동은 무엇인가?”
1. Selected coin + current price
2. Current paper position / order action
3. Account result KPIs
4. Trade plan
5. Orders / fills / events
6. Secondary diagnostics

### 전략 — “어떤 매매방법이 실제로 더 나은가?”
1. Strategy comparison rail
2. Selected strategy summary
3. Per-coin result
4. **Strategy-specific virtual trade ledger**
5. Equity / drawdown evidence
6. Candidate criteria / experiment settings

The strategy trade ledger is distinct from the global Paper fills page. It answers why one experiment produced its reported return.

### 기록 — “무슨 일이 실제로 기록됐나?”
1. All fills
2. Filters
3. Detail / feedback / journal drill-down

### 시스템 — “서비스가 정상인가 / 설정은 무엇인가?”
Diagnostics and settings only. It is accessed from the account control, not primary navigation.

## 6. Strategy virtual trade data contract

The UI accepts a strategy-specific ledger under `public.strategy_lab` using either canonical field:

- `strategy_trades`
- `trades`
- `fills`

Preferred canonical shape:

```json
{
  "strategy_trades": {
    "<experiment_id>": [
      {
        "ts": 0,
        "market": "KRW-BTC",
        "side": "buy",
        "price": 0,
        "qty": 0,
        "pnl_krw": 0,
        "fee_krw": 0,
        "status": "closed"
      }
    ]
  }
}
```

A flat array is also accepted when each row carries `experiment_id`.

Until the producer publishes this ledger, the Strategy screen must show an explicit data-missing state. It must not fabricate trades from aggregate statistics.

## 7. Existing-function mapping rule

When an existing component conflicts with this hierarchy:

- Keep the underlying function/data if useful.
- Move it to the responsible screen or a secondary layer.
- Do not preserve its old location merely to avoid code changes.
- Do not create arbitrary nested scroll containers. Bounded selection rails are allowed because they preserve simultaneous list/detail navigation.
- Do not solve ordering with CSS `order`.
- Do not add another global override stylesheet to repair a page-specific contradiction.

This document is the gate for subsequent UI work. Screen changes are evaluated against this hierarchy before visual polish.
