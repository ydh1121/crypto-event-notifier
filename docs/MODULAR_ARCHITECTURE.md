# Crypto Auto Trader Modular Architecture

이 문서는 기능이 늘어날수록 페이지/collector/scorer가 서로 얽히는 것을 막는 영구 구조 규칙이다.

핵심 원칙은 **한 기능의 수집, 저장, 계산, 점수화, 표시를 서로 다른 계층으로 분리하고 공통 로직은 한 곳에서만 소유하는 것**이다.

## 1. 의존 방향

의존은 아래 방향으로만 흐른다.

`source/collector → store/repository → feature/domain → score/decision → service/API → page/view`

역방향 의존을 만들지 않는다.

예:
- Viewer page가 거래소 API를 직접 호출하지 않는다.
- Viewer page가 수익률/신호/상태를 자체 계산하지 않는다.
- scorer가 HTML/UI 문구를 만들지 않는다.
- collector가 PAPER 매수 여부를 결정하지 않는다.
- Cloudflare API route에 동일한 domain 계산식을 복붙하지 않는다.

## 2. Cloudflare Pages Viewer

### core/
앱 생명주기만 소유한다.
- router
- store
- auth
- snapshot polling
- HTTP 공통 처리

### shared/
여러 페이지에서 재사용하는 순수 UI/interaction 로직만 둔다.
- format
- chart primitives
- table sorting
- IME guard
- UI continuity / scroll-focus preservation
- 공통 components

페이지 고유 데이터 의미를 shared에 넣지 않는다.

### services/
Viewer의 데이터 접근 경계다.
- API URL 구성
- cache
- fetch/retry
- response normalization

페이지에서 `fetch()` 또는 API URL을 직접 만들지 않는다.

### pages/
페이지는 **조합과 이벤트 wiring**만 한다.
- service에서 받은 모델을 표시
- store의 UI state 선택
- 공통 component 조합
- 사용자 이벤트를 store/service에 전달

새 계산식, 외부 fetch, 장기 cache, 복잡한 데이터 정규화는 pages에 넣지 않는다.

### styles/
공통 primitive와 페이지 레이아웃을 분리한다. 기능을 고치기 위해 무관한 전역 CSS override를 누적하지 않는다.

## 3. Cloudflare Functions

### functions/api/
HTTP boundary만 소유한다.
- auth
- query/body validation
- lib/service 호출
- response/error mapping

복잡한 identity, lifecycle, scoring, event classification 계산은 route 파일에 직접 누적하지 않는다.

### functions/lib/
도메인 규칙을 둔다.
예:
- coin identity
- taxonomy/facets
- market lifecycle
- return windows
- event taxonomy
- score normalization

### repository/storage helper
D1 SQL이 반복되기 시작하면 domain 계산과 분리된 repository helper로 승격한다.
같은 SELECT/UPSERT 문장을 여러 API route에 복붙하지 않는다.

## 4. Python runtime

새 분석기능은 아래 역할로 나눈다.

### collectors
외부/거래소 데이터를 읽고 canonical raw record를 만든다.
- market list
- OHLCV
- trades/orderbook
- listing notices
- news/events
- onchain/community

collector는 점수를 결정하지 않는다.

### stores/repositories
SQLite에 append/upsert하고 조회한다.
- raw source history
- feature history
- reaction outcomes
- PAPER journal

### features
순수 계산 또는 최소 side effect로 feature를 만든다.
예:
- return windows
- volume delta/CVD
- orderbook imbalance
- MA/RSI/Supertrend
- pivot/Fibonacci/channel
- lifecycle premium

### scorers
이미 만들어진 feature를 입력받아 독립 score family를 계산한다.
예:
- regime
- entry
- flow
- structure
- event
- human
- onchain
- lifecycle risk
- liquidity risk

### orchestration
supervisor/cycle은 collector/feature/scorer/store를 호출하는 순서만 소유한다.
도메인 계산식을 supervisor에 넣지 않는다.

## 5. Feature family 규칙

모든 신규 feature는 최소 다음 metadata를 가진다.
- source
- source_ts
- received_at
- freshness
- confidence
- feature_version

같은 가격현상을 설명하는 feature는 family를 공유한다. 최종 score에서 같은 family의 상관된 feature를 무제한 합산하지 않는다.

승격 단계:

`raw collection → normalized feature → history DB → reaction validation → shadow score → PAPER A/B → walk-forward → candidate`

검증 전 feature는 기존 PAPER 주문결정에 직접 영향을 주지 않는다.

## 6. UI continuity 규칙

스크롤/포커스/선택 상태는 페이지마다 임시 코드를 만들지 않는다.

공통 소유자:
`public/modules/shared/ui-continuity.js`

금지:
- 선택 버튼마다 `window.scrollTo()` 복붙
- 페이지마다 별도 `scrollTop` 저장 변수
- broad `MutationObserver`로 DOM 재렌더 감시
- polling 때 전체 페이지를 무조건 다시 생성

페이지 이동처럼 의도적으로 상단 이동이 필요한 경우만 opt-out 한다.

## 7. 신규 상장/lifecycle 구조

향후 상장/유의/상폐 기능은 하나의 lifecycle domain으로 소유한다.

입력:
- exchange market list diff
- official exchange notice
- first/last trade availability

출력 canonical state:
- NORMAL
- LISTING_ANNOUNCED
- NEW_LISTING
- CAUTION
- TERMINATION_SCHEDULED
- TERMINATED

Viewer, PAPER eligibility, history collector가 각각 공지 원문을 해석하지 않고 lifecycle state만 소비한다.

## 8. 가격/수급 구조

OHLCV, trade flow, orderbook은 raw history를 한 번 저장한 뒤 여러 feature가 재사용한다.

예:
- D-1~D-5 수익률
- relative strength
- volume delta/CVD
- price efficiency
- absorption
- technical indicators

같은 거래소 candle API를 각 기능이 따로 호출하지 않는다.

## 9. 완료 기준

새 기능을 완료 처리하려면:
- 계산/수집 로직의 단일 소유자가 명확함
- 기존 모듈에 동일 로직 복붙 없음
- API/page는 얇은 orchestration/representation 역할
- 저장 schema가 additive/backward compatible
- unit/contract test 존재
- 기존 PAPER와 Viewer regression PASS
- MASTER_ROADMAP/TASKS/HANDOFF 갱신

기능 구현이 빠르더라도 위 계층을 깨면 완료로 처리하지 않는다.
