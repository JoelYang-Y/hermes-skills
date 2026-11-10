---
name: proxy-chain-diagnostics
description: 用户问代理/翻墙/节点/DNS 污染/Telegram 连不上时使用，一键诊断 Surge 链路。
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [surge, proxy, dns, diagnostics, vpn, telegram]
    related_skills: [macos-app-network-diagnostics, reality-domain-finder, nas-docker-ops]
---

# Proxy Chain Diagnostics

一键诊断用户代理链路：Surge 状态 → 节点连通 → DNS 链 → 目标可达性，输出结构化报告。

## When to Use

- 用户报「连不上/卡/超时」：Telegram、Google、YouTube、DeepSeek 等任何海外服务
- 用户问「节点状态」「代理正常吗」「DNS 污染」
- Hermes gateway 的 Telegram 轮询超时（日志见 `~/.hermes/logs/gateway.log` "Timed out"）
- 排查 Surge 相关故障（先查链路再查应用）

## 环境架构（2026-08-10 实测）

```
客户端 → 10.0.0.1 (BE88U AdGuardHome, 直连国内 DNS = 海外域名污染源)
       → 10.0.0.6 (paopao: adguardhome:53 → paopaodns:5335, 反污染干净)
Surge 跑在本机 Mac (局域网 IP 10.0.0.2)：
  6171 WebUI API (X-Key: <密码>)  6170 external controller (同 key)
  6152 HTTP 代理  6153 SOCKS5 代理
节点（自建 vircs，用户坚持用，勿推荐机场）：
  AnyTLS-BWG / AnyTLS-AT&T → joel.jhsweetheart.com (64.64.237.34, 搬瓦工)
```

## 诊断步骤（按序执行）

### 1. Surge API 健康
```bash
curl -s --max-time 6 -H "X-Key: <密码>" http://10.0.0.2:6171/v1/profiles/current | head -c 300
curl -s --max-time 6 -H "X-Key: <密码>" http://10.0.0.2:6171/v1/policies
# 期望：返回 profile 配置 + {"proxies":["AnyTLS-BWG","AnyTLS-AT&T"],"policy-groups":[...]}
```

### 2. 端口监听（Surge 活着？）
```bash
lsof -nP -iTCP:6152 -iTCP:6153 -iTCP:6170 -iTCP:6171 -sTCP:LISTEN | grep Surge
```

### 3. 当前策略选中 + 组成员健康
```bash
curl -s --max-time 6 -H "X-Key: <密码>" http://10.0.0.2:6171/v1/policy_groups | python3 -m json.tool | head -40
# 每个组 → 成员数组（含顺序/类型/enabled）。组成员里出现 REJECT 且真节点不可用
# → 整组落 REJECT，用户端是「秒失败」而不是「超时」。
# 字段与端点速查见 references/surge-api-diagnostics.md
```

### 4. 节点连通性（走 Surge 代理实测）
```bash
# 经 HTTP 代理访问 Google
curl -s -o /dev/null -w "google via proxy: HTTP %{http_code} in %{time_total}s\n" \
  -x http://127.0.0.1:6152 --max-time 15 https://www.google.com/generate_204
# 经 SOCKS5 访问 Telegram API
curl -s -o /dev/null -w "telegram via socks5: HTTP %{http_code} in %{time_total}s\n" \
  -x socks5h://127.0.0.1:6153 --max-time 15 https://api.telegram.org
# 直连节点 IP
nc -z -w 5 64.64.237.34 443 && echo "node 443 reachable" || echo "node 443 UNREACHABLE"
```

### 5. DNS 链对比（污染检测）
```bash
# 10.0.0.1（BE88U，预期污染海外域名——这是已知行为，不是新故障）
nslookup youtube.com 10.0.0.1 | tail -5
nslookup -type=AAAA google.com 10.0.0.1 | tail -5   # 预期被毒化 2001::1
# 10.0.0.6（paopao，反污染，海外域名应给干净答案）
nslookup youtube.com 10.0.0.6 | tail -5
# 判断：10.0.0.1 污染属预期；若 10.0.0.6 也污染 → paopao 容器故障（查 NAS docker：nas-docker-ops）
```

**回答「某域名到底有没有公网记录」时，本机 DNS 命令不可信。** Mac 上所有 DNS 查询都经过
Surge TUN，`dig`/`nslookup`（即使显式写 `@1.1.1.1`）拿到的可能是 Surge 自己的 [Host] 映射或
DNS 接管结果，而不是被查询服务器的真实应答。地面真相必须走 DoH over HTTPS：
```bash
curl -s -H 'accept: application/dns-json' \
  'https://cloudflare-dns.com/dns-query?name=<域名>&type=A'
# Status 3 + 只有 Authority 段 = 该名字在权威 DNS 上不存在（无 A 记录）
# 对比主域和已知有公网记录的兄弟子域，才能下结论
```
实测差异样本：同一域名本机 `dig` 给 `10.0.0.3`（私有地址），DoH 给 Status 3（无记录）——
**私有地址出现在「公网解析」结果里，基本就是 TUN 接管而不是真实记录。**

### 6. 物理链路追踪（绕开 Surge TUN，2026-08-13 验证）

**任何「真实可达性」探测都不能在 Mac 上做。** 除了 traceroute，`nc`/`ssh` 到公网 IP 同样不可信：
Surge 会先本地 accept 再建连，于是 `nc -z` 报 `succeeded`、`ssh` 报
`kex_exchange_identification: Connection closed by remote host`——两个都是建连失败被本地掩饰后的假信号。
只要目标 IP 命中一个走代理的策略，就会出现这种「看着通、实际断」。真实探测从 NAS 10.0.0.3 做：

```bash
sshpass -p '<密码>' ssh -p 10000 -o StrictHostKeyChecking=no 18332733294@10.0.0.3 \
  "for p in 22 443; do timeout 6 bash -c \"cat </dev/null >/dev/tcp/<IP>/\$p\" \
   && echo \$p open || echo \$p FAIL; done"
```

Mac 侧 traceroute 必被 Surge TUN 截走（首跳 198.18.0.1 fake-ip，后面全 *）。真实物理路径必须从 **NAS 10.0.0.3** 跑（NAS 不走 Surge）：
```bash
# NAS 无 traceroute 命令 → 用 python raw ICMP 版（需 sudo 读 ICMP），脚本见本技能 scripts/traceroute_nas.py
# 用法：本地写脚本 → base64 -i → sshpass ssh NAS 解码 → sudo python3
# 实测 2026-08-13：国内路径 10.0.0.1 → 100.98.94.1(电信接入) → 58.213.x(南京电信) → 218.2.x(江苏电信) → 202.97.x(骨干) → baidu CDN 180.101.51.73
# 节点路径 同上 → 59.43.x(国际出口 ~138ms) → 搬瓦工 64.64.237.34
```

### 7. IPv6 专项（2026-08-13 验证）

- 国内 IPv6 直连：`curl -6 https://www.baidu.com` → 200/0.037s；`ping6 2400:3200::1`(阿里DNS) ~12ms；出口 = 本机 240e:3a3:1006:36d0:...（DIRECT 无代理）
- 海外 IPv6 域名（强制 -6 也一样）：paopao 屏蔽 AAAA → 域名只有 A 记录 → Surge 翻译走 **IPv4 代理**，出口仍是 AT&T 家宽（`curl -6 https://api64.ipify.org` 会返回**家宽的当前公网 IP**）。**AT&T 的公网 IP 是动态的，本文里出现的任何具体 IP 都只是历史样本，不得当作当前值引用**——用前先核实，见 `att-ops`「第 0 步：先核实当前 IP」
- 海外 IPv6 字面量（如 `https://[2606:4700:4700::1111]`）：**不可达**（节点无 IPv6 无法翻译 IP 字面量）——需要海外 IPv6 直连时无解，只能等节点支持
- ISP 层面电信 IPv6 国际**可达**（NAS ping6 Cloudflare 223ms / Google DNS 2001:4860::8888 197ms）——若未来想把某海外 IPv6 域名改直连，物理链路通
- macOS IPv6 命令：`ping6 -I en0 fe80::...`（`ping -6` 无效）、`traceroute6` 不支持 `-i`（会报 invalid ident）

### 8. 结构化报告输出

```markdown
## 🔗 代理链路诊断 <时间>
| 检查项 | 结果 |
|--------|------|
| Surge API | ✅/❌ <错误> |
| 端口 6152/6153/6170/6171 | ✅ 全监听 / ❌ <缺哪个> |
| 当前节点 | 节点选择 → AnyTLS-AT&T |
| Google 经代理 | ✅ 204 in X.XXs / ❌ <错误> |
| Telegram 经代理 | ✅ 200 in X.XXs / ❌ <错误> |
| 节点 IP 443 | ✅ / ❌ |
| DNS 10.0.0.1 (污染预期) | youtube → <IP> (异常才标红) |
| DNS 10.0.0.6 (paopao) | youtube → <IP> ✅ 干净 |
📌 结论：<一句话，给出故障点 + 下一步>
```

## 陷阱

1. **X-Key 带尾随句点** `<密码>`，漏句点 = 401
2. **Surge API 只读** —— 只 GET，绝不 POST 修改配置（用户明确要求）
3. **10.0.0.1 污染海外域名是预期行为**（BE88U 直连国内 DNS），别当故障报
4. **keepalive 5.5.5.5:55555 UDP**（Surge 探活机制）属正常，不是恶意流量
5. **策略组含 Nexitally（机场）**但用户坚持自建节点，诊断结论不要建议切机场
6. Surge API 无 `/v1/status`、`/v1/connections` 端点（unknown path 正常）
7. Telegram 轮询超时多为 Surge 链路抖动，先跑本技能步骤 4，通常 curl 实测能过就不必深挖
7.1 **「秒失败」和「超时」是两个完全不同的病**：`requests/recent` 里 `remark=Rejected by rule`、
   `Policy decision path: X -> <组> -> REJECT` 表示**策略组落到 REJECT**（组成员里 REJECT 排在真节点前、
   真节点探测失败），流量根本没发出去；而 `Connect failed`/超时才是真节点不可达。
   把两者混为一谈会让人去查网络，实际要查的是策略组成员与节点存活。
7.2 **`requests/recent` 的字段名是 `URL`（大写）、`startDate`（epoch）、`notes[]`**，没有 `time`/`url`/
   `error`/`statusCode`；用错名字只会得到一堆 None，不要据此得出「没有请求记录」的结论。
7.3 **磁盘上的 conf 不一定是运行态**：桌面端 Documents 下可能有多份 profile，先 `GET /v1/profiles/current`
   确认哪份在跑，再比对。拿错文件会得出「配置写的是 select，运行时怎么是 Fallback」的假矛盾。
7.4 **`curl -x http://127.0.0.1:6152` 得到 000 不代表链路坏**：代理端口有独立认证与规则二次匹配，
   必须用默认路径（不带 `-x`）跑同一目标做对照再下结论。
8. **本机 DNS 命令不能用来判断公网记录** —— 全部经 Surge TUN，必须用 DoH 取地面真相（见步骤 5）。
   同理：`curl` 探测「真实直连出口」时国外回显站会被规则二次匹配，须用国内回显站。
9. **用户报「某个内网服务打不开」时，先做兄弟域名隔离测试**：在同一设备上开另一个同架构的
   内网域名（emby./kuma./sub.），若都打不开则问题在设备到内网的路径，与那个服务本身无关；
   只有「兄弟能开、它不能开」才值得下钻该服务。链路与可达性矩阵见
   `references/internal-domain-access.md`。
10. **「App 连不上」还有第三类病：域名被 AdGuardHome 拦成 `0.0.0.0`**。阶梯是
   ① 策略组落 REJECT（秒失败）→ ② 节点不可达（超时）→ ③ 域名解析不出来。
   第三类的指纹：recent 里该域 `remote` 是 `127.0.0.1`/`0.0.0.0`，notes 写
   `[DNS] Use cached DNS result ... [Socket] Use the last successful address: 0.0.0.0` ——
   Surge 把 0.0.0.0 当本机去连，瞬断。此时链路没病，是 AGH 订阅过滤器（HaGeZi Pro /
   1Hosts / anti-AD）把 SDK 或 API 域当广告误拦了；判据与修法见 `surge-config-operations`
   的「双层故障：路由修好了 App 还是不行」。不要在节点与链路上继续纠缠。

### 9. Google「异常流量 / IP 地址 A ≠ B」= 同一 Google 生态被拆成两个出口（2026-10-26 实测）

sorry 页上 `IP 地址: A ≠ B` 不是链路坏了，是 Google 在同一浏览器会话里看到了**两个不同源 IP**。
取证（Surge 记录里 `originalPolicyName` 才是生效策略；`remoteAddress` 是**代理入口地址**，
AnyTLS-AT&T 与 AnyTLS-BWG 入口都是 64.64.237.34，不能拿它当出口 IP）：
```bash
curl -s -H "X-Key: <密码>" http://10.0.0.2:6171/v1/requests/recent | python3 -c "
import sys,json
for r in json.load(sys.stdin)['requests']:
    u=r.get('URL','')
    if any(k in u for k in ('youtube','googlevideo','ytimg','google','gstatic')):
        print(r.get('originalPolicyName'),'|',u[:60])"
```
判据：`www.youtube.com`/`googlevideo`/`i.ytimg.com` 命中一组策略，而 `www.google.com`/
`safebrowsing`/`oauthaccountmanager` 命中另一组 → 双出口。实测样例：YouTube 组被切到 BWG
（搬瓦工直出 64.64.237.34），Google 组 AT&T（家宽 108.230.34.31），sorry 页就显示
`108.230.34.31 ≠ 64.64.237.34`。

- 根治：让 YouTube 组**跟随** Google 组（`YouTube = select, Google, AT&T, ...`），任何切换都不会再分裂；
  或两组统一 AT&T 家宽。机房 IP 承载 Google 全家必然反复触发风控。
- 排除「IP 本身被拉黑」：从出口机本机 `curl https://www.google.com/search?q=test` 与 youtube，
  返回 200 且页面无 sorry → 家宽 IP 干净，问题只在客户端双出口（本机需 sshpass 到 AT&T 跑）。
- 止血：清 google.com/youtube.com cookie 或换 profile；风控 exemption 到期后自恢复。

## 验证

- 报告 8 个检查项齐全、结论含故障点和下一步 → 完成
- 修复动作属于 Surge 配置修改时必须先征求用户同意（只读原则）
