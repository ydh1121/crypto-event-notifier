# Crypto Auto Trader repository rules

## Restart-safe workstream protocol

Long-running work must never depend on one ChatGPT conversation staying open.

Repository state is the source of truth. The active workstream is `docs/workstreams/dashboard-v1/` unless a newer active workstream explicitly replaces it.

When starting or resuming in a new chat/session:

1. Read this `AGENTS.md` first.
2. Read `DESIGN.md` before UI work.
3. Read the active workstream `TASKS.md` and `HANDOFF.md` before changing code.
4. Check the current branch/commit against the handoff.
5. Resume from the task marked `[-] active` or the handoff `Next action`; do not reconstruct progress from chat memory.
6. After every meaningful completed unit, update `TASKS.md` and `HANDOFF.md` in the same work session.
7. If interrupted mid-task, record partial files, checks not yet run, blockers, and the exact next command/action before stopping.

Permanent product rules/specs belong in Git. Temporary research and QA notes may live in the workstream folder while active.

## Runtime/source-of-truth roles

- **Local SQLite**: authoritative runtime/trading journal and paper-forward-test data.
- **Private GitHub**: application code, non-secret desired state, agent/workstream/design rules.
- **Google Drive**: off-device backup of consistent SQLite snapshots and mirrors of non-secret control/dashboard files. Never treat a live SQLite file in Drive as the database.
- **Telegram**: user-requested trading alert channel. Current automatic policy is **fresh BUY_CANDIDATE only**; routine state, Git sync, errors, fills, risk-off, and daily summaries stay in the dashboard/journal unless the user explicitly changes this policy.
- **Phone access**: VPN-free HTTPS Cloudflare Tunnel to the loopback-only local API. Prefer a persistent named Tunnel + custom hostname once configured; Quick Tunnel is a temporary fallback. Do not expose port 8765 directly to the public internet.
- **Cloudflare Pages**: optional static dashboard shell only. It is not the live trading database or execution engine.

Secrets (`.env`, dashboard token/phone connection code, Telegram token, Cloudflare tunnel credentials, future exchange keys) stay local and must remain excluded from Git/Drive.

## Current scope boundary

The current workstream stops at paper-forward-testing, dashboard/analytics, Telegram operations, backup/sync, multi-asset context profiles, and phone external access.

**Real-money execution is intentionally deferred.** Do not add or enable live order placement in this workstream. Keep `LIVE_TRADING_ENABLED=false`. Future live execution must be handled as a separate workstream with explicit balance reconciliation, order idempotency, partial-fill handling, exchange balance as source of truth, hard daily-loss limits, and a small capped pilot.

## UI/design contract

Read and apply `DESIGN.md` before dashboard work.

The visual baseline is the user's Photo-eBook project. Reuse its design principles, not its product-specific content: Apple-style system typography, grouped neutral canvas, calm card hierarchy, 8/12/16/24-based spacing, restrained blue accent, soft translucent borders/shadows, native scrolling, safe-area awareness, stable geometry, and high-quality responsive behavior.

For UI changes, also review the current Photo-eBook `UI_REGRESSION_SPEC.md` when the issue concerns mobile Safari, interactive state, navigation, touch behavior, spacing, or regression risk. Do not blindly copy product-specific classes or assets; extract the proven interaction rule and adapt it to this dashboard.

Do not create generic AI-dashboard styling: no neon gradients, excessive glass everywhere, arbitrary colored cards, dense icon grids, giant KPI typography, decorative charts without decision value, or gratuitous animation.

Motion must communicate state or spatial continuity. Prefer short ease-out/spring-like transitions. Avoid animating every numeric refresh. Respect `prefers-reduced-motion`.

Desktop improvements must not break mobile. Mobile controls need comfortable touch targets, safe-area clearance, natural vertical flow, and no horizontal page overflow.

Live polling must never reset user interaction state. Open disclosures, selected tabs/ranges, focused forms, and other deliberate UI state must survive 5-second data refreshes unless the underlying item disappears.

## Korean UI copy contract

Before adding or materially rewriting Korean UI copy, read and apply the current Photo-eBook `docs/spec-v1/20-korean-copywriting-skill.md`. The user's current wording/feedback outranks generic copy advice.

The default user-facing dashboard and Telegram alerts must be understandable without trading vocabulary. Treat a Korean non-trader in their 60s as the comprehension baseline.

Primary surfaces must use ordinary Korean first. Internal terms such as `Regime`, `Entry`, `Context`, `RISK_OFF`, `WATCH`, `PAPER`, `DD`, `PnL`, `Profit Factor`, `spread`, `slippage`, and `bps` may remain in code, logs, or an explicit technical-details section, but must not be the only wording shown to the user.

Use the permanent mappings and score-grade bands in `DESIGN.md`. A numeric score must include a plain-language meaning, for example `전체 시장 분위기: 좋지 않음 (50/100)` rather than `Regime 49.62`.

Korean UI copy must be concise, natural, and operational. Put the user's decision/action before the explanation. Preserve facts and technical meaning while avoiding translationese and repetitive AI patterns.

Avoid habitual phrases such as `~에 대해`, `~을 통해`, `~할 수 있습니다`, `결론적으로`, hype wording, abstract noun chains, and unnecessary defensive explanations. Use consistent terms for the same concept. Button/tab labels stay short enough to remain on one line at supported widths.

## Trading-analysis contract

Keep two dimensions separate internally:

- **Regime**: whether the surrounding market is supportive. User-facing name: `전체 시장 분위기`.
- **Entry**: whether the current asset price/location is attractive. User-facing name: `지금 매수 타이밍`.

Never interpret a high Regime score alone as permission to chase price. Entry/risk guards remain separate.

Multi-asset profiles use a common market model plus asset-specific context. Ticker-only additions may start as `generic_alt`, then GPT may research and refine related sectors/ecosystems/markets in `control/assets.json`.

`ETH/BTC` is a **market reference**, not a KRW tradeable asset in the current engine. Derive and display ETH/BTC relative strength from BTC/ETH market data rather than trying to register it as `KRW-ETH/BTC`.

## Safety and changes

- PAPER mode remains default and mandatory for this workstream.
- Kill switch and risk guards must remain fail-closed.
- Never commit credentials, tokens, private keys, or exchange secrets.
- Never auto-apply code updates once a future live-trading mode is armed.
- Prefer backward-compatible SQLite migrations (`CREATE TABLE IF NOT EXISTS`, additive columns/tables).
- Runtime/database migrations require tests.
- Dashboard mutations require authentication for non-loopback clients.
- Do not loosen remote authentication merely to simplify phone access.
- A persistent Cloudflare named Tunnel may store its local config/credentials only under ignored local runtime paths. Never commit Cloudflare credentials.
- A loopback-only, user-initiated one-tap phone onboarding link may temporarily carry the phone connection code in the URL **fragment** (`#...`) only if it is never sent to the server, never logged, and is immediately removed from the address bar after import. Do not use query strings or paths for secrets.

## QA before considering a unit complete

At minimum:

- Python tests pass.
- Python modules compile.
- Dashboard static smoke checks pass, including the final UX override layer.
- Mobile layout has no obvious horizontal overflow at 360–430 px widths.
- iOS/Safari form fields that receive focus render at >=16 px to avoid browser auto-zoom.
- Primary button labels do not wrap; layout/container adapts instead.
- Repeated cards/panels have stable geometry and do not jump because optional data is missing.
- Live polling does not collapse open disclosures or reset deliberate interactive state.
- Desktop layout works at 1280–1920 px widths.
- Existing Git sync/PAPER operation does not regress.
- Telegram automatic alerts match the current user-approved policy.
- Top-level UI and Telegram alerts do not expose unexplained trading jargon.
- Update the active workstream handoff with completed checks and exact next action.
