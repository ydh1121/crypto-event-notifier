from __future__ import annotations

import json
from pathlib import Path

from b3_trader.reference_components import ReferenceComponentWatcher, _repo_slug


def test_repo_slug() -> None:
    assert _repo_slug("https://github.com/freqtrade/freqtrade") == "freqtrade/freqtrade"
    assert _repo_slug("https://github.com/ccxt/ccxt.git") == "ccxt/ccxt"


def test_version_watch_never_auto_promotes(tmp_path: Path, monkeypatch) -> None:
    catalog = tmp_path / "catalog.json"
    state = tmp_path / "state.json"
    catalog.write_text(
        json.dumps(
            {
                "components": [
                    {
                        "id": "demo",
                        "repo": "https://github.com/example/demo",
                        "watch": True,
                        "runtime_enabled": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    watcher = ReferenceComponentWatcher(catalog_path=catalog, state_path=state)
    monkeypatch.setattr(
        watcher,
        "_check_repo",
        lambda _url: {
            "repo": "example/demo",
            "default_branch": "main",
            "latest_sha": "abc123",
            "pushed_at": "2026-08-24T00:00:00Z",
            "archived": False,
            "html_url": "https://github.com/example/demo",
            "checked_at": 1.0,
        },
    )

    result = watcher.check_once()
    assert result["auto_promote"] is False
    assert result["auto_execute_external_code"] is False
    assert result["components"][0]["latest_sha"] == "abc123"
    assert result["components"][0]["runtime_enabled"] is False
