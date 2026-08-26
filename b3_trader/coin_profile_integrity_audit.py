from __future__ import annotations

import json
import os

import requests
from dotenv import load_dotenv


def _endpoint() -> tuple[str, str]:
    load_dotenv(override=True)
    ingest = os.getenv("CLOUDFLARE_VIEWER_INGEST_URL", "").strip()
    token = os.getenv("CLOUDFLARE_VIEWER_INGEST_TOKEN", "").strip()
    if not ingest or not token:
        return "", ""
    root = ingest[: -len("/api/ingest")] if ingest.endswith("/api/ingest") else ingest.rstrip("/")
    return root + "/api/coin-profile-integrity-audit", token


def run() -> dict:
    url, token = _endpoint()
    if not url or not token:
        return {"ok": False, "configured": False, "error": "Cloudflare ingest is not configured"}
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=45)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "configured": True, "error": f"{type(exc).__name__}: {exc}"}
    return payload if isinstance(payload, dict) else {"ok": False, "configured": True, "error": "invalid response"}


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
