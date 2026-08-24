# Research Platform v1 tasks

Status legend: `[ ]` pending · `[-]` active · `[x]` complete · `[>]` deferred

## Phase 0 — current dashboard/PAPER stabilization gate

- [-] User acceptance of Photo-eBook top navigation on PC + iPhone
- [-] Verify Chrome remains responsive during full-market PAPER research
- [-] Verify GitHub -> local sync runs without manual repair during a normal session
- [x] Preserve local SQLite/control state across restart
- [x] Keep live exchange execution out of this workstream

Phase 0 remains the release gate for calling the current dashboard stable, but it no longer blocks low-risk sidecar/viewer work. PAPER execution semantics remain unchanged.

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
- [ ] Add retention/compaction policy after real volume is measured
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
- [x] Add dashboard component-health UI
- [x] Add safe per-component on/off controls
- [x] Add immediate per-component `지금 실행` control without restarting the trader
- [x] Apply control-file changes live in the research supervisor
- [x] Restrict component mutations to loopback/local PC; remote clients are read-only

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
- [x] Show external-repo watch count/update/failure summary in the research component UI
- [ ] Review licenses before adopting code from any reference
- [ ] Add staged install directory and compatibility-test runner
- [ ] Add PAPER smoke test before promotion
- [ ] Add rollback version management
- [ ] Add manual promote action only after the staging/test/rollback chain exists

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

- [x] CI: Python tests + compile, dashboard smoke and Cloudflare typecheck passed for the initial Phase 1 foundation
- [x] CI: component-control API/supervisor/dashboard slice passed Python tests + compile, dashboard smoke and Cloudflare typecheck
- [ ] Long-run observation remains useful for retention sizing, but no longer blocks Phase 2 work
- [ ] Measure storage growth/day before choosing retention and compaction

## Phase 2 — Cloudflare Pages viewer + invite users

- [-] Stable free `*.pages.dev` viewer architecture/scaffold
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
