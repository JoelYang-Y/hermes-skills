---
name: adguardhome-doh-cert-renewal
description: Use when 给 AdGuardHome DoH 证书签发或自动续期。
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [adguardhome, acme, letsencrypt, doh, cloudflare, certificate]
    related_skills: [surge-config-operations, adguardhome-doh-deploy, site-egress-check]
---

# AdGuardHome DoH 证书签发与自动续期

给内网 AdGuardHome 的加密 DNS 端点（如 `adg.jhsweetheart.com`）签发并自动续期 Let's Encrypt 证书。

## When to Use

- 用户问「AGH 证书快过期了 / 续期 / 换证书」
- DoH 端点报证书过期，Surge `encrypted-dns-server` 开始回落明文
- 需要给内网服务签发新域名证书

## 前置判断（决定用哪种验证方式）

```bash
curl -s -H 'accept: application/dns-json' \
  'https://cloudflare-dns.com/dns-query?name=<domain>&type=A'
```

- **Status 3 / 无 A 记录** → 只能 DNS-01，必须有能改 DNS 的 API 凭据
- 有公网 A 且 80 端口可达 → 可 HTTP-01（内网机器通常不可行）

## 关键事实：AGH 支持从文件读证书

AdGuardHome `tls` 段有四个字段：

```yaml
tls:
  certificate_chain: ""        # 内嵌 PEM（旧方式，续期要改 yaml）
  private_key: ""
  certificate_path: "/opt/adguardhome/conf/ssl/fullchain.pem"   # 文件方式
  private_key_path: "/opt/adguardhome/conf/ssl/privkey.pem"
```

**优先用 `certificate_path`**：acme.sh 续期后只需重启容器，不必改 yaml。
v0.107.79 已验证支持（二进制里 `certificate_path|private_key_path` 命中 215 处）。

## 实施步骤

### 1. 备份

```bash
Y=/root/AdGuardHome/AdGuardHome.yaml
cp -a $Y $Y.bak-cert-$(date +%Y%m%d-%H%M%S)
cp -a /etc/crontabs/root /etc/crontabs/root.bak-cert-$(date +%Y%m%d-%H%M%S)
```

### 2. 装 acme.sh（Alpine 主机）

⚠️ 内网 Alpine 主机上 `github.com` / `codeload.github.com` 常返回 000（被墙），但 `raw.githubusercontent.com` 正常。

```bash
mkdir -p /root/.acme.sh /root/.acme.sh/dnsapi
curl -sL https://raw.githubusercontent.com/acmesh-official/acme.sh/master/acme.sh \
  -o /root/.acme.sh/acme.sh && chmod +x /root/.acme.sh/acme.sh
curl -sL https://raw.githubusercontent.com/acmesh-official/acme.sh/master/dnsapi/dns_cf.sh \
  -o /root/.acme.sh/dnsapi/dns_cf.sh
```

**不要用 `acme.sh --install`**：当 acme.sh 已被直接下载到 `--home` 目标路径时，它会报
`cp: 'acme.sh' and '/root/.acme.sh/acme.sh' are the same file` 然后 Installation failed。
直接从 `/root/.acme.sh/acme.sh` 运行即可，无需 `--install`。

### 3. 签发（Cloudflare DNS-01）

```bash
export CF_Token='<token>'
cd /root/.acme.sh
./acme.sh --issue --dns dns_cf -d adg.jhsweetheart.com \
  --keylength ec-256 --accountemail 'admin@example.com' --server letsencrypt
```

签发成功后 acme.sh 会自动把 `CF_Token` 持久化到 `account.conf` 的 `SAVED_CF_Token`，
**cron 环境无需再 export**。验证：`grep -oE '^SAVED_CF_[A-Za-z_]+' account.conf`。

### 4. 安装到挂载目录

AGH 容器把 `/root/AdGuardHome` 同时挂到 `/opt/adguardhome/conf` 和 `/opt/adguardhome/work`：

```bash
./acme.sh --install-cert -d adg.jhsweetheart.com --ecc \
  --key-file       /root/AdGuardHome/ssl/privkey.pem \
  --fullchain-file /root/AdGuardHome/ssl/fullchain.pem \
  --ca-file        /root/AdGuardHome/ssl/ca.pem \
  --reloadcmd      'docker restart adguardhome'
```

`--reloadcmd` 会以 base64 存进 `Le_ReloadCmd`，每次续期后自动执行。

**装完必须回查 conf 里三项真的写进去了**（文件存在不等于续期会生效）：

```bash
grep -E 'Le_RealCertPath|Le_RealKeyPath|Le_NextRenewTimeStr' \
  /root/.acme.sh/<domain>_ecc/<domain>.conf
grep -c 'Le_ReloadCmd=' /root/.acme.sh/<domain>_ecc/<domain>.conf   # 必须为 1
```

若 `Le_RealCertPath` 指向 `cert.pem` 而不是你在用的 `fullchain.pem`，
续期后 nginx/AGH 用的那份永远不会更新——表现为「定时任务一直在跑，证书却越来越旧」。

验证密钥匹配：
```bash
a=$(openssl x509 -in fullchain.pem -noout -pubkey | openssl sha256)
b=$(openssl pkey -in privkey.pem -pubout | openssl sha256)
[ "$a" = "$b" ] && echo KEY_MATCH_OK
```

### 5. 改 yaml 用文件方式（删内嵌 PEM）

主机无 python3，用 awk 状态机安全删除多行 PEM：

```bash
awk '
/^  certificate_chain: / { print "  certificate_chain: \"\""; skip=1; next }
/^  private_key: /       { print "  private_key: \"\""; skip=1; next }
/^  certificate_path: /  { print "  certificate_path: \"/opt/adguardhome/conf/ssl/fullchain.pem\""; skip=0; next }
/^  private_key_path: /  { print "  private_key_path: \"/opt/adguardhome/conf/ssl/privkey.pem\""; skip=0; next }
skip==1 { next }
{ print }
' $Y > /tmp/agh_new.yaml

grep -c 'BEGIN CERTIFICATE\|BEGIN PRIVATE KEY' /tmp/agh_new.yaml   # 必须为 0
cp -a /tmp/agh_new.yaml $Y && chmod 600 $Y && docker restart adguardhome
```

依赖顺序：`certificate_chain` → `private_key` → `certificate_path` → `private_key_path`。
skip 标志在遇到 `certificate_path` 时归零，正好只吃掉三段 PEM、不误删后续字段。

### 6. cron

```bash
grep -q 'acme.sh --cron' /etc/crontabs/root || \
  echo '17 3 * * * /root/.acme.sh/acme.sh --cron --home /root/.acme.sh >> /var/log/acme-renew.log 2>&1' \
  >> /etc/crontabs/root
kill -HUP $(pidof crond | awk '{print $1}')
```

### 7. 验证（三项都要做）

```bash
# ① 证书本身
echo | openssl s_client -connect 127.0.0.1:443 -servername <domain> 2>/dev/null \
  | openssl x509 -noout -subject -serial -dates

# ② 严格校验的 DoH 解析（POST wireformat，verify 必须为 0）
curl -s -o /tmp/dr.bin -w 'HTTP=%{http_code} verify=%{ssl_verify_result}\n' \
  -H 'content-type: application/dns-message' --data-binary @/tmp/dq.bin \
  https://<domain>/dns-query

# ③ cron 判定（不能真的续期，只看输出）
/root/.acme.sh/acme.sh --cron --home /root/.acme.sh | tail -5
# 期望：Skipping. Next renewal time is: <日期>
```

### 8. 强制续期演练（证明链路真的能无人值守跑通）

```bash
BEFORE=$(openssl x509 -in /root/AdGuardHome/ssl/fullchain.pem -noout -serial)
/root/.acme.sh/acme.sh --renew -d <domain> --ecc --force
sleep 8
AFTER=$(openssl x509 -in /root/AdGuardHome/ssl/fullchain.pem -noout -serial)
[ "$BEFORE" != "$AFTER" ] && echo 续期链路通
```

消耗 1 次 LE 签发配额（限流 5 次/周/域名），值得做——不做就无法确认 reloadcmd 真的会执行。

## 陷阱

1. **Alpine busybox date 解析不了 openssl 日期**：日志出现 `Cannot parse _ssldate2time Jan 26 12:03:49 2027 GMT`。
   不影响续期——acme.sh 改用 ARI 窗口（`ARI suggestedWindow`）计算 Next renewal，`--cron` 判定正常。
2. **macOS 上 Python urllib 验不了 LE 证书**（`unable to get local issuer certificate`）：
   该 Python 链的是 LibreSSL、不吃系统钥匙串。验证证书请用 `curl`（看 `ssl_verify_result=0`）或 `openssl s_client`，
   不要因为 Python 报错就判定证书链坏。
3. **macOS `openssl x509 -ext` 不存在**（LibreSSL 精简版），用 `openssl s_client ... | openssl x509 -text` 代替。
4. **1Panel 的 DNS 账号密钥取不出**：`website_dns_accounts.authorization` 是 AES 密文（约 94 字节），
   UI 只显示掩码，`ENCRYPT_KEY` 不在进程环境 / 配置文件 / settings 表里。别在这上面耗时间，直接找用户要 Token。
5. **Surge 侧最终判据是 `CP=doh`**：改完证书后在 AGH querylog 里确认 `"CP":"doh"` 仍占多数、
   且 `"IP":"10.0.0.2"`。若证书有问题 Surge 会静默回落明文 53，CP 就不再是 doh。
6. **docker restart 只中断 DNS 2-3 秒**，Surge 有 `dns-server` 第二项兜底，无需担心。
7. **`--install-cert` 不是一次性动作，它才能真正定义续期行为**：漏掉 `--fullchain-file`，
   acme.sh 只在 `Le_RealCertPath` 里存 `cert.pem`（叶子证书、无中间链）；漏掉 `--reloadcmd`，
   `Le_ReloadCmd` 为空，续期只改文件不 reload。两者任一缺失，到期那天都是静默失败。
   接手一台已有证书的机器时，先 grep 这三项再判断“续期能不能用”，不要只看文件 mtime。
8. **迁移/复用证书时先查现成资产**：`ls -d /root/.acme.sh/*_ecc/` 找到已覆盖目标域的通配符证书
   就直接 `--install-cert` 到新路径复用，比重新签发快，且续期链路已经在那里了。

## 交付话术

证书换完后必须清晰对照旧/新有效期，并说明下一步自动发生的时间点（如「2026-12-27 自动续期」），
让用户不用记这件事。若凭据曾在聊天中明文出现，主动提示轮换。
