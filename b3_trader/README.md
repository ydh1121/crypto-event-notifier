# B3 Paper Trader

B3 전용 시장 국면/진입 점수 기반 자동매매 실험 모듈입니다. 현재 Phase 2는 **실주문을 제출하지 않는 paper-only 모드**입니다.

## Phase 2에 추가된 것

- Bithumb Public WebSocket v1
  - `ticker`, `trade`, `orderbook`
  - 자동 재연결 및 REST fallback
- Bithumb Private WebSocket v2 클라이언트
  - `myOrder`, `myAsset`
  - 기본 비활성, API 키가 있을 때만 선택적으로 관찰용 연결
- 동적 외부 요인
  - 알트 바스켓 상대강도/상승 종목 비율
  - Base 후보군 상대강도
  - Gaming 후보군 상대강도
  - OKX BTC/ETH perpetual funding + open interest
- SQLite 거래 저널
  - 매 시점 signal snapshot
  - paper fill
  - 오류/차단 이벤트
- 가격 기반 백테스트
  - BTC/ETH/B3 동시간대 캔들 정렬
  - 48-bar rolling signal simulation
  - 최대 낙폭/수익률/fill 출력
- GitHub Actions 단위 테스트

## 중요한 설계 원칙

`RegimeScore`와 `EntryScore`를 분리합니다.

- RegimeScore: BTC/ETH/ETH-BTC/B3 상대강도 + 알트/Base/Gaming/파생시장
- EntryScore: B3 조정폭 + 38.2/50/61.8% retracement + 호가 imbalance + momentum + volatility

강한 장세라고 무조건 추격 매수하지 않고, 시장은 강하지만 진입 가격이 불리하면 `WAIT_PULLBACK`을 유지합니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r b3_trader/requirements.txt
cp b3_trader/.env.example .env
```

Windows에서는 가상환경 활성화 명령만 환경에 맞게 변경하면 됩니다.

## Paper runner

```bash
python -m b3_trader.main
```

Phase 2는 API 키 없이도 동작합니다. Public Bithumb/OKX 데이터만 사용합니다.

기본적으로:

- Bithumb 캔들: 60초마다 REST 갱신
- B3/BTC/ETH ticker/orderbook/trade: WebSocket
- Base/Gaming/alt/derivatives factors: 60초마다 갱신
- paper account: 1,000,000 KRW
- 단일 paper 주문: 50,000 KRW
- 최대 B3 paper position: 300,000 KRW
- daily loss circuit breaker: 3%

모든 값은 `.env`에서 변경할 수 있습니다.

## 거래 저널

기본 저장 위치:

```text
b3_trader/data/b3_trader.sqlite3
```

저장 테이블:

- `snapshots`
- `fills`
- `events`

SQLite 파일은 런타임 데이터이므로 Git에 커밋하지 않아야 합니다.

## Backtest

```bash
python -m b3_trader.backtest --bars 1000 --unit 5
```

현재 백테스트의 한계는 의도적으로 명시합니다.

- 과거 orderbook이 없으므로 neutral 처리
- 과거 Base/Gaming/derivatives/news가 없으므로 neutral 처리
- bar close 체결 가정
- 실거래 slippage/latency 모델은 아직 없음

따라서 이 결과는 실거래 수익률 증명이 아니라 전략 로직 회귀검증용입니다.

## Private WebSocket

실주문 없이 계좌/주문 이벤트만 관찰하려면:

```dotenv
PRIVATE_WEBSOCKET_ENABLED=true
BITHUMB_ACCESS_KEY=...
BITHUMB_SECRET_KEY=...
```

Private v2 endpoint를 사용합니다.

API 키는 저장소에 절대 커밋하지 말고 환경변수로만 주입합니다.

## Live trading

Phase 2 runner는 다음 값이 있어도 실주문을 제출하지 않습니다.

```dotenv
LIVE_TRADING_ENABLED=false
LIVE_TRADING_ACK=
```

실주문 전환은 별도 Phase에서 다음을 먼저 구현/검증한 뒤 진행합니다.

1. 실시간 slippage guard
2. 주문 idempotency
3. partial fill/reconciliation
4. kill switch
5. 최대 주문횟수/일일 손실 강제 제한
6. paper forward-test 결과 검토
