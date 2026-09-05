from b3_trader.runtime_config import RuntimeConfigStore


def test_runtime_config_patch(tmp_path):
    path = tmp_path / "runtime.json"
    store = RuntimeConfigStore(str(path))
    config = store.patch({"default_order_krw": 12345, "min_regime_score": 70})
    assert config.default_order_krw == 12345
    assert config.min_regime_score == 70
    reloaded = RuntimeConfigStore(str(path)).get()
    assert reloaded.default_order_krw == 12345
