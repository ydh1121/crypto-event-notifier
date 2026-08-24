from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWER_DIR = REPO_ROOT / "cloudflare-pages"
LOCAL_CONFIG_PATH = VIEWER_DIR / "wrangler.jsonc"
STATE_PATH = REPO_ROOT / "b3_trader/data/research-platform/cloudflare-pages-deploy-state.json"
DEFAULT_PROJECT = "crypto-paper-viewer-ydh1121"
DEFAULT_DATABASE = "crypto-paper-viewer"
DEFAULT_BRANCH = "b3-auto-trader-phase1"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _tool(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"required command not found: {name}")
    return resolved


def _local_wrangler() -> str:
    filename = "wrangler.cmd" if os.name == "nt" else "wrangler"
    path = VIEWER_DIR / "node_modules" / ".bin" / filename
    if not path.exists():
        raise RuntimeError("local Wrangler is missing; run npm install in cloudflare-pages")
    return str(path)


def _run(
    args: list[str],
    *,
    cwd: Path,
    timeout: float = 180.0,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        input=input_text,
        capture_output=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        label = " ".join(Path(args[0]).name if index == 0 else part for index, part in enumerate(args[:4]))
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}")
    return completed


def _git(*args: str) -> str:
    completed = _run([_tool("git"), *args], cwd=REPO_ROOT, timeout=30.0)
    return completed.stdout.strip()


class CloudflarePagesDeployer:
    """Deploys only the read-only Pages viewer from the 24/7 Windows research node.

    Wrangler authentication is kept by Wrangler on the local machine. No Cloudflare
    API token is read from the trader or committed to Git. This component cannot
    place orders or mutate PAPER strategy state.
    """

    def __init__(self) -> None:
        load_dotenv(REPO_ROOT / ".env", override=True)
        self.project = os.getenv("CLOUDFLARE_VIEWER_PROJECT", DEFAULT_PROJECT).strip() or DEFAULT_PROJECT
        self.database = os.getenv("CLOUDFLARE_VIEWER_D1", DEFAULT_DATABASE).strip() or DEFAULT_DATABASE
        self.branch = os.getenv("GIT_SYNC_BRANCH", DEFAULT_BRANCH).strip() or DEFAULT_BRANCH

    def _viewer_url(self) -> str:
        ingest = os.getenv("CLOUDFLARE_VIEWER_INGEST_URL", "").strip()
        if ingest.endswith("/api/ingest"):
            return ingest[: -len("/api/ingest")]
        return f"https://{self.project}.pages.dev"

    def _relevant_changes(self, previous_head: str, head: str) -> list[str]:
        if not previous_head or previous_head == head:
            return []
        try:
            output = _git(
                "diff",
                "--name-only",
                f"{previous_head}..{head}",
                "--",
                "cloudflare-pages",
                ".github/workflows/deploy-pages-viewer.yml",
            )
        except Exception:
            return ["cloudflare-pages"]
        return [line.strip() for line in output.splitlines() if line.strip()]

    def deploy_once(self, *, force: bool = False) -> dict[str, Any]:
        load_dotenv(REPO_ROOT / ".env", override=True)
        self.project = os.getenv("CLOUDFLARE_VIEWER_PROJECT", self.project).strip() or self.project
        self.database = os.getenv("CLOUDFLARE_VIEWER_D1", self.database).strip() or self.database
        started = time.time()
        if not VIEWER_DIR.exists() or not LOCAL_CONFIG_PATH.exists():
            return {
                "status": "not_configured",
                "configured": False,
                "viewer_url": self._viewer_url(),
                "elapsed_seconds": round(time.time() - started, 3),
            }

        try:
            head = _git("rev-parse", "HEAD")
        except Exception as exc:
            raise RuntimeError("cannot read local Git HEAD") from exc

        state = _read_json(STATE_PATH)
        previous_head = str(state.get("deployed_head") or "")
        changes = self._relevant_changes(previous_head, head) if previous_head else ["first-deploy"]
        if not force and previous_head == head:
            return {
                "status": "up_to_date",
                "configured": True,
                "head": head,
                "viewer_url": self._viewer_url(),
                "deployed_at": float(state.get("deployed_at") or 0.0),
                "elapsed_seconds": round(time.time() - started, 3),
            }
        if not force and previous_head and not changes:
            state.update({"deployed_head": head, "checked_at": time.time()})
            _atomic_json(STATE_PATH, state)
            return {
                "status": "no_viewer_changes",
                "configured": True,
                "head": head,
                "viewer_url": self._viewer_url(),
                "elapsed_seconds": round(time.time() - started, 3),
            }

        npm = _tool("npm")
        node = _tool("node")
        child_env = dict(os.environ)
        child_env["CI"] = "true"
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"
        _run([npm, "install", "--no-audit", "--no-fund"], cwd=VIEWER_DIR, timeout=300.0, env=child_env)
        wrangler = _local_wrangler()
        _run([npm, "run", "typecheck"], cwd=VIEWER_DIR, timeout=180.0, env=child_env)
        _run([node, "--check", "public/app.js"], cwd=VIEWER_DIR, timeout=60.0, env=child_env)

        _run(
            [
                wrangler,
                "d1",
                "migrations",
                "apply",
                self.database,
                "--remote",
            ],
            cwd=VIEWER_DIR,
            timeout=180.0,
            input_text="y\n",
            env=child_env,
        )
        _run(
            [
                wrangler,
                "pages",
                "deploy",
                "public",
                "--project-name",
                self.project,
                "--branch",
                self.branch,
                "--commit-hash",
                head,
                "--commit-dirty=true",
            ],
            cwd=VIEWER_DIR,
            timeout=300.0,
            env=child_env,
        )

        viewer_url = self._viewer_url()
        response = requests.get(f"{viewer_url}/api/health", timeout=20.0, headers={"Cache-Control": "no-cache"})
        response.raise_for_status()
        health = response.json() if response.content else {}
        now = time.time()
        payload = {
            "version": 1,
            "configured": True,
            "project": self.project,
            "database": self.database,
            "viewer_url": viewer_url,
            "deployed_head": head,
            "deployed_at": now,
            "checked_at": now,
            "changed_files": changes[:40],
            "health_ok": bool(isinstance(health, dict) and health.get("ok")),
        }
        _atomic_json(STATE_PATH, payload)
        return {
            "status": "deployed",
            "configured": True,
            "head": head,
            "viewer_url": viewer_url,
            "changed_files": len(changes),
            "health_ok": payload["health_ok"],
            "elapsed_seconds": round(time.time() - started, 3),
        }


def main() -> None:
    result = CloudflarePagesDeployer().deploy_once(force="--force" in os.sys.argv)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
