# B3 Auto Trader — Phase 1

목표: 빗썸 `KRW-B3`를 대상으로 시장 국면과 진입 매력도를 분리해 점수화하고, **실매매 전에 paper trading으로 검증**한다.

## 기본 원칙

- 기본값은 `PAPER` 모드다.
- `LIVE_TRADING_ENABLED=false`가 기본이며 실주문은 이 값과 별도의 확인 문자열이 모두 맞아야만 허용된다.
- API Key/Secret Key는 저장소에 넣지 않고 환경변수로만 주입한다.
- 출금 권한은 사용하지 않는다. 거래용 API Key에는 필요한 최소 권한만 준다.
- 가격·체결·호가는 빗썸 Public API/WebSocket을 사용하고, 실주문은 Private API `POST /v2/orders`를 사용한다.

## 전략 구조

1. `RegimeScore` — 시장 전체가 B3 롱 포지션에 우호적인지 평가
   - BTC 단기 추세
   - ETH 단기 추세
   - ETH/BTC 상대강도
   - B3/BTC, B3/ETH 상대강도
   - 외부 알트 확산도
   - Base 생태계 강도
   - Gaming 섹터 강도
   - 뉴스/언락/보안 이슈 modifier

2. `EntryScore` — 현재 가격이 실제 진입하기 좋은 위치인지 평가
   - B3 단기/중기 모멘텀
   - 직전 고점 대비 조정폭
   - 변동성 과열 여부
   - 호가 불균형
   - 거래량 가속도
   - 1파 후 38.2/50/61.8% 조정 구간 근접도

3. `RiskManager`
   - 1회 주문 한도
   - 최대 B3 비중
   - 일일 최대 손실
   - BTC 급락 circuit breaker
   - 비정상 슬리피지 차단
   - API 오류 누적 시 거래 중단

## 현재 Phase 1 구현 범위

- 빗썸 Public REST 기반 `KRW-B3`, `KRW-BTC`, `KRW-ETH` 가격 수집
- B3 호가 조회
- RegimeScore / EntryScore 계산
- Paper account 및 가상 체결
- 실제 Bithumb JWT 인증/주문 함수 구현하되 기본 비활성
- 외부 요인은 `ExternalFactors` 인터페이스로 연결점만 마련

다음 Phase에서는 Public WebSocket, Private WebSocket v2, Binance/OKX 파생시장 지표, Base/Gaming basket, 토큰 언락·뉴스 공급자를 붙인다.

## 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r b3_trader/requirements.txt
cp b3_trader/.env.example .env
python -m b3_trader.main
```

## 실매매 전환 조건

실매매는 아래 두 값을 모두 설정해야 한다.

```env
LIVE_TRADING_ENABLED=true
LIVE_TRADING_ACK=I_UNDERSTAND_REAL_ORDERS
```

그리고 `BITHUMB_ACCESS_KEY`, `BITHUMB_SECRET_KEY`가 필요하다. Phase 1에서는 이 값을 설정하더라도 충분한 paper 검증 전에는 실매매 전환을 권장하지 않는다.
