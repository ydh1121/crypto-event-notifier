# Crypto Auto Trader Master Roadmap

이 문서는 `dashboard-v1` workstream의 상위 실행 로드맵이다.

목표는 단순한 지표 모음이 아니라 **시장·이벤트·수급·기술구조·프로젝트 생애주기를 시간축으로 DB화하고, 코인별 반응 특성을 누적 학습해 실제 매매 의사결정에 쓸 수 있는 순위·타점·위험 정보를 만들고, 그 결과를 PAPER forward test로 검증하면서 승률/수익률을 개선하는 것**이다.

상세 Viewer 누락 체크는 `docs/VIEWER_REBUILD_CHECKLIST.md`를 유지한다. 이 문서는 백엔드/데이터/점수/PAPER/Viewer/QA의 전체 순서와 의존성을 관리한다.

Status legend: `[ ]` pending · `[-]` active · `[x]` complete · `[>]` deferred

## 0. 영구 원칙

- [x] PAPER-only 유지. 실제 주문은 별도 future workstream에서만 명시 승인 후 다룬다.
- [x] Local SQLite를 PAPER/학습/시간축 feature의 authoritative store로 유지한다.
- [x] Cloudflare Pages는 read-only Viewer로 유지한다.
- [x] 코인 identity는 ticker 단독으로 연결하지 않고 거래소 공식명/체인/contract/provider id/공식 domain을 교차검증한다.
- [x] 모든 신규 feature는 `수집 → DB 누적 → 품질/반응 검증 → shadow score → PAPER A/B → walk-forward → candidate` 순으로 승격한다는 개발 규칙을 고정한다.
- [ ] 같은 가격현상을 여러 지표가 중복 설명할 때 double counting을 막는 feature-family 정규화/상관 감쇠를 적용한다.
- [ ] 모든 score/feature에 source, source_ts, received_at, freshness, confidence, version을 저장한다.
- [x] 외부 GitHub 알고리즘은 참고용으로만 사용하며 URL/license/최근 유지상태/테스트 결과를 문서화한 뒤 사용한다는 규칙을 고정한다. 단일 repo를 정답으로 복제하지 않는다.

## 1. 현재 완료된 분석 기반

- [x] 전략 equity curve + drawdown
- [x] 전략별 코인 성과 상세
- [x] 코인 × 전략 matrix/detail
- [x] 전체 adaptive PAPER benchmark equity/drawdown
- [x] 빗썸/업비트 독립 PAPER 계좌 및 코인별 성과 DB
- [x] 코인별 fill/feedback/equity/market-memory 누적
- [x] 전략 Candidate/Warming/Rejected 및 gate 표시
- [x] 섹터 history D1 누적
- [x] 코인 프로필 전수조사 + identity integrity/backlog
- [x] Cloudflare snapshot/detail 전송 및 bounded retention
- [x] Build 38 lifecycle/notice/return-window 모듈 + PAPER self-heal + D1 write-budget 및 Windows runtime 검증
- [x] Build 39 pre-KRW CEX listing-history 모듈/전용 CI/Windows 실데이터 QA/compact Viewer projection 완료. 최신 상장 사례의 아직 도달하지 않은 post-listing window는 계속 시간 누적

## 2. 기존 Viewer 잔여 작업 — 먼저 닫을 것

- [x] 실제 보유자산 평가액/손익 history 저장 및 chart. 기존 전시장 가격을 재사용해 5분 간격 로컬 SQLite 평가 snapshot을 누적하고 private Viewer에 평가액/손익 차트를 표시하며 가격 coverage가 불완전한 시점은 기록하지 않음
- [x] 기록의 전략 필터. fill/feedback payload에 strategy 식별값을 보존하고 Viewer에서 전략별 필터 지원
- [x] 판단상태 변경 기록 별도 필터. 기존 분석 snapshot의 실제 action transition만 bounded journal로 투영
- [x] 시스템 이벤트 기록 별도 필터. 기존 journal event를 allowlist 기반 안전 필드만 bounded projection
- [x] GitHub Actions CI 상태를 Viewer 시스템 화면에 표시. 공개 GitHub API read-only 조회 + 5분 캐시, 토큰/쓰기 없음
- [-] 섹터 순위/코인 선택 및 기타 master-detail 선택 시 현재 스크롤 위치 보존. 공통 `ui-continuity.js` 구현 완료, 실제 브라우저 QA 대기
- [-] 섹터 코인 표 `D-5 / D-4 / D-3 / D-2 / D-1 / 24H` 표시 구현 완료. 실제 runtime 데이터/모바일 우선순위 QA 대기
- [ ] 390px / 430px 집중 모바일 QA를 마지막 통합 QA에 유지하되 각 단계에서도 회귀 확인

## 3. 신규 상장·유의·거래종료 자동 생애주기

### 3.1 거래소 market lifecycle registry
- [x] 빗썸/업비트 KRW market 목록을 동적으로 조회하는 기반
- [x] additive lifecycle registry/event journal로 market 목록 변화, 신규 market, 3회 연속 부재를 저장해 신규상장/제거를 자동 감지
- [x] 거래소 공식 공지 collector/DB/overlay 및 `announcement_at`, `deposit_at`, `trade_open_at`, `termination_at` 구조화 parser/store/Viewer projection 구현
- [x] 공지 timing은 정확한 날짜+시각이 있는 경우만 저장하고 날짜만 있는 경우 임의 `00:00`을 만들지 않는 fail-closed 규칙 적용
- [x] compact `market_notice_audit` CLI로 거래소별 notice/event/timing coverage를 확인 가능하게 함
- [x] Windows runtime에서 빗썸/업비트 공식 공지 source/timing, lifecycle gate, PAPER self-heal, Cloudflare snapshot/detail health 실데이터 검증
- [x] 상태 모델: `NORMAL`, `LISTING_ANNOUNCED`, `NEW_LISTING`, `CAUTION`, `TERMINATION_SCHEDULED`, `TERMINATED`
- [x] `유의 촉구`와 `유의`를 Viewer에서 동일 CAUTION 계층으로 취급
- [x] 티커/상태 표시: CAUTION=주황, 거래종료 예정/종료=빨강, 신규/상장예정=별도 label. 색만 의존하지 않고 텍스트 병기
- [x] `notice_only`를 Cloudflare snapshot에 투영해 아직 KRW market이 생기지 않은 `LISTING_ANNOUNCED`도 Viewer에서 표시
- [x] 공식 공지 + 실제 market-list lifecycle을 섹터 Viewer의 독립 panel에서 실시간 snapshot 갱신으로 표시
- [-] 신규 KRW market 발견 즉시 PAPER account/profile + market-memory 경로는 기존 전수 universe 구조로 자동 bootstrap된다. profile research backlog도 KRW universe에서 누락을 자동 포착한다. sector/facet까지 포함한 end-to-end 실환경 검증은 대기
- [x] `TERMINATION_SCHEDULED`/`TERMINATED`는 신규 PAPER 진입·추가매수를 차단하고 기존 포지션의 매도/정리와 과거 성과/history는 보존. CAUTION/NEW_LISTING은 현재 adaptive에서는 아직 shadow

### 3.2 국내 상장 전 가격 추적
- [x] 해외 CEX 연결 전 identity gate 구현: 기존 verified/corroborated profile을 재사용하고 ticker-only 매칭 금지
- [x] CoinGecko coin-id × 해외 거래소 식별자 × base/quote exact pair를 교차검증한 경우에만 CEX 가격 source를 허용
- [x] Binance/OKX/Bybit public source adapter를 공통 `ListingCandle` 형식으로 모듈화
- [x] 공식 KRW listing 공지만 stable notice-id case로 seed하고 Upbit USDT-only 공지는 KRW case에서 fail-closed 제외
- [x] 실제 국내 open은 현재가가 아니라 `trade_open_at` 주변 빗썸/업비트 공개 1분봉 opening price로 해석
- [x] additive local SQLite: `listing_history_cases`, `listing_history_sources`, `listing_history_candles`, `listing_history_features`
- [x] 국내 상장 전 해외 CEX 가격 snapshot: T-7d, T-5d, T-3d, T-1d, T-6h, T-1h, 국내 open 계산 및 Windows 실데이터 coverage/정확도 QA 완료. 상장 전 해외 거래기간이 짧은 사례는 오래된 T-window를 null 유지
- [x] 국내 상장가 대비 해외 기준 premium/discount 및 T-window 상승폭 feature 구현 + 실제 최근 상장 표본 QA 완료. CAP/CC 등에서 currency-safe KRW 환산과 premium/discount 실값 확인
- [x] 해외 CEX 최초 상장일/첫 가격/국내 상장 전 ATH/ATL 저장 및 provenance QA 완료. 거래소가 최초시각/가격을 증명하는 PROM/EURC 등은 저장하고 CAP/CC처럼 증명 불가한 source는 0을 유효값으로 오인하지 않고 null semantics 유지
- [x] bounded T-8d 연구 window 첫 봉을 해외 최초상장가로 오인하지 않는 provenance fail-closed 규칙 및 테스트
- [-] 국내 상장 후 5m/1h/6h/24h/3d/7d 반응 누적 로직 구현 및 실데이터 검증 완료. CC/CAP 등 완료 사례에서 +5m~+7d 확인, PROM/EURC처럼 아직 7일이 지나지 않은 최신 사례는 `tracking_postlisting`으로 계속 누적
- [x] `listing-history-research`를 PAPER와 독립된 15분 sidecar로 등록하고 회당 최대 3 case로 제한
- [x] `listing_history_audit` read-only CLI + Build 39 modular contract + dedicated CI
- [x] `scripts/verify-build39-runtime.ps1` 실환경 검증 완료. Build69 dedicated mode에서 generic listing-history supervisor를 계속 비활성으로 유지한 채 Pages deploy → official notice refresh → shared `ResearchWorkLock` one-shot 최대 3 case → audit PASS. lock 경합 시 network/DB 0으로 exit 75 defer
- [x] compact listing-history feature를 Cloudflare Viewer에 투영. `listing_history_snapshot.py`에서 case/source/derived feature만 bounded projection하고 raw candle/OHLCV는 로컬 SQLite에만 유지하며 리서치 화면에서 국내 상장 전후 값을 표시
- [x] CoinGecko venue 검증 public rate-limit 보강. exact coin-id×exchange-id×pair gate는 유지한 채 요청 간 최소 간격과 429 bounded backoff를 적용하고 전용/전체 CI PASS
- [x] DEX identity는 CEX pair 매칭과 분리하고 verified CoinGecko identity에서 chain/platform + exact contract address를 가져온 뒤 GeckoTerminal network+contract source만 사용. ticker-only DEX 매칭 금지

### 3.3 DEX 출발 코인
- [x] contract 기반 DEX pool 발견과 pool 생성 시점 수집. verified coin identity → chain/platform → exact contract → GeckoTerminal network+contract → pool 주소를 연결하고 primary accepted pool을 별도 선택
- [-] 최초 유효 유동성 시점과 `검증된 launch price`는 추가 증거가 필요. 현재 public OHLCV로 pool 생성 직후 최초 관측 가격·봉 거래량은 저장하지만 해당 시점의 historical pool reserve를 증명할 수 없어 feature v2에서 `historical_liquidity_verified=false`, `validated_launch_price=null`로 fail-closed 유지
- [x] DEX 관측 최초가·pool 생성시점·현재 reserve/24h volume·국내 상장 전 T-7d/T-5d/T-3d/T-1d/T-6h/T-1h·국내 상장 후 +5m/+1h/+6h/+24h/+3d/+7d 반응을 로컬 SQLite feature로 저장하고 compact Viewer에 표시. raw DEX OHLCV는 전송하지 않음
- [x] `DEX 관측 최초가 → 이후 DEX 반응` 및 `T-window → 국내 상장가` 수익률 feature 구현. 다만 `DEX 최초가 → 국내 상장가`를 유동성 검증 launch 수익률로 승격하지 않고 provenance 상태와 함께 관측 연구값으로만 취급
- [-] 극단적 저유동성 초기 체결 방어는 2단계. 현재 pool 선택에는 최소 reserve/24h volume gate를 적용하고, launch 시점 historical liquidity를 증명할 수 없는 최초봉은 Viewer에서 `관측값 · 유동성 미검증`으로 표시해 validated launch price로 사용하지 않는다. historical reserve source 확보 전에는 launch-time liquidity threshold PASS를 선언하지 않음
- [x] DEX compact Cloudflare projection/Viewer는 exact contract·primary pool·derived feature·launch provenance만 전달하고 raw candle은 로컬 SQLite에 유지. Build44 전용 CI와 전체 B3 regression PASS
- [x] 신규상장/DEX 과열 위험은 정보·shadow 단계로 제한. Build65 v2 사전등록 → Build66 forward-only shadow score → Build70/71 최소 30 event·20 unique asset gate를 통과하기 전 PAPER A/B·주문·LIVE 승격 금지

### 3.4 DEX shadow score v2 forward 검증
- [x] Build 65에서 v1을 폐기하고 v2 점수식·가중치·방향·2026-08-31 UTC cutoff·검증 기준을 사전등록
- [x] Build 66 forward-only v2 shadow scorer. pre-cutoff backscore, fitting, threshold, PAPER/order wiring 금지
- [x] Build 67 최신 공식 빗썸/업비트 KRW 상장 공지 intake와 Build 68 회당 최대 1건 forward enrichment
- [x] Build 69에서 Build 67 → Build 68 → Build 66을 회당 1회씩만 실행하는 bounded forward orchestrator 구현
- [x] Build 69 전용 15분 scheduled process 구현. 정상 Windows launcher가 함께 시작·재시작·종료하며 generic listing/DEX historical supervisor와 Build 47 cursor는 전용 모드에서 비활성
- [x] Build 70 event/asset-dedup core-label ledger와 30 event/20 unique asset readiness gate 구현
- [x] Build 71 preregistered forward validation 구현. Build 70 준비 전 Spearman/spread/late-half 통계 호출 자체를 차단
- [x] Build 71은 event/asset-dedup Spearman, 상·하위 quartile spread, 시간순 후반부, 강한 음의 core signal만 Build 65 기준으로 판정하며 PAPER A/B·주문·LIVE는 연결하지 않음
- [-] 실제 forward 표본 누적 대기. 현재 0 event / 0 unique asset이며 p1h·p6h·p24h 각각 30 event / 20 unique asset label 전에는 Build 71 통계 검증 금지
- [x] Build 69 scheduler Windows runtime 검증 완료. `runtime_verified`, fresh heartbeat/process lock, 900초 주기, generic listing/DEX supervisor 비활성, 첫 bounded `waiting_no_forward_cases`, failures 0, safety violations 0 확인
- [ ] Build 71이 실제 forward 표본에서 PASS한 경우에만 Build 72 parallel PAPER A/B 구현
- [ ] Build 72 PASS 후 Build 73 walk-forward/운영 안정성 검증 및 candidate promotion review

## 4. 분류체계 확장 — 단일 섹터에서 multi-facet으로

기존 `canonical_sector`는 대표 사업분류로 유지하되 아래 facet을 병렬 저장한다.

- [ ] 사업 섹터: L1/L2, DeFi, AI, DePIN, RWA, Gaming, Meme, Payments, Oracle, Bridge, Storage, Identity, Privacy, Exchange 등
- [ ] 생태계: Ethereum, Bitcoin, Solana, BNB, Cosmos, XRP, Sui, Aptos 등
- [ ] 국가·지역: 본사/재단/주요 개발조직의 기원과 주요 시장을 근거와 함께 별도 facet으로 저장
- [ ] 토큰 역할: gas, governance, utility, reward, LP, stablecoin, meme 등
- [ ] 출시방식: mining, ICO/IEO/IDO, airdrop, points conversion, DEX-first, CEX-first 등
- [ ] 생애주기: new/growth/mature/caution/termination
- [ ] 시장구조: low-float/high-FDV, unlock-heavy, illiquid, newly-listed, high-volatility 등
- [ ] 시총/유동성 bucket
- [ ] dynamic narrative tag: AI agent, restaking, DeSci 등 유행 narrative를 canonical sector와 분리
- [ ] Viewer에서 대표 섹터 외 facet 필터/교차필터 지원

## 5. 가격·수급 Feature Store

### 5.1 다중 기간 가격 history
- [ ] 1m/5m/15m/1h/4h/1d OHLCV의 bounded local history 수집
- [x] 기존 `research_market_memory_mx`를 재사용해 completed prior-day D-1~D-5와 현재 기준 1/3/5/7/30일 누적수익률을 분리 계산·compact market-detail projection·섹터 Viewer 연결. 30일 미달/스테일 history는 null fail-closed로 유지하며 Build38 전용 CI와 전체 B3 regression PASS
- [ ] BTC/ETH/도미넌스/시장 breadth 대비 상대강도 저장
- [ ] cross-exchange price gap 및 국내 premium/discount 저장

### 5.2 순매수/순매도 · volume delta
- [ ] public trade feed에서 aggressor side가 제공되는지 거래소별 검증
- [ ] side 미제공 시 tick rule/orderbook 기반 추정값과 confidence를 별도 저장
- [ ] 단위봉별 buy_volume, sell_volume, delta=`buy-sell`, delta_pct, CVD 누적
- [ ] 1m/5m/15m/1h/4h/1d CVD/volume delta history
- [ ] orderbook imbalance, spread, depth, slippage, bid/ask replenishment 속도
- [ ] price-flow divergence DB화
- [ ] Viewer 테이블/상세에 순매수·순매도·delta·CVD 및 기간 비교 표시

### 5.3 매집/분산 판정
- [ ] 단순 `가격하락 + 순매수>0 = 매집`으로 처리하지 않는다.
- [ ] `강한 market sell(negative delta)인데 가격 하락 효율이 낮고 bid가 반복 보충`되면 passive buy absorption/매집 후보
- [ ] `강한 market buy(positive delta)인데 가격 상승 효율이 낮고 ask가 반복 보충`되면 passive sell absorption/분산 후보
- [ ] price efficiency = 가격변화 / 공격적 체결량, replenishment, CVD divergence, volume profile 위치를 결합
- [ ] accumulation/distribution score와 confidence를 시간축으로 저장
- [ ] 코인별 `flow → 이후 15m/1h/4h/1d 수익률` 반응계수를 누적

## 6. 기술분석·시장구조 엔진

### 6.1 deterministic indicators
- [ ] Supertrend
- [ ] MACD
- [ ] Bollinger Bands
- [ ] MA 7/20/60/120/200/365
- [ ] RSI
- [ ] ATR/realized volatility
- [ ] volume / OBV
- [ ] VWAP + Anchored VWAP
- [ ] Volume Profile / POC / VAH / VAL
- [ ] Fibonacci retracement/extension 전체 주요 구간
- [ ] multi-timeframe 15m/1h/4h/1d alignment

### 6.2 구조·패턴
- [ ] swing pivot / multi-scale wave graph 구축
- [ ] support/resistance cluster: pivot, volume profile, MA, fib, previous high/low 중첩
- [ ] regression/parallel channel 및 channel break/retest
- [ ] liquidity sweep / stop-hunt 후보
- [ ] BOS / CHOCH
- [ ] FVG / imbalance
- [ ] ICT premium/discount zone 및 order-block 후보
- [ ] Wyckoff accumulation/distribution phase, spring/upthrust 후보와 confidence
- [ ] 파동은 주관적 Elliott label을 억지로 확정하지 않고 multi-scale pivot/wave와 confidence를 먼저 사용
- [ ] 현재 패턴 → 진입/추가매수/무효화/목표/손절 후보 가격대를 근거별로 산출

### 6.3 외부 GitHub 참고 검증
- [ ] `docs/TRADING_ANALYSIS_REFERENCE_REPOS.md` 생성
- [ ] Wyckoff/ICT/Fibonacci/channel/pivot/volume-profile/indicator 관련 공개 repo 다수 조사
- [ ] repo별 URL, license, 최근 유지상태, test coverage, 사용 알고리즘 기록
- [ ] 동일 입력 데이터에 여러 구현을 돌려 공통 구간/불일치 구간 비교
- [ ] 외부 구현의 output을 정답으로 사용하지 않고 우리 테스트 fixture와 공통 합의 구간만 참고

## 7. Phase 5 — 이벤트·뉴스·온체인·인간지표 Intelligence

### 7.1 source registry / ingest
- [ ] 국내외 거시경제 뉴스 source registry
- [ ] 프로젝트 공식 blog/RSS/X/공지 source registry
- [ ] 주요 해외 crypto news source registry
- [ ] 주요 커뮤니티/포럼 source registry
- [ ] 합법적 API/RSS 우선, scraping은 robots/ToS/rate limit 검토 후 사용
- [ ] 원문, 번역본, source URL, published_at, received_at, entity mapping, dedup hash 저장

### 7.2 event taxonomy
- [ ] macro: FOMC, CPI, PCE, NFP/고용, GDP, 금리/유동성
- [ ] geopolitical: 전쟁/제재/관세/정책 충돌
- [ ] crypto security: hack/exploit/bridge/chain halt
- [ ] token lifecycle: unlock, vesting, burn, airdrop, mainnet, upgrade
- [ ] exchange: listing, caution, delisting, deposit/withdraw halt
- [ ] regulatory/legal: 소송, 규제, ETF/승인/거절
- [ ] project/company: partnership, funding, product launch, insolvency
- [ ] event severity, scope(global/sector/coin), direction, uncertainty, freshness decay 정의

### 7.3 macro calendar
- [ ] FOMC/CPI/PCE/NFP 등 scheduled event calendar DB
- [ ] consensus/previous/actual/surprise 저장
- [ ] 발표 전후 BTC/ETH/sector/coin의 1m~1d 반응 누적
- [ ] 코인별 macro sensitivity beta 구축

### 7.4 인간지표
- [ ] 커뮤니티/source별 신뢰도와 bot/spam 위험도
- [ ] 키워드/문장/이슈 lexicon DB
- [ ] mention velocity, unique authors, engagement velocity, sentiment, disagreement, panic/euphoria 지표
- [ ] 절대 sentiment보다 baseline 대비 anomaly를 우선 사용
- [ ] 코인별 social impulse → 이후 가격/거래량 반응을 누적

### 7.5 온체인
- [ ] source availability에 따라 exchange inflow/outflow, whale transfer, holder concentration, active address, fee/activity를 단계적으로 추가
- [ ] chain별 데이터 품질/비용 차이를 confidence로 반영
- [ ] token contract migration/bridge/wrapped asset 혼동 방지

## 8. 추가로 포함할 시장정보 — 누락 방지

- [ ] derivatives: funding rate, open interest, basis, liquidation cluster/source 가능성 조사
- [ ] tokenomics: circulating/FDV, emissions, unlock schedule, treasury/team/investor concentration
- [ ] liquidity risk: spread/depth/slippage/orderbook resilience
- [ ] stablecoin liquidity/market-wide risk appetite
- [ ] BTC dominance, TOTAL/alt breadth, sector breadth
- [ ] cross-exchange premium/Kimchi premium 및 price discovery venue
- [ ] correlation/cluster risk: 같은 narrative/생태계가 동시에 무너질 때 portfolio concentration 표시
- [ ] manipulation heuristic: 비정상 거래량, orderbook cancel/replenish, low-liquidity pump 패턴은 confidence 낮은 위험 feature로만 사용

## 9. 통합 점수 엔진 v2

점수는 한 숫자에 모든 것을 바로 더하지 않고 feature family별 독립 score와 confidence를 먼저 만든다.

- [ ] `RegimeScore`: 전체 시장 분위기
- [ ] `EntryScore`: 현재 가격 위치/진입 적합성
- [ ] `FlowScore`: CVD/orderbook/volume-profile/수급
- [ ] `StructureScore`: trend/pivot/fib/channel/Wyckoff/ICT 구조
- [ ] `EventScore`: 뉴스/거시/보안/언락/상장 이벤트
- [ ] `HumanScore`: SNS/커뮤니티 anomaly
- [ ] `OnchainScore`
- [ ] `RelativeStrengthScore`: BTC/ETH/sector/peer 대비
- [ ] `LifecycleRiskScore`: 신규상장 premium, caution/delist, unlock 등
- [ ] `LiquidityRiskScore`
- [ ] family별 score를 0~100 또는 -100~+100으로 정규화
- [ ] stale/missing source는 0으로 간주하지 않고 confidence를 낮춘다.
- [ ] effective contribution = `normalized_signal × source_quality × freshness × historical_reliability`
- [ ] 서로 높은 상관의 feature는 contribution을 감쇠
- [ ] coin-specific reaction memory: `event/flow/technical condition → forward return`을 15m/1h/4h/1d별로 누적
- [ ] score version과 feature version을 모든 PAPER fill에 저장해 나중에 성능 귀속 가능하게 한다.

## 10. Intelligence Viewer 페이지

레이아웃은 정보량이 많아도 한 화면에서 '지금 무엇이 중요한가'가 먼저 보이도록 구성한다.

- [ ] 상단: 시장 위험/이벤트/수급/신규상장 핵심 4~6 KPI
- [ ] 좌측: 시간순 실시간 event/news stream + 심각도/영향범위 filter
- [ ] 중앙: 코인/섹터 impact heatmap + event 반응 chart
- [ ] 우측: 지금 볼 코인 ranking, 점수 변화 이유, 상승/하락 위험
- [ ] 탭: 뉴스·거시 / 인간지표 / 수급·CVD / 상장·유의 / 온체인
- [ ] 같은 이벤트의 중복 기사 clustering
- [ ] 한국어 번역/요약과 원문 링크/근거 표시
- [ ] event 클릭 → 영향을 받은 coin/sector의 전후 가격·거래량·CVD 비교
- [ ] 데이터 stale/누락을 사용자에게 숨기지 않고 표시

## 11. Phase 6 — AI 종합해석

- [ ] AI는 raw web 문장을 직접 점수화하지 않고 versioned feature/evidence를 입력으로 사용
- [ ] AI output: 현재 국면, 상승/하락 핵심 근거, 반대근거, 진입 후보, 추가매수, 무효화, 목표, 위험
- [ ] deterministic score와 AI narrative를 분리 저장
- [ ] AI가 수치/가격/이벤트를 발명하지 못하도록 evidence id를 요구
- [ ] 처음에는 shadow explanation만 생성하고 PAPER 주문결정에는 영향 없음
- [ ] 충분한 평가 후 AI-derived feature를 별도 family로 실험

## 12. PAPER 매매로직 v2 — 데이터 구축 후 수정

기존 adaptive 전략을 즉시 덮어쓰지 않는다.

- [ ] baseline `adaptive` 고정 보존
- [ ] 신규 `adaptive_intelligence_v2` shadow PAPER 전략 생성
- [ ] 동일한 coin/time에서 baseline과 v2 signal을 병렬 기록
- [ ] entry와 exit를 별도 모델/score로 평가
- [ ] 신규상장/유의/거래종료/lifecycle risk gate
- [ ] flow/structure/event/human/onchain score의 각 contribution을 fill snapshot에 저장
- [ ] 과열 추격 방지: 신규상장 premium, 1/3/5일 급등, 유동성/슬리피지 risk 결합
- [ ] 매집 후보: passive buy absorption + 지지구간 + 구조개선이 겹칠 때만 가점
- [ ] 분산 후보: passive sell absorption + 저항/과열 + 구조약화가 겹칠 때 감점
- [ ] 현재 최고 예상수익 코인 ranking과 실제 이후 수익률을 지속 비교
- [ ] score decile별 forward return, hit rate, MFE/MAE, drawdown으로 calibration
- [ ] 충분한 sample 전에는 가중치 자동 최적화 금지

## 13. Phase 7 — walk-forward / out-of-sample

- [ ] 시간 순서를 보존한 train/validation/test window
- [ ] bull/bear/sideways/high-volatility regime별 분리 검증
- [ ] 신규상장 age bucket별 분리 검증
- [ ] coin/sector concentration 검증
- [ ] 거래비용/slippage stress test
- [ ] parameter sensitivity / neighborhood stability
- [ ] look-ahead, survivorship, selection bias 검사
- [ ] baseline 대비 v2의 return/DD/PF/win-rate/expectancy 개선을 통계적으로 비교
- [ ] Viewer에 Phase 7 결과 화면

## 14. Phase 8 — candidate promotion

- [ ] 최소 trade/sample 수 gate
- [ ] out-of-sample 수익/expectancy gate
- [ ] max drawdown gate
- [ ] profit factor gate
- [ ] 최근 성능 deterioration gate
- [ ] sector/coin concentration gate
- [ ] slippage/liquidity stress gate
- [ ] score calibration gate
- [ ] Candidate/Warming/Rejected 근거를 versioned DB로 저장
- [ ] 자동 real-trading promotion은 금지. candidate는 실제 매매 참고 후보일 뿐
- [ ] Viewer에 Phase 8 promotion 화면

## 15. 실제 보유자산·기록·운영 완성

- [x] 실제 보유자산 valuation/PnL snapshot을 시간축으로 SQLite에 누적. 5분 최소 간격, 90일 로컬 retention, 불완전 가격 coverage는 기록 제외
- [x] 보유 포트폴리오 equity/PnL history chart. private Viewer에서 최근 7일 bounded history + 기간 필터 표시
- [x] 기록 payload에 strategy 식별값 포함
- [x] 판단 상태 변화 event journal. 기존 snapshot의 market별 action transition을 bounded projection
- [-] system event journal: 기존 PAPER/분석 안전 이벤트의 bounded Viewer projection은 완료. Git sync, Cloudflare, DB backup, publisher failure/recovery 등 운영 전반의 생산자 연결은 추가 필요
- [x] GitHub Actions 최신 branch CI 상태를 안전한 read-only summary로 Viewer에 표시
- [ ] 데이터 source health/freshness/rate-limit/error dashboard
- [ ] D1/SQLite/Drive storage growth budget와 retention monitor

## 16. 최종 모바일/상호작용 QA

- [ ] 390px 집중 QA
- [ ] 430px 집중 QA
- [ ] 360px 최소 폭 overflow sanity
- [ ] iOS Safari focus zoom/keyboard/safe-area
- [ ] 가로 rail native momentum
- [ ] master-detail 선택 후 scroll/focus 유지
- [ ] live polling 후 선택/검색/필터/스크롤/열린 disclosure 유지
- [ ] 신규 5일 등락/상장상태/수급 table의 모바일 정보 우선순위 검증
- [ ] Intelligence page 모바일 카드/탭/차트 밀도 검증
- [ ] 1280~1920 desktop regression

## 17. 진행 순서

권장 실행 순서는 아래와 같다.

1. Viewer 잔여 작은 부채 + scroll reset 수정/QA
2. 신규상장/유의/거래종료 lifecycle + 공지 시간 구조화 + market identity
3. 국내 상장 전 CEX/DEX 가격 이력
4. D-5~24H 가격 history 확장 + flow/CVD feature store
5. multi-facet sector/geography
6. 기술분석/구조 엔진 + reference repo 검증
7. Phase 5 news/macro/human/onchain ingest + event reaction DB
8. 통합 score v2 + coin-specific reaction memory
9. Intelligence Viewer
10. Phase 6 AI 종합해석 shadow
11. PAPER `adaptive_intelligence_v2` 병렬 forward test
12. Phase 7 walk-forward
13. Phase 8 candidate promotion
14. 실제 보유/기록/운영 잔여 완결
15. 최종 390/430 모바일 집중 QA

## 18. 완료 판단 기준

- [ ] 어떤 코인이 왜 상위인지 feature contribution과 evidence로 설명 가능
- [ ] 신규상장/유의/거래종료가 수동 개입 없이 반영됨
- [ ] 뉴스/이벤트/수급/기술구조 발생 후 코인별 실제 반응을 DB에서 재현 가능
- [ ] score 상승이 실제 forward return 개선과 연결되는지 decile/calibration으로 검증됨
- [ ] baseline 대비 intelligence v2 PAPER의 기대값/수익률/DD가 walk-forward에서도 개선됨
- [ ] 사용자가 실제 매매 전에 `왜 지금`, `어디서`, `어디까지`, `틀리면 어디서 무효`인지 한 화면에서 확인 가능
- [ ] 최종 candidate는 단기 급등 lucky winner가 아니라 반복 검증된 후보로만 표시