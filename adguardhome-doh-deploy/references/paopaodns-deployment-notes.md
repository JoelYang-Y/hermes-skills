# PaoPaoDNS Deployment Notes

## Key Environment Variables
| Variable | Value | Description |
|---|---|---|
| `CNAUTO` | `yes` | Enables automatic CN GeoIP-based routing. |
| `CNFALL` | `yes` | Fallback to CN DNS for CN domains. |
| `IPV6` | `yes` | Enable IPv6 resolution. |
| `UPDATE` | `daily` | Automatic update frequency for rules. |
| `CUSTOM_FORWARD_TTL` | `300` | Custom TTL for forwarded queries. |

## Common Pitfalls
- **Docker Mirror Issue**: In some environments (like China), `sliamb/paopaodns` might fail to pull or return 403. Use a mirror like `docker.1ms.run/sliamb/paopaodns:latest`.
- **Port Conflicts**: PaoPaoDNS typically listens on 53. If the host already has `systemd-resolved` or another DNS server, bind to a different host port (e.g., `5335:53`).
- **IPv6 in Bridge**: Docker bridge networks often don't have IPv6 enabled. If PaoPaoDNS needs to resolve IPv6, ensure the bridge network is configured for it or use `network_mode: host`.
- **ECS (EDNS Client Subnet)**: While PaoPaoDNS supports ECS, if the upstream (like `223.5.5.5`) doesn't receive ECS from your ISP, the GeoDNS optimization depends on PaoPaoDNS's own egress IP.
