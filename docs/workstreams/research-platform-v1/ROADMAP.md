# Research Platform v1 — staged roadmap

Status: **planned follow-on workstream**. The current `dashboard-v1` workstream remains active until its stabilization gate is accepted.

This roadmap assumes the Windows PC will run **24/7 as the primary research server**.

## North-star goal

Build a local-first crypto research platform that continuously learns from PAPER trading across Korean exchanges, combines market microstructure with on-chain/community/news/macro context, compares multiple trading styles fairly, and surfaces robust candidates for a later live-trading workstream.

The platform must remain **PAPER-only** until a separate live-execution workstream explicitly promotes selected strategies with exchange-balance reconciliation and hard risk controls.

---

# Architecture decisions

## 1. 24/7 PC is the research engine

The Windows PC is expected to remain online continuously and owns:

- exchange market collection,
- candles/orderbooks/tickers,
- per-market market-memory features,
- PAPER fills and account state,
- strategy experiments,
- on-chain/news/community/macro collection,
- local AI inference,
- experiment feedback and learning state,
- future live-execution supervisor.

The PC is not merely a temporary dashboard host. It becomes the long-running research node.

## 2. Google Drive is backup/export, not the live database

Do **not** use Google Drive as the transactional database for users, sessions, concurrent web reads or high-frequency research writes.

Use these roles instead:

- **Local SQLite** — authoritative trading journal, PAPER account state, profiles, fills and operational metadata.
- **Local Parquet + DuckDB** — large append-heavy market/feature/history warehouse for AI research and long-term pattern queries.
- **Cloudflare Pages** — stable `*.pages.dev` web shell deployed from GitHub.
- **Cloudflare Pages Functions / Worker** — authenticated read API, invite/session API, snapshot ingestion.
- **Cloudflare D1** — web users, invites, permissions and small read-oriented metadata.
- **Cloudflare KV or D1 snapshot tables** — latest dashboard snapshots only.
- **Google Drive** — encrypted/off-device backups, periodic export bundles and disaster recovery copies.
- **Private GitHub** — source code, specs and non-secret desired state.

## 3. Separate runtime data from published web data

Only compact read snapshots go to Cloudflare.

Never publish:

- exchange API secrets,
- local `.env`,
- raw SQLite databases,
- Cloudflare credentials,
- future live-order endpoints,
- unrestricted local admin controls.

Real holdings/average price may be published only into an owner-protected snapshot after login.

## 4. External repositories are references/adapters, not blindly copied code

Every external repo considered for adoption must have:

- repository URL,
- license reviewed,
- tested commit/tag pinned,
- adapter boundary defined,
- health check,
- update policy,
- rollback version,
- whether restart is required,
- whether it runs in-process, separate venv, subprocess or container.

Never auto-pull a new external version directly into a trading process without validation.

---

# Phase 0 — Stabilize the current baseline

Purpose: stop adding new subsystems on top of browser/sync regressions.

Deliverables:

- finish current Photo-eBook navigation QA on desktop + iPhone,
- verify Chrome remains responsive during full-market PAPER updates,
- verify one-owner Git synchronization works without manual repair,
- verify Bithumb all-market PAPER research resumes cleanly after restart,
- verify local SQLite state survives restarts,
- keep PR #1 Draft and unmerged until the user accepts the baseline.

Exit gate:

- at least one continuous normal session without browser freeze, navigation regression or manual Git realignment.

---

# Phase 1 — 24/7 local data foundation

Purpose: prepare the PC to accumulate enough structured history for future AI analysis.

## 1A. Storage split

Keep operational records in SQLite, but move high-volume time-series/features into date-partitioned Parquet files queried through DuckDB.

Suggested structure:

```text
local-data/
  market/
    bithumb/YYYY/MM/DD/*.parquet
    upbit/YYYY/MM/DD/*.parquet
  features/
    exchange=.../market=.../date=.../*.parquet
  text/
    news/
    community/
    macro/
  models/
  exports/
```

Persist at minimum:

- exchange + market,
- price/return,
- OHLCV features,
- spread,
- orderbook imbalance/depth,
- turnover/liquidity,
- realized volatility,
- pullback/drawdown,
- regime/entry/opportunity scores,
- position intent,
- strategy profile ID,
- later: on-chain/community/news/macro features.

## 1B. Collector supervisor

Create a local component supervisor with statuses:

- running,
- stopped,
- degraded,
- update available,
- restart required,
- failed health check.

A component must be independently restartable without bringing down the full dashboard.

Initial components:

- `market-bithumb`,
- `paper-research`,
- `web-api`,
- `backup`,
- later `market-upbit`, `news`, `community`, `onchain`, `macro`, `local-ai`.

## 1C. External repository registry / version watch

Add a registry such as:

```json
{
  "component": "freqtrade-reference",
  "repo": "https://github.com/freqtrade/freqtrade",
  "enabled": false,
  "installed_version": "pinned-tag-or-sha",
  "latest_seen_version": "...",
  "update_policy": "manual-promote-after-tests",
  "restart_required": true
}
```

The 24/7 PC may check GitHub Releases/default-branch versions periodically, but only mark `update available`.

Promotion flow:

`detect -> download/stage -> compatibility tests -> PAPER smoke test -> user-approved enable -> restart component -> health check -> rollback on failure`

Do **not** let external-repo changes silently alter active trading behavior.

Exit gate:

- 24h collector operation,
- restart-safe append-only history,
- component health/status dashboard,
- external repo registry can detect versions without auto-promoting them.

---

# Phase 2 — Cloudflare Pages viewer + invite-only users

Purpose: get a stable free `*.pages.dev` URL while the PC remains the 24/7 data engine.

## 2A. Pages shell

- deploy read-first dashboard through Cloudflare Pages from GitHub,
- use `*.pages.dev`; no purchased domain required,
- GitHub UI commits deploy directly to Pages,
- local admin-only actions stay out of the public viewer bundle.

## 2B. Local -> Cloudflare snapshots

Every 10–30 seconds, the PC publishes compact snapshots outbound to Cloudflare:

- aggregate PAPER capital/equity,
- exchange health,
- top/filtered market summaries,
- per-market detail on demand or in bounded batches,
- freshness timestamp,
- PC online/offline heartbeat.

PC offline behavior:

- Pages remains available,
- last snapshot remains visible,
- UI clearly shows `마지막 갱신` and stale/offline state.

## 2C. Invite-only login

Initial roles:

- `owner`,
- `viewer`.

Features:

- owner creates/revokes invite,
- user activates invite and creates login,
- HttpOnly secure session cookie,
- viewer is read-only,
- owner can decide whether real manual holdings are visible to a specific user,
- no local trading controls exposed remotely.

Recommended live web storage: Cloudflare D1.

Google Drive remains backup/export only.

Exit gate:

- stable `*.pages.dev` viewer,
- GitHub UI commits auto-deploy,
- owner and invited viewer login from iPhone,
- no changing tunnel URL or phone connection code needed for normal viewing.

---

# Phase 3 — Upbit full-market PAPER research

Purpose: duplicate the all-market experiment on Upbit and measure venue effects.

## 3A. Common exchange adapter

Normalize:

- market list,
- ticker,
- candles,
- orderbook,
- websocket/public stream,
- fee assumption,
- spread/slippage estimate,
- rate-limit/health status.

Implement:

- `BithumbPublicAdapter`,
- `UpbitPublicAdapter`.

## 3B. Experiment identity

Every experiment is isolated by:

`exchange + market + strategy_profile`

Examples:

- `BITHUMB:KRW-XRP:balanced`,
- `UPBIT:KRW-XRP:balanced`.

Each gets its own 10,000,000 KRW PAPER account.

## 3C. Cross-exchange comparison

For dual-listed markets show:

- current price difference,
- turnover difference,
- spread/depth difference,
- PAPER return by venue,
- win rate,
- drawdown,
- trade count,
- execution quality,
- whether the same strategy behaves differently by venue.

Exit gate:

- all valid Upbit KRW markets continuously collected,
- Bithumb/Upbit experiments isolated and comparable,
- one venue outage does not stop the other.

---

# Phase 4 — Strategy laboratory / user-selectable trading styles

Purpose: test multiple hypotheses instead of forcing every market through one conservative profile.

Initial families:

- **보수적** — high selectivity, smaller exposure, tighter liquidity/risk filters.
- **균형** — current adaptive baseline.
- **공격적** — earlier entries, higher but capped weights, quicker realization.
- **분할매수** — explicit staged entry plan, remaining rounds, average-price improvement targets.
- **역추세** — panic/oversold mean reversion with separate falling-knife protection.
- **스윙** — higher timeframe bias, wider stops/targets, longer holding horizon.

## UX

Before an experiment starts:

- select exchanges,
- select all markets / filtered universe / chosen coins,
- check one or more styles,
- choose virtual capital,
- optionally choose maximum concurrent positions/risk budget,
- press `가상매매 시작`.

## Isolation rule

Each style gets its own experiment/account/profile state. Never mix fills or learned parameters across styles.

## Comparison metrics

- KRW profit/loss,
- return %,
- maximum drawdown,
- win rate,
- profit factor,
- expectancy per trade,
- trade frequency,
- average holding time,
- fee/slippage burden,
- regime-specific performance,
- performance stability by time window.

Exit gate:

- at least the six initial styles can run simultaneously in PAPER mode without state contamination.

---

# Phase 5 — External intelligence feature layer

Purpose: add non-price context without letting noisy headlines directly control orders.

All external context is first stored as timestamped features/evidence. Strategy use comes only after correlation/forward-test validation.

## 5A. On-chain

Per asset/chain when meaningful:

- exchange inflow/outflow,
- active addresses,
- transaction count/value,
- fees/gas,
- TVL/protocol flow,
- stablecoin flows,
- whale/concentration changes where available,
- unlock/supply events.

Normalize into `onchain_feature` records with source, timestamp, confidence and freshness.

## 5B. Community / "human indicator"

Collect compliant public text/signals from sources such as:

- Reddit,
- X/Twitter where API/access permits,
- Telegram public channels where lawful/accessible,
- Korean crypto communities where terms permit,
- project Discord/public announcements where accessible.

Do not reduce this to simple positive/negative sentiment only.

Extract:

- repeated words/phrases,
- change in message volume,
- urgency/fear/euphoria language,
- meme/slang changes,
- newcomer vs holder language,
- certainty/hedging language,
- buy-the-dip / exit / scam / listing narratives,
- disagreement/polarization,
- language-specific nuance.

Store both raw-source references and derived features so later AI analysis can reproduce why a score changed.

## 5C. Global news

Build event objects rather than one global sentiment number:

- affected assets/sectors,
- event type,
- source reliability,
- novelty,
- urgency,
- expected horizon,
- bullish/bearish/ambiguous,
- confidence,
- first-seen time,
- follow-up corrections.

## 5D. Macro calendar / event risk

Include scheduled and surprise effects for:

- FOMC rate decisions,
- Powell/Fed communication,
- CPI/PCE,
- US payrolls/unemployment,
- GDP/retail sales/ISM when empirically useful,
- major regulatory decisions,
- ETF/listing/security incidents.

Strategy integration should support event states such as:

- `PRE_EVENT_REDUCE`,
- `NO_NEW_ENTRY_WINDOW`,
- `POST_EVENT_WAIT`,
- `VOLATILITY_BREAKOUT_ALLOWED`,
- `NORMAL`.

Do not hard-code that CPI/FOMC is always bullish or bearish. Measure market reaction and surprise.

Exit gate:

- external features stored continuously,
- source/freshness/confidence visible,
- PAPER experiment can enable/disable each feature family independently for A/B comparison.

---

# Phase 6 — Local AI research service

Purpose: use the 24/7 PC for local inference over accumulated market/text/event history.

The AI service is initially an **analyst/feature extractor**, not an autonomous live trader.

Jobs:

- classify news/events,
- summarize community narrative shifts,
- generate language/narrative embeddings,
- cluster recurring market setups,
- compare current pattern against historical analogues,
- explain why a strategy performed differently on two venues,
- identify which features preceded successful/failed entries,
- create nightly research reports,
- propose bounded strategy parameter experiments.

Recommended design:

- local model server,
- scheduled batch jobs for expensive text analysis,
- small fast model for continuous classification,
- optional embedding/vector index,
- all model outputs include `model_id`, `model_version`, prompt/schema version and source timestamps.

Model changes must be versioned so future backtests know which AI generated each feature.

Exit gate:

- reproducible model/version metadata,
- no AI output can silently mutate active live logic,
- AI proposals are evaluated as new PAPER experiments.

---

# Phase 7 — Evidence-based automatic strategy improvement

Purpose: move beyond naive "win -> loosen, loss -> tighten" tuning.

Add:

- rolling train/validation windows,
- untouched holdout periods,
- walk-forward evaluation,
- minimum trade/sample requirements,
- parameter-change audit history,
- rollback to prior profile,
- feature-ablation tests,
- venue/style/regime segmentation.

A profile may be promoted only if improvement survives out-of-sample data.

Never choose the highest recent return alone.

Candidate score should include at least:

- total/annualized return,
- maximum drawdown,
- trade count,
- expectancy,
- profit factor,
- win rate,
- consistency across windows,
- performance across market regimes,
- execution/slippage sensitivity,
- robustness on both Bithumb/Upbit when applicable,
- sensitivity to removing AI/external features.

Exit gate:

- strategy promotion is evidence-based and reversible.

---

# Phase 8 — Candidate promotion gate for future live trading

This phase still does **not** place real orders.

Produce a shortlist:

- best coin/exchange/style combinations,
- why they qualify,
- PAPER sample size,
- drawdown and tail-risk behavior,
- recent-vs-long-window performance,
- whether AI/external signals materially help,
- exact strategy/profile version.

Only after this report is accepted should a new `live-execution-v1` workstream be opened.

That later workstream must separately implement:

- exchange balance as source of truth,
- order idempotency,
- open-order/partial-fill reconciliation,
- stale-order cancellation,
- exchange-level exposure limits,
- hard daily-loss kill,
- tiny capped live pilot,
- fail-closed software/version updates.

---

# External repositories to study / optionally integrate

These are **reference inputs**, not automatic dependencies. Before integration, inspect license, release health, architecture fit and exchange support at that time.

## Trading engines / execution architecture

### Freqtrade
https://github.com/freqtrade/freqtrade

Study for:
- dry-run/live separation,
- backtesting,
- hyperparameter optimization,
- strategy lifecycle,
- WebUI/Telegram operations,
- FreqAI concepts.

Important: Freqtrade is GPL-family software; review license implications before copying/integrating source. Prefer architectural reference or isolated-service evaluation unless licensing is explicitly accepted.

### Hummingbot
https://github.com/hummingbot/hummingbot

Study for:
- event-driven crypto connectors,
- standardized REST/WebSocket connector boundaries,
- paper trading,
- high-frequency/orderbook-centric strategy architecture,
- componentized exchange integrations.

### NautilusTrader
https://github.com/nautechsystems/nautilus_trader

Study for:
- event-driven architecture,
- backtest/live execution parity,
- deterministic strategy/event modeling,
- high-performance market-data pipelines.

### CCXT
https://github.com/ccxt/ccxt

Study for:
- normalized multi-exchange interfaces,
- exchange capability detection,
- market/ticker/order normalization.

For Bithumb/Upbit, compare normalized behavior against official exchange APIs before adoption; Korean venue-specific semantics must not be hidden by abstraction.

### PyUpbit
https://github.com/sharebook-kr/pyupbit

Study specifically for:
- Upbit public/private API ergonomics,
- Korean-market examples.

Official Upbit API behavior remains the authority.

## Quant research / model evaluation

### vectorbt
https://github.com/polakowo/vectorbt

Study for:
- fast vectorized strategy comparisons,
- large parameter sweeps,
- portfolio analytics.

Useful primarily as an offline research/reference layer rather than the always-on execution engine.

### Microsoft Qlib
https://github.com/microsoft/qlib

Study for:
- quantitative ML dataset pipelines,
- experiment management,
- factor/model evaluation,
- train/validation/test discipline.

### FinRL
https://github.com/AI4Finance-Foundation/FinRL

Study later for:
- reinforcement-learning experiment design,
- environment/agent separation.

Do not let RL control live funds merely because a backtest score is high; require holdout/walk-forward evidence.

## Financial text / local AI

### FinGPT
https://github.com/AI4Finance-Foundation/FinGPT

Study for:
- financial text classification,
- sentiment/event extraction,
- financial LLM datasets/workflows.

Use as a feature-generation reference, not a direct buy/sell oracle.

### Ollama
https://github.com/ollama/ollama

Candidate local model server for the 24/7 PC.

Study for:
- local model lifecycle,
- simple HTTP inference service,
- model version swapping,
- always-on local inference.

### llama.cpp
https://github.com/ggml-org/llama.cpp

Alternative/lower-level local inference runtime.

Study for:
- efficient quantized inference,
- CPU/GPU portability,
- local model serving without cloud dependency.

## Local analytical storage / memory

### DuckDB
https://github.com/duckdb/duckdb

Recommended reference for querying large local Parquet market/feature history without introducing a heavy server database.

### Qdrant
https://github.com/qdrant/qdrant

Optional later component for vector/embedding retrieval across:
- community narratives,
- news events,
- historical setup descriptions,
- AI-generated research notes.

Do not add a vector database until the text corpus/embedding use case is large enough to justify it.

## Macro / market-data integration reference

### OpenBB
https://github.com/OpenBB-finance/OpenBB

Study for:
- macro/economic data provider abstractions,
- financial-data normalization,
- research API patterns.

For FOMC/CPI/payrolls, primary official sources/calendars should remain the final authority.

## On-chain integration reference

### DefiLlama Adapters
https://github.com/DefiLlama/DefiLlama-Adapters

Study for:
- protocol/chain normalization,
- TVL/flow adapter patterns,
- mapping heterogeneous on-chain sources into comparable metrics.

---

# Reference-repo operating policy

Create a future `control/reference-components.json` with fields like:

```json
{
  "id": "ollama",
  "repo": "https://github.com/ollama/ollama",
  "purpose": "local_ai_runtime",
  "enabled": false,
  "installed_ref": null,
  "latest_seen_ref": null,
  "update_channel": "release",
  "auto_download": false,
  "auto_activate": false,
  "restart_required": true,
  "healthcheck": "http://127.0.0.1:11434/api/tags",
  "rollback_ref": null
}
```

Dashboard component controls should eventually support:

- 설치 상태,
- 현재 버전,
- 새 버전 존재,
- 변경사항 보기,
- PAPER 호환성 테스트,
- 켜기/끄기,
- 재시작,
- 이전 버전으로 복구.

Default policy:

- detecting a new version is automatic,
- downloading may be automatic later,
- activation is never automatic for a component that can affect trading decisions,
- promotion requires tests,
- future live mode requires explicit user approval and fail-closed update behavior.

---

# Recommended implementation order

1. **Phase 0:** stabilize current dashboard/Git/PAPER runtime.
2. **Phase 1:** 24/7 data warehouse + component/version supervisor.
3. **Phase 2:** Cloudflare Pages viewer + users/login.
4. **Phase 3:** Upbit full-market PAPER adapter.
5. **Phase 4:** multi-style strategy laboratory.
6. **Phase 5:** on-chain/community/news/macro collectors.
7. **Phase 6:** local AI research service.
8. **Phase 7:** holdout/walk-forward automatic improvement.
9. **Phase 8:** produce live-candidate shortlist; open a separate live workstream only afterward.

This ordering is deliberate: first make the 24/7 data foundation reliable, then add another exchange and multiple strategies, then add expensive/noisy external intelligence and AI. Otherwise it becomes impossible to tell whether an observed performance change came from the strategy, the venue, the data source or the model.