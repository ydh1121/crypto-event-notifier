# Google Drive backup (one-time)

The runtime database remains local. Google Drive is used as an off-device backup/mirror, not as a live SQLite database.

1. Install rclone from https://rclone.org/downloads/
2. Run `rclone config`
3. Create a Google Drive remote named `gdrive`
4. Keep `.env`: `RCLONE_REMOTE=gdrive:Crypto Auto Trader/backups`
5. In the web dashboard click **백업 실행**.

Each backup creates a consistent SQLite snapshot and mirrors:
- `control/` -> `Crypto Auto Trader/control`
- `dashboard/` -> `Crypto Auto Trader/dashboard`

Do not store Bithumb keys, Telegram token, dashboard token, or `.env` in Drive/GitHub.
