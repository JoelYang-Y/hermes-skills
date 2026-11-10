---
name: oracle-cloud-ops
description: 用户问甲骨文云 OCI/oci/oci2 运维、部署或清退自托管服务时使用。
version: 2.0.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [oracle-cloud, oci, arm64, selfhosted, nginx, docker]
---

# 甲骨文云 OCI ARM 运维 (Oracle Cloud Ops)

用户持有**一台** OCI Always Free ARM 实例（Ampere A1，2 OCPU / 12GiB / 96GB 根盘），是全网云端生产底座。

⚠️ 原「1 号机」已因甲骨文政策变化退役，资产记录已全部清除。**不要再假设存在第二台实例**，
不要再按旧笔记去连另一个 IP——任何出现第二次 OCI IP 的记录都是历史残渣，须以本表的单一在役实例为准。

## When to Use

- 用户问甲骨文云 / Oracle OCI / oci / oci2 相关运维
- 用户问「这台机器上部署了什么服务」——要实际登录枚举，不能凭笔记背（见「已上线服务」）
- 在甲骨文机上部署新自托管服务（静态站、监控、其他）
- 绑定域名、签证书、配 Nginx 反代、放行防火墙端口
- 排查甲骨文机服务异常、容器状态、端口连通
- 有云主机要退役、或要把域名/服务从一台机器迁到另一台
- 主站返回 Cloudflare 5xx（尤其 526）、证书告警

## 资产与连接

| 别名 | IP | SSH 端口 | 登录方式 | 角色 |
| :--- | :--- | :--- | :--- | :--- |
| `oci` / `oci2` / `oci-arm` | 129.153.89.114 | 59421 | `~/.ssh/id_ed25519` | 唯一在役：主站导航 + 证书，无其他自建服务 |

- **三个别名全部指向同一台**。退役重命名时保留旧别名（写在同一行 `Host oci oci2 oci-arm`），
  这样历史脚本、cron、笔记里的 `ssh oci2` 不会静默失效——比改名后逐个修引用更省事且不会漏。
- root 密码登录备用；免密失效时用 `sshpass -p '<pass>' ssh-copy-id -p 59421 -i ~/.ssh/id_ed25519.pub root@<ip>` 重推公钥。
- **本机直连不通时的手动登录**（用户问「这机器我怎么登录」就给这一行）：
  `ssh -J root@64.64.237.34:59421 -p 59421 root@129.153.89.114`
  交互式 `-J` 在 BWG 与 OCI 同密码时实测只提示一次密码就进去了，不要为了让用户「少输一次」去堆复杂方案；
  脚本化 / 免交互才需要下面那套 `SSH_ASKPASS_REQUIRE=force`。
- 系统：Ubuntu 24.04 ARM64；**禁止启用 ufw**（会覆盖 Docker iptables 链并可能锁死 SSH），端口用原生 iptables + netfilter-persistent。

## 安全与保活基线

1. **NeverIdle 保活**：`-cp 0.25 -m 3 -n 4h`，防 OCI 7 天 95 分位 <20% 回收。
2. **Fail2ban**：监控 59421，maxretry=3/findtime=10m/bantime=1d，ignoreip 白名单 = `127.0.0.1/8 ::1 108.230.34.31 64.64.237.34 129.153.89.114`。
   IP 变更（如 AT&T 家宽换 IP）后必须同步改 ignoreip，否则新出口会被自己封掉。
3. **Docker 镜像加速**：`/etc/docker/daemon.json` 用 `docker.1ms.run` 等可用源。
4. **泛域名证书**：acme.sh Cloudflare DNS-01 签发 `jhsweetheart.com + *.jhsweetheart.com` ECC-256，落盘 `/etc/ssl/oracle2/`（cert.pem / fullchain.pem / privkey.pem，fullchain 应为 4 层链）。

## 证书续期：查落盘路径，不要只查文件存在

aсme.sh 的续期是否真的会生效，取决于 conf 里三项，缺一即静默失效：

```bash
grep -E 'Le_RealCertPath|Le_RealKeyPath|Le_NextRenewTimeStr' \
  /root/.acme.sh/<domain>_ecc/<domain>.conf
grep -oE 'Le_ReloadCmd=.*' /root/.acme.sh/<domain>_ecc/<domain>.conf
```

两个真实陷阱：

- **只装了叶子证书**：`Le_RealCertPath` 指向 `cert.pem`，而 nginx 配的是 `fullchain.pem`。续期只更新 `cert.pem`，
  nginx 用的那份永远停在旧证书，到期后站点直接挂——从外部看就是「续期一直在跑但证书没变」。
- **`Le_ReloadCmd` 为空 / `-`**：文件更新了但 nginx 不 reload，进程仍持有旧证书。

修法（一次补齐，之后 cron 自动走这条链路）：

```bash
cd /root/.acme.sh
./acme.sh --install-cert -d <domain> --ecc \
  --cert-file      /etc/ssl/oracle2/cert.pem \
  --key-file       /etc/ssl/oracle2/privkey.pem \
  --fullchain-file /etc/ssl/oracle2/fullchain.pem \
  --reloadcmd      "systemctl reload nginx"
```

修完必须做一次强制续期演练（`--renew --force`，看 serial 是否变化 + `Reload successful`），
否则等于没验证——消耗 1 次 LE 配额（限流 5 次/周/域名）换一个确定的结论，值得。

## 远程执行多行命令：用 heredoc，不要堆内联引号

多层引号嵌套（ssh + shell + grep/sed 的正则）几乎一定会出错，典型症状是
`unexpected EOF while looking for matching '`，或者更危险的情况：**引号提前闭合，
远程命令被本地 shell 执行**（输出里出现本机路径的 `No such file or directory` 就是它）。

固定写法：

```bash
ssh -o BatchMode=yes oci 'bash -s' <<'REMOTE'
echo "步骤一"
ls -la /etc/ssl/oracle2/
grep -E "Le_RealCertPath|Le_ReloadCmd" /root/.acme.sh/<domain>_ecc/<domain>.conf
REMOTE
```

`<<'REMOTE'` 加引号才是关键——它阻止本地展开变量与命令替换，引号层级立刻归零。
远程脚本里就可以自由地用单/双引号写 grep 正则。

### 本机连不上时：经搬瓦工跳板进 OCI

确认是本机分流问题、而 BWG 出口（64.64.237.34）在 fail2ban 白名单内时，用 BWG 做跳板是最快的恢复路径。
BWG 上没有 sshpass，且 **Hermes 终端会拒绝含 `setsid` / `nohup` / `disown` 的命令**（判定为后台包装器，
整条命令直接不执行），所以网上 `setsid ssh` 那套 askpass 写法在这里跑不通。
改用 `SSH_ASKPASS_REQUIRE=force`：它在无 tty 时也强制走 askpass，不需要 setsid。

```bash
sshpass -p '<bwg_pass>' ssh -o StrictHostKeyChecking=no -p 59421 root@64.64.237.34 'bash -s' <<'REMOTE'
printf '#!/bin/sh\necho <oci_pass>\n' > /tmp/.apx; chmod 700 /tmp/.apx
export SSH_ASKPASS=/tmp/.apx SSH_ASKPASS_REQUIRE=force
ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    -o NumberOfPasswordPrompts=1 -p 59421 root@129.153.89.114 'bash -s' 2>/dev/null <<'EOS'
hostname; docker ps
EOS
rm -f /tmp/.apx
REMOTE
```

要点：`PreferredAuthentications=password` + `PubkeyAuthentication=no` 必须加，否则会先撞 BWG 上那把
不被 OCI 接受的 key 再退化，白等一轮；`/tmp/.apx` 用完立刻 `rm`，密码不落持久文件、不写进记忆库。

## 连不上 OCI：先分层定位，别先怀疑 fail2ban

症状常是「SSH 秒断」或「全端口超时」，但真因分布在四个互不相干的层。按顺序排除，每层都有确定性判据。

**第 0 层：Surge TUN 会伪造 TCP 握手，本机的连通性自测不可信。**
`nc -z`、`bash -c 'echo > /dev/tcp/IP/PORT'`、甚至 Python `socket.connect()` 在 Surge 增强模式下都会
**本地立即 ACK**，显示 OPEN 而远端其实没通。判定真实连通只能用应用层证据——SSH 是否拿到 banner，
或从不经 Surge 的机器（BWG）做同样的探测。

**第 1 层：SSH 失败停在哪一阶段——这一条就分开网络层和认证层。**

| 报错 | 含义 |
| :--- | :--- |
| `kex_exchange_identification: Connection closed by remote host` | banner 之前就断 = **网络层**拦截 |
| `Permission denied (publickey,password)` | 链路完全正常，只是**认证**问题 |

从另一条出口能拿到 `Permission denied`，就证明 sshd 活着、端口开着，服务器侧无责。

**第 2 层：fail2ban（最常被冤枉的一层）。**
`fail2ban-client status sshd` —— `Currently banned: 0` 且 `Total banned: 0` 就排除它。
真要解封用 `fail2ban-client set sshd unbanip <ip>`，不要先动 ignoreip。

**第 3 层：iptables INPUT 有没有按源 IP 的封禁。**
`iptables -L INPUT -n -v --line-numbers`。这台机是**端口白名单 + 末尾兜底 REJECT**
（ACCEPT 80 / 443 / 443udp / 3478udp / 59421 / 22，然后 `REJECT with icmp-host-prohibited`），
另有 DOCKER 链对 127.0.0.1 目标做 `! -i lo -j DROP`。**规则里没有按源 IP 的封禁**——
只要 59421 那条 ACCEPT 在，服务器就没拦你，该去查本地路由。

**第 4 层：Surge 规则——裸 IP 的流量会被 `FINAL` 吞掉。**

```bash
grep -nE '<机器IP>' "$CFG"; grep -nE '^FINAL' "$CFG"
```

`FINAL,AT&T` 表示任何没被前面规则命中的流量（含直接访问 OCI 裸 IP）都走 AT&T 家宽策略。
一旦 `IP-CIDR,<ip>/32,DIRECT` 这条规则缺失或被删，SSH 与 curl 全部静默超时，而服务器完全无辜。
它的指纹很好认：**Cloudflare 橙云域名照常 200，灰云域名和裸 IP 全死**——两件事同时成立就是它。
修法是补回 DIRECT 规则，但 Surge 配置是用户红线，只出 diff 交给用户自己在 App 内应用。

判据速记：**ICMP 通 + TCP 全端口超时 + 服务器 fail2ban/iptables 干净 = 本地分流问题，不是服务器问题。**

## 统一网关模式（部署新服务的标准套路）

所有公网服务走**宿主机 Nginx 443 终结 TLS**，容器只绑 `127.0.0.1`：

1. 容器 compose 端口一律 `"127.0.0.1:<port>:<port>"`，绝不直接暴露 0.0.0.0。
2. Nginx 配置放 `/etc/nginx/conf.d/<name>.conf`，每服务一个 `listen 443 ssl http2;` server 块，
   证书 `/etc/ssl/oracle2/fullchain.pem` + `privkey.pem`，按需带 `X-Forwarded-Proto` 与 WebSocket 升级头。
3. `nginx -t && systemctl reload nginx`。
4. iptables 放行新增外部端口（UDP 也要）+ `netfilter-persistent save`。
5. Cloudflare 加 A 记录 → 服务器侧 `curl --resolve` 先验回环，再验公网。

### 静态站部署：权限是最常见的 403 来源

从 macOS `scp -r` 传过去会**保留本地 600/700 权限**，nginx worker 读不到，表现为 403 而不是 404。
每次部署后固定执行：

```bash
find /opt/<site> -type d -exec chmod 755 {} \;
find /opt/<site> -type f -exec chmod 644 {} \;
```

### 从 macOS 上传：`._` 元数据文件会一起进去

全程经跳板时，`tar` 管道比 scp 省事也更快（先打包再 `ssh ... 'tar xzf - -C /opt/<site>'`，
在目标机一侧收 stdin 解包，一次 RTT 完成）。打包会带进 macOS 的 AppleDouble 元数据，必须清。
预防优于事后清理：`COPYFILE_DISABLE=1 tar czf ... --exclude '._*'` 打出来就没有 `._*`；
漏了再补下面的清理：

```bash
find /opt/<site> -name '._*' -delete       # 每个文件都配一个 163 字节的 ._ 兄弟文件
chown -R root:root /opt/<site>            # tar 保留了本地 uid 501
find /opt/<site> -type d -exec chmod 755 {} \;
find /opt/<site> -type f -exec chmod 644 {} \;
```

`--delete` 语义要自己补：先 `rm -rf /opt/<site>/*` 再解包，否则旧 hash 的 `assets/index-*.js` 会残留，
索引页指向新文件而旧文件仍在，排查时极易误判成缓存问题。
清空前确认 acme-challenge 的 root 是 `/var/www/html`（不在站点目录内），清空站点不影响证书续期。

部署后回读产物里的关键字计数（例如 `grep -c -i '<被删服务名>' /opt/<site>/assets/*.js`）应为 0，
只看 HTTP 200 不能证明旧内容已消失。

## 已上线服务

回答「这台机器上跑着什么」时，以 `docker ps` + `systemctl list-units --type=service --state=running` +
`/etc/nginx/conf.d/*.conf` 里的 `server_name`/`proxy_pass` 三处**实测**为准，不要凭笔记或历史记忆作答。

| 服务 | 域名 | 后端 | 目录 |
| :--- | :--- | :--- | :--- |
| 主站导航 startpage | jhsweetheart.com / www | Nginx 直出静态 | /opt/startpage |

- **当前只有主站一个站点，没有任何自建 Docker 容器**。曾经跑过 Gatus（8085）和步数托管台（18765），
  已连同容器、镜像、volume、站点配置、证书、iptables 放行、Cloudflare 记录一并清退。
  再看到这两个端口或 `jiemei.` / `gatus.` 子域的笔记，都是历史残渣。
- 证书现在只剩一条链路：`/etc/ssl/oracle2/` 的 acme.sh 通配符。但**新增服务若用 certbot**，
  会多出 `/etc/letsencrypt/live/<domain>/` 一条，`certbot.timer` 独立在跑——查到期限必须两处都查。
- 常驻 systemd：nginx、fail2ban、docker/containerd、neveridle、unified-monitoring-agent（OCI 官方）。
  曾有 beszel-agent（`*:45876`，被 NAS Beszel Hub 采集），已随服务清退移除；
  **Beszel Hub 里的采集目标不会自动消失，必须人工删**，否则面板永久显示离线。
- **本机不跑 s-ui / ss-rust**：18848 与 56833 从外部实测 FILTERED，那两个是搬瓦工侧的服务。
  历史笔记里「OCI 上有 s-ui 面板和 ss-rust 入站」属旧机残渣，别写进服务清单。
  原 Headscale / n8n / Dify / Vaultwarden 均已下线，不应再出现在健康检查或导航卡片里。

## 下线单个服务（主机保留）

用户说「除了 X 全清掉」时，一个服务是**五处引用**，不是进程表里的一行。固定顺序：
**先备份 → 再删本地 → 再清外部 → 最后验证**。

0. **保留项先讲清楚**：`neveridle` 不是服务而是防回收保活，删掉 7 天内实例会被甲骨文回收；
   `unified-monitoring-agent` 是平台自带组件，删了云平台会重装并报异常。
   动手前把这两项写进「保留」清单并说给用户听，否则「全清掉」会被字面执行成灾难。
1. **先备份再删**。一次 tar 到 `/root/backup-purge-<ts>/`：站点目录、`/etc/nginx/conf.d`、
   systemd 单元、`/etc/letsencrypt/{live,archive,renewal}/<domain>`、`iptables-save`、导航页目录。
   有了备份，「清掉」就不再不可逆，用户也更敢放手。
2. **`cd /root` 之后再删目录**。当前 shell 的 cwd 若在被删目录里，之后每条命令都会打
   `sh: 0: getcwd() failed: No such file or directory`，紧跟的 `netfilter-persistent save`
   可能因此没写进 `rules.v4`，重启后规则复活。
3. 容器：`docker compose down -v`（**`-v` 才删数据卷**）→ `docker rm -f` → `docker rmi` → `rm -rf /opt/<svc>`。
   再 `docker network ls` 看僵尸网络——早已下线的服务常留着 `<svc>_default`，逐个 `docker network rm`；
   `docker system prune -f` 收尾，通常回收几百 MB。
4. nginx：删 `/etc/nginx/conf.d/<svc>.conf` → `nginx -t && systemctl reload nginx`（reload，不是 restart）。
5. systemd：`systemctl disable --now` → 删 unit **和** `multi-user.target.wants/` 里的软链 →
   `daemon-reload` → 删二进制。只删 unit 文件会留下悬空软链。
6. 防火墙：`iptables -D INPUT -p tcp --dport <port> -j ACCEPT` 后必须 `netfilter-persistent save`，
   并回读 `grep <port> /etc/iptables/rules.v4` 确认清零——只删内存规则等于没删。
7. 证书：certbot 签的 `certbot delete --cert-name <domain> --non-interactive`；acme.sh 签的用 `acme.sh --remove`。
8. Cloudflare：删 A 记录后**用 DoH 回验 NXDOMAIN**（`curl -H 'accept: application/dns-json' https://1.1.1.1/dns-query?name=<domain>&type=A`
   应为 `Status 3`）。本地 `dig` 会被 Surge 接管，不可信。
9. 导航页：死链卡片是清理漏得最多的一处，判定与改法见下节「导航页卡片维护」。
10. 收尾清单要连外部一起报：监控面板（Beszel / Uptime Kuma）里的采集目标与探针不会自动消失，
    需人工删；残留的灰云 A 记录会落进主站 default server 返回首页，看着「能用」其实是死记录。

## 导航页卡片维护（清死卡片 / 改卡片信息）

主站 `/opt/startpage` 是 Vite 静态产物，**绝不直接改 `dist/` 里的压缩 JS**——改源码重构建。

1. **两处数据源都要改**：`src/config/site.config.ts`（`cards` 数组）与 `src/data/config.json`
   （按分类分组的 `items`）。只改一处，页面仍渲染旧卡片。
2. **JSON 里数组最后一项没有尾逗号**。用字符串替换删最后一项时，`old_string` 必须连前一项的
   `},` 一起匹配、并替换成 `}`；只匹配 `{ ... }` 块本身会「命中 0」而静默什么都不做。
   删完用 `json.loads` 或 `npm run build` 验证语法。
3. **死卡片是双判据实测出来的，不是凭记忆**：
   ```bash
   curl -sk -o /dev/null -w "%{http_code}\n" --max-time 8 "https://<domain>/"          # 000 = 不可达
   curl -s -H 'accept: application/dns-json' "https://1.1.1.1/dns-query?name=<domain>&type=A"  # Status 3 = NXDOMAIN
   ```
   两条同时成立才删。**内网服务不能这样判**——它们靠 Surge `[Host]` / AdGuard 映射到 NAS，
   公网必然 NXDOMAIN 但服务是活的；直接打后端 `IP:端口`（如 `10.0.0.3:3003`、`10.0.0.4:8006`），
   返回 200/302/401 即为活。按域名判会把活卡片全删光。
4. **第三方服务卡片：描述必须当场打开站点核实**。服务商可能已改名或转型，沿用记忆里的旧定位会写错。
   `web_extract` 在 Surge FakeIP 环境下会把公网站点判成私网地址而拒抓，改用浏览器打开读
   `document.title` 与正文；图标取站点官方 `favicon.svg` 原文存到 `public/icons/<name>.svg`。
5. **验证三件套**：产物关键字计数为 0、浏览器里 `document.querySelectorAll('a[href]')` 无死链、
   新图标 URL 返回 200。只看首页 200 证明不了卡片改对了。
6. `dist/` 通常在 `.gitignore` 里，提交只带 `src/` 与 `public/icons/`，产物靠 build 生成。

## 账户退役与域名迁移

完整清单见 `references/decommission-and-migration.md`。核心三条：

1. **退役机器的 IP `/32` 规则必须从所有规则集删除**——IP 释放后可能被他人获得，
   残留的 `/32` 会让陌生人的流量错误命中你的代理策略，这是路由污染而不只是垃圾配置。
2. **搜完所有引用层再动手**：记忆、`~/.ssh/config`、私钥文件、`known_hosts`、本地脚本、
   GitHub 规则集、Cloudflare DNS、**监控探针配置文件**。只改一层等于没清。
   监控探针是最常被漏的一层：机器退役后 Gatus / Uptime Kuma 里那条 TCP 检查会永远红着，
   每次看面板都像新故障，还误导后来人以为「这台机还没下线」。
   定位方式：Gatus 看 `/opt/gatus/config/*.yaml` 的 `url:`，Uptime Kuma 看面板里的监控项，
   按旧 IP / 旧域名搜。**这套清单对「单机退役」和「下线单个服务」同样适用。**
3. **迁移前先查有没有现成的通配符证书**（`ls -d /root/.acme.sh/*_ecc/`）。
   有 `*.example.com` 就直接复用，比重新签一张快一个数量级，且续期链路已经就绪。

## 排查 Cloudflare 5xx：先分清 526 与 502

- **526 = Cloudflare 与源站 SSL 握手失败**。绝大多数情况是源站 IP 已死、或源站证书过期/不匹配，
  而不是 Cloudflare 配置错。先确认 DNS 指向的那台机器还活着、且它的证书对得上域名。
- 502 才是源站应用层不可达。
- 橙色云（proxied）的记录改 IP 后立即生效，不需要等 TTL；灰色云（DNS only）同理但客户端有缓存。

## 支撑文档

- `references/deploy-pitfalls.md` — Nginx / rsync / 容器部署踩坑与修复
- `references/dns-and-navigation-linkage.md` — Cloudflare API 凭据、DNS 记录操作、导航站联动要点
- `references/cert-renewal-and-gateway.md` — 证书续期与统一网关：`sed -i` 换 inode 导致单文件 bind mount 不生效、`certbot.timer` 在跑但无受管证书的误判、acme.sh 整目录迁移复用
- `references/decommission-and-migration.md` — 服务器退役与域名迁移全链路清单（含 Cloudflare API 改记录/删记录的实际调用与验证）
