# PAPER Strategy v2 / CCXT integration review

Status: design review only. No private exchange credentials, no live orders, no score promotion.

## 1. Current active PAPER path

The active Bithumb supervisor resolves `b3_trader.auto_demo.AutoPaperDemo` to `BithumbScopedPaperDemo`, which subclasses `MultiExchangePaperDemo`. `MultiExchangePaperDemo` reuses the execution and sizing semantics from `auto_demo_v2.AutoPaperDemo` while storing state by `exchange + market + strategy`.

The current adaptive PAPER account model allocates an independent KRW 10,000,000 virtual account to every market. This is useful for per-coin research comparison, but it is not portfolio-capital allocation and must not be treated as a live-capital model.

### Current sizing behavior

- default base weight: 7.5% of the per-market KRW 10,000,000 account
- maximum position: 45% of that per-market account
- suggested order weight is clamped to 2.5%..15.0%
- exploration orders multiply the calculated weight by 0.55
- staged add orders multiply it by 0.75
- actual buy amount is the minimum of suggested amount, remaining position room, and remaining per-market cash

This architecture naturally produces many small tickets. A 2.5% order is KRW 250,000 and a 5% order is KRW 500,000. The add multiplier makes an averaging order smaller than an otherwise equivalent first entry.

### Current averaging trigger

An existing position is eligible for an add only when all of the following remain true:

- 30 minute buy cooldown has elapsed
- opportunity score is at least `max(62, exploration_floor + 5)`
- planned entries remain
- price is at/below the computed staged add level, or a high-opportunity momentum-add exception is met
- market lifecycle policy still allows adds
- spread/slippage/BTC-flash risk checks allow the simulated fill

The staged price is based on the current average price and volatility-dependent 2.0%..4.5% steps. Because a falling market can simultaneously lower regime/entry/opportunity scores, the strategy can reach the averaging price while failing the opportunity gate. Therefore an averaging plan can be visible without an averaging fill.

The Strategy Lab `dca` style has the same conceptual issue in a different form: it requires the style entry filters to remain valid before an add and then requires price to be at least `add_drop_pct` below average. DCA follow-up size is also reduced to 92% of the base desired order rather than increased.

## 2. Diagnosis

The user's observation that the PAPER engine trades in small KRW clips and appears not to average down is consistent with the code contract.

This is not primarily an exchange-client problem. The main defects to solve are strategy/risk architecture:

1. Per-market independent KRW 10M accounts are research scopes, not a shared portfolio budget.
2. Position sizing is mostly fixed-percent sizing instead of risk-budget sizing.
3. Averaging is gated by the same/stronger opportunity conditions that can deteriorate during the pullback intended to trigger averaging.
4. Add size is smaller than the base entry, so the average price moves slowly.
5. There is no explicit capital reservation for a planned averaging ladder.
6. Planned/due/blocked/executed averaging states are not first-class execution states with durable blocker reason history.
7. PAPER fills are simplified immediate simulations and are not yet modeled as a real order lifecycle with partial fills, cancel/replace, reserved cash and reconciliation.

Do not fix these defects by simply increasing every order amount or by using an unbounded martingale multiplier.

## 3. What CCXT can improve

CCXT is suitable as an exchange integration layer, not as the strategy engine.

Useful capabilities for this project:

- one unified exchange interface for Bithumb, Upbit and later exchanges
- public market metadata and market loading
- normalized ticker/OHLCV/order-book/trade access
- unified balance/order/open-order/closed-order operations where supported by each exchange
- market precision and amount/price formatting
- exchange-specific capability inspection before calling a method
- built-in request throttling/rate-limit metadata
- synchronous and asynchronous Python usage; CCXT Pro provides WebSocket-oriented interfaces for supported exchanges
- exchange-specific fallbacks remain possible through the raw/implicit APIs when a unified method is absent

Current CCXT Bithumb support includes spot market data, balances, create/cancel/fetch orders, open/closed orders and batch order support. Current Upbit support includes spot market data, balances, create/cancel/edit/fetch orders and open/closed orders. Both exchange definitions currently declare spot sandbox support as false, so our own PAPER execution engine remains necessary.

CCXT must not be allowed to decide signals, position size, averaging levels or risk budgets.

## 4. Recommended target architecture

Keep the current research and signal stack, but split execution into explicit layers.

### Strategy / portfolio layer

- signal generation
- market regime
- portfolio opportunity ranking
- shared capital budget
- risk-per-trade budget
- target position exposure
- averaging ladder reservation
- exit policy

### Order intent layer

Create an exchange-neutral `OrderIntent` containing at minimum:

- exchange
- market
- side
- order type
- requested cost / amount
- limit price when applicable
- strategy id
- position id / averaging ladder id
- idempotency key
- reason
- maximum slippage
- time-in-force intent

### Execution gateway

Define one gateway contract and multiple implementations:

- `PaperExecutionGateway`
- `CcxtExecutionGateway`

Both must consume the same `OrderIntent` after the same pre-trade risk checks. This is the main parity requirement for later live trading.

### Reconciliation layer

Before live trading, persist and reconcile:

- submitted order
- exchange order id
- open/partial/filled/canceled/rejected state
- cumulative filled quantity/cost
- fee
- reserved KRW
- position quantity and average cost
- duplicate/idempotency status

Live mode must fail closed when exchange state cannot be reconciled.

## 5. Position sizing v2 direction

Replace the current fixed small-ticket model with a bounded portfolio allocator. A future implementation should have configurable but hard-bounded inputs such as:

- shared PAPER portfolio capital
- maximum total exposure
- maximum exposure per asset
- maximum new risk per setup
- initial tranche percentage of target position
- reserved capital for planned adds
- maximum number of adds
- maximum total loss at invalidation

The first entry should be derived from target position/risk budget, not from a universal KRW 250k-500k clip.

Averaging should be a pre-declared finite ladder. Each add should have a planned price condition, size, remaining reserved capital and invalidation condition. The ladder must be canceled when the setup is invalidated rather than requiring a strong opportunity score at every lower price.

No unbounded martingale is permitted. The total position and total loss-at-stop must remain bounded before the first order is accepted.

## 6. Implementation order

1. Add read-only diagnostics for current fill sizes and averaging blocker reasons.
2. Introduce shared portfolio/risk-budget model in PAPER only.
3. Implement explicit finite averaging-ladder state machine and reserved capital.
4. Make PAPER execution model order lifecycle, fees, slippage and partial fills.
5. Add CCXT public/read-only adapter alongside existing native adapters; compare normalized outputs.
6. Add CCXT private gateway contract with calls disabled by default and no credentials in repository.
7. Use exchange market precision/limits/capability checks in PAPER preflight.
8. Run forward PAPER comparison between legacy and v2 strategies.
9. Only after evidence gates pass, consider a separately armed live execution phase.

## 7. Immediate decision

Adopt CCXT, but do not replace the strategy with CCXT and do not switch the current Bithumb runtime to private CCXT calls yet.

The immediate strategy priority is Position Sizing v2 + Averaging Ladder v2. CCXT should be introduced in parallel as an exchange gateway/parity layer so that the improved PAPER strategy can later move to live execution without rewriting its strategy logic.
