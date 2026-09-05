# Trading UI Reference Patterns

이 문서는 Cloudflare Pages Viewer를 다시 설계할 때 참고한 공개 트레이딩 UI 저장소의 구조와 채택 원칙을 고정한다.

목적은 외부 UI를 복제하는 것이 아니라, 운영형 트레이딩 제품에서 반복되는 안정적인 정보구조 패턴을 추출하고 우리 데이터/권한 모델에 맞게 적용하는 것이다.

검토 기준일: 2026-08-26

## 1. FreqUI — `freqtrade/frequi`

확인 경로:
- `src/pages/dashboard.vue`
- `src/components/layout/NavBar.vue`
- `src/components/ftbot/BotComparisonList.vue`
- `src/stores/layout.ts`
- `e2e/dashboard.spec.ts`
- `e2e/analysis.spec.ts`
- `e2e/backtest.spec.ts`

관찰:
- Dashboard는 Profit over time, Bot comparison, Open Trades, Closed Trades, Cumulative Profit, Wallet History, Profit Distribution, Trades Log처럼 목적이 다른 블록을 명시적인 컴포넌트로 나눈다.
- 페이지와 store/layout 책임이 분리되어 있다.
- 반복 비교 데이터는 개별 큰 카드보다 비교/list 컴포넌트를 사용한다.
- 화면 구성에 E2E 검증이 존재한다.

채택:
- [x] 페이지 모듈과 store/router 분리
- [x] 전략 비교는 표 중심
- [x] PAPER 코인 결과는 master-detail
- [x] 기록은 별도 workspace
- [x] 레이아웃/기능 계약을 CI에서 검사

비채택:
- [x] 사용자가 직접 drag/resize 하는 Dashboard grid는 기본 기능으로 도입하지 않음. 우리 Viewer는 읽기 전용이고 우선순위가 고정되어야 한다.

## 2. Hummingbot Dashboard — `hummingbot/dashboard`

확인 경로:
- `frontend/pages/orchestration/portfolio/`
- `frontend/pages/orchestration/instances/`
- `frontend/pages/performance/bot_performance/`
- `frontend/pages/config/*`
- `frontend/components/backtesting.py`
- `frontend/components/risk_management.py`
- `frontend/components/executors_distribution.py`

관찰:
- Portfolio, bot instance orchestration, performance, strategy/config가 별도 페이지 영역으로 분리된다.
- backtesting/risk/distribution 같은 기능이 공통 component로 분리되어 페이지가 조합한다.
- 전략 설정과 전략 성과를 같은 화면에 무조건 섞지 않는다.

채택:
- [x] 자산 / PAPER / 전략 연구 / 시스템을 독립 workspace로 분리
- [x] 공통 formatter/selectors/components/services를 pages 밖에 둠
- [x] 전략 생성/제어와 외부 read-only 성과 확인 권한을 분리

비채택:
- [x] 로컬 운영/오케스트레이션 기능을 외부 Pages에 그대로 노출하지 않음.

## 3. OpenAlgo — `marketcalls/openalgo`

확인 경로:
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/monitoring/TrafficDashboard.tsx`
- `frontend/src/pages/monitoring/LatencyDashboard.tsx`
- `frontend/src/App.tsx`
- `docs/userguide/07-dashboard-overview/README.md`

관찰:
- Dashboard 상단은 Available Balance, Collateral, Unrealized P&L, Realized P&L, Utilised Margin 같은 계정 핵심 숫자를 먼저 둔다.
- 데이터/세션 상태는 별도 상태 표시로 처리한다.
- 검색, 로그, P&L Tracker, Latency Monitor 등 목적이 다른 기능은 Quick Access/독립 route로 분리한다.
- monitoring 기능은 일반 Dashboard와 분리한다.

채택:
- [x] Dashboard에는 전체 상태와 이동 진입점만 둠
- [x] 시스템 최신 상태는 주 Navigation이 아니라 utility 영역으로 분리
- [x] 실제 자산/PAPER 손익 숫자를 첫 화면에서 바로 확인

비채택:
- [x] 주문/브로커 조작 UI는 도입하지 않음. 이 Viewer는 PAPER/READ ONLY 계약을 유지한다.

## 4. OpenBB — `OpenBB-finance/OpenBB`

관찰:
- 금융 데이터 기능을 provider/extension 단위로 분리하는 대규모 모듈 구조가 강하다.
- 제품 범위가 우리 Viewer보다 훨씬 넓어 화면 배치를 직접 복제할 대상은 아니다.

채택:
- [x] 향후 Phase 5 context data와 Phase 6 AI를 기존 페이지의 service/provider 계층으로 추가하고 새로운 최상위 페이지를 남발하지 않는다.

비채택:
- [x] 범용 금융 터미널 수준의 다중 메뉴/데이터 카탈로그를 현재 Viewer에 도입하지 않는다.

## 5. 우리 Viewer에 고정하는 레이아웃 패턴

### Dashboard
- Summary dashboard.
- 먼저 확인할 것 → 실제 자산 → 시장 → 전체 PAPER → 전략 검증 → 최근 중요 변화.
- 긴 상세 목록/설정 폼 금지.

### Research
- PC master-detail.
- 좌측: 거래소/시장요약/검색/필터/후보 목록.
- 우측: 현재 판단 → 가격 → 점수 → 실제보유 → PAPER 참고 → 판단근거/차트/체결/학습.
- 코인 선택 때문에 다른 최상위 route로 자동 이동 금지.

### Assets
- PC master-detail.
- 위: 평가액/원금/손익/배분.
- 좌측: 실제 보유종목.
- 우측: 선택 보유종목 상세 + 빗썸/업비트 리서치/PAPER 참고.
- 종목 클릭 시 자산 화면 유지.

### PAPER
- Summary + master-detail + compare.
- 요약: 빗썸+업비트 전체 증감액을 최우선.
- 코인별: 좌측 목록, 우측 계좌/계획/체결/학습.
- 거래소 비교: 검색/정렬/sticky header.

### Strategy
- Comparison table + selected detail.
- 전략별 큰 카드 반복 금지.
- 사용자 전략 생성/제어는 로컬 PC 전용.

### Records
- Filter toolbar + chronological feed/table.
- 거래소/기간/코인/종류 필터.
- 기록 선택 때문에 다른 화면으로 강제 이동 금지.

### System
- Status/settings workspace.
- 메인 사용자 여정에서 분리.

## 6. 금지 규칙

- [x] page module이 다른 page DOM을 수정하지 않는다.
- [x] 동일 데이터의 renderer를 여러 스크립트가 중복 소유하지 않는다.
- [x] 거래소 선택을 전역 단일 mode로 공유하지 않는다.
- [x] 상태 badge와 action button을 같은 visual role로 만들지 않는다.
- [x] 반복 비교 데이터를 큰 카드 묶음으로 만들지 않는다.
- [x] 외부 Pages에서 실제 주문/보유자산 수정/전략 생성 기능을 추가하지 않는다.
- [x] 기능을 삭제하거나 숨길 때 `VIEWER_REBUILD_CHECKLIST.md`를 먼저 갱신한다.
