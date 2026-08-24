# Research Platform v1 tasks

Status legend: `[ ]` pending · `[-]` active · `[x]` complete · `[>]` deferred

## Phase 0 — current dashboard/PAPER stabilization gate

- [-] User acceptance of Photo-eBook top navigation on PC + iPhone
- [-] Verify Chrome remains responsive during full-market PAPER research
- [-] Verify GitHub -> local sync runs without manual repair during a normal session
- [x] Preserve local SQLite/control state across restart
- [x] Keep live exchange execution out of this workstream

Phase 0 remains the release gate. Phase 1 foundation below is deliberately sidecar/read-only so it does not change PAPER execution semantics.

## Phase 1 — 24/7 local data foundation

### 1A. Analytical warehouse

- [x] Add DuckDB runtime dependency
- [x] Add incremental SQLite -> Parquet exporter
- [x] Export append-heavy `research_market_memory`
- [x] Export PAPER fills
- [x] Export learning feedback
- [x] Export equity history
- [x] Partition Parquet by table + UTC date
- [x] Persist export checkpoints locally so restart does not duplicate old rows
- [x] Keep SQLite authoritative; Parquet remains secondary analytical history
- [ ] Add retention/compaction policy after real 24h volume is measured
- [ ] Add Upbit partitions after Phase 3 adapter exists
- [ ] Add news/community/on-chain/macro partitions in Phase 5

Local root:

`b3_trader/data/research-warehouse/`

This path remains ignored by Git.

### 1B. 24/7 research component supervisor

- [x] Add separate non-trading research supervisor process
- [x] Start/stop supervisor with the normal Windows launcher
- [x] Keep supervisor alive across normal trader operation
- [x] Restart supervisor when Git/Python update requests exit code 75
- [x] Component failures are isolated and retried instead of stopping the trader
- [x] Persist component health/status locally
- [x] Persist bounded local supervisor log
- [ ] Add dashboard component-health UI after Phase 0 UI is accepted
- [ ] Add safe per-component on/off controls
- [ ] Add independent restart control per component

Current managed components:

- `warehouse-export` — every 5 minutes
- `reference-version-watch` — every 6 hours

Safety contract:

- cannot place orders
- cannot change PAPER strategy profiles
- cannot auto-promote external code

### 1C. External repository registry/version watch

- [x] Add committed reference catalog at `control/reference-components.json`
- [x] Record purpose/category/restart requirement/update policy
- [x] Mark license review as pending instead of guessing
- [x] Observe default-branch commit versions from GitHub
- [x] Persist latest-seen SHA/status locally
- [x] No cloning/execution/update promotion from watcher
- [x] Optional local `REFERENCE_GITHUB_TOKEN` support only for API-rate headroom; not required
- [ ] Review licenses before adopting code from any reference
- [ ] Add staged install directory and compatibility-test runner
- [ ] Add PAPER smoke test before promotion
- [ ] Add rollback version management
- [ ] Add `update available` UI and manual promote action

Initial catalog:

- Freqtrade
- Hummingbot
- NautilusTrader
- CCXT
- PyUpbit
- vectorbt
- Microsoft Qlib
- FinRL
- FinGPT
- Ollama
- llama.cpp
- OpenBB
- DefiLlama Adapters
- DuckDB
- Qdrant

## Phase 1 validation gate

- [ ] One continuous 24-hour local run
- [ ] Parquet files continue growing without duplicate checkpoints after restart
- [ ] DuckDB can query several days of accumulated market-memory Parquet
- [ ] supervisor status remains healthy/degraded without taking the trader down
- [ ] external version watcher detects upstream versions but never changes active code
- [ ] measure storage growth/day before choosing retention and compaction

## Phase 2 — Cloudflare Pages viewer + invite users

- [ ] Stable free `*.pages.dev` viewer
- [ ] GitHub -> Pages auto deploy
- [ ] outbound local snapshot publisher
- [ ] Cloudflare D1 owner/viewer accounts and invites
- [ ] secure session cookie
- [ ] owner-selectable visibility for manual holdings
- [ ] Google Drive remains backup/export only

## Phase 3 — Upbit all-market PAPER

- [ ] common public exchange adapter
- [ ] Upbit full KRW market collection
- [ ] independent 10M account per `exchange + market + strategy`
- [ ] Bithumb/Upbit cross-venue comparison

## Phase 4 — strategy laboratory

- [ ] 보수적
- [ ] 균형
- [ ] 공격적
- [ ] 분할매수
- [ ] 역추세
- [ ] 스윙
- [ ] multi-style experiment launcher
- [ ] isolated metrics/learning state per style

## Phase 5+ — context AI and promotion research

- [ ] on-chain feature collectors
- [ ] Korean/global community language features
- [ ] global news event objects
- [ ] FOMC/CPI/jobs/macro event-risk layer
- [ ] local AI inference service
- [ ] walk-forward/holdout strategy-improvement validation
- [ ] candidate promotion score using return + drawdown + sample size + stability + execution quality

Real-money execution stays deferred to a separate future workstream.