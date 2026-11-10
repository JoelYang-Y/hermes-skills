---
name: adguardhome-doh-deploy
description: "Deploy AdGuard Home with public DoH/DoT behind a reverse proxy (openresty or nginx) using a shared Let's Encrypt certificate. Covers container port mapping, AGH TLS settings, reverse-proxy vhost for both UI and DoH endpoint, anti-scanner random paths, and the `Root YR` intermediate cert gotcha that breaks nginx upstream verification."
version: 1.0.0
category: devops
tags:
  - adguardhome
  - doh
  - dns-over-https
  - reverse-proxy
  - openresty
  - nginx
  - lets-encrypt
  - 1panel
triggers:
  - deploy AdGuard Home DoH
  - adguard home https reverse proxy
  - set up DoH server
  - adguardhome docker compose DoH
  - 1panel openresty adguardhome
  - nginx proxy_pass adguardhome 443
  - AGH trusted_proxies
  - atpx.com adguard doh article
  - adguard home 证书续期
  - AGH DoH 证书自动续期
---

# AdGuard Home DoH deployment with shared cert (reverse proxy + 1Panel/openresty)

Recipe for putting a public DoH endpoint on AdGuard Home by combining:
- AGH container publishing HTTPS on a host port (e.g. `127.0.0.1:8443:443`)
- A reverse proxy (openresty or nginx) terminating client TLS with the real Let's Encrypt cert
- Same cert mounted into the AGH container so AGH serves HTTPS with a valid chain (not a self-signed)
- AGH yaml `tls.enabled: true` + `certificate_path/private_key_path` pointing at the mounted cert

Pattern follows the atpx.com article but with the gotchas that article didn't surface.

## Step 0 — Verify preconditions BEFORE writing config

```bash
# 1. Where is the cert? Confirm both files exist and the leaf has the right CN.
openssl x509 -in /usr/local/adg/fullchain.pem -noout -subject -issuer -dates -ext subjectAltName
# expect: subject=CN = <your domain>, issuer=Let's Encrypt

# 2. How many certs in the chain? LE certs from late 2024+ ship 3: leaf + YR2 + Root YR
grep -c "BEGIN CERTIFICATE" /usr/local/adg/fullchain.pem
# 3 (with the YR2/Root YR intermediates). If 2, the gotcha below doesn't apply.

# 3. Is the docker network isolated? The proxy will reach AGH via 127.0.0.1:<hostport>.
docker network ls
# AGH on its own network is FINE. The proxy and AGH don't need to share a network —
# the host-published port works.

# 4. Does the public DNS record for the domain point to the right IP?
dig +short <your-do-h-domain> @1.1.1.1
# If empty: the cert will work but no client can reach you. Add the A record in
# Cloudflare (or wherever the NS is delegated) before testing.
```

## Step 1 — docker-compose for AGH (the part the user usually pastes wrong)

```yaml
# /home/adguardhome/docker-compose.yml  (lowercase! See path-case pitfall below)
services:
  adguardhome:
    image: adguard/adguardhome:latest
    container_name: adguardhome
    restart: unless-stopped
    ports:
      - 127.0.0.1:8443:443/tcp   # HTTPS — ONLY loopback; reverse-proxied from openresty
      - 127.0.0.1:3000:3000/tcp  # Web UI — only the proxy needs to reach this
    volumes:
      - ./work:/opt/adguardhome/work
      - ./conf:/opt/adguardhome/conf
      - /usr/local/adg:/opt/adguardhome/cert  # host dir → container cert dir
    networks:
      agh_net:
        ipv4_address: 172.20.1.2

networks:
  agh_net:
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet: 172.20.1.0/24
```

**Pitfall — path case matters.** The user almost always pastes `/home/AdGuardHome/` (capital A) from old tutorials, but the running container's actual host bind is `/home/adguardhome/` (lowercase). On a fresh deploy with the capital-A path, docker happily creates an empty dir and AGH starts with **no persisted state** — port mappings still work but the previous config is gone. Fix the compose before `docker compose up -d`. Verify with `docker inspect <container> --format '{{json .Mounts}}' | jq` to see which host path is actually bound.

**Pitfall — `0.0.0.0:3000:3000` is a security hole.** The UI listens on plain HTTP and 3000 is the management port. Always bind to `127.0.0.1` so only the reverse proxy can reach it.

## Step 2 — patch AdGuardHome.yaml for TLS

Three fields must be set. Edit `/home/adguardhome/conf/AdGuardHome.yaml` and change the `tls:` block:

```yaml
tls:
  enabled: true
  server_name: "doh.example.com"            # your domain
  force_https: false
  port_https: 443
  port_dns_over_tls: 853
  port_dns_over_quic: 0                     # 0 = disabled
  port_dnscrypt: 0
  dnscrypt_config_file: ""
  certificate_chain: ""
  private_key: ""
  certificate_path: "/opt/adguardhome/cert/fullchain.pem"
  private_key_path: "/opt/adguardhome/cert/privkey.pem"
  strict_sni_check: false
```

After editing, `docker restart adguardhome` and verify the log shows:
```
webapi: serving url=https://doh.example.com:443
starting https server server=https
```
NOT just `serving url=http://127.0.0.1:3000` — that means TLS didn't take.

**trusted_proxies MUST include every bridge subnet the proxy traffic can originate from.** Modern AGH yaml ships with `127.0.0.0/8`, `::1/128`, and the AGH network subnet, but **that is NOT sufficient when the reverse proxy is on the host network or in a different docker network.** The default `127.0.0.0/8` only matches if the proxy literally connects from a loopback IP. In the common 1Panel deployment the reverse-proxy container is in its own docker network (e.g. `1panel-network`, subnet `172.19.0.0/16`) and AGH publishes its port via `docker-proxy` on `127.0.0.1:3000`. The TCP connection that AGH sees has **source IP = the bridge gateway of the reverse-proxy container** (e.g. `172.19.0.1`), NOT `127.0.0.1`. AGH then logs that gateway as the `client`, and worse, refuses to honor `X-Real-IP` / `X-Forwarded-For` because it doesn't trust the source.

For 1Panel-openresty → docker-proxy → AGH, the connection arrives at AGH from the **1panel-network bridge gateway** (commonly `172.19.0.1`) OR the **AGH network gateway** if openresty were on it. Either way the safe rule is: **add every docker bridge subnet your proxy container sits on, plus 10.0.0.0/8 as a safety net.**

```yaml
# /home/adguardhome/conf/AdGuardHome.yaml
dns:
  trusted_proxies:
    - 127.0.0.0/8
    - ::1/128
    - 172.19.0.0/16    # 1panel-network (openresty container's bridge)
    - 172.28.0.0/16    # dns-server_dns_net (AGH container's bridge)
    - 172.17.0.0/16    # docker default bridge (in case openresty is on host with veth)
    - 10.0.0.0/8       # catch-all for any other private bridge
```

Verification (run on the openresty host, after restarting AGH with the new config):

```bash
# Login to AGH via API (cookie jar). Password is whatever the user set in AGH web UI;
# if they don't remember it, the bcrypt hash is in AdGuardHome.yaml under users[0].password.
curl -sS -c /tmp/agh.cookies -X POST http://127.0.0.1:3000/control/login \
  -H "Content-Type: application/json" \
  -d '{"name":"root","password":"<AGH_PASSWORD>"}'

# Hit the reverse-proxied DoH endpoint with a fake X-Real-IP
docker exec <openresty-container> sh -c '
  curl -sS --resolve <domain>:8443:127.0.0.1 \
    -H "Host: <domain>" \
    -H "X-Real-IP: 8.8.8.8" \
    -H "X-Forwarded-For: 8.8.8.8" \
    -H "accept: application/dns-message" \
    "https://<domain>:8443/<doh-path>?dns=AAABAAABAAAAAAAAB2dhdGV3YXkCZmUJYXBwbGUtZG5zAmNuAAAcAAE"
'

# Pull the in-memory querylog; if trusted_proxies is right, client == "8.8.8.8"
curl -sS -b /tmp/agh.cookies http://127.0.0.1:3000/control/querylog | python3 -c "
import sys, json
d = json.load(sys.stdin)
for it in d.get('data', [])[:5]:
    print('client=', it.get('client'), ' proto=', it.get('client_proto'))
"
```

If the printed `client` is `172.19.0.1` (or some other bridge gateway) instead of `8.8.8.8`, the trusted_proxies is missing the bridge subnet — add it and restart AGH.

**Bonus: querylog must be enabled in memory or file to see this** (otherwise `/control/querylog` returns empty). Newer AGH ships `querylog.enabled: true` by default; if not, enable via `curl -b /tmp/agh.cookies http://127.0.0.1:3000/control/querylog` (read-only GET shows current state — there is no POST setter in v0.107, so edit yaml and `docker restart`).

## Step 3 — reverse proxy vhost

### 3a. On 1Panel v2.2.2 (openresty in a container)

The vhost directory bind-mounted from openresty container to host:
- Host: `/opt/1panel/www/conf.d/<site>.conf`
- Container: `/usr/local/openresty/nginx/conf/conf.d/<site>.conf` (auto-included via `include .../conf.d/*.conf;` in the openresty main `nginx.conf`)

**Do NOT write to `/www/server/panel/vhost/{nginx,openresty}/`** — those are 1Panel v1.x paths. The 1Panel v2.2.2 site config goes in `/opt/1panel/www/conf.d/`.

### 3b. The vhost (with anti-scanner random paths)

```nginx
# /opt/1panel/www/conf.d/doh.example.com.conf

server {
    listen 80;
    server_name doh.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name doh.example.com;

    ssl_certificate     /usr/local/openresty/nginx/conf/ssl/doh.example.com/fullchain.pem;
    ssl_certificate_key /usr/local/openresty/nginx/conf/ssl/doh.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    add_header Strict-Transport-Security "max-age=31536000" always;

    access_log /var/log/nginx/doh.example.com.access.log main;
    error_log  /var/log/nginx/doh.example.com.error.log;

    # Random path to dodge path-scanners (replace 234f55d7bc2a240b with your own)
    location /q-234f55d7bc2a240b/ {
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_ssl_server_name  on;
        proxy_ssl_name          doh.example.com;
        proxy_ssl_verify        off;             # <-- SEE "ROOT YR" PITFALL BELOW
        proxy_pass       https://127.0.0.1:8443/dns-query;
    }

    # Non-default path for the AGH web UI (replace e452e056f281 with your own)
    location /ag-e452e056f281/ {
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cookie_path / /ag-e452e056f281/;
        proxy_redirect   / /ag-e452e056f281/;
        proxy_pass       http://127.0.0.1:3000/;
    }

    location / { return 404; }
}
```

Reload: `docker exec 1Panel-openresty-XXXX openresty -s reload` (the `1Panel-openresty-XXXX` is whatever the running container's name is — check with `docker ps --format '{{.Names}}'`).

Generate the random paths with `openssl rand -hex 8` for the DoH path and `openssl rand -hex 6` for the UI path. Generate a UUIDv4 for the ClientID: `python3 -c 'import uuid; print(uuid.uuid4())'`.

### 3c. Plain nginx (non-1Panel)

Same content; the only differences are where you put the file (`/etc/nginx/conf.d/<site>.conf` or `sites-enabled/<site>`) and the reload command (`nginx -s reload`).

## The "Root YR" pitfall — why `proxy_ssl_verify on` breaks

If the Let's Encrypt cert was issued after late 2024, the chain is **3 certs**:
1. `leaf` (your domain)
2. `YR2` (intermediate; issuer=`Root YR`)
3. `Root YR` (intermediate, **not** self-signed; issuer=`ISRG Root X1`)

When nginx does `proxy_pass https://127.0.0.1:8443/dns-query` with `proxy_ssl_verify on`, it builds a trust path from the server's chain against the trust anchors in `proxy_ssl_trusted_certificate`. The naive options — and why they each fail:

| Trust bundle tried | Result |
|---|---|
| `ISRG_Root_X1.pem` only | `unable to get issuer certificate` (error 2). nginx can't connect `Root YR → ISRG Root X1` because of trust-anchor interpretation. |
| `fullchain.pem` (leaf + YR2 + Root YR) | `unable to get local issuer certificate` (error 20). The chain is internally consistent but ends in a non-self-signed intermediate. |
| `fullchain.pem` + `ISRG_Root_X1.pem` | Still `unable to get local issuer certificate` (error 20). Adding the self-signed root doesn't help because nginx's path builder never re-anchors. |
| Just `proxy_ssl_verify off` | **Works.** Connection succeeds. |

Verified empirically on 1Panel openresty `1.31.1.1-0-noble` with openssl 3.0.13. The same combination will misbehave on stock nginx (1.24+) for the same reason.

**Recommendation: `proxy_ssl_verify off` for local upstreams.** The proxy is on the same host (127.0.0.1), in a docker network AGH has no route out of. The MITM surface is effectively zero. The TLS handshake the proxy performs on the **client-facing** side is what matters for security — and that one uses `ssl_verify_client off` semantics already (you don't issue client certs to DoH users).

If you really need `verify on`, the fix is to obtain a cert chain that ends in a **self-signed** root in the local trust store. As of mid-2026, this means either (a) re-issuing via an ACME provider that doesn't include `Root YR` (e.g. ZeroSSL with ISRG Root X1 only), or (b) using a private CA with self-signed intermediates — neither is what the user wants for a public DoH endpoint.

## Step 4 — verify the wireformat

Once openresty reloaded:

```bash
# Inside the openresty container (avoids the public-DNS pollution problem):
docker exec <openresty-container> sh -c '
# Build a DNS query for example.com A: 12-byte header + qname + qtype + qclass
RAW=$(perl -e "print pack(\"H*\", \"123401000001000000000000076578616d706c6503636f6d0000010001\")")
B64=$(printf "%s" "$RAW" | base64 | tr -d "\n" | tr "+/" "-_" | tr -d "=")

# POST (RFC 8484 wireformat)
curl -sS -m 8 --resolve doh.example.com:443:127.0.0.1 \
  -H "content-type: application/dns-message" \
  --data-binary "$RAW" \
  -o /tmp/resp.bin \
  -w "HTTP %{http_code} | bytes %{size_download} | ct %{content_type}\n" \
  "https://doh.example.com/q-234f55d7bc2a240b/"

# GET (RFC 8484 GET method, base64url query)
curl -sS -m 8 --resolve doh.example.com:443:127.0.0.1 \
  -H "accept: application/dns-message" \
  -o /tmp/resp2.bin \
  -w "HTTP %{http_code} | bytes %{size_download}\n" \
  --get --data-urlencode "dns=$B64" \
  "https://doh.example.com/q-234f55d7bc2a240b/"
'

# Decode the response with python3
python3 - <<'PY'
import struct
data = open('/tmp/resp.bin','rb').read()
def name(d, off):
    parts = []
    while True:
        ln = d[off]
        if ln == 0: return '.'.join(parts), off+1
        if ln & 0xc0:
            ptr = ((ln & 0x3f) << 8) | d[off+1]
            sub, _ = name(d, ptr); parts.append(sub); return '.'.join(parts), off+2
        parts.append(d[off+1:off+1+ln].decode()); off += 1+ln
h = struct.unpack('!HHHHHH', data[:12])
print(f'QR={(h[1]>>15)&1} RCODE={h[1]&0xf} AN={h[3]}')
off = 12
for _ in range(h[2]):
    n, off = name(data, off); qt, qc = struct.unpack('!HH', data[off:off+4]); off += 4
    print(f'Q: {n} type={qt}')
for _ in range(h[3]):
    n, off = name(data, off); rt, rc, ttl, rdlen = struct.unpack('!HHiH', data[off:off+10]); off += 10
    rd = data[off:off+rdlen]; off += rdlen
    if rt == 1 and rdlen == 4:
        print(f'A: {n} ttl={ttl}s -> {rd[0]}.{rd[1]}.{rd[2]}.{rd[3]}')
PY
```

Expected output: `HTTP 200 | bytes ~50-80 | ct application/dns-message` and the parser prints `QR=1 RCODE=0 AN≥1` plus a real A record.

## 升级已有 AGH 容器（内网 10.0.0.6 节点实战流程）

已部署节点的例行升级，不许改 daemon.json（重启 dockerd 会中断 DNS）。实测流程：

```bash
# 0. 登录（10.0.0.6 = PVE VM 100，Alpine，root 密码与 PVE 同一套 <密码>）
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no root@10.0.0.6

# 1. 查当前版本 + 部署路径
docker exec adguardhome /opt/adguardhome/AdGuardHome --version   # -> v0.107.78
docker inspect adguardhome --format '{{json .Config.Labels}}' | tr ',' '\n' | grep config_files
# -> /root/AdGuardHome/docker-compose.yml（注意：大写 A 的 AdGuardHome 是这台机的真实路径，
#    与技能上文 "小写 adguardhome" 的坑不冲突——必须以 docker inspect .Mounts 实测为准）

# 2. 查最新稳定版（web_extract 打不开 api.github.com：它被判定为内网地址，用 terminal curl）
curl -sS -m 20 https://api.github.com/repos/AdguardTeam/AdGuardHome/releases/latest | grep -m1 tag_name

# 3. 备份配置（必做，AGH 启动时会重写 yaml）
cp -av /root/AdGuardHome/AdGuardHome.yaml /root/AdGuardHome/AdGuardHome.yaml.bak-$(date +%Y%m%d-%H%M%S)
```

**关键坑 1 — 磁盘只有 1.2 G。** VM 100 的根分区就 1.2 GiB，`/var/lib/docker` 挂在同一分区，跑满会直接拖垮 DNS。升级前先 `docker rmi` 明确未使用的镜像，升级后删悬空镜像；可用空间低于 ~250 MB 时不要贸然 pull。

实测基线（2026-10-25）：长期运行后根分区 941.6M/1.2G（85%，可用仅 160.7M），两个历史悬空镜像 `1ea34eafe5dc`(114M) + `e6f2b8bcda06`(110M) 即占 224M。`docker rmi <两个悬空ID>` 后立即回到 740.9M/1.2G（67%，可用 361.4M），全程不重启任何容器、53 端口零中断（`docker rmi` 只删无引用的层）。**例行升级前先跑 `docker system df` 看可回收量，按 ID 精确删悬空镜像，不要用 `docker system prune`**——会波及 `sliamb/paopaodns:latest` 这类必须保留的运行镜像。

**版本核对三方比对（防误判有无更新）：** 容器 `--version` ↔ GitHub `releases/latest`（`prerelease=false`）↔ Docker Hub `hub.docker.com/v2/repositories/adguard/adguardhome/tags/latest` 的 `digest` 与本地镜像 ID 前 12 位。三者一致即已最新，不必 pull。注意上游存在 `v1.0.0-b.x` / `v0.108.0-b.x` 预发布版，跨大版本会改配置与 API，稳定版跟进策略下不应误升。

**关键坑 2 — daemon.json 里的自建 mirror 比官方源还慢。** `/etc/docker/daemon.json` 的 `registry-mirrors` 首位是自建 registry 时，`docker pull adguard/adguardhome:latest` 会在它上面挂住（实测 420 s 未完成，60 s 只写 3 MB）。**不要为了提速去改 daemon.json 重启 dockerd（会中断 53 端口解析）**，改用显式源地址直拉，实测 45 s 跑完：

```bash
docker pull docker.1ms.run/adguard/adguardhome:latest     # 绕过 mirror 直连加速源
docker run --rm --entrypoint /opt/adguardhome/AdGuardHome \
  docker.1ms.run/adguard/adguardhome:latest --version     # 先验版本再替换
```

**关键坑 3 — 拉下来的镜像名不对，compose 认不出。** compose 里写的是 `image: adguard/adguardhome:latest`，而显式源拉下来的 tag 是 `docker.1ms.run/adguard/adguardhome:latest`。必须先 retag 才能让 compose 用到新镜像（否则 `up -d` 因本地已有 latest 而跳过）：

```bash
docker tag docker.1ms.run/adguard/adguardhome:latest adguard/adguardhome:latest
cd /root/AdGuardHome && docker compose up -d --force-recreate
```

**关键坑 4 — `pkill -f 'docker pull adguard'` 会杀掉自己。** 该模式匹配到 ssh 传入的整条命令行（含同样字符串），会话立即中断。先取 PID 再 kill：

```bash
PID=$(ps -eo pid,args | grep -F "pull adguard" | grep -v grep | awk '{print $1}' | head -1)
[ -n "$PID" ] && kill $PID
```

慢速拉取要放后台带日志：`nohup docker pull <img> > /tmp/agh_pull.log 2>&1 < /dev/null &`，再周期性查看该日志文件的尾部。

**升级后验证清单（缺一不可）：**

```bash
# a. 日志：必须出现 https server + 53/853 监听，且无 error
docker logs adguardhome 2>&1 | grep -E 'starting https server|listening to (udp|tcp) addr|error'
# 可忽略的两个无害 warning：DDR（证书无 IP SAN）、work 目录权限 0755 want 0700

# b. 明文解析 + 拦截规则
dig +short @10.0.0.6 www.baidu.com A      # 有真实 IP
dig +short @10.0.0.6 doubleclick.net A    # 0.0.0.0 = 拦截生效

# c. schema 未漂移
grep '^schema_version' /root/AdGuardHome/AdGuardHome.yaml   # 0.107.x 内小版本升级保持 34
```

**DoH 端到端测试的 payload 构造陷阱：** bash 变量无法保存 NUL 字节，`printf '\x12\x34...' "$RAW"` 会在命令替换时被截断/警告（`忽略输入中的 null 字节`），AGH 直接回 HTTP 400。**必须把二进制写进文件再 `--data-binary @file`**：

```bash
python3 -c "
import struct
h=struct.pack('!HHHHHH',0x1234,0x0100,1,0,0,0)
q=b''.join(bytes([len(p)])+p.encode() for p in 'example.com'.split('.'))+b'\x00'
open('doh_q.bin','wb').write(h+q+struct.pack('!HH',1,1))"
curl -sS -m 12 --resolve adg.jhsweetheart.com:443:10.0.0.6 \
  -H 'content-type: application/dns-message' --data-binary @doh_q.bin \
  -w 'HTTP %{http_code} | bytes %{size_download}\n' \
  https://adg.jhsweetheart.com/dns-query
# 期望：HTTP 200 + application/dns-message + RCODE=0 AN>=1 + 真实 A 记录
```

**macOS 侧排障误区：** `echo > /dev/tcp/10.0.0.6/443` 在 macOS bash 下会误报 CLOSED（连 53 都报 closed，但 `dig @10.0.0.6` 明明通），`timeout` 命令在 macOS 也不存在。判断端口用 `nc -z -G 4`，判断响应码用 `curl --resolve`。

## DoH 证书的自动续期（内网 AGH · DNS-01）

内网 DoH 域名（如 `adg.<domain>`，公网无 A 记录）**只能走 Cloudflare DNS-01**。先证伪再动手：

```bash
dig +short adg.<domain> @1.1.1.1     # 空 = HTTP-01 / TLS-ALPN-01 都没有入口，别试 webroot/standalone
```

### 第一步 — 把内嵌证书改成文件路径（不改就没法自动化）

AGH 有两种证书存法，先判断是哪一种：

| yaml 形态 | 续期后果 |
|---|---|
| `certificate_chain` + `private_key` 内嵌 PEM | 续期不生效；每次都要重写多行 PEM，`sed` 改坏缩进会让 AGH crash-loop 且 `docker exec` 被拒 |
| `certificate_path` + `private_key_path` 指向文件 | 续期后只需重启容器 |

v0.107.x 的 `tls` 段默认两个路径字段都在、值为空串。先把目录挂进容器再切路径：

```bash
# 宿主 /root/AdGuardHome 同时挂到 /opt/adguardhome/conf 与 .../work
mkdir -p /root/AdGuardHome/ssl && chmod 700 /root/AdGuardHome/ssl
docker exec adguardhome ls -ld /opt/adguardhome/conf/ssl   # 看不到 = 挂载不是目录级，先修 compose
```

对应 yaml（内嵌两项一并清空）：

```yaml
  certificate_chain: ""
  private_key: ""
  certificate_path: "/opt/adguardhome/conf/ssl/fullchain.pem"
  private_key_path: "/opt/adguardhome/conf/ssl/privkey.pem"
```

### 第二步 — acme.sh（受限网络下的安装）

`github.com` 与 `codeload.github.com` 直连可能返回 000，而 `raw.githubusercontent.com` 正常 —— **不要下 tar.gz 包，逐文件取**：

```bash
mkdir -p /root/.acme.sh/dnsapi
curl -sL https://raw.githubusercontent.com/acmesh-official/acme.sh/master/acme.sh \
  -o /root/.acme.sh/acme.sh && chmod +x /root/.acme.sh/acme.sh
curl -sL https://raw.githubusercontent.com/acmesh-official/acme.sh/master/dnsapi/dns_cf.sh \
  -o /root/.acme.sh/dnsapi/dns_cf.sh
```

`acme.sh` 是自包含脚本，**不需要 `--install`**。反而在脚本已经落到 `$HOME/.acme.sh/acme.sh` 之后再跑 `--install` 会报
`cp: 'acme.sh' and '/root/.acme.sh/acme.sh' are the same file` 并中止，`dnsapi/` 一个文件都不会复制 —— 上面两条 curl 已经把这件事做完，`--version` 能跑就说明可用。

### 第三步 — 签发与续期钩子

```bash
export CF_Token='...'        # 或 CF_Key + CF_Email（Global API Key）
/root/.acme.sh/acme.sh --issue -d adg.<domain> --dns dns_cf --keylength ec-256
/root/.acme.sh/acme.sh --install-cert -d adg.<domain> --ecc \
  --key-file       /root/AdGuardHome/ssl/privkey.pem \
  --fullchain-file /root/AdGuardHome/ssl/fullchain.pem \
  --reloadcmd      "docker restart adguardhome"
```

`--reloadcmd` 在**每次续期成功后**执行，这就是闭环；AGH 启动时读 `certificate_path`，不必再改 yaml。

**接手一台“已经有 acme.sh 在跑”的机器时，先 grep 三项再判断续期能不能用**——文件存在不等于续期会生效：

```bash
grep -E 'Le_RealCertPath|Le_RealKeyPath|Le_NextRenewTimeStr' \
  /root/.acme.sh/<domain>_ecc/<domain>.conf
grep -c 'Le_ReloadCmd=' /root/.acme.sh/<domain>_ecc/<domain>.conf   # 必须为 1
```

两个真实陷阱：

- **`Le_RealCertPath` 指向的是 `cert.pem`（叶子证书，无中间链），而服务用的是 `fullchain.pem`** —— 续期只更新 `cert.pem`，服务读的那份永远停在旧证书。表面上 cron 天天在跑、文件 mtime 也在变，到期那天照样挂。
- **`Le_ReloadCmd` 为空或 `-`** —— 文件更新了但服务不 reload，进程仍持有旧证书。

修法就是重新跑一遍带 `--fullchain-file` 与 `--reloadcmd` 的 `--install-cert`，然后 **必须做一次 `--renew --force` 演练** 看 serial 是否真变化、reload 是否真执行；消耗 1 次 LE 配额（限流 5 次/周/域名）换一个确定结论，值得。

迁移或复用场景优先找现成资产：`ls -d /root/.acme.sh/*_ecc/`，已有覆盖目标域的通配符证书就直接 `--install-cert` 到新路径，比重新签一张快，且续期链路已经在那里。

Alpine 是 busybox crond，续期任务写在 `/etc/crontabs/root`（没有 systemd timer）：

```
17 3 * * * /root/.acme.sh/acme.sh --cron --home /root/.acme.sh > /dev/null
```

`--cron` 只在剩余 <30 天时真正续期，天天跑是幂等的。

### 凭据从哪来（别在 1Panel 里找）

1Panel v2 把 DNS 账号存在 `/opt/1panel/db/agent.db` 的 `website_dns_accounts.authorization`，但那是 **AES 密文**：base64 长度约 94，而真实 Cloudflare Global Key 是 37 字符十六进制，拿密文当 `X-Auth-Key` 会返回 `Invalid format for X-Auth-Key header`。密钥不在进程 environ、不在 `/opt/1panel/conf`、也不在 core.db 的 settings 表里可读位置 —— **读到密文不等于能用，不要承诺"从 1Panel 复用凭据"**。正确做法是让用户在 Cloudflare 后台取 Global API Key，或新建 `Edit zone DNS` 限权 Token。

### 到期审计（每次体检必做）

```bash
echo | openssl s_client -connect 127.0.0.1:443 -servername adg.<domain> 2>/dev/null \
  | openssl x509 -noout -subject -dates
ls -d ~/.acme.sh 2>/dev/null; crontab -l 2>/dev/null | grep -i acme; systemctl list-timers 2>/dev/null | grep -i cert
```

**AGH 内嵌证书不在 `/etc/letsencrypt`，因此不会被同域通配符证书的 acme 续期覆盖** —— 三处续期痕迹全空 + 到期在 30 天内即 P0。到期后客户端的 `encrypted-dns-server` TLS 校验失败，静默回落明文 53 或备用 DoH，表现为"部分站点偶发异常"而不是报错，极难事后归因。

## Pitfalls index (read these once before starting)

- **证书续期闭环**：只要 `tls` 段是内嵌 PEM，这个部署就没有续期能力。先切 `certificate_path`，再接 acme.sh；顺序颠倒会多走一轮 yaml 手术。
- **连续 ssh 同一台内网机**：短时间内多次连接会被拒（`Permission denied` 而非 timeout），等 30–60 s 即恢复；批量巡检时每条之间插 `sleep 5`，否则中途掉线会让人误判成密码或 fail2ban 问题。
- **Path case**: `/home/AdGuardHome/` (capital A) vs `/home/adguardhome/` (lowercase). The live container uses lowercase; the user's compose file usually has capital. **Match the compose to the live mount before `up -d`.**
- **0.0.0.0:3000**: should be `127.0.0.1:3000` for the UI port. The plain HTTP UI does not need to be on the public internet — the reverse proxy handles all inbound.
- **Root YR intermediate cert**: 3-cert chain breaks `proxy_ssl_verify on`. Use `off` for local upstreams.
- **1Panel v1 vs v2 paths**: in v2.2.2 user sites go in `/opt/1panel/www/conf.d/`, NOT `/www/server/panel/vhost/`.
- **`openresty -s reload` (not `nginx -s reload`)**: the openresty image's binary is named `openresty`. Both accept the same signals.
- **`default_server` `ssl_reject_handshake on`**: any 443 hit without a matching `server_name` gets TCP-RST'd. Don't try to debug by `curl -k https://127.0.0.1/` from inside the openresty container — use `--resolve` with the actual domain name.
- **No public DNS record**: the cert is valid, AGH serves correctly, but no client can reach the IP because the subdomain doesn't resolve. Check `dig +short <domain> @1.1.1.1` first.
- **Public-IP MITM risk vs. local-IP MITM risk**: this design assumes a public IP exposed on the internet. The DoH endpoint is reachable by anyone. The anti-scanner random path + the future ClientID allowlist are the primary defenses. Don't expose port 3000 or 8443 directly to the internet.
- **Surge VM DNS hijack on macmini**: if the user tests `dig +short <domain>` on their Mac and gets a `198.18.0.0/15` answer, that's Surge intercepting — not the real DNS. Use `dig +short @1.1.1.1` to bypass.
- **`scp-then-bash` > `cat | ssh 'bash -s'`**: see `remote-server-ops` skill gotcha #5; deploy a script once with scp and re-run it instead of streaming it. The deployment sequence has many `set -e` traps where the streaming variant kills the connection on first non-zero.
- **`sed -i` on yaml will crash-loop AGH if you break indentation.** AGH v0.107 uses `go-yaml` which fails parse with "mapping values are not allowed in this context" the moment you produce an unindented `- 1.2.3.4` after `trusted_proxies:`. AGH enters a crash-restart loop on bad yaml and **refuses `docker exec`** until the file is fixed. Recipe for safely rewriting a single yaml block (must run with container stopped, edit host bind-mount path directly):
  ```bash
  docker stop adguardhome
  python3 - <<'PYEOF'
  p = "/opt/1panel/docker/compose/dns-server/adguardhome/conf/AdGuardHome.yaml"
  with open(p) as f: lines = f.read().split("\n")
  out, i = [], 0
  while i < len(lines):
      line = lines[i]
      if line.startswith("  trusted_proxies:"):
          out.append(line); i += 1
          # skip existing 4-space-indented items
          while i < len(lines) and lines[i].startswith("    "):
              i += 1
          out.extend([
              "    - 127.0.0.0/8", "    - ::1/128",
              "    - 172.19.0.0/16", "    - 172.28.0.0/16",
              "    - 172.17.0.0/16", "    - 10.0.0.0/8"])
      else:
          out.append(line); i += 1
  open(p, "w").write("\n".join(out))
  PYEOF
  docker start adguardhome
  docker logs adguardhome --tail 5   # confirm "starting https server" appears
  ```
  Inline heredoc from `ssh ... bash -c` is the same trap — bash quoting inside `<<` heredocs inside `ssh '...'` inside `docker exec` is fragile. Write the python to a file first (`scp` it, or use `write_file` to /tmp on the host and scp), then run it.
- **Always verify `docker logs adguardhome` after editing yaml**, before assuming the change took. AGH silently uses the OLD config if the new one fails parse, and only `docker logs` reveals that.

## "Public 443 fails but inside-container works" — the tcpdump-vs-curl disambiguation recipe

The single most common end-state for this skill is: AGH runs fine, openresty config is valid, the inside-container test returns `200`, but the user's `curl https://your-domain/` from their Mac returns `SSL_ERROR_SYSCALL` (or `SSLEOFError`, or `Connection reset by peer`). The skill's existing checklist line "if public test fails but inside-container test passes, it's the network path" is correct but **operators need a procedure to prove which side is at fault** before they tear apart a working deployment.

The recipe below distinguishes the four realistic causes:

| Cause | Symptom on public test | What the pcap shows |
|---|---|---|
| **A. Server actually broken** | Connection never completes OR completes with wrong cert | Server SYN-ACK absent, or ServerHello never sent, or cert CN mismatch |
| **B. Cloud security group / firewall** | `Connection refused` or `Connection timed out` | **Nothing arrives at eth0** — pcap empty |
| **C. Client-network MITM (the common one)** | `SSL_ERROR_SYSCALL` AFTER successful TCP+SYN-ACK+ClientHello ACK | Server SYN-ACK normal, server ACKs the ClientHello, server **never sends ServerHello** → client RSTs after timeout → curl reports `SSL_ERROR_SYSCALL` |
| **D. SNI mismatch / `ssl_reject_handshake on`** | Server FIN's immediately after ClientHello | Server sends **7-byte TLS Alert (`unrecognized name`, alert 112)** then FIN |

**There is also a one-shot version of this recipe in `scripts/diag-public-443.sh`** — pass `--public-ip`, `--domain`, `--out`, and it runs the tcpdump, waits for traffic, then prints the verdict (A/B/C/D) automatically. Use it instead of typing the tcpdump incantation by hand.

**Run this from inside the openresty container, while the public test runs from the user's machine:**

```bash
# On the host: start a targeted tcpdump, then trigger from outside.
# Use -i any and a tight BPF so you only capture the diagnostic connection.
nohup tcpdump -i eth0 -nn -s 0 -w /tmp/diag.pcap \
    "tcp port 443 and host <SERVER_PUBLIC_IP>" -c 40 \
    > /tmp/diag.log 2>&1 &
TCPDPID=$!

# Wait briefly so tcpdump is definitely up before the client hits the endpoint.
sleep 1

# Have the user (or curl on macOS) hit the endpoint now.
# curl --resolve your-domain:443:<SERVER_PUBLIC_IP> -k -v https://your-domain/...

sleep 3
kill $TCPDPID 2>/dev/null; wait 2>/dev/null
tcpdump -r /tmp/diag.pcap -nn
```

Read the pcap top-to-bottom:

```
# If the pcap is empty for the public IP → cause B (security group).
# If SYN-ACK is sent and ACK comes back, then ClientHello is ACKed, then FIN+7-byte Alert → cause D (SNI mismatch).
# If SYN-ACK is sent and ACK comes back, ClientHello is ACKed, then **client RSTs** with **no server response** → cause C (client-network MITM).
# If SYN-ACK is absent or ServerHello is malformed → cause A (server config).
```

**Cause C test — the instant portable bypass:** if you suspect client-network MITM (router/ISP/企业网关 intercepting 443 outbound), add a temporary vhost on the same server listening on a non-standard TLS port like `8443`, with the **same** cert and the **same** `proxy_pass` to AGH:

```nginx
# /opt/1panel/www/conf.d/diag-8443.conf
server {
    listen 8443 ssl;
    listen [::]:8443 ssl;
    http2 on;
    server_name _;
    ssl_certificate     /usr/local/openresty/nginx/conf/ssl/<site>/fullchain.pem;
    ssl_certificate_key /usr/local/openresty/nginx/conf/ssl/<site>/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    location / { proxy_pass http://127.0.0.1:3000/; proxy_set_header Host $host; }
}
```

```bash
docker exec <openresty> openresty -t && docker exec <openresty> openresty -s reload
/usr/sbin/iptables -I ufw-user-input -p tcp --dport 8443 -j ACCEPT  # see PATH pitfall below
```

If `curl -k https://<SERVER_PUBLIC_IP>:8443/` works from the user's Mac but `:443` does not, you have **proven** cause C. The 8443 vhost can stay as a permanent fallback or be removed once the user's network is fixed.

### Cause A sub-cases specific to 1Panel openresty (the usual suspects)

When the pcap says the server side is broken, work through these:

1. **`PATH` doesn't include `/usr/sbin`** in fresh 1Panel shells, so `which iptables`/`which nft` return empty. Always use absolute paths: `/usr/sbin/iptables`, `/usr/sbin/iptables-save`. (`ufw` is similarly not on PATH; the binary is `/usr/sbin/ufw`.) This makes it look like the firewall isn't configured when in fact it is — a classic time-waster.

2. **1Panel OpenResty container runs in `host` network mode.** Inside the container, `127.0.0.1` IS the host loopback. So `proxy_pass http://127.0.0.1:3000` from the openresty vhost reaches the AGH port published on host loopback. **Do not** assume the container needs to be on the AGH docker network; it doesn't.

3. **`00.default.conf` ships with `listen 443 ssl default_server; ssl_reject_handshake on;`** in `/usr/local/openresty/nginx/conf/default/`. Any HTTPS hit whose `Host:` / SNI doesn't match a real `server_name` gets the 7-byte Alert → FIN. Verify SNI is being sent by the client with `docker exec <openresty> openssl s_client -connect 127.0.0.1:443 -servername <your-domain> -brief` from inside the container. If the user's curl is hitting `https://<SERVER_PUBLIC_IP>/` (no SNI=domain), it'll always fail. Make them use the hostname, or use `curl --resolve`.

4. **WAF lua module**: `/usr/local/openresty/1pwaf/waf.lua` runs on every request via `access_by_lua_file`. If WAF is mis-tuned it can drop legitimate requests silently. Check `docker logs` for WAF block messages and `/usr/local/openresty/1pwaf/data/conf/waf.conf` for current rules.

5. **Two `1Panel-openresty-XXXX` containers may exist** if the user changed site configs without a clean restart — one old worker handles requests with stale config while a new worker does nothing. `docker ps --format '{{.Names}} {{.Status}}'` and check which container the reload actually targeted.

6. **Tencent Cloud Lighthouse (and other VPS providers) puts the public IP on a NAT** — eth0 is a private RFC1918 address (e.g. `172.17.0.13/20`), and `1.15.50.225` is the NATted public IP. This means **`ss -tn` shows connections to `172.17.0.13:443`, not `1.15.50.225:443`** — don't panic when filtering tcpdump for the public IP and seeing the private one.

7. **Tencent Cloud `YJ-FIREWALL-INPUT` / `sgagent` / `YunJing` agents** are installed by default and run as separate processes. They don't usually block 443 inbound, but if you're desperate, `ls /usr/local/qcloud/YunJing/YDEyes/` to confirm the agent is doing nothing harmful; their blacklist is in `nft list chain ip filter YJ-FIREWALL-INPUT`.

8. **`/etc/iptables/rules.v4` is overwritten by a Tencent Cloud cron** (`@reboot iptables-restore < /etc/iptables/rules.v4` + a `*/5 * * * *` cron running `stargate/admin/start.sh` that resets state). If the user added iptables rules by hand, they may vanish within 5 minutes. Use 1Panel's own firewall API or the ufw-managed chain (`ufw allow`) instead.

### Verification checklist (run all of these after deploying)

- [ ] `docker exec adguardhome sh -c "grep -c 'BEGIN CERTIFICATE' /opt/adguardhome/cert/fullchain.pem"` → `3`
- [ ] `docker logs --tail 30 adguardhome | grep -E 'starting https server|webapi: serving url=https'` → present
- [ ] `docker exec <openresty> openresty -t` → `syntax is ok`
- [ ] From inside the openresty container, `curl --resolve doh.example.com:443:127.0.0.1 https://doh.example.com/q-.../` → `404` (your `location /` returns 404)
- [ ] Same container, `curl https://doh.example.com/ag-.../` → `302` redirect to `/login.html`
- [ ] Same container, POST a DNS query to `/q-.../` → `200`, `application/dns-message`, decoded RCODE=0 AN≥1
- [ ] From the public internet (curl from a non-LAN host): same `200` response. **This is the only test that proves end-to-end.**
- [ ] `docker logs --tail 50 adguardhome | grep -E 'starting https server|certificate does not verify'` → no `certificate does not verify` errors
- [ ] **Client IP in AGH web UI matches the actual public client IP**, not a docker bridge gateway like `172.19.0.1`. If it doesn't, run `scripts/verify-trusted-proxies.sh` to confirm `trusted_proxies` is set correctly.

If the public-internet test fails but the inside-container test passes, the problem is in the network path (firewall, ISP blocking 443, missing DNS A record) — not in the deploy.
