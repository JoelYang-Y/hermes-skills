# 甲骨文机自托管服务部署踩坑实录（2026-08-19 oci2 实测）

## 1. Headscale（v0.29.3 + 嵌入式 DERP）

- **ENTRYPOINT 已是 `headscale`**：compose `command: headscale serve` 会执行成 `headscale headscale serve` → `unknown command "headscale"` 无限重启。**必须写 `command: serve`**。
- **DERP 私钥必须显式配置**：`derp.server.private_key_path: /var/lib/headscale/derp_server_private.key` 缺失时报 `saving private key to disk at path ""`。同时配 `automatically_add_embedded_derp_region: true` 和 `ipv4: <公网IP>`（DERP map 才能对外广播）。
- **配置修改后必须强制重建**：`docker compose down -v && docker compose up -d`，否则旧配置缓存导致修改"看似未生效"。
- 验证运行：日志应出现 `derp region: {RegionID:999 ...}` 与 `stun server started at [::]:3478`。
- 官方模板核对：`curl -sL https://raw.githubusercontent.com/juanfont/headscale/v<tag>/config-example.yaml`（web_extract 可能被安全策略拦，用 curl）。
- DERP 节点 `DERPPort: 443` 意味着 DERP over HTTPS 走 Nginx 443 反代 `/derp`；STUN 走 UDP 3478（iptables 需放行 UDP）。

## 2. n8n（容器数据卷权限）

- **n8n 容器内以 node 用户 (UID 1000) 运行**，宿主机 root 创建的数据目录会导致 `EACCES: permission denied, open '/home/node/.n8n/config'`。
- 修复：`chown -R 1000:1000 /opt/n8n/data && docker compose restart n8n`。
- 首次启动做数据库迁移需 1-2 分钟，`/healthz` 从 000 → 200 属正常；日志尾部出现 `Initializing n8n process` 表示迁移中。

## 3. Dify（docker compose 全家桶）

- **Dify nginx 有两条端口映射**：`${EXPOSE_NGINX_PORT}` (80) 和 `${EXPOSE_NGINX_SSL_PORT}` (443)。只改第一条会残留 `0.0.0.0:443` 与宿主机 Nginx 冲突（`address already in use`）。
- 修复组合：
  - compose 两行都改 `127.0.0.1:${...}:${...}`
  - `.env`: `EXPOSE_NGINX_PORT=8081`、`EXPOSE_NGINX_SSL_PORT=8443`、`NGINX_HTTPS_ENABLED=false`（TLS 由宿主机终结）
  - `SECRET_KEY=$(openssl rand -hex 32)` 写入 `.env`
- 首次启动 14 个容器，镜像总量数 GB，拉取 8-12 分钟属正常；`docker-api-1` 健康检查 `health: starting` 期间返回 000/502 是瞬态。
- 就绪标志：`curl http://127.0.0.1:8081/` 返回 307 → `location: /install`（首次安装引导页）。
- 拉取用 git：`git clone --depth 1 https://github.com/langgenius/dify.git /opt/dify`。

## 4. 宿主机 Nginx 反代

- Ubuntu 24.04 自带 Nginx 1.24 **不支持 `http2 on;` 指令**（1.25.1+ 语法），须用 `listen 443 ssl http2;`，否则 `unknown directive "http2"`。
- 代理 WebSocket 服务（n8n / Dify / Headscale）必须加 `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`。
- Dify 需 `proxy_read_timeout 3600s;` 与 `client_max_body_size 100m;`。
- 验证多站点：`curl -sk -H 'Host: <sub>.jhsweetheart.com' https://127.0.0.1/`。

## 5. rsync 部署路径

- 生产站容器（unified-gateway-nginx）挂载映射：宿主机 `/opt/startpage` → 容器内 `/usr/share/nginx/html/startpage`。
- 旧 deploy.sh 的 `REMOTE_PATH=/usr/share/nginx/html/startpage` 是容器内路径，宿主机不存在 → `rsync error code 11 (unexpected end of file)`。**目标必须是宿主机 `/opt/startpage/`**。
- 路径定位技巧：`docker inspect <nginx容器> --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'`。

## 6. 通用

- 拉 Dify/大镜像前先确认 daemon.json 镜像加速生效（`docker info` 看 Registry Mirrors）。
- iptables 放行新端口：`iptables -C INPUT -p <tcp|udp> --dport <port> -j ACCEPT 2>/dev/null || iptables -I INPUT 3 -p <tcp|udp> --dport <port> -j ACCEPT`，然后 `netfilter-persistent save`。
