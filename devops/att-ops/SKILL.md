---
name: att-ops
description: 用户问 ATT/美国家宽/AnyTLS 出口时使用，管理美国家宽服务器（公网 IP 动态，须先核实）。
version: 2.1.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [att, us-home, anytls, proxy, 美国家宽]
    related_skills: [vps-ops, nas-docker-ops, proxy-chain-diagnostics, hermes-system-optimization]
---

# ATT Ops (美国家宽)

管理美国家宽服务器（用户称其为 **ATT**）：**AnyTLS 出口**、系统状态、链路排查。

> **2026-11-10 重大变更**：旧机（`108.230.34.31`，ss-rust/52937，端口 22 密码登录）**已销毁**。现役机为 `108.241.86.178`，SSH **59421**、**仅公钥免密**、出口 **AnyTLS 34443**。本文已按新机重写；旧写法（`sshpass`、`-p 22`、`52937`）一律作废。

## When to Use

- 用户提到「ATT」或「美国家宽」——指的就是这台家宽机器（**不是搬瓦工**）
- 用户问 AnyTLS 出口 / US 出口稳定性 / 系统状态
- 美国出口相关排查（US 信用卡申请、IP 稳定性）

## 第 0 步：先定位现役主机（必做）

**公网 IP 是动态的，换过机。绝不能把技能里的 IP 当固定标识符直接连。**

定位优先级：

1. 用户当场告知的 IP（最权威）
2. `dig +short cheers.jhsweetheart.com`（该名已解析到现役机）
3. 都不行就问用户

**`person.jhsweetheart.com` 已作废**：它曾指向旧机 `108.230.34.31`，该 A 记录已于 2026-11-10 从 Cloudflare 删除（`dig @1.1.1.1` 复核为空）。旧 IP 全端口失联，不要再用它定位。

```bash
ATT_IP=$(dig +short cheers.jhsweetheart.com | tail -1)
```

IP 一旦变化，联动项：搬瓦工侧指向 ATT 的 outbound、各机 fail2ban `ignoreip`、探针配置、AnyTLS 自签证书 CN。

## 连接信息（现役机）

```bash
ssh -p 59421 -i ~/.ssh/id_ed25519 root@$ATT_IP "<cmd>"
```

- 用户 `root`；端口 **59421**（22 已关）；**仅 id_ed25519 公钥免密**
- **密码方式已不可用**，本文不记录任何口令（凭据不入库、不入文档）
- 主机名 `cheers.jhsweetheart.com`（AS7018 AT&T Enterprises, Irvine CA）
- 系统：Debian 13 trixie + xanmod 7.3.3
- 资源：**1.9 GiB RAM / 20G 盘 / 1G swap**（比旧机的 7.7G/50G 小很多，重负载前先看内存）

## 服务清单

| 服务 | 说明 |
|------|------|
| AnyTLS 出口 | 端口 **34443**，自签证书 `CN=cheers.jhsweetheart.com`，**仅放行来源 `64.64.237.34`**（搬瓦工） |

- **角色**：ATT 是链式代理的**出口**——客户端不直连它，由搬瓦工侧把 AnyTLS 配成 outbound。
- 旧机的 `ss-rust`（52937 / Shadowsocks-2022）**已不存在**，别再按 ss-rust 排查。
- fail2ban **已在运行**（2026-11-10 实测 `systemctl is-active fail2ban` → active，enabled）。配置只存在于 `/etc/fail2ban/jail.d/zz-joel-sshd.local`（**没有** `jail.local`）：`banaction = nftables-multiport`、`backend = systemd`、jail `sshd` port **59421**、maxretry 5 / findtime 10m / bantime 1h；`ignoreip` 含 `64.64.237.34`、`35.148.249.5`。真实封禁表为 `table inet f2b-table`（**按需创建**，无封禁时不存在）。

## 中转链路实测口径（BWG → ATT，2026-11-10 实测）

用户问「这条线怎么中转的 / 能不能套 WireGuard / 为什么 UDP 不通」时，先按这层事实回答，不要临场猜：

| 跳 | 事实 |
|---|---|
| 家宽 → BWG `64.64.237.34:443` | TCP 443，TLS 在 **haproxy** 终止；`tcp-request` 读前 32 字节 **AnyTLS auth 前缀**做 ACL 分流 |
| haproxy → sing-box | `127.0.0.1:8444`，**明文**（inbound 无 tls 块，证明 TLS 已在 haproxy 终结）；同前端另一前缀走 8443 直出 |
| BWG sing-box → ATT `34443` | 第二段独立 AnyTLS over TLS，自签证书**内嵌 PEM 做 pin**；ATT 侧 `anytls-relay-in` 解流后 `direct`，出口即 ATT 公网 IP |

- **多路复用只发生在 BWG 之后**：实测同一时刻家宽→443 有 265 条会话，haproxy→8444 也是 265（1:1 透传），BWG→ATT 只有 105 条（含 2 条 `min_idle_session` 预建）。压缩来自 sing-box 的 idle session 池（`idle_session_check_interval 30s` / `idle_session_timeout 120s` / `min_idle_session 2`），**Surge 侧每条代理连接都是一个独立 TLS 会话，前端没有复用**。
- **这条线实际是 TCP-only**：haproxy 443 只 bind TCP，UDP 到不了 ATT。不是配置漏项，是架构决定的；`sing-box check` 对 anytls outbound 加 `network` 字段直接报 `unknown field`，社区 issue 亦记录 anytls outbound 对 UDP 静默丢弃。**别承诺给这条线加 QUIC/游戏 UDP。**
- **能套 WireGuard，但先问目的**：两端都有 `wireguard.ko` 与 sing-box `with_wireguard`，防火墙 input 均 drop。运维隧道（BWG 服务端 + ATT 主动连出，地址段 `10.66.0.0/24`）零风险；若要替换数据面则需 `ip_forward=1` + nft forward accept + SNAT + MTU 1420 / MSS clamp 1380，属真实系统变更，**须单独授权**。
- **换证即断链**：ATT 若重装或换自签证书，BWG 配置里内嵌的 PEM 必须同步替换，否则中转直接不通——排查「突然全断且两端都活着」时优先查这条。

## 常用操作模板

```bash
# 系统状态
ssh -p 59421 root@$ATT_IP "uptime; free -h; df -h / | tail -1"

# 监听端口（确认 34443 在听）
ssh -p 59421 root@$ATT_IP "ss -tlnp | head -10"

# 服务状态（服务名现场用 systemctl list-units 找，不要猜）
ssh -p 59421 root@$ATT_IP "systemctl list-units --type=service --state=running | head -20"
```

**从 Mac 上 `nc -z $ATT_IP 34443` 不能证明任何事**——Mac 的 TCP 全走 Surge TUN，Surge 会先本地 accept 再建连，`nc` 报成功而实际链路可能已死。真实可达性只能从 NAS 测。

## 出口失联分层诊断

### 第 1 层：从 NAS 做真实 TCP 探测（唯一可信的国内直连点）

```bash
ssh -p 10000 18332733294@10.0.0.3 \
  "for p in 59421 34443; do timeout 6 bash -c \"cat </dev/null >/dev/tcp/$ATT_IP/\$p\" \
   && echo ATT:\$p open || echo ATT:\$p FAIL; done"
```

- **判据：59421 与 34443 都超时 = ATT 整机对外失联**，问题在美国家宽侧（断电/掉线/ONT/端口映射/IP 变更），不在 Surge 也不在 BWG。
- **跨国家宽 ICMP 100% 丢包是正常的**（住宅网关丢 ICMP），`ping` 失败不能当故障证据，只有 TCP 超时才是指标。
- **补充（2026-11-10 起）**：该机已主动 `icmp type echo-request drop`，**全球 ping 不通是设计值**，不是故障信号。别拿 ping 当探针，也别把 ping 不通报成「机器掉了」——只有 59421/34443 的 TCP 超时才是指标（配方见 `linux-icmp-hardening`）。
- 反向对照：同一命令测 `64.64.237.34` 的 32636/21174/59421，若全通 → 中转侧健康，故障被隔离到 ATT。

### 第 2 层：全球多点探测

从 NAS 调 check-host.net API（本机 curl 会被 Surge 规则二次匹配，不可用）：

```bash
curl -s -H 'Accept: application/json' \
  "https://check-host.net/check-tcp?host=$ATT_IP:34443&max_nodes=6"
# 取 request_id 后 sleep 15，再取 check-result
```

- **必须看 `us*.node.check-host.net` 美国节点的结果**——它才是家宽链路的地面真相。
- 全部 `Connection timed out` = 全球不可达 = ATT 侧故障已确认。

### 第 3 层：Surge 侧表征

AT&T 组若为 Fallback 且成员含 `[REJECT, …]`，节点探测失败时整组落到 REJECT，用户端表现为**秒失败**（0.01s）而非超时。取证：

```bash
curl -s -H "X-Key: $SURGE_API_KEY" http://127.0.0.1:6171/v1/policy_groups
curl -s -H "X-Key: $SURGE_API_KEY" http://127.0.0.1:6171/v1/requests/recent
```

`notes` 里出现 `Policy decision path: … -> REJECT` + `Rejected by rule` 即此症。**API key 从环境变量取，不写进本文。**

### 第 4 层：IP 有没有变

- `dig +short cheers.jhsweetheart.com` 得 DDNS 当前值；`dig +short -x <IP>` 看 PTR 是否仍为 AT&T 住宅段。
- **边界**：机器失联时 DDNS 脚本根本没机会上报，「记录长期未变」既可能是 IP 没变（断网），也可能是 IP 变了但更新失败——无法从外部区分，须让用户看现场网关的 WAN IP。

### 不要用的「证据」

- 监控探针全绿不能证明出口健康：它只探搬瓦工入口的 TCP 端口，ATT 出口死了照样可能报成功。

## 陷阱

1. **不记录、不复用任何口令**：本机已改为公钥免密，密码方式不可用；旧版本文里的明文口令已移除，且本技能库镜像到公开仓库，任何凭据都不得写入。
2. **IP 是动态的**——文中任何具体 IP 都只是「上次已知值」，用前必须重新核实并联动 fail2ban 白名单与探针。
3. **用户叫它 ATT**——别与搬瓦工搞混：AnyTLS 出口的 IP 就是美国家宽，搬瓦工只是入口。
4. **22 端口已关**：连 22 会超时，别当成整机失联；先试 59421。
5. **资源只有 1.9G 内存 / 20G 盘**：别在这台机上装重东西或跑构建。
6. **34443 只放行 `64.64.237.34`**：从别处探测会是关的，这≠故障。
7. **IP 稳定性敏感**：美国家宽 IP 对 US 信用卡/银行风控重要，别做可能断网/换 IP 的操作。

## 验证步骤

1. `ssh -p 59421 -i ~/.ssh/id_ed25519 root@$ATT_IP "echo OK"` → 连接 OK
2. `ss -tlnp | grep 34443` → 在听
3. `systemctl is-active fail2ban`（若启用，确认 jail 端口为 59421）
4. 变更后从 NAS 测 59421/34443（**不要用 Mac 的 `nc`**），再用 `proxy-chain-diagnostics` 验链路
5. 若不可登录：先在 NAS 做第 1 层探测，再决定是否升级到 check-host 全球探测，不要反复重试 ssh

## 来源

- **第二手实测**：2026-11-10 `default` profile 通过 `message_agent` 投递的迁移后现状（SSH 直连自有主机执行并回读验证），未经 skill-keeper 复现。
- 变更事实：新 IP `108.241.86.178` / SSH 59421 / 仅公钥 / AnyTLS 34443 自签证书仅放行 `64.64.237.34` / Debian 13 + xanmod 7.3.3 / 1.9G RAM / 20G 盘；旧 IP 全端口失联；`person.jhsweetheart.com` 的 A 记录已删。
- **已核实（2026-11-10 实测）**：fail2ban active/enabled，jail 端口 59421，配置在 `jail.d/zz-joel-sshd.local`；封禁表 `inet f2b-table` 按需创建（`nft list tables` 看不到它属正常，用 `banip <测试IP>` 验证后再 unban）。除 AnyTLS 外无其他业务服务；`ss -tlnp` 实测仅 59421(sshd) 与 34443(sing-box) 在听。
- 修订：v1.1.0 → v2.0.0 按新机重写，并移除旧版本内的明文口令与 API key。
