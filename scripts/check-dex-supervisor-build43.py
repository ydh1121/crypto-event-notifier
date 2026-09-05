from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    control = text("b3_trader/research_control.py")
    supervisor = text("b3_trader/research_supervisor.py")
    cycle = text("b3_trader/dex_launch_research_cycle.py")
    store = text("b3_trader/dex_launch_store.py")
    lifecycle = text("b3_trader/cloudflare_snapshot_lifecycle.py")
    dex_snapshot = text("b3_trader/dex_launch_snapshot.py") if (ROOT / "b3_trader/dex_launch_snapshot.py").exists() else ""
    secure_launcher = text("start-trader-secure.bat")
    stale_cleanup = text("scripts/cleanup-stale-runtime-supervisors.ps1")

    checks = {
        "build43_component_registered": (
            '"dex-launch-research"' in control
            and '"default_enabled":True' in control
            and '"default_interval_seconds":3600' in control
            and '"min_interval_seconds":1800' in control
        ),
        "build43_supervisor_runner_registered": (
            "from .dex_launch_research_cycle import DexLaunchResearchCycle" in supervisor
            and '"dex-launch-research": self._run_dex_launch_once' in supervisor
        ),
        "build43_lazy_thread_owner": (
            "self.dex_launch_research: DexLaunchResearchCycle | None = None" in supervisor
            and "def _run_dex_launch_once" in supervisor
            and "self.dex_launch_research = DexLaunchResearchCycle()" in supervisor
        ),
        "build43_thread_local_close": (
            'if name == "dex-launch-research"' in supervisor
            and "cycle = self.dex_launch_research" in supervisor
            and "self.dex_launch_research = None" in supervisor
            and "cycle.close()" in supervisor
        ),
        "build43_one_case_per_run": "MAX_CASES_PER_RUN = 1" in cycle,
        "build43_retry_cooldown_preserved": (
            "DEFAULT_RETRY_AFTER_SECONDS = 6 * 3600" in store
            and '"source_waiting"' in store
            and '"pool_quality_waiting"' in store
        ),
        "build43_shadow_safety_status": (
            '"dex_launch_public_sources_only": True' in supervisor
            and '"dex_launch_shadow_only": True' in supervisor
            and '"can_place_orders": False' in supervisor
        ),
        "build43_cycle_paper_only": (
            '"paper_only": True' in cycle
            and '"shadow_only": True' in cycle
            and '"can_place_orders": False' in cycle
        ),
        "build43_no_order_wiring": (
            "from .decision" not in cycle
            and "from .order" not in cycle
            and ".place_order(" not in cycle
            and "place_order(" not in cycle
        ),
        "build43_raw_dex_stays_local": (
            "dex_launch_candles" not in lifecycle
            and (
                not dex_snapshot
                or (
                    '"raw_candles_included": False' in dex_snapshot
                    and "dex_launch_candles" not in dex_snapshot
                )
            )
        ),
        "build43_stale_supervisor_cleanup": (
            "cleanup-stale-runtime-supervisors.ps1" in secure_launcher
            and '.venv\\Scripts\\python.exe' in stale_cleanup
            and "Get-CimInstance Win32_Process" in stale_cleanup
            and "b3_trader.research_supervisor" in stale_cleanup
            and "b3_trader.paper_runtime_supervisor" in stale_cleanup
            and "Stop-Process" in stale_cleanup
        ),
    }

    print("=== DEX SUPERVISOR BUILD 43 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        raise SystemExit(f"DEX_SUPERVISOR_BUILD43=FAIL: {', '.join(failed)}")
    print("DEX_SUPERVISOR_BUILD43=PASS")


if __name__ == "__main__":
    main()
