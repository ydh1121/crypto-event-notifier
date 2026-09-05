from pathlib import Path

from b3_trader.runtime_state import RuntimeState
from b3_trader.sync_manager import GitAutoSync


def test_git_sync_disables_cleanly_without_git_metadata(tmp_path: Path):
    state = RuntimeState()
    sync = GitAutoSync(
        repo_dir=str(tmp_path),
        branch="b3-auto-trader-phase1",
        enabled=True,
        interval_seconds=60,
        state=state,
    )

    result = sync.check_once()

    assert result["status"] == "disabled"
    assert result["reason"] in {"not_a_git_clone", "git_not_installed"}
    assert state.snapshot()["sync"]["status"] == "disabled"


def test_publish_control_disables_cleanly_without_git_metadata(tmp_path: Path):
    state = RuntimeState()
    sync = GitAutoSync(
        repo_dir=str(tmp_path),
        branch="b3-auto-trader-phase1",
        enabled=True,
        interval_seconds=60,
        state=state,
        push_control_changes=True,
    )

    result = sync.publish_control("test")

    assert result["status"] == "disabled"
    assert result["reason"] in {"not_a_git_clone", "git_not_installed"}


def test_dashboard_changes_hot_reload_without_server_restart(tmp_path: Path):
    sync = GitAutoSync(
        repo_dir=str(tmp_path),
        branch="b3-auto-trader-phase1",
        enabled=False,
        interval_seconds=60,
        state=RuntimeState(),
    )

    assert not sync._restart_required(["dashboard/navigation-v3.js"])
    assert not sync._restart_required(["dashboard/navigation-v3.css"])
    assert not sync._restart_required(["dashboard/index.html"])
    assert not sync._restart_required(["scripts/run-local.ps1"])
    assert not sync._restart_required(["start-trader-secure.bat"])
    assert not sync._restart_required(["control/assets.json"])
    assert sync._restart_required(["b3_trader/local_app.py"])
    assert sync._restart_required(["b3_trader/sync_manager.py"])
