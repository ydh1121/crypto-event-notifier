from __future__ import annotations

import os
import secrets
import sys
import time
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

from b3_trader.cloudflare_pages_deployer import CloudflarePagesDeployer
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


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _force_pages_deploy() -> dict:
    result = CloudflarePagesDeployer().deploy_once(force=True)
    if result.get("status") != "deployed" or not result.get("health_ok"):
        raise RuntimeError(
            f"Pages redeploy failed after secret update: status={result.get('status')} health_ok={result.get('health_ok')}"
        )
    return result


def _publish_until_ready(token: str, timeout_seconds: float = 30.0) -> dict:
    os.environ["CLOUDFLARE_VIEWER_INGEST_TOKEN"] = token
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            result = CloudflareSnapshotPublisher().publish_once()
            if result.get("status") == "published":
                result["rotation_verify_attempts"] = attempt
                return result
            last_error = RuntimeError(f"unexpected publish status: {result.get('status')}")
        except Exception as exc:
            last_error = exc
        time.sleep(min(4.0, 1.0 + attempt * 0.5))
    if last_error:
        raise RuntimeError(f"new ingest token was not accepted after Pages redeploy within {timeout_seconds:.0f}s") from last_error
    raise RuntimeError("new ingest token verification timed out")


def main() -> None:
    values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    project = str(values.get("CLOUDFLARE_VIEWER_PROJECT") or "").strip()
    old_ingest = str(values.get("CLOUDFLARE_VIEWER_INGEST_TOKEN") or "").strip()
    old_owner = _read_text(BOOTSTRAP_PATH)
    if not project:
        raise SystemExit("Cloudflare viewer project is not configured. Run the normal viewer setup first.")
    if not old_ingest:
        raise SystemExit("Local ingest token is missing; refusing rotation because rollback would be unsafe.")
    if not old_owner:
        raise SystemExit("Local owner bootstrap token is missing; refusing rotation because rollback would be unsafe.")

    wrangler = _local_wrangler()
    _ensure_login(wrangler)

    new_ingest = secrets.token_urlsafe(48)
    new_owner = secrets.token_urlsafe(48)

    print("Cloudflare viewer secret rotation")
    print(f"project={project}")
    print("Secret values will not be printed.")

    owner_changed = False
    ingest_changed = False
    pages_redeployed = False
    try:
        _put_secret(wrangler, project, "OWNER_BOOTSTRAP_TOKEN", new_owner)
        owner_changed = True
        _put_secret(wrangler, project, "INGEST_TOKEN", new_ingest)
        ingest_changed = True

        _update_env({"CLOUDFLARE_VIEWER_INGEST_TOKEN": new_ingest})
        _atomic_text(BOOTSTRAP_PATH, new_owner + "\n")
        os.environ["CLOUDFLARE_VIEWER_INGEST_TOKEN"] = new_ingest

        print("Redeploying Pages so the new secrets become active...")
        deploy = _force_pages_deploy()
        pages_redeployed = True
        result = _publish_until_ready(new_ingest)
    except Exception:
        rollback_errors: list[str] = []
        print("Rotation verification failed; restoring previous secrets.")
        if ingest_changed:
            try:
                _put_secret(wrangler, project, "INGEST_TOKEN", old_ingest)
                _update_env({"CLOUDFLARE_VIEWER_INGEST_TOKEN": old_ingest})
                os.environ["CLOUDFLARE_VIEWER_INGEST_TOKEN"] = old_ingest
            except Exception as exc:
                rollback_errors.append(f"INGEST_TOKEN rollback failed: {type(exc).__name__}")
        if owner_changed:
            try:
                _put_secret(wrangler, project, "OWNER_BOOTSTRAP_TOKEN", old_owner)
                _atomic_text(BOOTSTRAP_PATH, old_owner + "\n")
            except Exception as exc:
                rollback_errors.append(f"OWNER_BOOTSTRAP_TOKEN rollback failed: {type(exc).__name__}")

        if not rollback_errors and (ingest_changed or owner_changed or pages_redeployed):
            try:
                print("Redeploying Pages with the restored secrets...")
                _force_pages_deploy()
                _publish_until_ready(old_ingest, timeout_seconds=20.0)
                print("rollback_status=PASS")
            except Exception as exc:
                rollback_errors.append(f"Pages rollback redeploy/verify failed: {type(exc).__name__}")

        if rollback_errors:
            print("WARNING: " + "; ".join(rollback_errors))
            print("Run the normal Cloudflare Pages viewer setup before resuming publishing.")
        raise

    print("rotation_status=PASS")
    print("pages_redeploy=PASS")
    print("ingest_publish_check=PASS")
    print(f"deployed_head={str(deploy.get('head') or '')[:7]}")
    print(f"propagation_attempts={int(result.get('rotation_verify_attempts') or 1)}")
    print("The previous viewer ingest/bootstrap tokens are no longer valid.")


if __name__ == "__main__":
    main()
