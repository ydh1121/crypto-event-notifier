from b3_trader.assets import AssetRegistry, default_profile, normalize_market


def test_normalize_ticker():
    assert normalize_market("b3") == "KRW-B3"
    assert normalize_market("KRW-xrp") == "KRW-XRP"


def test_registry_roundtrip(tmp_path):
    path = tmp_path / "assets.json"
    registry = AssetRegistry(str(path))
    assert registry.get("B3") is not None
    profile = registry.add_generic("SEI")
    assert profile.market == "KRW-SEI"
    loaded = AssetRegistry(str(path))
    assert loaded.get("KRW-SEI").context_mode == "generic_alt"


def test_b3_default_context():
    profile = default_profile("B3")
    assert profile.context_mode == "base_gaming"
    assert "KRW-IMX" in profile.related_markets
