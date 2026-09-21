from __future__ import annotations

import json
from pathlib import Path

import pytest

from b3_trader import auto_demo_v2


def test_atomic_json_retries_replace_and_removes_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime-demo-upbit.json"
    calls: list[tuple[Path, Path]] = []
    real_replace = auto_demo_v2.os.replace

    def flaky_replace(src, dst) -> None:
        calls.append((Path(src), Path(dst)))
        if len(calls) == 1:
            raise PermissionError(5, "Access is denied")
        real_replace(src, dst)

    monkeypatch.setattr(auto_demo_v2.os, "replace", flaky_replace)
    monkeypatch.setattr(auto_demo_v2.time, "sleep", lambda _seconds: None)

    auto_demo_v2._atomic_json(path, {"ok": True, "exchange": "upbit"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True, "exchange": "upbit"}
    assert len(calls) == 2
    assert calls[0][0] == calls[1][0]
    assert calls[0][1] == path
    assert calls[0][0].name.startswith(f".{path.name}.")
    assert set(tmp_path.iterdir()) == {path}


def test_atomic_json_preserves_destination_and_cleans_temp_on_terminal_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime-demo-upbit.json"
    path.write_text('{"old":true}', encoding="utf-8")
    calls = 0

    def denied_replace(_src, _dst) -> None:
        nonlocal calls
        calls += 1
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(auto_demo_v2.os, "replace", denied_replace)
    monkeypatch.setattr(auto_demo_v2.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError):
        auto_demo_v2._atomic_json(path, {"ok": True})

    assert calls == 6
    assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
    assert set(tmp_path.iterdir()) == {path}
