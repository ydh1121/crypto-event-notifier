# Viewer Build 34 — Operations Visibility

Build 34 keeps the approved navigation and page structure intact. It deepens the existing System utility page so the owner can diagnose the 24-hour research node without opening PowerShell for routine checks.

## Scope

1. Git status
   - Show current branch, local HEAD and local origin-tracking HEAD.
   - Show whether the two known refs are aligned.
   - Do not fetch or mutate Git from the viewer snapshot path.

2. Cloudflare status
   - Summarize snapshot publishing, market-detail publishing and Pages deployment from the existing research supervisor component results.
   - Show last success, retries, payload size / request counts where available, deployed HEAD, viewer health and viewer URL.
   - No Cloudflare credentials or ingest tokens are exposed.

3. Warehouse status
   - Summarize the local Parquet research warehouse using the existing `warehouse-export` result and warehouse state file.
   - Show exported row totals, tracked tables, latest export and current run result.

4. Telegram readiness
   - Show only configuration booleans: enabled, token configured, chat configured and ready.
   - Never publish the Telegram token or chat ID itself.

5. Component diagnostics
   - Keep the current component list, but expose interval, run count, last success and a small safe result summary.
   - Errors remain visible without exposing secrets.

## Existing asset averaging contract

The Asset page already satisfies the remaining read-only averaging requirement:

- saved averaging plans are read from the private snapshot,
- up to 20 averaging rows can be calculated in the browser,
- browser drafts do not mutate the authoritative SQLite plan,
- local SQLite remains authoritative and configured Drive backup contains the same DB.

Build 34 does not duplicate this feature.

## Safety

- Viewer remains READ ONLY.
- No Git pull/reset/push from Cloudflare.
- No component control actions from Cloudflare.
- No Telegram secrets, Cloudflare secrets or exchange keys in the public snapshot.
- PAPER only; no real orders.
