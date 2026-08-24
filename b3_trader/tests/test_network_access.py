from b3_trader import network_access


def test_network_status_builds_safe_urls(monkeypatch):
    monkeypatch.setattr(network_access, "_lan_ipv4", lambda: "192.168.0.10")
    monkeypatch.setattr(
        network_access,
        "_tailscale_status",
        lambda: {
            "installed": True,
            "connected": True,
            "ipv4": "100.64.0.10",
            "dns_name": "trader.tail.test",
        },
    )

    result = network_access.network_status(8765)
    assert result["lan"]["url"] == "http://192.168.0.10:8765"
    assert result["tailscale"]["url"] == "http://100.64.0.10:8765"
    assert result["tailscale"]["dns_url"] == "http://trader.tail.test:8765"
    assert result["tailscale"]["preferred"] == "ipv4"
    assert result["public_port_forwarding_recommended"] is False
    assert result["remote_auth_required"] is True
