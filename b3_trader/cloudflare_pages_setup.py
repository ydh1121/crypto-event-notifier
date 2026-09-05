from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from .cloudflare_pages_deployer import (
    DEFAULT_DATABASE,
    DEFAULT_PROJECT,
    LOCAL_CONFIG_PATH,
    REPO_ROOT,
    VIEWER_DIR,
    CloudflarePagesDeployer,
)
from .research_control import patch_component

BOOTSTRAP_PATH = REPO_ROOT / "b3_trader/data/research-platform/cloudflare-viewer-bootstrap.txt"
SETUP_STATE_PATH = REPO_ROOT / "b3_trader/data/research-platform/cloudflare-viewer-setup.json"
ENV_PATH = REPO_ROOT / ".env"


def _command(name: str) -> str:
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
    timeout: float = 300.0,
    capture: bool = True,
    input_text: str | None = None,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        input=input_text,
        capture_output=capture,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0 and not allow_failure:
        label = " ".join(Path(part).name if index == 0 else part for index, part in enumerate(args[:4]))
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}")
    return completed


def _json_output(args: list[str], *, cwd: Path) -> Any:
    completed = _run(args, cwd=cwd, timeout=120.0, capture=True)
    text = completed.stdout.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Wrangler returned non-JSON output") from exc


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _update_env(values: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    remaining = dict(values)
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    if remaining:
        if output and output[-1].strip():
            output.append("")
        output.append("# ===== Cloudflare Pages read-only viewer =====")
        for key, value in remaining.items():
            output.append(f"{key}={value}")
    _atomic_text(ENV_PATH, "\n".join(output).rstrip() + "\n")


def _copy_to_clipboard(value: str) -> bool:
    if os.name != "nt":
        return False
    clip = shutil.which("clip.exe") or shutil.which("clip")
    if not clip:
        return False
    try:
        completed = subprocess.run([clip], input=value, text=True, timeout=10.0, check=False)
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _ensure_login(wrangler: str) -> None:
    whoami = _run([wrangler, "whoami"], cwd=VIEWER_DIR, timeout=60.0, capture=True, allow_failure=True)
    if whoami.returncode == 0:
        return
    print("Cloudflare 로그인이 필요합니다. 브라우저 인증 창을 엽니다.")
    login = _run([wrangler, "login"], cwd=VIEWER_DIR, timeout=600.0, capture=False, allow_failure=True)
    if login.returncode != 0:
        raise RuntimeError("Cloudflare browser login was not completed")
    verify = _run([wrangler, "whoami"], cwd=VIEWER_DIR, timeout=60.0, capture=True, allow_failure=True)
    if verify.returncode != 0:
        raise RuntimeError("Cloudflare login verification failed")


def _pages_projects(wrangler: str) -> list[dict[str, Any]]:
    value = _json_output([wrangler, "pages", "project", "list", "--json"], cwd=VIEWER_DIR)
    return value if isinstance(value, list) else []


def _d1_databases(wrangler: str) -> list[dict[str, Any]]:
    value = _json_output([wrangler, "d1", "list", "--json"], cwd=VIEWER_DIR)
    return value if isinstance(value, list) else []


def _ensure_project(wrangler: str, desired: str) -> str:
    projects = _pages_projects(wrangler)
    if any(str(row.get("name") or row.get("Project Name") or "") == desired for row in projects):
        return desired
    candidates = [desired, f"{desired}-{secrets.token_hex(2)}", f"{desired}-{secrets.token_hex(3)}"]
    for candidate in candidates:
        created = _run(
            [wrangler, "pages", "project", "create", candidate, "--production-branch", "b3-auto-trader-phase1"],
            cwd=VIEWER_DIR,
            timeout=120.0,
            capture=True,
            allow_failure=True,
        )
        if created.returncode == 0:
            return candidate
    raise RuntimeError("Cloudflare Pages project creation failed")


def _ensure_database(wrangler: str, desired: str) -> tuple[str, str]:
    databases = _d1_databases(wrangler)
    for row in databases:
        if str(row.get("name") or "") == desired:
            database_id = str(row.get("uuid") or row.get("id") or "")
            if database_id:
                return desired, database_id
    created = _run(
        [wrangler, "d1", "create", desired, "--location", "apac"],
        cwd=VIEWER_DIR,
        timeout=120.0,
        capture=True,
        allow_failure=True,
    )
    if created.returncode != 0:
        raise RuntimeError("Cloudflare D1 creation failed")
    databases = _d1_databases(wrangler)
    for row in databases:
        if str(row.get("name") or "") == desired:
            database_id = str(row.get("uuid") or row.get("id") or "")
            if database_id:
                return desired, database_id
    raise RuntimeError("Cloudflare D1 database id could not be resolved")


def _write_wrangler_config(project: str, database: str, database_id: str) -> None:
    payload = {
        "name": project,
        "pages_build_output_dir": "./public",
        "compatibility_date": "2026-08-24",
        "d1_databases": [
            {
                "binding": "DB",
                "database_name": database,
                "database_id": database_id,
                "migrations_dir": "migrations",
            }
        ],
    }
    _atomic_text(LOCAL_CONFIG_PATH, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _existing_local_secret(key: str) -> str:
    values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    return str(values.get(key) or "").strip()


def _secret_value(path: Path, fallback_bytes: int = 32) -> str:
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    return secrets.token_urlsafe(fallback_bytes)


def setup() -> dict[str, Any]:
    npm = _command("npm")
    _command("node")
    if not VIEWER_DIR.exists():
        raise RuntimeError("cloudflare-pages directory is missing; sync Git first")

    print("1/6 Cloudflare Pages viewer 코드를 검사합니다.")
    _run([npm, "install", "--no-audit", "--no-fund"], cwd=VIEWER_DIR, timeout=300.0, capture=False)
    wrangler = _local_wrangler()
    _run([npm, "run", "typecheck"], cwd=VIEWER_DIR, timeout=180.0, capture=False)

    print("2/6 Cloudflare 계정 연결을 확인합니다.")
    _ensure_login(wrangler)

    desired_project = _existing_local_secret("CLOUDFLARE_VIEWER_PROJECT") or DEFAULT_PROJECT
    desired_database = _existing_local_secret("CLOUDFLARE_VIEWER_D1") or DEFAULT_DATABASE
    print("3/6 무료 pages.dev 프로젝트와 D1을 준비합니다.")
    project = _ensure_project(wrangler, desired_project)
    database, database_id = _ensure_database(wrangler, desired_database)
    _write_wrangler_config(project, database, database_id)

    ingest_token = _existing_local_secret("CLOUDFLARE_VIEWER_INGEST_TOKEN") or secrets.token_urlsafe(36)
    owner_token = _secret_value(BOOTSTRAP_PATH, 36)
    print("4/6 로그인/수집용 보안 키와 D1 스키마를 설정합니다.")
    _run(
        [wrangler, "pages", "secret", "put", "INGEST_TOKEN", "--project-name", project],
        cwd=VIEWER_DIR,
        timeout=120.0,
        capture=True,
        input_text=ingest_token + "\n",
    )
    _run(
        [wrangler, "pages", "secret", "put", "OWNER_BOOTSTRAP_TOKEN", "--project-name", project],
        cwd=VIEWER_DIR,
        timeout=120.0,
        capture=True,
        input_text=owner_token + "\n",
    )
    _run(
        [wrangler, "d1", "migrations", "apply", database, "--remote"],
        cwd=VIEWER_DIR,
        timeout=180.0,
        capture=True,
        input_text="y\n",
    )

    viewer_url = f"https://{project}.pages.dev"
    _update_env(
        {
            "CLOUDFLARE_VIEWER_PROJECT": project,
            "CLOUDFLARE_VIEWER_D1": database,
            "CLOUDFLARE_VIEWER_INGEST_URL": f"{viewer_url}/api/ingest",
            "CLOUDFLARE_VIEWER_INGEST_TOKEN": ingest_token,
            "CLOUDFLARE_PUBLISH_PRIVATE_HOLDINGS": "true",
        }
    )
    _atomic_text(BOOTSTRAP_PATH, owner_token + "\n")

    print("5/6 첫 웹 버전을 배포하고 상태를 확인합니다.")
    deploy_result = CloudflarePagesDeployer().deploy_once(force=True)
    if deploy_result.get("status") != "deployed" or not deploy_result.get("health_ok"):
        raise RuntimeError("Pages viewer deployment health check failed")

    patch_component("cloudflare-snapshot-publish", enabled=True, run_now=True)
    patch_component("cloudflare-pages-deploy", enabled=True, run_now=False)
    setup_state = {
        "version": 1,
        "configured_at": time.time(),
        "project": project,
        "database": database,
        "database_id": database_id,
        "viewer_url": viewer_url,
        "private_holdings_enabled": True,
        "read_only": True,
    }
    _atomic_json(SETUP_STATE_PATH, setup_state)

    copied = _copy_to_clipboard(owner_token)
    print("6/6 완료했습니다.")
    print(f"Viewer: {viewer_url}")
    print("관리자 생성 키 값은 콘솔에 출력하지 않았습니다.")
    print(f"관리자 생성 키 로컬 파일: {BOOTSTRAP_PATH.relative_to(REPO_ROOT)}")
    if copied:
        print("관리자 생성 키를 Windows 클립보드에 복사했습니다. 첫 관리자 생성 화면에서 붙여넣으면 됩니다.")
    else:
        print("첫 관리자 생성 시 위 로컬 파일의 값을 직접 복사하세요. 채팅에는 붙여넣지 마세요.")
    print("로그인한 owner와 권한을 받은 viewer만 실제 보유자산 스냅샷을 볼 수 있습니다.")
    try:
        webbrowser.open(viewer_url)
    except Exception:
        pass
    return setup_state


def main() -> None:
    try:
        setup()
    except KeyboardInterrupt:
        print("설정이 취소되었습니다.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"Cloudflare Pages 설정 실패: {type(exc).__name__}: {exc}")
        print("보안 키 값은 출력하지 않았습니다.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
