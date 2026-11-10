# 服务器退役与域名迁移

一台云主机退役（账号失效、资源回收、换提供商、降本）时，把它的资产记录清干净、
把还需要的服务迁到新机器。核心原则：**一台机器不是一个 IP，是一组跨六层的引用。**
只清理看得见的那层等于没清。

## 一、先清查，不要先动手

在任何删除操作之前，把六层引用全部列出来：

| 层 | 怎么查 |
| :--- | :--- |
| 记忆库 | `mem0_search` 用「机器名 / IP / 角色关键词」多轮检索，记录命中的 memory_id |
| SSH 与密钥 | `grep -n "<ip>\|<alias>" ~/.ssh/config`；`ls ~/.ssh/ | grep -i <name>`；`ssh-keygen -R <ip>` 查 known_hosts |
| 本地脚本与文档 | `grep -rl "<ip>\|<机器名>" ~/scripts ~/.hermes/scripts ~/Documents/<笔记目录>` |
| 规则集仓库 | `grep -rn "<ip>" <repo>/ --include="*.list" --include="*.md"`（含 `IP-CIDR,<ip>/32` 与 README 说明） |
| 公网 DNS | Cloudflare API 拉全量记录，按 content 过滤 |
| 监控与告警 | Uptime Kuma / Beszel / Gatus 里的探针与采集目标 |

清查结果先汇总成清单再改，避免改一半发现漏了某层。

## 二、别名重命名：多别名指向新机，不要删旧别名

退役后如果只剩一台，把**所有历史别名写在同一行指向新 IP**：

```
Host oci oci2 oci-arm
    HostName <new-ip>
    User root
    Port 59421
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking no
```

原因：cron、脚本、历史命令、肌肉记忆都在用旧别名。删掉别名会让 `ssh oci2` 静默失败，
而你很难第一时间意识到那是别名问题而不是机器问题。

配套三件：

```bash
chmod 600 ~/.ssh/config
mv ~/.ssh/<old-key> ~/.hermes/cache/scratch/<retired>/   # 移出 .ssh，不直接 rm
ssh-keygen -R <old-ip>                                   # 清 known_hosts 旧指纹
```

私钥**移出而非删除**：放到 scratch 目录（按策略自动过期），既满足「从常规位置清除」，
又给一个短窗口反悔。

## 三、规则集里的 IP `/32` 必须删

`IP-CIDR,<retired-ip>/32,no-resolve` 这类精确规则清不清？**必须清。**

理由不是整洁：IP 释放后会可能被其他客户获得，你残留的 `/32` 会让陌生人的流量
命中你配置的策略（走代理 / 走家宽），既是路由污染也是不必要的信任面。

```bash
sed -i '' '/^IP-CIDR,<retired-ip>\/32,no-resolve$/d' repo/surge/*.list
```

改完必须**回读远端 Raw**（用 commit SHA 固定链接，绕 CDN 缓存）确认残留为 0，
不能只看 `git push` 成功：

```bash
SHA=$(git rev-parse HEAD)
curl -s "https://raw.githubusercontent.com/<owner>/<repo>/$SHA/surge/<file>" | grep -c '<retired-ip>'
```

## 四、Cloudflare DNS：改指向与删记录

先用 Global Key / Token 拉全量记录，把指向退役 IP 的全部找出来：

```bash
curl -s -H "Authorization: Bearer $TOK" \
  "https://api.cloudflare.com/client/v4/zones/$ZID/dns_records?per_page=100" > /tmp/dns.json
```

两类处理：

```bash
# 服务还需要的域名：PATCH 只改 content，保留 proxied 等其余属性
curl -s -X PATCH -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  --data '{"content":"<new-ip>"}' \
  "https://api.cloudflare.com/client/v4/zones/$ZID/dns_records/<record-id>"

# 服务已消失的域名：DELETE
curl -s -X DELETE -H "Authorization: Bearer $TOK" \
  "https://api.cloudflare.com/client/v4/zones/$ZID/dns_records/<record-id>"
```

注意：

- **`www` 和裸域是两条独立记录**，容易只改一条。
- 橙色云（`proxied=true`）改 content 后**立即生效**，不需要等 TTL。
- 删记录前确认该域名确实没有其他用途（邮件 DKIM、验证记录等是 `CNAME`/`TXT`，不在 A 记录里）。

## 五、目标机准备（迁移前必查）

### 1) 先看有没有现成的通配符证书

```bash
ls -d /root/.acme.sh/*_ecc/
openssl x509 -in /root/.acme.sh/<domain>_ecc/fullchain.cer -noout -subject -dates -text | grep -A1 'Subject Alternative Name'
```

若已有 `*.example.com` 且未过期，**直接复用**——比重新签一张快得多，续期链路也已就绪。

### 2) 静态站：部署后立即改权限

`scp -r` 从 macOS 传文件会保留 600/700，nginx worker 读不到，表现为 **403 而非 404**：

```bash
find /opt/<site> -type d -exec chmod 755 {} \;
find /opt/<site> -type f -exec chmod 644 {} \;
```

### 3) nginx server 块模板

```nginx
server {
    listen 80; listen [::]:80;
    server_name example.com www.example.com;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2; listen [::]:443 ssl http2;
    server_name example.com www.example.com;
    ssl_certificate     /etc/ssl/oracle2/fullchain.pem;
    ssl_certificate_key /etc/ssl/oracle2/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    root  /opt/<site>;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }
    location /assets/ { expires 7d; add_header Cache-Control "public"; }
}
```

部署前先 `nginx -t`，再 `systemctl reload nginx`（不要 restart，会断其他站点）。

### 4) 修 acme.sh 的落盘路径

迁移常发现旧机器的 acme.sh 只装 `cert.pem`（无中间链）且 `Le_ReloadCmd` 为空。
迁移后统一补齐：

```bash
/root/.acme.sh/acme.sh --install-cert -d <domain> --ecc \
  --cert-file      /etc/ssl/<dir>/cert.pem \
  --key-file       /etc/ssl/<dir>/privkey.pem \
  --fullchain-file /etc/ssl/<dir>/fullchain.pem \
  --reloadcmd      "systemctl reload nginx"
```

## 六、验证顺序：回环 → 公网 → 静态资源 → 证书链

```bash
# ① 服务器回环（指定 SNI，绕 DNS）
curl -sk -o /dev/null -w '%{http_code}\n' --resolve example.com:443:127.0.0.1 https://example.com/

# ② 公网
curl -s -o /dev/null -w '%{http_code} %{time_total}\n' https://example.com/

# ③ 静态资源逐个打（JS / 图片 / manifest）—— 只测 HTML 会漏权限问题
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://example.com/assets/app.js

# ④ 证书链层数（通配符+中间证书应为 3-4）
echo | openssl s_client -connect 127.0.0.1:443 -servername example.com -showcerts 2>/dev/null | grep -c '^ *[0-9] s:'
```

回环 200 但公网 526 → 是 Cloudflare 回源证书问题；回环 403 → 是文件权限；
回环 404 → 是 root 路径或 try_files 配错。三种症状对应三种根因，不要混着排查。

## 七、清理顺序

先做**可逆**的（记忆、别名、文档、规则集），最后做**外部可见**的（DNS 切换）。
DNS 一改就是面向公网的状态变更，前面任何一步没准备好都会以 5xx 的形式公开暴露。
