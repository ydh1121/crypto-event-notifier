import json

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


def test_cloudflare_status_reports_named_tunnel(monkeypatch, tmp_path):
    stable = tmp_path / "cloudflare-stable.json"
    active = tmp_path / "cloudflare-tunnel-url.txt"
    stable.write_text(
        json.dumps(
            {
                "hostname": "trader.example.com",
                "tunnel_id": "00000000-0000-0000-0000-000000000001",
            }
        ),
        encoding="utf-8",
    )
    active.write_text("https://trader.example.com\n", encoding="utf-8")
    monkeypatch.setattr(network_access, "CLOUDFLARE_STABLE_FILE", stable)
    monkeypatch.setattr(network_access, "CLOUDFLARE_URL_FILE", active)

    result = network_access._cloudflare_status()
    assert result["active"] is True
    assert result["stable"] is True
    assert result["mode"] == "named_tunnel"
    assert result["url"] == "https://trader.example.com"


def test_cloudflare_status_exposes_configured_stable_url_while_stopped(
    monkeypatch, tmp_path
):
    stable = tmp_path / "cloudflare-stable.json"
    active = tmp_path / "missing-active-url.txt"
    stable.write_text(
        json.dumps(
            {
                "hostname": "trader.example.com",
                "tunnel_id": "00000000-0000-0000-0000-000000000001",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(network_access, "CLOUDFLARE_STABLE_FILE", stable)
    monkeypatch.setattr(network_access, "CLOUDFLARE_URL_FILE", active)

    result = network_access._cloudflare_status()
    assert result["active"] is False
    assert result["configured"] is True
    assert result["stable"] is True
    assert result["mode"] == "named_tunnel"
    assert result["url"] == "https://trader.example.com"
