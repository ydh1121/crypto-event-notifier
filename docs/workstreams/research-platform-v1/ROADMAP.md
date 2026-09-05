# Research Platform v1 Roadmap

## 0. 운영 원칙

이 프로젝트는 현재 단계에서 **실거래가 아닌 PAPER 연구 플랫폼**이다. Windows PC를 24시간 연구 서버로 사용하고, 거래소 공개 데이터·가상매매·시장 특성·연구 데이터를 로컬에서 계속 축적한다.

핵심 원칙:

- 실제 주문 기능은 별도 미래 Workstream으로 분리한다.
- SQLite는 실시간 PAPER 운영 상태의 원본이다.
- Parquet + DuckDB는 장기 연구·AI 분석용 보조 저장소다.
- Cloudflare Pages는 조회용 껍데기다. 매매 명령을 받지 않는다.
- Google Drive는 라이브 DB가 아니라 백업/내보내기 용도다.
- 외부 GitHub 프로젝트는 자동 실행/자동 승격하지 않는다.
- 외부 구성요소 새 버전은 감지 → staging → 호환성 검사 → PAPER smoke test → 수동 승격 → 상태 확인 → 실패 시 rollback 순서를 지킨다.
- UI 기준은 Photo-eBook의 현재 Liquid navigation 계약을 따른다.

## Phase 0 — 기존 PAPER/UI 안정화

목표:

- Photo-eBook 기준 상단 메뉴/필터 Liquid 동작 유지
- Chrome 전체시장 연구 화면 응답성 유지
- GitHub → 로컬 자동 동기화 신뢰성 확보
- 로컬 SQLite, 보유자산/평단, 물타기 계획, control 파일 보존

장기 관찰은 계속하지만, 이 검증을 이유로 데이터/조회 인프라 구축을 멈추지는 않는다.

## Phase 1 — 24시간 로컬 연구 노드

### 1A. 분석 데이터 창고

운영 DB와 AI/통계용 장기 데이터를 분리한다.

```text
SQLite (PAPER runtime source of truth)
    ↓ incremental export
Parquet / date partitions
    ↓
DuckDB
    ↓
local quantitative / AI research
```

현재 수집 대상:

- 코인별 시장 움직임/가격/점수/변동성
- 가상매매 체결
- 코인별 equity history
- 알고리즘 학습 feedback

향후 추가:

- Upbit 데이터
- 뉴스
- 커뮤니티/SNS 언어 데이터
- 온체인
- 거시경제 이벤트

### 1B. Research Supervisor

매매 엔진과 별도 프로세스로 실행한다.

현재/예정 구성요소:

- `warehouse-export`
- `reference-version-watch`
- `cloudflare-snapshot-publish`
- `cloudflare-pages-deploy`
- 향후 `upbit-market-collector`
- 향후 `news-collector`
- 향후 `community-language-collector`
- 향후 `onchain-collector`
- 향후 `macro-event-collector`
- 향후 `local-ai-inference`

각 구성요소는 별도 ON/OFF, 즉시 실행, 오류 상태를 가진다. 하나가 실패해도 PAPER 엔진을 중지시키지 않는다.

### 1C. 외부 레포 버전 레지스트리

초기 참고 대상:

- Freqtrade — https://github.com/freqtrade/freqtrade
- Hummingbot — https://github.com/hummingbot/hummingbot
- NautilusTrader — https://github.com/nautechsystems/nautilus_trader
- CCXT — https://github.com/ccxt/ccxt
- PyUpbit — https://github.com/sharebook-kr/pyupbit
- vectorbt — https://github.com/polakowo/vectorbt
- Microsoft Qlib — https://github.com/microsoft/qlib
- FinRL — https://github.com/AI4Finance-Foundation/FinRL
- FinGPT — https://github.com/AI4Finance-Foundation/FinGPT
- Ollama — https://github.com/ollama/ollama
- llama.cpp — https://github.com/ggml-org/llama.cpp
- OpenBB — https://github.com/OpenBB-finance/OpenBB
- DefiLlama Adapters — https://github.com/DefiLlama/DefiLlama-Adapters
- DuckDB — https://github.com/duckdb/duckdb
- Qdrant — https://github.com/qdrant/qdrant

현재 watcher는 upstream SHA만 관찰한다. 실제 코드 채택 전에 라이선스와 통합 위험을 별도로 검토한다.

## Phase 2 — 무료 pages.dev 개인/초대형 Web Viewer

### 목적

Windows PC의 PAPER 계산을 그대로 유지하면서 웹/모바일에서는 안정적인 무료 주소로 결과를 본다.

```text
GitHub
  ↓ local GitAutoSync
Windows 24/7 research PC
  ├─ PAPER / SQLite / DuckDB / Parquet
  ├─ snapshot publisher
  └─ Pages deploy bridge
       ↓
Cloudflare Pages + Functions + D1
       ↓
https://<project>.pages.dev
```

### 구현 구조

Cloudflare Pages:

- 정적 HTML/CSS/JS
- 로그인
- owner/viewer
- 사용자 초대
- 전체 PAPER 현황
- 코인 검색/정렬/필터
- 권한이 있을 때만 실제 보유자산/평단/손익 표시

Cloudflare D1:

- users
- invites
- sessions
- snapshots
- audit_log

PC → Cloudflare:

- `POST /api/ingest`
- 별도 ingest secret
- raw SQLite 업로드 금지
- 화면에 필요한 compact snapshot만 전송
- 실제 보유자산은 인증된 사용자에게만 반환

Cloudflare → PC:

- 없음
- 매매 제어 없음
- kill/pause/resume 없음
- 자산 수정 없음
- 전략 변경 없음

### 배포 방식

기본 경로는 GitHub API token을 저장소에 넣지 않는 **local Wrangler bridge**다.

1회만 Windows PC에서:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-cloudflare-pages-viewer.ps1
```

이 작업이:

- Wrangler 브라우저 OAuth
- Pages 프로젝트 생성/재사용
- D1 생성/재사용
- D1 binding
- migrations
- Pages secrets
- 최초 배포
- health check
- 로컬 snapshot publisher 활성화
- 로컬 Pages auto-deployer 활성화

까지 수행한다.

이후 흐름:

```text
GitHub cloudflare-pages/** 변경
→ PC GitAutoSync
→ 30초 내 viewer 변경 감지
→ typecheck
→ migration
→ Pages deploy
→ /api/health 확인
```

GitHub Actions 직접 배포는 Cloudflare GitHub secrets를 나중에 추가하는 경우의 선택적 수동 fallback으로 남긴다.

## Phase 3 — Upbit 전체 KRW PAPER

목표는 Bithumb 전용 코드에서 공통 거래소 모델로 전환하는 것이다.

식별키 기본형:

```text
exchange + market + strategy
```

예:

```text
bithumb | KRW-XRP | balanced
upbit   | KRW-XRP | balanced
```

각 조합은 독립 10,000,000 KRW PAPER 계좌를 가진다.

구현 순서:

1. `PublicExchangeAdapter` 계약
2. Bithumb adapter로 기존 기능 감싸기
3. Upbit public adapter
4. Upbit KRW 전체시장 수집
5. 거래소별 독립 PAPER 계좌
6. Bithumb ↔ Upbit 성과/유동성/스프레드 비교
7. 거래소 자체 가격차/거래량 특징 장기 기록

실제 Upbit 주문 API는 이 단계에 포함하지 않는다.

## Phase 4 — Strategy Lab

한 가지 전략을 모든 코인에 강요하지 않는다.

초기 스타일:

- 보수적
- 균형
- 공격적
- 분할매수
- 역추세
- 스윙

향후 조합형 예:

```text
거래소: Bithumb / Upbit
코인: XRP
스타일: 역추세 + 분할매수
가상원금: 10,000,000 KRW
```

각 실험은 다음을 독립 보유한다.

- 현금
- 포지션
- 평단
- 매수회차
- 실현/미실현손익
- drawdown
- 승률
- 기대값
- profile/학습 파라미터
- entry/exit history
- 학습 feedback

사용자 UI에서는 조건을 체크한 뒤 `연구 시작`으로 새 실험을 만들 수 있도록 한다.

## Phase 5 — 외부 컨텍스트 데이터

가격만 보고 거래하는 계층과 별도로 외부 이벤트를 구조화한다.

### 온체인

예시 특징:

- exchange inflow/outflow
- holder concentration
- whale wallet activity
- active addresses
- transfer volume
- TVL/bridge flow 가능한 자산

모든 코인에 동일 온체인 데이터가 존재하지 않으므로 availability score를 함께 기록한다.

### 커뮤니티/SNS 인간지표

단순 positive/negative sentiment만 쓰지 않는다.

기록 후보:

- 언급량 변화
- 신규 참여자 비중 추정
- 반복되는 단어
- 강한 확신 표현
- 공포/조롱/광신/항복 뉘앙스
- 특정 가격 목표 반복
- pump/fomo/bagholder/손절/존버 류의 문맥 변화
- 한국 커뮤니티와 글로벌 커뮤니티의 온도 차
- 동일 문장/봇성 게시물 반복도
- narrative 변화 속도

원문 전체를 영구 저장하기보다 가능한 경우 timestamp/source/id/feature/embedding/짧은 근거 형태로 정규화한다.

### 뉴스

- 글로벌 crypto news
- 거래소 상장/상폐
- 프로젝트 공식 발표
- 규제
- 해킹/익스플로잇
- ETF/기관 흐름
- 주요 인물 발언

### 거시 이벤트

- FOMC
- CPI
- PCE
- 미국 고용지표/NFP
- 실업률
- GDP
- Powell 발언
- 국채 금리/달러 관련 급변 이벤트

각 이벤트는 예정시각을 미리 기록하여 `event risk window`를 만들고, 발표 전후 시장 반응도 저장한다.

초기에는 이 데이터를 주문 신호로 바로 사용하지 않는다. 먼저 특징과 결과의 관계를 검증한다.

## Phase 6 — Local AI Research Service

PC의 장기 데이터에 로컬 모델을 붙인다.

후보 역할:

- 뉴스 요약/분류
- 커뮤니티 문장 분류
- narrative clustering
- 비슷한 과거 국면 검색
- 특정 코인 움직임의 반복 특성 요약
- 승리/실패 진입의 공통 특징 추출
- 이벤트 전후 반응 비교

후보 런타임:

- Ollama
- llama.cpp

구조화 데이터는 DuckDB, 의미 검색이 실제로 필요해질 때 Qdrant 도입을 검토한다.

AI 출력 자체는 매매 명령이 아니다. 신뢰도와 근거, 검증 결과를 별도로 저장한다.

## Phase 7 — 자동 개선 검증

현재의 단순 profile 조정보다 엄격한 검증층을 만든다.

- train / validation 기간 분리
- walk-forward
- holdout
- market-regime split
- 수수료/슬리피지 반영
- 최소 거래 표본
- 최대 낙폭 제한
- 과최적화 감지
- 이전 버전과 challenger 비교

새 알고리즘은 단순 누적수익이 높다는 이유만으로 활성화하지 않는다.

## Phase 8 — 실거래 후보 승격 연구

후보 점수 예:

- return
- max drawdown
- expectancy
- trade count
- win/loss asymmetry
- execution quality
- regime stability
- exchange stability
- data completeness
- external-event robustness

이 단계가 충분히 검증된 뒤에만 별도 실거래 Workstream을 연다.

현재 프로젝트의 실제 주문 기능은 계속 비활성/범위 밖으로 유지한다.
