from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

DEFAULT_CATALOG = Path("control/reference-components.json")
DEFAULT_STATE = Path("b3_trader/data/research-platform/reference-components-state.json")
USER_AGENT = "crypto-auto-trader-research/1.0"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


def _repo_slug(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"invalid GitHub repository URL: {url}")
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"{owner}/{repo}"


class ReferenceComponentWatcher:
    """Checks upstream GitHub versions without downloading or executing them."""

    def __init__(self, catalog_path: Path = DEFAULT_CATALOG, state_path: Path = DEFAULT_STATE) -> None:
        self.catalog_path = Path(catalog_path)
        self.state_path = Path(state_path)

    def load_catalog(self) -> dict[str, Any]:
        value = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("components"), list):
            raise ValueError("reference component catalog is invalid")
        return value

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
        token = os.getenv("REFERENCE_GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _check_repo(self, repo_url: str, timeout: float = 12.0) -> dict[str, Any]:
        slug = _repo_slug(repo_url)
        headers = self._headers()
        repo_response = requests.get(f"https://api.github.com/repos/{slug}", headers=headers, timeout=timeout)
        repo_response.raise_for_status()
        meta = repo_response.json()
        default_branch = str(meta.get("default_branch") or "main")
        commit_response = requests.get(
            f"https://api.github.com/repos/{slug}/commits/{default_branch}", headers=headers, timeout=timeout
        )
        commit_response.raise_for_status()
        commit = commit_response.json()
        return {
            "repo": slug,
            "default_branch": default_branch,
            "latest_sha": str(commit.get("sha") or ""),
            "pushed_at": meta.get("pushed_at"),
            "archived": bool(meta.get("archived")),
            "html_url": meta.get("html_url") or repo_url,
            "checked_at": time.time(),
        }

    def check_once(self) -> dict[str, Any]:
        catalog = self.load_catalog()
        previous: dict[str, Any] = {}
        if self.state_path.exists():
            try:
                raw = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    previous = raw
            except (OSError, json.JSONDecodeError):
                previous = {}

        prior_by_id = {
            str(row.get("id")): row
            for row in (previous.get("components") or [])
            if isinstance(row, dict) and row.get("id")
        }
        results: list[dict[str, Any]] = []
        for component in catalog.get("components") or []:
            if not isinstance(component, dict) or not component.get("watch", True):
                continue
            item = {**component}
            component_id = str(item.get("id") or "")
            prior = prior_by_id.get(component_id) or {}
            try:
                upstream = self._check_repo(str(item.get("repo") or ""))
                previous_sha = str(prior.get("latest_sha") or "")
                latest_sha = str(upstream.get("latest_sha") or "")
                item.update(upstream)
                item["status"] = "update_available" if previous_sha and latest_sha != previous_sha else "current_seen"
                item["previous_seen_sha"] = previous_sha
            except Exception as exc:  # version watching must never stop the trader
                item.update(
                    {
                        "status": "check_failed",
                        "error": f"{type(exc).__name__}: {exc}",
                        "checked_at": time.time(),
                        "latest_sha": str(prior.get("latest_sha") or ""),
                    }
                )
            results.append(item)

        payload = {
            "version": 1,
            "checked_at": time.time(),
            "auto_promote": False,
            "auto_execute_external_code": False,
            "components": results,
        }
        _atomic_json(self.state_path, payload)
        return payload


def main() -> None:
    print(json.dumps(ReferenceComponentWatcher().check_once(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
