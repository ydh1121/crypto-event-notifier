from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def _same_path(a: str, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except OSError:
        return False


if os.name == "nt" and VENV_PYTHON.exists() and not _same_path(sys.executable, VENV_PYTHON):
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]])

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import dotenv_values

from b3_trader.cloudflare_pages_setup import (
    BOOTSTRAP_PATH,
    ENV_PATH,
    VIEWER_DIR,
    _atomic_text,
    _ensure_login,
    _local_wrangler,
    _run,
    _update_env,
)
from b3_trader.cloudflare_snapshot_publisher import CloudflareSnapshotPublisher


def _put_secret(wrangler: str, project: str, name: str, value: str) -> None:
    _run(
        [wrangler, "pages", "secret", "put", name, "--project-name", project],
        cwd=VIEWER_DIR,
        timeout=120.0,
        capture=True,
        input_text=value + "\n",
    )


def main() -> None:
    values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    project = str(values.get("CLOUDFLARE_VIEWER_PROJECT") or "").strip()
    old_ingest = str(values.get("CLOUDFLARE_VIEWER_INGEST_TOKEN") or "").strip()
    if not project:
        raise SystemExit("Cloudflare viewer project is not configured. Run the normal viewer setup first.")
    if not old_ingest:
        raise SystemExit("Local ingest token is missing; refusing rotation because rollback would be unsafe.")

    wrangler = _local_wrangler()
    _ensure_login(wrangler)

    new_ingest = secrets.token_urlsafe(48)
    new_owner = secrets.token_urlsafe(48)

    print("Cloudflare viewer secret rotation")
    print(f"project={project}")
    print("Secret values will not be printed.")

    # OWNER_BOOTSTRAP_TOKEN is independent of the live publisher, so rotate it first.
    _put_secret(wrangler, project, "OWNER_BOOTSTRAP_TOKEN", new_owner)

    ingest_changed = False
    try:
        _put_secret(wrangler, project, "INGEST_TOKEN", new_ingest)
        ingest_changed = True
        _update_env({"CLOUDFLARE_VIEWER_INGEST_TOKEN": new_ingest})
        _atomic_text(BOOTSTRAP_PATH, new_owner + "\n")

        result = CloudflareSnapshotPublisher().publish_once()
        if result.get("status") != "published":
            raise RuntimeError(f"post-rotation publish verification failed: {result.get('status')}")
    except Exception:
        if ingest_changed:
            try:
                _put_secret(wrangler, project, "INGEST_TOKEN", old_ingest)
                _update_env({"CLOUDFLARE_VIEWER_INGEST_TOKEN": old_ingest})
            except Exception:
                print("WARNING: automatic ingest-token rollback also failed. Run the viewer setup before resuming publishing.")
        raise

    print("rotation_status=PASS")
    print("ingest_publish_check=PASS")
    print("The previous viewer ingest/bootstrap tokens are no longer valid.")


if __name__ == "__main__":
    main()
