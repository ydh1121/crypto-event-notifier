# CRYPTO SIMPLIFIED TRADING MIGRATION PLAN v1

Status: IMPLEMENTATION ORDER CANONICAL
Date: 2026-09-21
Parent: WO-007 accepted planning artifacts
Production: prohibited

## 0. Migration rule

Do not rewrite the entire Viewer.

Migrate in bounded slices while preserving:
- all existing data contracts;
- PAPER execution semantics;
- holdings mutation semantics;
- polling continuity;
- simple/detail reader mode;
- light/dark theme;
- secondary access to existing capabilities;
- no real-money order path.

The two primary user destinations are:
1. 실전매매
2. 가상매매

Secondary:
- 탐색
- 기록
- 운영
- 연구·데이터 as contextual/deep evidence, not necessarily top-level.

## 1. WO-008 — Primary shell + 실전매매 composition v1

### Goal
Make the first primary page actually answer:
- 어떤 코인?
- 어떤 전략?
- 어디서 몇 % 진입?
- 어디서 몇 % 익절?
- 보유 중이면 물타기/익절 계산은?

### Allowed
- Add a new primary route/page module for 실전매매.
- Change visible top navigation hierarchy to 실전매매 / 가상매매 / 탐색 / 기록.
- Keep 운영 under owner/admin utility access.
- Reuse existing selectors/store data from holdings, dashboard watch candidates, PAPER plans, strategy summaries and calculators.
- Reuse existing averaging / holding-plan logic.
- Add composition-specific CSS only when the canonical component/foundation layers cannot express the layout.
- Add contract test for route/nav/capability presence.

### Not allowed
- Delete old routes/modules.
- Change PAPER execution.
- Change strategy algorithm semantics.
- Invent dominant-strategy evidence.
- Fake recommendation rows or fake prices.
- Change holdings write semantics.
- Build real trading/order submission.
- Production deploy.

### Required visible blocks

1. Context bar
   - exchange
   - ticker/search
   - current price
   - actual holding summary only when held

2. Rising-candidate rail/list
   - use only existing real watch/candidate data
   - if dominant-strategy/reaction evidence is not projected yet, omit those fields rather than inventing them

3. Strategy plan workspace
   - current available strategy/PAPER evidence
   - split entry target + allocation
   - split exit target + allocation when source supports it
   - sample/validation state
   - unresolved dominance must show “검증 부족/비교 필요”, never an invented winner

4. Calculator workspace
   - 물타기
   - 익절/고점보호
   - one local mode visible at a time
   - inherit selected actual holding when available

### Acceptance
- No route hopping needed between selected coin context, strategy plan and calculators.
- No horizontal overflow at 390 and desktop.
- No large empty right-half layout.
- No clipped master list.
- No generic dashboard cards added.
- Existing assets/PAPER/research/strategy routes remain reachable for fallback/secondary use.
- Full Viewer typecheck/contracts pass.
- Preview-only QA; Production unchanged.

## 2. WO-009 — 가상매매 selected-coin consolidation

### Goal
Selected coin persists while user switches:
- 전략
- BTC/ETH 대비
- 이벤트 반응

### Strategy mode
Merge existing PAPER + Strategy surfaces:
- per-strategy account state
- current position/plan
- strategy performance
- trade ledger

If per-strategy account/trade ledger projection is absent, this WO may add only the bounded projection required for those blocks.

### BTC/ETH mode
Project and render selected-coin BTC/ETH relative history.

### Event mode
Project and render selected-coin event/reaction memory.

No general news portal.

## 3. WO-010 — Secondary route consolidation

Reclassify without feature deletion:
- market/theme/project profile -> 탐색
- historical fills/learning/decision/event/incident -> 기록
- runtime/collector/db/publisher/backup/CI/access -> 운영
- flow/CVD/orderbook/absorption/listing/DEX -> 연구·데이터 contextual entry

Top-level clutter is removed only after deep-link/reachability tests prove no capability became unreachable.

## 4. WO-011 — Evidence-backed recommendation completion

Only after required projections exist.

Recommendation row:
- exchange
- ticker
- current price
- dominant strategy or insufficient-evidence state
- next entry
- recent PAPER evidence
- BTC/ETH relative summary
- latest event-reaction summary

No recommendation promotion when evidence freshness/sample gate fails.

## 5. WO-012 — Device/release QA

Re-open the deferred WO-006 concerns against the new IA:
- 360/390/430
- iPhone Safari focus/keyboard/safe-area
- polling continuity
- selected coin/strategy state
- light/dark
- desktop 1280/1440/1920
- no clipped controls or broken market grid

Production remains blocked until this gate passes.

## 6. Implementation sequencing rule

Do not jump ahead because a later feature is easier.

Order:
WO-008 -> WO-009 -> WO-010 -> WO-011 -> WO-012

Any source mutation requires fresh local clean/aligned parent verification first.
