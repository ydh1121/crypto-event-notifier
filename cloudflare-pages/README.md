# Crypto Auto Trader — Cloudflare Pages viewer

This directory is a **separate read-only web viewer** for the 24/7 Windows research node.

It does not replace or modify the existing `cloudflare/` Container experiment.

## Purpose

- free stable `*.pages.dev` address
- owner/viewer login with long-lived secure session cookie
- owner-created invite links
- optional per-user permission to see manually entered holdings
- outbound-only PC snapshot publishing
- Git changes can be deployed by the 24/7 PC after local Git sync
- no remote trading controls
- no exchange API secrets, SQLite database or local admin token uploaded to Pages

## Recommended setup: local Wrangler bridge

The repository does not currently require Cloudflare API credentials in GitHub.

On the Windows research PC, after the latest branch is synced, run once:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-cloudflare-pages-viewer.ps1
```

The setup performs these steps without printing secrets:

1. validates the Pages viewer code,
2. opens Wrangler browser OAuth if Cloudflare is not already authenticated,
3. creates or reuses a Pages project,
4. creates or reuses the D1 database,
5. binds D1 as `DB` through a local ignored Wrangler config,
6. applies D1 migrations,
7. creates the ingest + first-owner bootstrap secrets,
8. stores the ingest configuration only in local `.env`,
9. stores the first-owner bootstrap key only under ignored `b3_trader/data/`, and copies it to the Windows clipboard when possible,
10. deploys and verifies `/api/health`,
11. enables snapshot publishing and local Pages auto-deploy components.

Default project name:

`crypto-paper-viewer-ydh1121.pages.dev`

If that name cannot be created in the Cloudflare account, setup automatically tries a short unique suffix and records the resulting stable URL locally.

After the one-time setup, the data/code path is:

```text
GitHub branch update
  -> local GitAutoSync
  -> cloudflare-pages-deploy component detects viewer changes
  -> Pages deploy

Windows PAPER engine
  -> cloudflare-snapshot-publish every ~20s
  -> D1 latest snapshot
  -> authenticated pages.dev viewer
```

The auto-deployer checks the Git HEAD every ~30 seconds but only runs npm/typecheck/migration/deploy when `cloudflare-pages/**` actually changed. It does not restart or control the PAPER engine.

## D1 schema

`migrations/0001_init.sql` contains:

- `users`
- `invites`
- `sessions`
- `snapshots`
- `audit_log`

The first owner is created from the site with the local bootstrap key. After an owner already exists, the bootstrap API refuses creating another owner from that key.

## Local PC publisher

The research supervisor component is named `cloudflare-snapshot-publish`.

The setup script writes these values only to the PC's ignored `.env`:

```env
CLOUDFLARE_VIEWER_PROJECT=<project-name>
CLOUDFLARE_VIEWER_D1=<database-name>
CLOUDFLARE_VIEWER_INGEST_URL=https://<project>.pages.dev/api/ingest
CLOUDFLARE_VIEWER_INGEST_TOKEN=<local secret>
CLOUDFLARE_PUBLISH_PRIVATE_HOLDINGS=true
```

Raw SQLite is never uploaded. The published private section contains only a compact manual-holdings snapshot. It is returned only to:

- the owner, or
- viewers created with `내 자산정보도 보이기` permission.

Set `CLOUDFLARE_PUBLISH_PRIVATE_HOLDINGS=false` at any time to stop sending manual holdings/average price while continuing public PAPER snapshot publishing.

## Security boundary

The Pages viewer has no API route for:

- pausing/resuming the trader,
- kill switch,
- changing PAPER strategy settings,
- editing manual holdings,
- exchange orders,
- exchange credentials,
- local Git control.

The only machine-to-cloud write is `POST /api/ingest`, protected by the ingest secret.

## Optional GitHub Actions deployment

`.github/workflows/deploy-pages-viewer.yml` can deploy directly from GitHub if repository secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` are configured later.

If those GitHub secrets are absent, the workflow still validates the viewer and exits successfully; deployment stays delegated to the local Wrangler bridge. This avoids storing a Cloudflare API token in GitHub solely for this personal viewer.

## Manual Cloudflare alternative

If the local setup bridge is not used, the equivalent Pages settings are:

- production branch: `b3-auto-trader-phase1`
- root directory: `cloudflare-pages`
- framework preset: None
- build command: `npm run build`
- build output directory: `public`
- D1 binding: `DB`
- secrets: `INGEST_TOKEN`, `OWNER_BOOTSTRAP_TOKEN`

Google Drive remains backup/export only and is not the live web database.
