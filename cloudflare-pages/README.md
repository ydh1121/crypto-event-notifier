# Crypto Auto Trader — Cloudflare Pages viewer

This directory is a **separate read-only web viewer** for the 24/7 Windows research node.

It does not replace or modify the existing `cloudflare/` Container experiment.

## Purpose

- free stable `*.pages.dev` address
- GitHub push -> Cloudflare Pages deployment
- owner/viewer login with long-lived secure session cookie
- owner-created invite links
- optional per-user permission to see manually entered holdings
- outbound-only PC snapshot publishing
- no remote trading controls
- no exchange API secrets, SQLite database or local admin token uploaded to Pages

## Cloudflare resources

Create:

1. one Cloudflare Pages project connected to this private GitHub repository,
2. one D1 database,
3. Pages Functions D1 binding named `DB`,
4. encrypted secret `INGEST_TOKEN`,
5. encrypted secret `OWNER_BOOTSTRAP_TOKEN`,
6. optional environment variable `SESSION_DAYS` (default 30, max 90).

### Pages Git settings

Use:

- project name: your choice; this becomes `<project>.pages.dev`
- production branch: `b3-auto-trader-phase1` while this PR remains the active test branch
- root directory: `cloudflare-pages`
- framework preset: None
- build command: `npm run build`
- build output directory: `public`

Cloudflare Pages supports private GitHub repositories and deploys production-branch pushes automatically.

## D1 migration

Run `migrations/0001_init.sql` against the D1 database, then bind that database to the Pages project as `DB` for both production and preview when needed.

The schema contains:

- `users`
- `invites`
- `sessions`
- `snapshots`
- `audit_log`

## First owner

Set `OWNER_BOOTSTRAP_TOKEN` to a strong random value in Cloudflare Pages secrets.

Open the site, choose `처음 관리자 계정 만들기`, enter that bootstrap key once and create the owner account.

After the owner exists, `/api/auth/bootstrap` refuses a second owner bootstrap even if the secret is known.

## Local PC publisher

The local research supervisor has a disabled-by-default component named `cloudflare-snapshot-publish`.

Add these only to the PC's local `.env`:

```env
CLOUDFLARE_VIEWER_INGEST_URL=https://<project>.pages.dev/api/ingest
CLOUDFLARE_VIEWER_INGEST_TOKEN=<same value as Cloudflare INGEST_TOKEN>
CLOUDFLARE_PUBLISH_PRIVATE_HOLDINGS=false
```

Then restart once so the research supervisor receives the new environment, open local Settings and turn on `웹 상태판 데이터 보내기`.

The default publish interval is 20 seconds and can be controlled locally through the research component manager.

### Manual holdings privacy

`CLOUDFLARE_PUBLISH_PRIVATE_HOLDINGS=false` is the default.

When it is `true`, only the compact manual-holdings snapshot is sent; the raw local SQLite database is never uploaded. The Pages API serves that private snapshot only to:

- the owner, or
- viewers created with `내 자산정보도 보이기` permission.

## Security boundary

The Pages viewer has no API route for:

- pausing/resuming the trader,
- kill switch,
- changing PAPER strategy settings,
- editing manual holdings,
- exchange orders,
- exchange credentials,
- local Git control.

The only machine-to-cloud write is `POST /api/ingest`, protected by `INGEST_TOKEN`.

## Local checks

```bash
cd cloudflare-pages
npm install
npm run typecheck
```

Cloudflare account-side project creation, D1 binding and secrets are intentionally not committed to Git.
