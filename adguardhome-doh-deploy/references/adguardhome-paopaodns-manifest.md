# AdGuardHome + PaoPaoDNS Docker Stack Deployment

## Architecture
`Surge (DoH) -> AdGuardHome (Port 53) -> PaoPaoDNS (Port 5335) -> Upstream DNS (e.g. 223.5.5.5)`

This stack optimizes home network DNS by combining AdGuardHome's UI/filtering with PaoPaoDNS's GeoDNS/CDN optimization.

## Deployment Manifests

### AdGuardHome
```yaml
services:
  adguardhome:
    image: adguard/adguardhome:latest
    container_name: adguardhome
    restart: always
    ports:
      - "53:53/tcp"
      - "53:53/udp"
      - "3000:3000/tcp"
      - "80:80/tcp"
      - "443:443/tcp"
    volumes:
      - ./work:/opt/adguardhome/work
      - ./conf:/opt/adguardhome/conf
    environment:
      TZ: "Asia/Shanghai"
```

### PaoPaoDNS
```yaml
services:
  paopaodns:
    image: sliamb/paopaodns:latest
    container_name: paopaodns
    volumes:
      - ./data:/data
    environment:
      CNAUTO: "yes"
      DNS_SERVERNAME: "dns.home"
      TZ: "Asia/Shanghai"
      UPDATE: "daily"
      IPV6: "yes"
      CNFALL: "yes"
      EXPIRED_FLUSH: "yes"
      CUSTOM_FORWARD_TTL: "300"
      ADDINFO: "yes"
      USE_MARK_DATA: "yes"
      CN_TRACKER: "yes"
      HTTP_FILE: "yes"
    restart: always
    ports:
      - "5335:53/tcp"
      - "5335:53/udp"
      - "5304:5304/tcp"
      - "5304:5304/udp"
      - "7889:7889/tcp"
```

## Configuration Steps
1. Deploy PaoPaoDNS first to ensure the port 5335 is available.
2. Deploy AdGuardHome.
3. In AdGuardHome Web UI (Settings -> DNS Settings), set Upstream DNS to `127.0.0.1:5335` (or the internal IP if on different hosts).
4. For CN optimization, PaoPaoDNS environment variables `CNAUTO` and `CNFALL` should be "yes".
