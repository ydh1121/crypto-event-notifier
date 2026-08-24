# Research Platform v1 handoff

## Active state

This follow-on workstream is now active for low-risk research/viewer infrastructure while `dashboard-v1` stabilization continues in parallel.

Hard boundary: **PAPER-only**. No live exchange execution, private exchange endpoints or automatic promotion of external code.

## Current implemented slice

### 24/7 local research node

The Windows PC is the long-running research server.

Operational roles:
- local SQLite: authoritative PAPER/runtime state
- Parquet + DuckDB: secondary analytical warehouse
- research supervisor: non-trading sidecar
- private GitHub: source/specs/reference catalog
- Google Drive: future backup/export only
- Cloudflare Pages/D1: Phase 2 viewer/login layer, not yet deployed

### Research supervisor

Files:
- `b3_trader/research_supervisor.py`
- `b3_trader/research_control.py`
- `b3_trader/research_warehouse.py`
- `b3_trader/reference_components.py`

Managed periodic components:
- `warehouse-export` — default 5 minutes
- `reference-version-watch` — default 6 hours

The supervisor reloads local control state live. Component enable/disable changes do not restart the trader. `지금 실행` increments a run nonce and wakes that component for an immediate cycle.

Safety:
- cannot place orders
- cannot modify PAPER profiles
- cannot auto-promote/download/execute reference repositories
- component failure is isolated from the trader

Local runtime files:
- `b3_trader/data/research-platform/components.json`
- `b3_trader/data/research-platform/status.json`
- `b3_trader/data/research-platform/supervisor.log`
- `b3_trader/data/research-platform/reference-components-state.json`
- `b3_trader/data/research-warehouse/`

All remain ignored/local.

### Local research control API

Files:
- `b3_trader/research_routes.py`
- integrated into `b3_trader/local_app.py`

Endpoints:
- `GET /api/research/components` — authenticated read status
- `PATCH /api/research/components/{name}` — loopback/local PC only
- `POST /api/research/components/{name}/run` — loopback/local PC only

Remote/Tunnel clients can view component status but cannot mutate it.

### Dashboard component manager

Files:
- `dashboard/research-components.js`
- `dashboard/research-components.css`
- loaded by `dashboard/research-capital.js`

Settings now gets a full-width `데이터 수집 · 연구 구성요소` panel showing:
- research supervisor online/offline
- per-component health
- interval
- last success
- latest export summary
- external repo update/failure counts
- local-only `켜기/끄기`
- local-only `지금 실행`

The visible build pill is patched to `UI 2026.08.24-9` when this module loads.

## Validation

CI must cover:
- Python tests
- Python module compile
- dashboard JS syntax/smoke including `research-capital.js` and `research-components.js`
- Cloudflare typecheck

New unit coverage:
- local component control persistence/bounds
- run nonce increment
- research status/reference summary

## Current next action

Do not wait 24 hours before continuing.

Proceed to **Phase 2 — Cloudflare Pages viewer scaffold**:
1. create a separate Pages/Functions project so the existing Cloudflare Container experiment is untouched,
2. serve a read-first dashboard at free `*.pages.dev`,
3. add authenticated snapshot ingestion from the 24/7 PC,
4. add D1 owner/viewer/invite/session schema,
5. keep all remote actions read-only,
6. add local outbound snapshot publisher,
7. prepare GitHub -> Pages deployment configuration.

Actual Cloudflare project creation/binding/deployment may require the user's Cloudflare account session/credentials; source scaffolding can be completed in Git first.

## Parallel observations that no longer block Phase 2

- Photo-eBook navigation acceptance on PC/iPhone
- Chrome long-run responsiveness
- Git auto-sync long-run behavior
- Parquet growth/day and retention sizing

These remain tracked but should not stall infrastructure development.
