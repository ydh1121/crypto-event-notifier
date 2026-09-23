from pathlib import Path
from b3_trader.runtime_process_contract import SIDECARS


def test_secure_launcher_owns_market_flow_stream_lifecycle() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "scripts" / "run-local.ps1").read_text(encoding="utf-8")

    assert '& $python -m b3_trader.local_process_host' in script
    assert ('market_flow', 'b3_trader.market_flow_stream', (), True) in SIDECARS
    assert '$env:DEX_FORWARD_PIPELINE_DEDICATED_MODE = "true"' in script
    # Actual crash/retry/shutdown behavior is exercised by test_local_process_host.
