# Phase 5 Intelligence implementation status

This file records the implementation state behind `MASTER_ROADMAP.md` Phase 5 without changing the existing PAPER decision path.

Status legend: `[ ]` pending · `[-]` active · `[x]` implemented/tested

## 1. Safety boundary

- [x] Phase 5 remains research/shadow evidence only.
- [x] No Phase 5 module places orders or imports PAPER decision/order execution owners.
- [x] No arbitrary hard-coded score such as `NASDAQ up = +N points` or `CPI surprise = -N points` is enabled.
- [x] Missing/stale/ambiguous timestamps fail closed instead of being replaced by invented clocks.
- [x] Provider identity and exchange identity remain explicit; observations from different providers/venues are not silently merged.
- [ ] EventScore / RegimeScore / RelativeStrengthScore contribution remains disabled until sample/confidence/regime promotion gates and forward validation are complete.

## 2. Official source registry and ingest

- [x] Shared `IntelligenceSource` registry and normalized `IntelligenceEvent` contract.
- [x] Shared SQLite `research_intelligence_events` store with source/published/scheduled/observed/received clocks and dedup evidence.
- [x] BLS official release-calendar adapter for CPI, Employment, PPI and ECI families.
- [x] BEA official release-schedule adapter for PCE/personal income, GDP and U.S. trade families.
- [x] Federal Reserve FOMC meeting calendar adapter. Date-only meetings stay date-only; an exact statement clock is not invented.
- [x] SEC official press-release RSS adapter.
- [x] CFTC official press-release RSS adapter with committee/event noise excluded from the policy classifier.
- [x] Bounded `IntelligenceIngestCycle`; network collection is disabled by default and source failures are isolated.
- [x] Research Supervisor component `phase5-intelligence-ingest` runs the network-enabled official-source cycle on its own worker thread at a 900-second default interval with a 300-second minimum interval.
- [x] Phase 5 does not reuse the Build69/listing/DEX `ResearchWorkLock`; the existing forward-pipeline blocked component set remains unchanged.
- [ ] Project-specific official blog/RSS/X sources.
- [ ] Broader crypto-news source registry and duplicate-article clustering.
- [ ] Community/forum and human-indicator sources.

## 3. Event-conditioned coin reaction memory

- [x] Fixed forward windows: 15m / 1h / 4h / 1d.
- [x] Reaction anchor priority for observed events: published_at -> observed_at -> scheduled_at; received_at is never substituted as the event clock.
- [x] Forward-only start/end alignment; pre-event and pre-horizon prices are rejected.
- [x] `research_intelligence_reactions` raw evidence store.
- [x] `IntelligenceReactionBuilder` builds reactions from closed OHLCV only.
- [x] 15m/1h/4h use closed 1m paths; 1d uses closed 5m paths.
- [x] Full contiguous same-source candle path is required between reaction endpoints.
- [x] `research_intelligence_reaction_memory` aggregates sample count, mean, median, dispersion, positive/negative rate, recency and alignment delays by event type / coin / window / provider / exchange.
- [x] Reaction-memory confidence remains `None / not_promoted` until an explicit evidence gate exists.
- [ ] Entity-to-coin/sector mapping beyond the current explicit market research universe.
- [ ] Regime-conditioned and true lag-shifted reaction statistics.

## 4. U.S. equity/risk reference evidence

- [x] Nasdaq Composite, S&P 500 and VIX reference-series contract.
- [x] Reference observations require provider ID, observed time, latency class, session state, provider URL and data-rights note.
- [x] Reference-return calculations cannot mix providers.
- [x] Event-conditioned coin reaction <-> U.S. reference pair store.
- [x] Pairing is forward-only around the same event anchor and horizon.
- [x] Empirical sample count, covariance, beta, correlation and same-direction rate are computed per event type / coin / horizon / coin provider / exchange / reference provider.
- [x] VIX is stored with its raw sign; the research layer does not silently invert it into a risk-on score.
- [x] U.S. sensitivity confidence remains `None / not_promoted`.
- [x] Reviewed Massive Indices Snapshot adapter for Nasdaq Composite (`I:COMP`), S&P 500 (`I:SPX`) and VIX (`I:VIX`) with explicit provider timestamp, session state, latency class and data-rights metadata.
- [x] Massive `last_updated` nanoseconds map to `observed_at`; `REAL-TIME` and `DELAYED` map explicitly to realtime / 15-minute-delayed evidence, and unsupported timeframe/session values fail closed.
- [x] The required COMP/SPX/VIX set is atomic: missing entitlement, malformed data or one failed ticker causes zero reference rows to be persisted for that capture attempt.
- [x] Massive credentials are accepted only from `MASSIVE_API_KEY`, are sent via Authorization header, and are never persisted in evidence or result payloads.
- [x] Bounded Massive 1-minute custom-bars collector supports only `I:COMP`, `I:SPX` and `I:VIX`, uses an explicit `MASSIVE_INDICES_PLAN`, limits one request window to 48 hours and keeps the three-index capture atomic on request/parse failure.
- [x] Massive 1-minute bar timestamp `t` is treated as bar-open time; the stored close observation clock is `t + 60s`. Empty provider intervals stay empty and are never synthetically filled.
- [x] Massive Basic / Starter / Advanced plan metadata is preserved as end-of-day / 15-minute-delayed / realtime evidence instead of inferring entitlement from possession of an API key.
- [x] `assess_us_market_reference_path()` provides a research-only reference-path quality gate with configurable endpoint skew, coverage ratio and maximum-gap thresholds plus latency/data-rights consistency checks. It does not create market scores or fill missing bars.
- [ ] `IntelligenceUsMarketSensitivityStore.build_pairs()` does not yet enforce the new path-quality result for `massive_indices_1m`; quality-gated pair construction and rejected-path audit are the next backend step.
- [ ] Massive runtime cadence is intentionally not supervisor-wired until a real account/plan is configured and its permitted usage/latency class is observed. The adapters/collector are implemented/tested only.
- [ ] Regular/pre-market/after-hours regime conditioning after sufficient source coverage.

## 5. Macro values and surprise

- [x] Provider-neutral previous / consensus / actual value contract with provider, unit, reference period, known-at clock, data-rights and revision provenance.
- [x] Revisions are preserved as separate rows; initial actual is not overwritten by later revisions.
- [x] Surprise calculation uses the scheduled release boundary when available.
- [x] Consensus must have been known strictly before the release boundary; same-time/post-release consensus is rejected.
- [x] Initial actual must be known at/after the release boundary.
- [x] Unit/reference-period mismatches fail closed.
- [x] Absolute and relative surprise are evidence only; z-score, confidence and score contribution remain unset.
- [x] BLS official initial-actual adapter for CPI all-items MoM/YoY, nonfarm payroll change and unemployment rate.
- [x] BLS actual capture is bounded to a post-release window, does not call before scheduled release, refuses late historical backfill, requires a complete metric set and never overwrites a captured initial actual.
- [x] BEA official PCE actual-value adapter uses the registered BEA Data API only (`NIPA`, `T20804`, `T20807`); there is no HTML-scraping fallback for actual values.
- [x] BEA PCE actual capture produces headline/core MoM and YoY evidence, requires all four metrics atomically, preserves the first complete API observation as revision 0 and refuses late historical backfill outside the bounded post-release window.
- [x] BEA API credentials are accepted only from `BEA_API_KEY` / `BEA_USER_ID`; missing or malformed credentials cause a no-network fail-closed result and credential values are never written to result payloads or evidence rows.
- [x] Reviewed Trading Economics economic-calendar consensus adapter for CPI, Employment and PCE. Official BLS/BEA schedules remain release clocks and are not treated as consensus providers.
- [x] Trading Economics capture is limited to a complete snapshot inside the final 45 minutes before the official scheduled release; `known_at` must be strictly pre-release, event time/reference period must match, and incomplete/conflicting sets persist zero rows.
- [x] Trading Economics credentials are accepted only from `TRADING_ECONOMICS_API_KEY`; missing credentials cause zero network requests and do not poison official-source ingest health.
- [ ] Historical surprise distribution and z-score; do not calculate until enough clean comparable samples exist.
- [ ] Macro sensitivity confidence/promotion gate.

## 6. Runtime QA

- [x] Read-only runtime checker implemented as `python -m b3_trader.phase5_runtime_check`.
- [x] Checker requires current supervisor heartbeat, PAPER-only safety, `can_place_orders=false`, enabled/healthy Phase 5 component, at least one successful network-enabled cycle, all five official source IDs and zero source failures.
- [x] A healthy zero-new-event cycle is accepted; event count is not used as a fake health signal.
- [x] Malformed/missing runtime fields fail closed instead of being silently coerced into a pass.
- [ ] Real 24-hour PC runtime smoke has not yet been observed after pulling this HEAD. Do not mark runtime green until the local command returns `"ok": true` after the supervisor has completed at least one cycle.
- [ ] A valid BEA registered API UserID has not yet been configured and observed on the real 24-hour PC. BEA actual API capture is implemented/tested but not runtime-proven until a due PCE release is captured there.
- [ ] A valid Trading Economics subscription key has not yet been configured and observed on the real 24-hour PC. Consensus capture is implemented/tested but not runtime-proven until one supported release receives a complete pre-release snapshot.
- [ ] A Massive Indices plan/key has not yet been configured and observed on the real 24-hour PC. The actual entitlement and returned `REAL-TIME` / `DELAYED` class must be recorded before enabling a recurring reference-data worker.

## 7. Remaining promotion path

1. Enforce the reference-path quality gate inside U.S. sensitivity pair construction for `massive_indices_1m`, retain rejected-path reason counts/evidence and keep legacy/snapshot providers explicitly distinguishable.
2. Pull/restart the 24-hour PC on the current branch and run `python -m b3_trader.phase5_runtime_check` after the first Phase 5 cycle; retain the result as runtime evidence.
3. Configure a valid BEA API UserID as a local environment secret (`BEA_API_KEY` or `BEA_USER_ID`; never commit the value) and observe one due PCE initial-actual capture.
4. Configure a reviewed Trading Economics subscription key (`TRADING_ECONOMICS_API_KEY`) and observe one complete pre-release consensus snapshot for CPI, Employment or PCE.
5. Configure a Massive Indices key (`MASSIVE_API_KEY`) plus explicit `MASSIVE_INDICES_PLAN`, verify COMP/SPX/VIX entitlement and actual latency semantics, then choose a bounded recurring collection cadence before supervisor wiring.
6. Accumulate forward-only macro surprise, coin reaction and quality-approved U.S. reference samples across events, coins and regimes.
7. Add true lag-shifted and regime-conditioned reaction/sensitivity statistics.
8. Define minimum sample, dispersion, recency, provider-quality and regime-stability gates.
9. Produce shadow EventScore / RegimeScore / RelativeStrengthScore contributions only for groups that pass those gates.
10. Run baseline vs intelligence-v2 PAPER A/B without altering the current baseline strategy.
11. Validate walk-forward/out-of-sample behavior before any candidate promotion.
12. Project evidence and explanations into the Viewer only after the backend contracts are stable.

## 8. Current implementation commits

- `a44b4eb` source registry + normalized event + event store
- `7a6c51f` BLS release calendar
- `7b0cc1f` BEA release schedule
- `20955ef` FOMC date-only calendar
- `8782331` U.S. market reference time-series contract
- `1ac39a4` SEC/CFTC RSS adapters
- `275cf6a` CFTC classifier fix + bounded ingest cycle
- `5571786` forward-only event reaction contract/store
- `8b94dc1` empirical coin reaction memory
- `8071acc` closed-OHLCV reaction builder
- `879a98f` reaction-builder float assertion correction; full B3 CI green
- `5769097` event-conditioned U.S. market sensitivity evidence; full B3 CI green
- `6eb14f9` look-ahead-safe macro previous/consensus/actual contract; full B3 CI green
- `934bf74` bounded BLS CPI/Employment initial-actual capture + ingest-cycle integration
- `7842de6` BLS fixture timestamp correction; full B3 CI green
- `7d85610` Phase 5 Research Supervisor runtime wiring + control/tests; full B3 CI green
- `6262455` read-only Phase 5 runtime smoke checker
- `5538b4d` runtime checker unit tests
- `e08fe4d` fail-closed runtime field parsing hardening
- `8e00fed` bounded official BEA NIPA PCE actual adapter
- `3f4deb0` BEA actual adapter tests
- `3aa5541` BEA actual capture ingest-cycle wiring
- `e0b31b7` BEA ingest wiring tests
- `801e2bf` BEA status documentation; 23/23 workflows green at that checkpoint
- `d7be160` Trading Economics pre-release consensus adapter + ingest wiring + tests; Python regression green
- `739d8ce` Massive COMP/SPX/VIX reference adapter + atomic entitlement/timestamp/latency tests; Python regression green
- `7e6b4a1` bounded Massive COMP/SPX/VIX 1-minute aggregate collector
- `78feb12` Massive 1-minute aggregate collector tests
- `d9a8ffb` realistic aggregate OHLC fixture correction; Python/Viewer/dashboard checks green at validation point
- `312b5b4` configurable U.S. reference-path quality assessor
- `bc9c798` reference-path quality gate tests; Python regression green
