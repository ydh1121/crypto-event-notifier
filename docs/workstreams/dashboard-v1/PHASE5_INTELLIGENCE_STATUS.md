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
- [ ] Reviewed live/intraday Nasdaq/S&P 500/VIX data-provider adapter with explicit permitted usage and timestamp semantics.
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
- [ ] BEA official actual-value adapter. BEA API credentials/data-access handling must be reviewed before implementation; HTML scraping is not an accepted substitute.
- [ ] Reviewed external consensus provider. Official schedule sources are not treated as consensus providers.
- [ ] Historical surprise distribution and z-score; do not calculate until enough clean comparable samples exist.
- [ ] Macro sensitivity confidence/promotion gate.

## 6. Runtime QA

- [x] Read-only runtime checker implemented as `python -m b3_trader.phase5_runtime_check`.
- [x] Checker requires current supervisor heartbeat, PAPER-only safety, `can_place_orders=false`, enabled/healthy Phase 5 component, at least one successful network-enabled cycle, all five official source IDs and zero source failures.
- [x] A healthy zero-new-event cycle is accepted; event count is not used as a fake health signal.
- [x] Malformed/missing runtime fields fail closed instead of being silently coerced into a pass.
- [ ] Real 24-hour PC runtime smoke has not yet been observed after pulling this HEAD. Do not mark runtime green until the local command returns `"ok": true` after the supervisor has completed at least one cycle.

## 7. Remaining promotion path

1. Pull/restart the 24-hour PC on the current branch and run `python -m b3_trader.phase5_runtime_check` after the first Phase 5 cycle; retain the result as runtime evidence.
2. Connect the BEA official actual-value adapter after credential/data-access review.
3. Connect a reviewed external consensus source.
4. Connect a reviewed U.S. intraday reference provider.
5. Accumulate forward-only samples across events, coins and regimes.
6. Define minimum sample, dispersion, recency, provider-quality and regime-stability gates.
7. Produce shadow EventScore / RegimeScore / RelativeStrengthScore contributions only for groups that pass those gates.
8. Run baseline vs intelligence-v2 PAPER A/B without altering the current baseline strategy.
9. Validate walk-forward/out-of-sample behavior before any candidate promotion.
10. Project evidence and explanations into the Viewer only after the backend contracts are stable.

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
