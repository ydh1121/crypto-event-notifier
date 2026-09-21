# CRYPTO PURPOSE → PAGE CANONICAL MAP

Status: CANONICAL IA v2 — SIMPLIFIED
Date: 2026-09-21
Authority: user-defined trading workflow. Existing features must fit this structure, not the other way around.

## 0. Product rule

The product is not a dashboard collection.

It has three user-facing jobs:

1. 실제로 살 코인을 고르고, 어떤 전략으로 어디서 얼마나 진입/익절할지 본다.
2. 개별 코인에서 전략별 PAPER 성과와 BTC/ETH 대비 움직임, 뉴스·지표 이벤트 반응을 본다.
3. 그 외 이미 개발된 기능은 위 두 작업을 방해하지 않도록 보조/관리 페이지에 정리한다.

Any feature that does not directly serve job 1 or job 2 must not compete for primary screen space.

---

# 1. 실전매매

This is the primary operating page.

## 1.1 거래 대상 선택

- 거래소
  - 빗썸
  - 업비트
- 코인명 / 티커 검색
- 현재 가격

## 1.2 현재 우세 전략

Selected coin 기준.

- 우세 전략 1개 또는 복수
- 전략별 검증 상태
- 전략별 최근 PAPER 성과
- 표본 부족 시 명확히 "검증 부족"

No decorative score wall. The purpose is to choose the strategy to act on.

## 1.3 전략별 진입 계획

Each strategy row/panel:

- 전략명
- 진입 타점
  - 1차
  - 2차
  - 3차+
- 진입 비중
  - 1차 %
  - 2차 %
  - 3차+ %
- 총 진입 비중
- 현재가 대비 거리
- 조건 충족 여부

## 1.4 전략별 익절 계획

Each strategy row/panel:

- 익절 타점
  - 1차
  - 2차
  - 3차+
- 익절 비중
  - 1차 %
  - 2차 %
  - 3차+ %
- 잔여 물량
- 고점보호 / trailing 기준이 존재하면 함께 표시

## 1.5 물타기 계산기

- 현재 보유 수량
- 현재 평균단가
- 추가 투입금
- 분할 횟수
- 회차별 매수가
- 회차별 투입 비중
- 회차별 수량
- 예상 평균단가
- 총 투입금

## 1.6 익절 계산기

- 보유 수량
- 평균단가
- 현재가
- 목표 익절가
- 분할 횟수
- 회차별 익절가
- 회차별 익절 비중
- 예상 실현이익
- 잔여 수량
- 최종 수익률

## 1.7 곧 상승 가능성이 높아 보이는 코인

A compact recommendation panel, not a separate dashboard.

Each row:

- 거래소
- 티커
- 현재가
- 우세 전략
- 다음 진입 타점
- 최근 PAPER 근거
- BTC/ETH 대비 움직임
- 최근 이벤트 반응 요약
- "실전매매에서 보기"

Recommendation must be evidence-backed. If evidence is insufficient, do not promote the coin.

---

# 2. 가상매매

Primary purpose: validate strategies per coin.

## 2.1 코인 선택

- 거래소
- 티커 검색
- 현재가
- 현재 PAPER 상태

## 2.2 개별 코인 페이지

The coin stays selected while moving between the following tabs.

### A. 전략별 탭

One tab per strategy.

Each strategy tab must contain:

#### 계좌 현황
- 시작금
- 현재 평가액
- 현금
- 보유 수량
- 평균단가
- 미실현손익
- 실현손익
- 누적수익률
- 최대 낙폭

#### 현재 포지션 / 계획
- 현재 포지션
- 다음 진입 타점
- 다음 진입 비중
- 다음 익절 타점
- 다음 익절 비중
- 손절 / 중단 기준

#### 매매 내역
- 매수/매도
- 체결 시각
- 체결가
- 수량
- 비중
- 실현손익
- 진입/청산 근거

#### 전략 성과
- 거래수
- 승률
- 평균 손익
- 기대값
- 최대 낙폭
- 최근 N회 성과
- 검증 상태

### B. BTC / ETH 대비 움직임

- 코인 vs BTC
- 코인 vs ETH
- 상대강도
- 기간별 반응
  - 15m
  - 1h
  - 4h
  - 1d
- 상승/하락 시 동조 또는 역행 여부

### C. 뉴스·지표·이벤트 반응

Timeline/table 형태.

- 이벤트 종류
  - 거시지표
  - FOMC
  - 규제/공식 뉴스
  - 거래소 공지
  - 상장/유의/종료
  - 코인 개별 뉴스
- 이벤트 시각
- 당시 가격
- BTC 반응
- ETH 반응
- 해당 코인 반응
- 15m / 1h / 4h / 1d 반응
- 과거 동일 유형 평균 반응
- 표본 수

No separate event maze. This exists to explain the selected coin.

---

# 3. 보조 페이지

All other current features go here. They must remain accessible but must not dominate the primary workflow.

## 3.1 시장 / 탐색

- 전체 시장 상태
- 상승/하락 종목
- 거래대금
- 테마/섹터
- 상장/유의/종료
- 시장 온도
- BTC/ETH 시장 컨텍스트

Purpose: scanning and discovery only.

## 3.2 연구 / 데이터

- Flow
- CVD
- orderbook
- absorption
- price-flow divergence
- listing history
- DEX research
- source/provenance
- raw evidence
- research completeness

Purpose: deep inspection when needed.

## 3.3 기록

- PAPER 체결 전체
- 전략 연구 체결 전체
- 판단 변경
- 학습 변경
- 이벤트 기록
- 오류/incident

Purpose: audit/history.

## 3.4 운영 / 시스템

- runtime status
- collector status
- DB row/freshness
- publisher/projection
- backup
- Git/CI
- Pages deployment
- alerts
- account/access

Purpose: operations only.

---

# 4. Global navigation candidate

Keep the top level short.

- 실전매매
- 가상매매
- 탐색
- 기록
- 운영

"연구/데이터" can be a secondary route under 탐색 or a detail entry from the selected coin.

Do not restore a large top-level route list.

---

# 5. Existing route disposition

| Current area | Canonical destination |
|---|---|
| Home/dashboard | remove as a primary destination; useful recommendation/readiness fragments move into 실전매매 or 탐색 |
| Research/Coin | becomes 가상매매 selected-coin evidence + secondary research entry |
| Market dashboard | 탐색 |
| Theme/Sectors | 탐색 |
| PAPER | 가상매매 |
| Strategy | 가상매매 strategy tabs/comparison |
| Assets | 실전매매 calculators/actual position inputs |
| Records | 기록 |
| System | 운영 |

No implemented capability is deleted. It is reclassified.

---

# 6. UI priority rules

1. 실전매매 page must answer within one screen:
   - 무엇을 살까?
   - 어떤 전략이 우세한가?
   - 어디서 몇 % 살까?
   - 어디서 몇 % 팔까?

2. 가상매매 coin page must answer:
   - 이 코인에서 어떤 전략이 실제 PAPER로 잘 작동했나?
   - BTC/ETH와 어떻게 다르게 움직였나?
   - 뉴스/지표 이벤트 때 어떻게 반응했나?

3. Supporting features may be one or two clicks away.
4. Supporting features must not create competing dashboard cards on the primary pages.
5. If a feature cannot be assigned to one of these purposes, place it under 연구/데이터 or 운영.
6. No UI coding begins until existing features are mapped to this simplified tree.

---

# 7. Immediate next planning task

Create one implementation mapping table only:

| Existing capability | Current route | Canonical destination | Reuse as-is / move / merge / hide-secondary | Projection gap |
|---|---|---|---|---|

Then build page wireframes from that table.

Do not create another broad feature tree.
Do not resume page-by-page cosmetic repair first.
