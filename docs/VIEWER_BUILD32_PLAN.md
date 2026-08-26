# Viewer Build 32 — 전체 코인 사업·섹터 전수조사

## 목표

섹터 화면의 코인별 `무슨 사업을 하나`가 섹터 공통 설명으로 반복되는 문제를 제거하고, 빗썸·업비트 KRW 전체 종목에 대해 프로젝트별 고유 설명과 대표 섹터를 누적한다.

## 조사 우선순위

1. 거래소 공식 명칭과 투자자용 설명 자료
2. 프로젝트 공식 홈페이지, Docs, whitepaper, 공식 source code
3. CoinMarketCap metadata/tags와 CoinGecko categories/description 교차확인
4. 공식·프로젝트가 연결한 X, Telegram, Reddit 등 community 링크는 보조 근거로 보존

커뮤니티 게시물 하나만으로 사업 내용이나 대표 섹터를 확정하지 않는다. 동일 ticker가 여러 프로젝트에서 사용될 수 있으므로 영문명 일치와 공급자 식별자를 함께 확인하고 match confidence를 저장한다.

## 전수조사 방식

`coin-profile-enrichment` supervisor component가 90초 간격으로 현재 빗썸·업비트 KRW market catalog를 다시 읽고 순환한다. 한 번 실행할 때 bounded batch만 조사해 외부 API rate limit을 피하고, cursor가 전체 market을 끝까지 돌면 다음 cycle을 시작한다. 신규상장·리브랜딩·사업 변경에 대응할 수 있도록 반복 검증한다.

수집 결과는 D1 `coin_profile_cache`에 다음과 같이 누적한다.

- business_summary_ko / business_summary_en
- canonical_sector
- categories / tags
- official homepage / docs / whitepaper / source code
- community links
- evidence source list
- research_status: verified / corroborated / single_source / unresolved / pending
- source_count / match_confidence / last_verified_at

## UI 계약

- 섹터 공통 설명은 `이 섹터는 무엇을 하나` 영역에서만 표시한다.
- 코인별 `무슨 사업을 하나`는 project-level business summary 또는 project description만 사용한다.
- 프로젝트 고유 근거가 없으면 `프로젝트별 설명 수집 중`이라고 표시하며 섹터 문구로 대신 채우지 않는다.
- 근거 출처, 검증 상태, source count, match confidence, 최근 검증일을 표시한다.
- 공식 홈페이지·Docs·백서·GitHub와 community corroboration links를 분리해서 표시한다.
- sector summary에는 전체 종목 중 조사 완료 수와 추가 조사 수를 표시한다.

## 분류 계약

수동 ticker mapping은 명확한 대표 프로젝트에 대한 high-confidence override로만 유지한다. 그 밖의 종목은 external categories/tags와 project-specific description text를 함께 사용해 분류한다. `ai` 같은 짧은 키워드는 단순 substring으로 찾지 않아 `chain` 같은 단어를 AI로 잘못 분류하지 않도록 word boundary를 사용한다.

대표 섹터가 확정되지 않으면 `미분류 검토`를 유지하되 background enrichment가 근거를 얻는 즉시 다음 sector summary에서 재분류한다.

## 안전 경계

- public/reference sources only
- private balance/order API 사용 금지
- real order 기능과 연결 금지
- community source는 corroboration only
- 외부 project code 자동 적용 금지

## 다음 묶음

Build 32 QA 이후 `strategy equity curve → 전략별 코인 성과 → 코인×전략 비교 → 전체 PAPER equity/drawdown`으로 진행한다.
