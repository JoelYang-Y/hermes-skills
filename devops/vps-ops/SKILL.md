---
name: vps-ops
description: 用户问搬瓦工 VPS/节点/AnyTLS/s-ui/1Panel 时使用，密码方式管理 VPS。
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [vps, bandwagon, anytls, s-ui, 1panel, sing-box, proxy]
    related_skills: [nas-docker-ops, proxy-chain-diagnostics]
---

# VPS Ops (搬瓦工 64.64.237.34)

密码方式管理搬瓦工 VPS：节点服务（s-ui/AnyTLS）、1Panel、Docker、系统状态。

## When to Use

- 用户说「**搬瓦工**」= 64.64.237.34（用户指定别名，与 ATT/NAS 区分）
- 用户说「**NodeMach**」或「**nm**」= 68.164.60.143（CN2 GIA KVM，独立于 BWG 的另一台机器）
- 用户问 VPS / 节点 / AnyTLS / vircs / joel.jhsweetheart.com 的状态、日志、重启
- 用户问 s-ui 面板、1Panel 面板、VPS 磁盘/内存
- 节点连不上时配合 proxy-chain-diagnostics 排查（先本地链路后 VPS 侧）

## 连接信息：搬瓦工（已验证 2026-08-10）

```bash
sshpass -p '<密码>' ssh -p 59421 -o StrictHostKeyChecking=no root@64.64.237.34 "<cmd>"
```

- 用户：`root`，端口 `59421`（非 22），密码 `<密码>`（**尾随句点**，与 NAS/Surge 同款格式）
- 域名：joel.jhsweetheart.com → 64.64.237.34
- 系统：Debian 13 (trixie)，xanmod 7.1.6 内核，KVM 虚拟化（qemu guest agent）
- 资源：**1 GiB RAM**（易 OOM，避免编译/大任务）、19G 盘（约 18% 用）

## NodeMach CN2 GIA（68.164.60.143 · 已验证 2026-11-07）

```bash
sshpass -p '<密码>' ssh -p 59421 -o StrictHostKeyChecking=no root@68.164.60.143 "<cmd>"
```

- 品牌：nodemach（原 VirCS），KVM + 中国电信 CN2 GIA + NVMe 全闪
- 主机名 `nm`，Debian 13 (trixie)，xanmod `7.2.15-x64v3-xanmod1`，KVM（qemu-guest-agent 在跑）
- 规格：**1 核 / 1.9 GiB RAM / 20G 盘（约 15% 用）** —— 与 BWG 同级低配，禁止在上面编译或跑大容器
- 时区 `America/Los_Angeles` (PST)，出口 IP = 本机 68.164.60.143（直出，无链式出站）
- 实测 RTT ~137 ms，ICMP 与 59421 均通，SSH 可正常建立。**但不要误判为直连**：`SSH_CLIENT=68.164.60.143`（源 IP = 目标机自身），说明 Mac mini 发起时命中 Surge 代理规则、经本机 443(xray)/8443(sing-box) 节点出口回环再连回 59421；若为物理 DIRECT，源 IP 应为家宽出口 222.95.190.242。自环验证命令：`ssh root@... 'echo $SSH_CLIENT'`。SSH 断连排查先看 Surge 规则/节点，而非服务器侧

入站清单：

| 端口 | 服务 | 说明 |
|------|------|------|
| 59421 | sshd | 管理入口（v4+v6） |
| 443 | xray 26.10.31 | VLESS + Reality（tcp），outbound freedom/direct + blackhole，routing 规则 0 条 |
| 8443 | sing-box 1.14.4 | AnyTLS 入站（tag `anytls-in`），监听 `::` 双栈 |
| 80 / 127.0.0.1:8444 | nginx 1.26.3 | 反代 `nm.jhsweetheart.com`（静态站 /var/www/nm.jhsweetheart.com/html） |
| 127.0.0.1:3000 | AdGuardHome v0.107.80 | Web 后台，**仅本机可达**，账号 `admin` / 通用密码 |
| 127.0.0.1:5353 | AdGuardHome | 私有 DNS 监听 |
| 127.0.0.1:9443 | nginx | 私有 DoH 入口（`conf.d/adguardhome-private-doh.conf`）：仅放 `GET/POST /dns-query`，`limit_req 50r/s burst=100`，其余 location 直接 404 |

### 访问 AdGuardHome 后台（必须 SSH 隧道）

```bash
ssh -p 59421 -L 3000:127.0.0.1:3000 root@68.164.60.143   # 前台保持，Ctrl-C 即断
# 浏览器 http://127.0.0.1:3000 → admin / 通用密码
```

- 已实测：`POST /control/login` 返 200 + `OK`；`/control/status` 返 `version v0.107.80`、`dns_addresses 127.0.0.1:5353`、`protection_enabled=true`
- 本地 3000 若被占用（如 dsh 相关）换个本地端口即可，远端固定 3000
- **绝对不要把 admin 密码写进导航站卡片描述**：jhsweetheart.com 走 Cloudflare 橙云、公网可访问，且该密码与 root 同款
- 该实例同时提供私有 DoH（9443），AGH 配置里 `tls.doh.insecure_enabled: true`；配置路径 `/var/lib/adguardhome/AdGuardHome.yaml`，历史备份 `/root/doh-backup-*`

## fail2ban（nm 已部署 2026-11-07）

安装：`apt-get install -y fail2ban python3-systemd`。Debian 13 无 rsyslog，`/var/log/auth.log` 是 0 字节空壳，**必须用 journald backend**。

`/etc/fail2ban/jail.local` 关键项（照抄可用）：

```ini
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1 68.164.60.143
backend  = systemd
banaction = nftables
bantime.increment = true
bantime.factor = 2
bantime.maxtime = 1w

[sshd]
enabled  = true
port     = 59421
action   = nftables[port=59421, name=sshd]
maxretry = 5
findtime = 10m
```

**四个必须知道的坑**：

1. **`action` 必须显式带 `port=59421`**。`action.d/nftables.conf` 的 `[Init]` 写死 `port = ssh`（=22），jail 的 `port` 不会传给它。只写 jail 的 `port` 会生成 `tcp dport 22 ... reject`，对 59421 完全无效（实测踩过）。
2. **`banaction = nftables`，不要用 iptables**。nm 的真实防火墙在 `nft table inet filter`（policy drop，放行 80/443/8443/59421）；`iptables -S` 显示三条链全 ACCEPT 是 iptables-nft 兼容层的假象，**不要据此判断机器敞开**。
3. **`ignoreip` 必须含本机公网 IP**。从 Mac mini 连 nm 的 SSH 经本机 xray/sing-box 节点回环，源 IP 恒为 68.164.60.143；不加白名单，任何一次随机认证失败都在给自己记账。这类偶发 `Failed password` 源于回环链路密码传输截断，不是密码错。
4. **手动 `fail2ban-client set sshd banip <IP>` 绕过 ignoreip**。拿它测白名单会把自己封死（实测：封完 SSH 立即 `Connection closed`）。白名单只对自动封禁生效——ignored IP 的失败连 `Total failed` 都不计入。

**自封救援路径**：直连断了就走 BWG 跳板（BWG 需先装 `sshpass`）：

```bash
sshpass -p '<密码>' ssh -p 59421 root@64.64.237.34
apt-get install -y --no-install-recommends sshpass
sshpass -p '<密码>' ssh -p 59421 root@68.164.60.143 'fail2ban-client set sshd unbanip 68.164.60.143'
```

**重启安全性**：`/etc/nftables.conf` 首行是 `flush ruleset`，会清掉 f2b 表；但 `nftables.service` 的 Before 含 `fail2ban.service`，顺序为「flush+建基线 → fail2ban 重建 f2b 表 → 从 `/var/lib/fail2ban/fail2ban.sqlite3` 恢复封禁」，实测安全。

**f2b 链**：`type filter hook input priority filter - 1`（-1 早于基线的 0），`tcp dport 59421 ip saddr @addr-set-sshd reject with icmp port-unreachable`。

**验收方法（端到端，别只看 `status`）**：
- 基线：从 BWG `cat < /dev/null > /dev/tcp/68.164.60.143/59421` 应通
- 非白名单源错密码 6 次 → `Total failed: 5`、`Banned IP list` 出现该 IP
- 该源再连 → `Connection refused`
- unban → 恢复可达

- 证书：Let's Encrypt `nm.jhsweetheart.com`，到期 2027-02-05；存在 `/etc/cron.d/certbot`，但**续期是否真正生效未验证**（BWG 上同类配置曾被证实空转，先按存疑处理）
- **安全面现状（2026-11-07 复核）**：真实防火墙是 nftables `table inet filter`（policy drop，仅放行 80/443/8443/59421，配置在 `/etc/nftables.conf`）；fail2ban 1.1.0 已部署（见下节）

## 服务清单（2026-08-10 实测）

| 服务 | 说明 | 管理方式 |
|------|------|---------|
| s-ui | sing-box 面板（节点核心） | `systemctl status s-ui` / `journalctl -u s-ui -n 100` |
| 1Panel | Linux 管理面板（已配置 OpenResty 反代标准 HTTPS 访问：https://joel.jhsweetheart.com/Joel） | `systemctl status 1panel-core` / `1pctl user-info`；反代必须包含 `/Joel`、`/assets/`、`/public/`、`/resource/`、`/api/` 避免前端转圈 |
| Docker | containerd + docker | `docker ps -a`（当前运行 1Panel-openresty-NmV4） |
| nginx 脚本站（已迁 1Panel OpenResty） | joel.jhsweetheart.com → /opt/1panel/www/scripts（容器内 /www/scripts） | 1Panel 管理；站点配置 /opt/1panel/www/conf.d/scripts.conf，容器 1Panel-openresty-NmV4，重载 `docker exec 1Panel-openresty-NmV4 openresty -s reload` |
| 证书 | Let's Encrypt @ /usr/local/etc/{fullchain,privkey}.pem（2026-11-03 到期），已复制到 1Panel ssl 目录 /opt/1panel/apps/openresty/openresty/conf/ssl/ | 到期前需续期，续期后要同步复制到 1Panel ssl 目录 |
| AnyTLS 节点 | vircs 自建，VLESS+XTLS Vision/Reality（历史） | 走 s-ui |

监听端口（实测）：`59421` SSH / `80` `443`（nginx 脚本站）/ `18848` s-ui 面板 / `18849` `18850` 1Panel / **`21174` s-ui 代理入站（家宽 AnyTLS 入口，承载实际转发流量，不是面板）** / `32636` AnyTLS 入站 / **`12726` xray VLESS Reality 入站（dokodemo-door，固定转发 127.0.0.1:45987）** / `45876` beszel-agent ——**都别乱关**

**链式代理拓扑（用户 2026-08-10 确认）**：搬瓦工 = **入口**（AnyTLS 入站），ATT 107.141.151.219 = **出口**（ss-rust ss2022）。s-ui 面板里把 ATT ss2022 配置为 outbound。Surge 节点 AnyTLS-AT&T = 搬瓦工入口 + ATT 家宽出口（故称 AT&T）；AnyTLS-BWG = 搬瓦工直连出口。排查节点问题时：先查 s-ui 入站，再查 ATT 出口（att-ops 技能）。

## 常用操作模板

```bash
# 系统状态
sshpass -p '<密码>' ssh -p 59421 root@64.64.237.34 "uptime; free -h; df -h / | tail -1"

# s-ui 状态 + 日志
... "systemctl status s-ui --no-pager | head -6; journalctl -u s-ui -n 50 --no-pager"

# 重启 s-ui（节点短暂中断，先问用户）
... "systemctl restart s-ui"

# 端口监听
... "ss -tlnp | head -15"

# Docker
... "docker ps -a"
```

## 入站连接盘点（「谁在连这台机」）

用户问「最近有几个 IP 连了服务器 / 有没有陌生 IP」时用。现成脚本 `scripts/conn_inventory.sh`
（`sshpass ... 'sh -s' < scripts/conn_inventory.sh`），或手动跑：

```bash
for p in 443 59421 32636 21174 12726 18848 18849 18850 45876; do
  echo "=== port $p ==="
  ss -tn state established "sport = :$p" | tail -n +2 \
    | awk '{print $4}' | sed -E 's/:[0-9]+$//' | sort | uniq -c | sort -rn | head -12
done
conntrack -L 2>/dev/null | grep -oE 'src=[0-9.]+' | sort | uniq -c | sort -rn | head -10
last -20 -i; lastb -15 -i; fail2ban-client status sshd
```

**三个解析陷阱（都实测踩过）**：
- `ss -tn state established` 的输出**没有 State 列**（已被 state 过滤器去掉），列序是
  `Recv-Q Send-Q Local Peer`：`$3`=Local、`$4`=Peer。按 `$4/$5` 取会整体错位，
  得到「80 条连到 443」这类假结果，且不会报错。
- 必须用 `sport = :<端口>` 过滤出**入站**。不过滤时表里绝大多数是服务器自己的出站连接
  （临时高位端口 → 外部 443），会把 CDN 目标 IP 误报成「连进来的客户端」。
- 对端常是 IPv6-mapped 形式 `[::ffff:222.95.190.242]`，naive `split(":")` 会切坏并静默丢 IP。

**判读基线**：来自用户自有线路（家宽电信、手机移动）的入站属正常；SSH 登录若全部显示
`from 64.64.237.34`，是用户经本机代理回连、源 IP 被还原成节点自身，**不是**可疑记录——
要看的是 `lastb` 与 fail2ban 的 failed/banned 计数。

## 代理流量可观测性（「访问了什么服务」）

两条入站的日志能力**不一样**，先分清再承诺：

| 入站 | 内核 | 日志里能看到 |
|---|---|---|
| `21174`（家宽经 Surge 走 AnyTLS） | s-ui / sing-box | **真实目标域名**：`inbound connection to meta.graph.meta.com:443` |
| `12726`（手机移动网络走 VLESS Reality） | xray `dokodemo-door` | 只有写死的内网目标 `accepted tcp:127.0.0.1:45987`，**看不到域名** |

```bash
journalctl -u s-ui --since '24 hours ago' --no-pager \
  | grep -oE 'inbound connection to [^ ]+' | sed 's/inbound connection to //; s/:[0-9]*$//' \
  | grep -vE '^[0-9.]+$' | sort | uniq -c | sort -rn | head -40
journalctl -u s-ui --since '24 hours ago' --no-pager \
  | grep -oE 'inbound connection from [0-9.]+' | awk '{print $NF}' | sort | uniq -c | sort -rn
```

**先跑第二条按源 IP 分组**，确认哪条链路真的在记域名，再决定能回答什么——
否则容易把「家宽有数据」讲成「手机也有数据」。答案里要写明覆盖范围。

要让移动流量也进统计，唯一干净做法是让手机切到 AnyTLS（21174）。改 xray 的 dokodemo 开嗅探没用：
xray access log 记的是连接目标，嗅探出的域名不进 `accepted` 行，开 debug 级日志只会被噪音淹没。

## 陷阱

1. **密码带尾随句点** `<密码>`（用户所有设备统一密码格式）
2. **SSH 端口 59421**，不是 22
3. **1 GiB RAM 低配**——docker build、编译、大容器会 OOM，遇内存压力先查 `free -h`
4. **节点配置修改必须征求用户同意**（s-ui 配置直接影响用户代理链路）
5. **只围绕自建节点排查**，勿推荐切机场（奶昔 nexitallysafe.com 仅备用）
6. 面板端口（21174 等）与节点入站端口（32636 等）别乱关，关前先 `ss -tlnp` 确认
7. 历史协议为 VLESS+XTLS Vision/Reality，现已迁移 s-ui/sing-box（Shadowsocks-2022 架构），查配置以 s-ui 为准

## 验证步骤

1. `sshpass -p '<密码>' ssh -p 59421 root@64.64.237.34 "echo OK"` → 连接 OK
2. `systemctl is-active s-ui` → active
3. 变更 s-ui/节点后：用 proxy-chain-diagnostics 验证链路通（Google/Telegram 经代理实测）
4. 重启后必须复核 8 个节点端口：`59421 80 443 18848 18849 18850 21174 32636`

## 证书链与重启

详见 `references/cert-chain-and-reboot.md`。要点：

- 本机**没有** acme.sh，`/etc/cron.d/certbot` 在 systemd 主机上空转；真正的续期者是
  **1Panel 内置定时证书任务**（每日 06:00 续签 joel.jhsweetheart.com 并令 s-ui 重载 AnyTLS 证书）
- **隐型缺口**：该任务不同步 OpenResty 容器内的 ssl 副本
  （`/opt/1panel/apps/openresty/openresty/conf/ssl/`），会出现“续期日志一切正常、证书却会到期”。
  已用 `/usr/local/bin/sync-1panel-ssl.sh` + cron `30 6 * * *` 幂等兼底
- 替换证书前**必须先比对公钥**（同一密钥对才能直接替换，否则会搞挂 HTTPS）
- 判断源站证书不能用 `jhsweetheart.com`（走 CF 代理，看到的是 CF 边缘证书），
  要用 DNS-only 子域如 `oracle.` / `gatus.`
