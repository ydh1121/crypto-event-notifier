# B3 trader on Cloudflare Containers

This directory deploys the existing Python B3 paper-trading process as a single Cloudflare Container.

## Why Containers

The trader keeps outbound Bithumb WebSocket connections and runs continuously, so a normal short-lived Worker is not a good fit. Cloudflare Containers can run the Python process unchanged. A one-minute Cron Trigger calls `captureCheckpoint()`, which both keeps the singleton container active and copies the latest paper-trading checkpoint into the Container Durable Object's persistent SQLite storage.

Container disk itself is ephemeral. The local SQLite journal is therefore treated as a fast runtime journal, while minute checkpoints survive container restarts in Durable Object storage.

## Safety

- `LIVE_TRADING_ENABLED=false` is baked into the image.
- The container currently runs PAPER mode only.
- No Bithumb API key is required for this deployment.
- `/status`, `/history`, and `/capture` require `ADMIN_TOKEN`.
- `/ready` and `/health` are public operational endpoints and do not expose API secrets.

## Deploy

Cloudflare Containers require the Workers Paid plan.

From this directory:

```bash
npm install
npx wrangler secret put ADMIN_TOKEN
npm run typecheck
npm run deploy
```

After deployment, the Cron Trigger will start the `b3-singleton` instance within about one minute. Hitting `/health` also starts/routes to the singleton.

Check:

```bash
curl https://<worker>.workers.dev/health
curl -H "Authorization: Bearer <ADMIN_TOKEN>" \
  https://<worker>.workers.dev/status
```

## Future live pilot

Do not add Bithumb credentials until the paper forward-test and execution-safety gates are accepted. When that phase is approved, store credentials as Cloudflare Worker Secrets and pass only the minimum required variables into the Container at start time. Do not enable withdrawal permissions on the Bithumb API key.
