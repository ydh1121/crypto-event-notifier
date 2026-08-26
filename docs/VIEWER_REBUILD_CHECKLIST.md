# Viewer Rebuild Checklist

이 문서는 외부 Cloudflare Pages Viewer의 기능 누락 방지 계약이다.

규칙:
- 구현 완료 + 새 모듈 UI에서 접근 가능해야 `[x]`.
- 백엔드에만 존재하거나 이전 UI에만 있으면 `[ ]`.
- 페이지 간 자동 이동으로 상세를 대신하지 않는다.
- 한 기능의 DOM은 한 페이지 모듈만 소유한다.
- 공통 상태/HTTP/라우팅/포맷은 `public/modules/core|shared|services`만 소유한다.
- 외부 공개 트레이딩 UI 레퍼런스는 `docs/TRADING_UI_REFERENCE.md`를 기준으로 하되 우리 권한/데이터 모델에 맞게 적용한다.

## 0. 모듈 아키텍처
- [x] core/http: HTTP/JSON 오류 처리 공통화
- [x] core/store: 사용자/스냅샷/UI 상태 단일 store
- [x] core/router: 최상위 화면 전환 단일 router
- [x] core/auth: 로그인/부트스트랩/초대/로그아웃
- [x] core/snapshot: 15초 snapshot polling, 중복 요청 방지, 5xx 1회 재시도
- [x] shared/format: 원화/퍼센트/가격/판단문구
- [x] shared/selectors: 거래소 projection, 보유자산, PAPER, 전략, 기록 selector
- [x] shared/components: KPI/점수/로딩/빈상태/거래소 segment
- [x] services/market-detail: 코인 상세 API + 짧은 캐시
- [x] pages/*: 페이지별 DOM 소유권 분리
- [x] 거래소 UI 상태를 research/paper/strategy/records 별도로 분리
- [x] 기존 app.js/canonical/exchange/records/strategy DOM 후처리 스크립트 미로딩
- [x] 외부 공개 트레이딩 UI 레퍼런스/채택 원칙 문서화

## 1. 대시보드
- [x] 먼저 확인할 것
- [x] 실제 자산 평가액/손익/수익률
- [x] 시장 상태/관찰 후보
- [x] 빗썸+업비트 전체 PAPER 증감액/수익률
- [x] 전략 후보/검증중/미통과 요약
- [x] 지금 볼 코인
- [x] 거래소별 PAPER 요약
- [x] 최근 중요 변화 타임라인 - 두 거래소 최근 체결/학습 통합

## 2. 리서치
- [x] PC master-detail 2열 고정
- [x] 빗썸/업비트 독립 거래소 선택
- [x] 시장/진입/후보 요약
- [x] 티커/코인명 검색
- [x] 전체/매수후보/눌림대기/관찰/매수금지/PAPER보유 필터
- [x] 우선 후보 목록
- [x] 코인 클릭 시 같은 화면 우측 상세 갱신
- [x] 현재 판단을 가격보다 우선 표시
- [x] 시장/매수타이밍/기회점수
- [x] 실제 보유 평단/평가액/손익
- [x] 해당 코인 PAPER 평가액/보유/수익률/거래/승률
- [x] 다음 진입/추가매수, 목표, 손절, 분할 계획
- [x] 되돌림/변동성/호가/BTC 흐름 진단
- [x] PAPER equity mini chart
- [x] 기회점수 history mini chart
- [x] 최근 체결
- [x] 최근 학습
- [ ] 가격 history + buy/sell marker
- [ ] 시장/진입/기회 3선 history chart
- [ ] 1H/6H/24H/7D range selector
- [ ] ETH/BTC 별도 시장참고 블록
- [ ] Phase 5 온체인/뉴스/커뮤니티/거시
- [ ] Phase 6 AI 종합 해석

## 3. 자산
- [x] 현재 평가액/투입원금/손익/수익률/종목수
- [x] 외부 조회용 자산 배분 시각화
- [x] PC 좌측 보유종목 목록
- [x] PC 우측 선택 종목 상세
- [x] 보유종목 클릭 시 탭 이동 금지
- [x] 보유 수량/평단/현재가/평가액/손익
- [x] 선택 종목 빗썸 판단/점수/PAPER 참고
- [x] 선택 종목 업비트 판단/점수/PAPER 참고
- [x] 로컬 PC에서만 보유/물타기 계획 관리한다는 권한 표시
- [ ] 로컬 averaging plan을 read-only snapshot으로 외부 Viewer에 표시
- [ ] 포트폴리오 평가액/손익 history chart

## 4. PAPER
- [x] 요약 / 코인별 성과 / 거래소 비교 3영역 분리
- [x] 기본 진입은 요약
- [x] 빗썸+업비트 통합 시작금액/평가액/증감액/수익률
- [x] 빗썸 별도 성과
- [x] 업비트 별도 성과
- [x] 코인별 성과 빗썸/업비트 선택
- [x] 검색
- [x] 전체 필터 항상 노출
- [x] 보유/매매완료/수익/손실 필터
- [x] 전체 보기 reset
- [x] 수익률/거래/승률/보유금액/기회점수 정렬
- [x] PC 좌측 코인 목록 + 우측 선택 코인 상세
- [x] 독립 계좌 평가액/현금/보유/평단/미실현/실현/거래/승률
- [x] 현재 진입/추가매수/목표/손절/분할 계획
- [x] 최근 체결/학습
- [x] 빗썸↔업비트 공통 코인 비교표
- [x] 거래소 비교 검색/정렬/전체 보기
- [x] 비교표 sticky header
- [ ] 전체 PAPER equity curve
- [ ] 전체 drawdown curve
- [ ] 선택 코인 price + fill chart

## 5. 전략 연구
- [x] 최상위 독립 화면
- [x] 빗썸/업비트 독립 선택
- [x] 기본 6전략 + 사용자 전략을 같은 표에 표시
- [x] 수익률/최대하락폭/PF/거래/승률/검증 비교
- [x] 선택 전략 우측 상세
- [x] 기대값/수익시장비율/손익집중도
- [x] Candidate/Warming/Rejected 상태
- [x] 후보 Gate 8개 기준 표시
- [x] 자동승격 없음 표시
- [x] 사용자 조합전략은 로컬 PC 전용 관리 표시
- [ ] 전략 equity curve
- [ ] 전략별 코인 성과 상세표
- [ ] 코인 × 전략 matrix/detail
- [ ] Phase 7 walk-forward 화면
- [ ] Phase 8 candidate promotion 화면

## 6. 기록
- [x] 최상위 독립 화면
- [x] 빗썸/업비트 선택
- [x] 기간 필터 - 최근 1H/6H/24H/7D/전체
- [x] 코인 검색 필터
- [x] 전체/매수/매도/학습 필터
- [x] 누적 체결/누적 학습/최근 매도손익/마지막 기록
- [x] 체결가/금액/실현손익/이유/시간
- [x] 학습 전후 시장/진입/비중 변화
- [x] 기록 클릭에 의한 강제 리서치 이동 없음
- [ ] 전략 필터 - 현재 snapshot record payload에 전략 식별값 없음
- [ ] 판단 상태 변경 기록 별도 탭
- [ ] 시스템 이벤트 기록 별도 탭

## 7. 시스템
- [x] 주 Navigation에서 분리, 우측 최신상태/사용자 버튼으로 접근
- [x] 연구 노드 상태
- [x] 구성요소 목록
- [x] 계정/권한
- [x] 관리자 사용자 초대
- [x] PAPER ONLY / READ ONLY / Cloudflare→PC 제어없음 / 실제주문없음
- [ ] Git local/remote/CI 상세
- [ ] Cloudflare snapshot/detail/deploy 상세
- [ ] Warehouse/Drive backup 상세
- [ ] Telegram BUY_CANDIDATE 상태
- [ ] 로컬 전용 휴대폰 연결/제어 상태 외부 요약

## 8. 로컬 PC 전용 - 외부 Pages에 쓰기 기능 추가 금지
- [x] 보유 수량/평단 저장은 로컬
- [x] 보유 정보 삭제는 로컬
- [x] 물타기 최대 20회 계획 저장/수정/삭제는 로컬
- [x] 사용자 조합 전략 생성/일시정지/재개는 로컬
- [x] Cloudflare Pages는 읽기 전용

## 9. 구현 순서
- [x] V6 모듈 경계 정의
- [x] 대시보드 모듈
- [x] 리서치 master-detail 모듈
- [x] 자산 master-detail 모듈
- [x] PAPER 모듈
- [x] 전략 연구 모듈
- [x] 기록 모듈
- [x] 시스템 모듈
- [x] V6 static/remote 배포 checker 구현
- [x] 최신 기능 HEAD GitHub Actions PASS - Python / Dashboard / Cloudflare / modular viewer
- [ ] Windows/Pages 실제 배포 PASS
- [ ] PC 브라우저 영상 QA
- [ ] 모바일 390/430 QA
- [ ] 남은 `[ ]` 기능을 우선순위대로 복구/구현

## 10. Dead UI asset 정리
- [ ] V6 CI + 실제 Pages PASS 후 기존 `app.js` / canonical / exchange-phase3 / local-parity / asset-local-port / records-port / strategy-lab-v2 dead UI asset 삭제
- [ ] 삭제 후 Cloudflare Pages typecheck/배포 재검증
