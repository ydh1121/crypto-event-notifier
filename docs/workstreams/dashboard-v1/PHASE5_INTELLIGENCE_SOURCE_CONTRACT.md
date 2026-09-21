# Phase 5 Intelligence Source Contract

이 문서는 미국 경제일정·미국 증시·중요 뉴스가 코인별 매매점수에 들어가기 전 반드시 거쳐야 하는 첫 데이터 계약을 고정한다.

## 현재 단계

구현 범위:

`source registry → normalized event → local SQLite store`

아직 구현하지 않는 것:

- 임의 뉴스 scraping
- 미국 지수 실시간 가격 scraper
- 이벤트별 임의 가중치
- EventScore/RegimeScore/RelativeStrengthScore 반영
- 현재 PAPER 주문/position sizing 변경
- 실주문

## 등록된 1차 공식 기준소스

경제일정:
- BLS release calendar: CPI, Employment, ECI, PPI
- BEA release schedule: PCE, GDP, Personal Income, Trade
- Federal Reserve FOMC calendar: meeting, statement, minutes, projections

미국 시장 기준축:
- Nasdaq Composite official index reference
- S&P 500 official index reference
- Cboe VIX official index reference

규제성 중요뉴스 기준축:
- SEC press releases
- CFTC press releases

등록은 곧 수집 활성화를 뜻하지 않는다. 현재 `collection_enabled=false`이며 adapter가 별도 테스트를 통과하기 전에는 네트워크 수집을 시작하지 않는다.

## normalized event 핵심 필드

- `event_id`: source 내부 stable identity
- `external_id`: source가 제공하는 공식 id가 있을 때 보존
- `source_id`, `source_family`, `event_type`
- `title`, `source_url`
- `scheduled_at`: 예정된 경제발표/FOMC 등
- `published_at`: 실제 발표·기사 게시 시각
- `observed_at`: 지수/시장 snapshot 관측 시각
- `source_ts`: observed → published → scheduled 우선순위의 대표 timestamp
- `received_at`: 우리 시스템이 받은 시각
- `entities`, `market_scope`
- `raw_text`, `summary_ko`
- `attributes`: 실제값/예상값/이전값/단위 등 adapter별 구조화 확장용
- `dedup_hash`: 동일 내용 clustering용 content fingerprint
- `confidence`: 아직 근거가 없으면 null. 임의 기본점수를 만들지 않는다.
- `version`

`freshness_seconds`는 저장 당시 고정하지 않고 조회시 `source_ts`와 현재시각으로 계산한다. 예정 이벤트는 stale로 취급하지 않는다.

## SQLite

- `research_intelligence_sources`
- `research_intelligence_events`

이 저장소는 Phase 5 연구용이며 score/PAPER/live-order authority가 없다.

부분 refresh가 기존에 확보한 공식 timestamp, 원문, 한국어 요약, attributes를 빈 값으로 지우지 않도록 upsert한다.

## 다음 구현 순서

1. BLS ICS bounded adapter
2. Fed/BEA 일정 adapter
3. 미국 시장지수용 timestamp/license가 명확한 market-data adapter 계약
4. SEC/CFTC 공식뉴스 adapter + entity mapping
5. event/article dedup + 같은 사건 clustering
6. 이벤트 전후 BTC/ETH/개별코인 15m/1h/4h/1d 반응 저장
7. 코인별 sensitivity beta / lag / sample count / dispersion / hit-rate / recency / confidence 계산
8. 충분한 표본에서만 shadow `EventScore`, `RegimeScore`, `RelativeStrengthScore` 후보 생성
9. 기존 PAPER와 parallel A/B 후 walk-forward 검증

고정 규칙:

`collect → persist → quality/reaction validation → shadow score → parallel PAPER A/B → walk-forward → candidate`

실제 점수 가중치는 표본 검증 전에 정하지 않는다.
