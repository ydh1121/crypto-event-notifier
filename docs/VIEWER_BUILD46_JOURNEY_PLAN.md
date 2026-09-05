# Viewer Build 46 — beginner journey reset

## User baseline

Primary review persona: a Korean coin trader in their 60s who can use an exchange app but is not a developer or technical trader.

The default experience must answer, in this order:

1. Is the market broadly strong, weak, or unclear today?
2. Which coins deserve attention now, which should wait, and which should be avoided?
3. For a coin I already own, what are my average price/P&L and the current strategy reference for the next add, remaining split count, take-profit target, and stop?
4. Has the current PAPER method actually performed well?
5. What changed recently?

Technical research terms remain available in detail screens but are not the first layer.

## Build 46 IA

Top navigation:

- 홈
- 코인 찾기
- 내 코인
- 매매 성적
- 기록

Secondary routes:

- 홈: 오늘 보기 / 상세 현황
- 코인 찾기: 코인 보기 / 섹터별 보기
- 매매 성적: 매매 성적 / 전략 비교
- 시스템: top navigation에서 제외하고 우측 상태/사용자 utility로 접근

Existing advanced pages are preserved. This build changes discovery and context, not the research/PAPER engine.

## Home contract

Home prioritizes plain-language actions:

- current market mood
- 매수 관심 / 가격 기다림 / 지금은 피하기 counts
- highest-priority coins by current decision
- actual holdings sorted from the worst unrealized P/L first
- selected holding: next add reference price, remaining PAPER split count, take-profit reference, stop
- current combined PAPER summary
- recent fills/learning changes
- optional entry points to sector, strategy comparison, and advanced dashboard

The add/take-profit/stop values are existing PAPER trade-plan references. They are not new live-order logic.

## Context continuity

When the user explicitly moves between related workspaces, carry the current exchange/market where possible:

- Research ↔ Sector
- Research ↔ PAPER
- PAPER ↔ Strategy
- Research/PAPER → Assets

This is route-transition context handoff, not a single global exchange mode.

## Roadmap audit after Build 46

### Confirmed incomplete in existing repository roadmap

- Phase 5: on-chain / news / community / macro context
- Phase 6: AI combined interpretation
- Phase 7: walk-forward UI
- Phase 8: candidate-promotion UI
- GitHub Actions CI status surfaced in Viewer
- mobile 390/430 focused QA

The rebuild checklist still marks some items as incomplete even though newer code has already implemented them. Current code includes holdings history, record strategy filtering, decision-change records, and system-event records; the checklist needs reconciliation rather than duplicate implementation.

### Build 47 candidate — market context for ordinary users

Existing roadmap only names the broad Phase 5 categories. The following concrete US-market/event scope is added from current product requirements:

- crypto news headline/event ingestion with source and timestamp
- major US risk indicators: S&P 500, Nasdaq, Dow, VIX, DXY, US 2Y/10Y yields
- economic calendar: FOMC/rate decision, Fed Chair speeches, CPI, PPI, PCE, employment/NFP, unemployment, GDP
- before/after event windows and plain-language impact labels
- important-event countdown on Home and Research
- avoid presenting a causal claim when only temporal correlation is known

### Build 48 candidate — holding action guidance

The current averaging calculator can model up to 20 manual rounds, but a true beginner-facing recommendation layer still needs:

- when not to average down
- risk-aware recommended number of remaining adds using actual exposure, remaining budget, stop distance, and volatility
- per-round suggested amount rather than only price
- projected average price and break-even after each add
- maximum exposure / stop-loss conflict checks
- staged take-profit plan (partial exits) instead of a single target only
- trailing/profit-protection rule after target progress
- plain-language explanation of why the plan changed

Until that risk layer exists, Viewer must label the current values as PAPER strategy references rather than personalized live-order instructions.

### Research/OOS work that continues independently

- V1 vs V2 forward OOS comparator data collection
- V2 observation gate after enough forward events
- V2 confirmation gate after larger forward sample
- adopt/reject decision without retrospective threshold lowering
- only after validation: PAPER integration preregistration and later execution-safety work
