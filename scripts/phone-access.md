# Phone dashboard

## Same Wi-Fi
1. Start `start-trader.bat`.
2. Find the PC IPv4 address with `ipconfig`.
3. On the phone open `http://PC_IP:8765`.
4. Enter the token printed on the PC console or stored at `b3_trader/data/dashboard-token.txt`.

## Outside home: recommended free path
Use Tailscale Personal on the PC and phone. After both devices join the same tailnet, open `http://TAILSCALE_PC_IP:8765`.

The API is bearer-token protected. Do not expose port 8765 directly through router port forwarding.
