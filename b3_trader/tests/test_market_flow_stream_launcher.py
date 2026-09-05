from pathlib import Path


def test_secure_launcher_owns_market_flow_stream_lifecycle() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "scripts" / "run-local.ps1").read_text(encoding="utf-8")

    assert "function Start-MarketFlowStream" in script
    assert 'b3_trader.market_flow_stream' in script
    assert '$marketFlowStream = $null' in script
    assert '$marketFlowStream = Start-MarketFlowStream -PythonPath $python' in script
    assert 'Stop-Process -Id $marketFlowStream.Id -Force' in script
    assert "PAPER-only, score/order unwired" in script
