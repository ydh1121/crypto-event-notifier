# Local Multi-Asset Trader

Preferred runtime during strategy validation.

## Roles
- Local SQLite: authoritative runtime DB (signals, fills, events)
- Private GitHub: code + non-secret desired state (`control/*.json`)
- Google Drive: off-device SQLite backups + mirrors of `control/` and `dashboard/`
- Cloudflare Pages: optional free static dashboard mirror
- Telegram: strategy/risk/fill notifications
- GPT: edits the private GitHub branch; the local sync agent pulls it. In PAPER mode, code changes trigger an automatic restart through the wrapper.

Secrets are excluded from GitHub/Drive: Bithumb keys, Telegram token, dashboard token and `.env`.

## Start
Double-click `start-trader.bat`.

First run creates `.venv`, installs dependencies, creates `.env`, starts port 8765 and generates `b3_trader/data/dashboard-token.txt`.

PC: `http://127.0.0.1:8765`
Phone same Wi-Fi: `http://<PC-LAN-IP>:8765`
Outside home: use Tailscale Personal rather than router port forwarding.

## Add coins
Enter XRP, SEI, SOL etc in the dashboard. Ticker-only additions start with `generic_alt` context.

For context-aware setup ask GPT, for example: `XRP를 자동매매 시스템에 추가하고 현재 생태계/섹터/관련 코인/외부요인을 조사해서 profile을 보완해.` GPT updates `control/assets.json`; the local process polls GitHub and applies it.

## Telegram
Set locally in `.env`:
`TELEGRAM_ENABLED=true`, `TELEGRAM_TOKEN=...`, `TELEGRAM_CHAT_ID=...`, restart, then use the dashboard test button.

## Google Drive
Configure rclone once using `scripts/setup-drive-backup.md`. Drive is not a live SQLite DB; the process creates consistent snapshots before upload.

## Cloudflare Pages
The `dashboard/` directory is static and can be connected to Cloudflare Pages Free.
Framework: None. Build command: blank. Output directory: `dashboard`.
When hosted there, use **연결 설정** to point the dashboard at the reachable local API, preferably a Tailscale address.
