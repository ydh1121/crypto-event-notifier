# Viewer Build 35 — Operations Completion

Build 35 closes the remaining system-observability gaps without changing the approved viewer information architecture or weakening the PAPER/READ-ONLY boundary.

## 1. SQLite / Drive backup status

- Read backup state only from the local loopback dashboard.
- Show local backup count, latest backup time and latest file size.
- Show whether rclone is configured/installed and whether the last backup reached the Drive mirror.
- Never publish the local filesystem path or the rclone remote path.
- Backup remains owned by the local `BackupManager`; the Cloudflare Viewer cannot trigger or modify backups.

## 2. Telegram BUY_CANDIDATE status

- Preserve the existing automatic-alert contract: only fresh `BUY_CANDIDATE` action events may generate automatic Telegram messages.
- Track automatic BUY_CANDIDATE delivery count and the last successful delivery time in process memory.
- Show only configuration booleans, delivery counts/times and the alert mode in the external Viewer.
- Never publish the bot token, Chat ID or Telegram error payload containing sensitive values.
- Manual Telegram test remains a local-dashboard operation.

## 3. Phone / remote-access summary

- Read `/api/network` from loopback and publish only sanitized state.
- Show whether the local dashboard is online, Cloudflare tunnel mode/HTTPS state, Tailscale installed/connected state, and whether remote authentication is required.
- Never publish LAN/Tailscale IP addresses, DNS names, tunnel URLs, dashboard connection codes or tokens.
- The external Viewer remains unable to control the PC.

## 4. System UI

The existing System screen keeps the same route and gains six operational cards:

1. Git
2. Cloudflare
3. Warehouse
4. SQLite / Drive Backup
5. Telegram BUY_CANDIDATE
6. Phone / Remote Access

Detailed sidecar diagnostics remain below the cards.

## 5. Checklist reconciliation

`VIEWER_REBUILD_CHECKLIST.md` is updated to reflect work already completed in Builds 28–35, including:

- read-only averaging plans,
- strategy equity / coin performance / coin×strategy,
- overall PAPER equity / drawdown,
- dead Pages UI asset removal,
- Git / Cloudflare / Warehouse / Drive / Telegram / remote-access system diagnostics.

Items still not implemented remain unchecked; in particular Phase 5/6 research, portfolio history, records-event extensions, Phase 7/8 strategy lifecycle screens, GitHub Actions CI detail inside the Viewer, and mobile QA.

## Safety

- PAPER ONLY.
- Cloudflare Pages READ ONLY.
- No live exchange-order API activation.
- No PC control path from Cloudflare.
- No token, Chat ID, local address, DNS name, local path or rclone remote path in the public snapshot.
