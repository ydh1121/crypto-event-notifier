# Dashboard v1 handoff

## Current phase

Phase 4 continuation: local multi-asset PAPER engine + operational dashboard redesign/analytics + secure phone access.

## User-approved scope

Proceed through dashboard redesign, charts/analytics, forward-test persistence, Telegram operational alerts, multi-asset context UI, Git/Drive backup flow, and phone external access.

Do **not** build real-money execution in this workstream. Live execution is a future separate Work/workstream.

## Runtime that already works

- Local FastAPI/Uvicorn server on port 8765
- loopback dashboard authentication without stale-token lockout
- remote/LAN clients require Dashboard token
- B3 live market analysis in PAPER mode
- Regime/Entry/context scoring
- Bithumb/OKX public market inputs
- PAPER buy/risk-off paths and execution guards
- SQLite journal
- GitHub auto-sync on branch `b3-auto-trader-phase1`
- Telegram local configuration + successful test message
- ticker-based multi-asset registry

## Design baseline

Primary approved reference: `ydh1121/Photo-eBook` current UI and its `AGENTS.md`, `UI_REGRESSION_SPEC.md`, core tokens/layout/components.

Permanent dashboard design rules now live in root `DESIGN.md`. Restart/session rules live in root `AGENTS.md`.

Reference principles distilled from:

- emilkowalski/skills: motion/UI detail discipline
- meliwat/awesome-ios-design-md: explicit design-system specs for agents
- VoltAgent/awesome-design-md Apple spec: restrained product hierarchy and structural spacing
- leonxlnx/taste-skill / tastesmd: audit hierarchy/spacing before decoration; avoid generic AI UI
- DaleSeo/korean-skills + KatFishNet reference: natural Korean, translationese/AI-pattern avoidance
- user-provided GitHub topic/organization references for broader UI/code patterns

Do not copy third-party product identity or large chunks of source text; apply principles through the project-specific `DESIGN.md`.

## Files added in this workstream

- `AGENTS.md`
- `DESIGN.md`
- `docs/workstreams/dashboard-v1/TASKS.md`
- `docs/workstreams/dashboard-v1/HANDOFF.md`

## Active task

`B. Dashboard information architecture and visual redesign`

## Exact next action

1. Extend `TradeJournal` with portfolio snapshot/history/performance queries.
2. Make `MultiPaperPortfolio` restore from journal fills after restart.
3. Record portfolio snapshots from `MultiAssetEngine`.
4. Expose analytics/history/network APIs from `local_app.py`.
5. Replace `dashboard/index.html`, `dashboard/styles.css`, and `dashboard/app.js` with the new 5-view responsive dashboard and dependency-light charts.
6. Add Tailscale/LAN network status + setup script.
7. Run/update tests and CI.
8. Update TASKS/HANDOFF after each verified unit.

## Safety constraints

- Keep PAPER-only behavior.
- Keep `LIVE_TRADING_ENABLED=false` and do not add live order execution.
- Never commit local tokens/secrets.
- Do not expose port 8765 publicly; Tailscale/LAN only.
- Preserve remote bearer-token authentication.

## Branch / PR

Work continues on `b3-auto-trader-phase1`, existing Draft PR #1. Do not merge unless the user explicitly requests it.
