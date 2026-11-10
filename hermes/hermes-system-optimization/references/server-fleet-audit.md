# 云服务器与主机机队体检 (Server Fleet Audit)

用户说「检测一下我的云服务器」「检查服务器有没有问题」「全面体检」时的主机级审计 SOP。

与第四阶段的连通性探测互补：**HTTP 200 只证明进程活着，不证明配置正确。**连通性全绿之后必须继续跑本文的审计项。

## 一、采集清单（每台主机都跑，命令成套复制）

主机分组与连接方式：内网主机走 `ssh root@10.0.0.x`；搬瓦工与两台甲骨文统一 `sshpass -p '<统一密码>' ssh -p 59421`（**端口不是 22**）；AT&T 家宽 `sshpass` + 端口 22。各主机的当前 IP/端口/密码以对应技能（`vps-ops` / `oracle-cloud-ops` / `att-ops` / `nas-docker-ops` / `pve-ops`）为准，不要凭记忆写死。

```bash
uptime                              # 存活 + 负载
free -h | head -2                   # 内存水位（低配机重点看）
df -h / | tail -1                   # 根分区
for s in <该主机应有服务列表>; do printf "%-16s %s\n" "$s" "$(systemctl is-active $s)"; done
ss -tlnp | grep -E ':(<预期端口列表>)\b'      # 监听端口逐一对齐
ss -tlnp | head -15                 # 预期之外的监听也要看一眼
docker ps --format '{{.Names}}  {{.Status}}'
fail2ban-client status sshd         # jail 是否存在 + 当前封禁数
apt list --upgradable 2>/dev/null | grep -c upgradable   # 待装更新
```

证书一项单独查，见下面第 2.1 节（不能只 `ls` 一眼了事）。

## 二、判定规则

### 服务 inactive ≠ 故障

服务迁移到容器后，宿主机的 systemd 单元**本来就会是 inactive**（典型：`nginx` 单元 inactive，但 OpenResty / 统一网关容器在跑 80/443）。

判定口径：**以「端口是否在听 + 容器是否在跑」为准，不以 systemd 单元为准。**先分清「有意停用」与「挂了」再报异常——把有意停用报成故障会浪费一轮排查。

### 端口要逐个对齐预期清单

少一个才算异常；多出计划外的监听反而更值得看一眼。

### 白名单里有 IP ≠ 白名单里有正确的 IP

见 2.2 节，必须对着**当前**的 IP 值逐个比对。

## 三、两类高频配置漂移（每次审计必查）

### 3.1 证书续期矩阵

**规则：证书「有没有续期机制」是按「每一张证书」单独成立的，不是按主机成立的。**

同一台机器上经常同时存在多张证书、由完全不同的机制管理，只有其中一部分会在到期前自动续：

| 机制 | 怎么认 | 会续吗 |
| :--- | :--- | :--- |
| certbot | `/etc/letsencrypt/live/<name>/` 有该 lineage，且 `certbot.timer` 为 enabled | 会 |
| acme.sh | `/root/.acme.sh/<domain>_ecc/<domain>.conf` 且有 `Le_RealFullChainPath` | 会（文件会更新） |
| 手工复制 / 一次性签发 | 既无 lineage 也无 acme 记录 | **不会**——到期即断 |

排查方法：**从 nginx 的实际配置反查，不要猜、也不要只看某个目录**。

```bash
# 宿主 nginx
search_files 'ssl_certificate ' in /etc/nginx/
# 容器化网关
docker exec <gateway-container> sh -c 'grep -rnE "server_name|ssl_certificate " /etc/nginx/conf.d/'
```

配置里出现的**每一个** `ssl_certificate` 路径都必须能回答「它由谁续期」。答不出来的就是孤儿证书。

**孤儿证书的消除办法**：用通配符证书覆盖。当 `*.domain.com` 的 SAN 已经包含该主机上所有二级域名时，把各 server 块统一指向通配符证书，即可整体并入 certbot 自动续期，不必为每个二级域名单签发一张。查 SAN：

```bash
openssl x509 -noout -ext subjectAltName -in <fullchain.pem>
```

**续期 ≠ 生效（第二个坑）**：续期动作会更新证书文件，但 nginx 只在启动/reload 时读证书。没有 reload 钩子的话，内存里仍是旧证书，续期看着成功、实际一直在发旧证书，直到某次重启才突然生效。

- certbot：`/etc/letsencrypt/renewal-hooks/{pre,deploy,post}/` 里有没有脚本
- acme.sh：`Le_ReloadCmd` 是否为空字符串
- **容器化的 nginx 要 reload 容器，不是宿主**（宿主 `systemctl reload nginx` 对容器无效）

**分发副本是否落后**，用指纹比对，不要看时间戳：

```bash
openssl x509 -noout -fingerprint -sha256 -in <源证书>
openssl x509 -noout -fingerprint -sha256 -in <分发副本>
```

指纹不同就是副本落后，两个到期时间接近也不代表是同一张。

到期剩余天数速算（便于报告）：

```bash
EXP=$(date -j -f "%b %d %H:%M:%S %Y %Z" "<notAfter>" +%s); echo $(( (EXP-$(date +%s))/86400 )) 天
```

### 3.2 Fail2ban ignoreip 白名单漂移

**规则：任何一台对等主机的公网 IP 变了，其余所有主机的白名单都要重新核对一遍。**

动态 IP（家宽类）尤其容易漏：换 IP 之后旧值会一直躺在各主机白名单里，`fail2ban-client status` 看着一切正常，「已配置白名单」的错觉就此成立。

```bash
# 每台都跑，逐台横向比对
fail2ban-client get sshd ignoreip
```

比对要点：每台是否都含**当前**的全部对等 IP（本机、回环、其余每台服务器、家宽当前公网 IP）。横向差异本身就是信号——同一批机器里各台白名单不一致，说明有过一次没联动到底的变更。

### 3.3 审计项的加固配方（新建或补白名单时照抄）

```ini
# /etc/fail2ban/jail.local
[DEFAULT]
bantime  = 1d
findtime = 10m
maxretry = 3
backend  = systemd
ignoreip = 127.0.0.1/8 ::1 <对等主机 IP 逐个列出>

[sshd]
enabled = true
port    = <该机 SSH 端口>
mode    = normal
```

- Debian/Ubuntu 一律 `backend = systemd`（走 journal，不要用默认的 auth.log 路径猜测）
- 改完 `systemctl enable --now fail2ban && systemctl restart fail2ban`
- 生效验证：`fail2ban-client status sshd` 的 `Journal matches` 行应指向 `_SYSTEMD_UNIT=ssh.service`，且 `fail2ban-client get sshd ignoreip` 与文件一致
- **`systemctl restart` 后立刻查 socket 可能报 `Failed to access socket path`——那是启动竞态，等 2 秒再查即可，不是配置错误**

## 四、报告形态（用户偏好）

- **先给总体结论**（「全部健康 / 查出 N 项隐患」），再逐台列状态，最后才是隐患清单
- 每台按「主机名 + 存活/负载/内存/磁盘/服务/容器/端口」分块用项目符号列出，**不要用宽表格**（Telegram 渲染会散架）
- 隐患**按优先级排序并打标**：🔴 会到期/会断服务的 > 🟡 配置漂移 > 🟢 待装更新
- 每条隐患先给**证据**（命令与输出片段、指纹比对、行号），再给结论——不要只下判断
- 收尾单列一节「需你授权才能执行的动作」，逐条编号；**审计阶段一律只读**，不要顺手改配置
- 结论要如实：没查到根因就说没查到，不要为了收尾好看而编一个「已修复 XX」的说法

## 五、相关

- 连通性探测脚本：`scripts/health_check_all.py`（本文是它的主机级补充）
- 各主机连接信息与专属服务清单：`vps-ops` / `oracle-cloud-ops` / `att-ops` / `nas-docker-ops` / `pve-ops`
- IP 质量与纯净度：`ip-quality-xykt`；出口路由：`site-egress-check` / `proxy-chain-diagnostics`
