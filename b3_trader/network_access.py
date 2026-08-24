from __future__ import annotations

import json
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any


CLOUDFLARE_URL_FILE = Path("b3_trader/data/cloudflare-tunnel-url.txt")


def _lan_ipv4() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packet is sent; connect only asks the OS which interface would be used.
        sock.connect(("8.8.8.8", 80))
        value = sock.getsockname()[0]
        return value if value and not value.startswith("127.") else None
    except OSError:
        try:
            value = socket.gethostbyname(socket.gethostname())
            return value if value and not value.startswith("127.") else None
        except OSError:
            return None
    finally:
        sock.close()


def _tailscale_binary() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    candidates = (
        Path(r"C:\Program Files\Tailscale\tailscale.exe"),
        Path(r"C:\Program Files (x86)\Tailscale\tailscale.exe"),
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _tailscale_status() -> dict[str, Any]:
    binary = _tailscale_binary()
    if not binary:
        return {
            "installed": False,
            "connected": False,
            "ipv4": None,
            "dns_name": None,
        }
    try:
        completed = subprocess.run(
            [binary, "status", "--json"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if completed.returncode != 0:
            return {
                "installed": True,
                "connected": False,
                "ipv4": None,
                "dns_name": None,
                "message": (completed.stderr or completed.stdout).strip()[:240],
            }
        payload = json.loads(completed.stdout or "{}")
        self_node = payload.get("Self") or {}
        ips = list(self_node.get("TailscaleIPs") or [])
        ipv4 = next((value for value in ips if ":" not in str(value)), None)
        backend_state = str(payload.get("BackendState") or "")
        online = bool(self_node.get("Online")) or backend_state.lower() == "running"
        dns_name = str(self_node.get("DNSName") or "").rstrip(".") or None
        return {
            "installed": True,
            "connected": bool(online and ipv4),
            "ipv4": ipv4,
            "dns_name": dns_name,
            "backend_state": backend_state or None,
        }
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        return {
            "installed": True,
            "connected": False,
            "ipv4": None,
            "dns_name": None,
            "message": f"{type(exc).__name__}: {exc}",
        }


def _cloudflare_status() -> dict[str, Any]:
    try:
        if not CLOUDFLARE_URL_FILE.exists():
            return {
                "active": False,
                "url": None,
                "mode": "quick_tunnel",
            }
        url = CLOUDFLARE_URL_FILE.read_text(encoding="utf-8-sig").strip()
        if not url.startswith("https://") or ".trycloudflare.com" not in url:
            return {
                "active": False,
                "url": None,
                "mode": "quick_tunnel",
            }
        return {
            "active": True,
            "url": url,
            "mode": "quick_tunnel",
            "vpn_required": False,
            "https": True,
        }
    except OSError as exc:
        return {
            "active": False,
            "url": None,
            "mode": "quick_tunnel",
            "message": f"{type(exc).__name__}: {exc}",
        }


def network_status(port: int, host: str = "0.0.0.0") -> dict[str, Any]:
    lan_ip = _lan_ipv4()
    tailscale = _tailscale_status()
    cloudflare = _cloudflare_status()
    tailscale_ip = tailscale.get("ipv4")
    tailscale_dns = tailscale.get("dns_name")
    loopback_only = str(host).strip() in {"127.0.0.1", "localhost", "::1"}
    lan_url = None if loopback_only else (f"http://{lan_ip}:{port}" if lan_ip else None)
    return {
        "port": int(port),
        "bind_host": host,
        "loopback_only": loopback_only,
        "lan": {
            "ipv4": lan_ip,
            "url": lan_url,
            "enabled": bool(lan_url),
        },
        "cloudflare": cloudflare,
        "tailscale": {
            **tailscale,
            # Prefer the 100.x Tailscale address. It does not depend on MagicDNS.
            "url": f"http://{tailscale_ip}:{port}" if tailscale_ip else None,
            "dns_url": f"http://{tailscale_dns}:{port}" if tailscale_dns else None,
            "preferred": "ipv4",
        },
        "public_port_forwarding_recommended": False,
        "public_http_warning": (
            "Do not use a public/WAN IP for this dashboard. "
            "For VPN-free phone access use the HTTPS Cloudflare Tunnel launcher."
        ),
        "remote_auth_required": True,
    }
