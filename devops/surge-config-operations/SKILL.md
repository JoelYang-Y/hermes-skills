---
name: surge-config-operations
description: 用户问 Surge UDP/QUIC/MASQUE 节点配置或 SubStore 批量参数时使用。
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [surge, udp, quic, substore, masque, proxy-config]
    related_skills: [proxy-chain-diagnostics, vps-ops, nas-docker-ops, site-egress-check]
---

# Surge 配置运维（UDP/QUIC/MASQUE/SubStore）

管理 Surge 的 QUIC/UDP 行为、MASQUE 节点支持、以及通过 SubStore 批量注入节点参数。与 proxy-chain-diagnostics（链路诊断）互补：本技能管"配置怎么调"，那个管"链路通不通"。

## When to Use

- 用户报 ChatGPT/游戏等 iOS app 间歇连不上，怀疑 QUIC/UDP
- 用户问"怎么用 MASQUE"、"搞个支持 UDP 的节点"
- 用户问 SubStore 能对节点做什么、批量改节点参数（block-quic/udp/tfo）
- 需要在 Surge 与 SubStore 之间同步节点策略
- 用户问 IPv6 能不能开/怎么开/规则支不支持 IPv6、reload Surge、改生效 profile（见 IPv6 章节）
- 用户提到"手机端改了配置等 iCloud 同步"（生效 profile 在 iCloud 云盘，不是本地 Profiles）
- 用户报 Surge Ponte 连不上/无法使用（见 Ponte 章节）
- 用户要求创建、扩展或发布 Surge 远程 `RULE-SET` 规则集

## 远程 RULE-SET 生成与 GitHub 发布

### 标准流程

1. 先检查目标仓库、当前分支和工作区状态；只新增或修改规则集相关文件，绝不把已有的无关改动一起提交。
2. 按服务类别拆分规则文件，并提供一个合并规则集；根域名优先使用 `DOMAIN-SUFFIX`，只有确认过的单 IP 才加入 `IP-CIDR,/32,no-resolve`。
3. 不要把 Cloudflare、Akamai、Fastly、AWS 等共享 CDN 的大网段加入金融、购物或通信规则，因为会误匹配大量无关站点；IP-CIDR 仅作为动态 DNS 快照辅助项。
4. 写入后检查规则数量、重复项和格式；规则行应匹配 `DOMAIN-SUFFIX,<domain>` 或 `IP-CIDR,<ip>/32,no-resolve`，并确认没有 Surge FakeIP（如 `198.18.0.0/15`）被误当作真实服务 IP。
5. 使用 `gh auth status`、`gh repo view ... --json isPrivate,visibility` 检查 GitHub 权限和可见性；只暂存目标规则文件，提交并推送后，通过 `gh api repos/<owner>/<repo>/contents/<path>?ref=<branch>` 回读每个文件。
6. 私有仓库的 `raw.githubusercontent.com` 对 Surge 通常返回 `404`；只有用户明确授权公开时才修改仓库可见性，并提醒公开仓库会暴露全部现有内容，禁止其中存在凭据、Cookie、证书私钥或 Token。
7. 验证订阅链接时同时测试分支链接和提交固定链接。GitHub Raw 分支地址可能短暂命中 CDN 旧缓存；用完整提交 SHA 的 Raw 地址验证新内容，并把分支地址作为自动更新链接、固定地址作为立即可用的回退链接。实测（2026-10）：`main` 分支 Raw 刷新延迟约 5-6 分钟（push 后 2 分钟仍返回旧内容，第 6 分钟才更新），期间只认 SHA 链接；不要因为它仍旧就反复重推或新建文件。追加 `?v=<sha>` 查询串可当场绕过缓存自检。
8. 用户要求删除或替换一条规则时，先在 `surge/*.list` 和远程分支中全局搜索该规则，再同步清理所有已发布的派生列表；只改一体化文件会让分类订阅继续暴露旧规则。**资产退役、换 IP、卖机器时必须清掉对应的 `IP-CIDR,<旧IP>/32`**：该 IP 释放后可能被他人获得，残留的精确规则会让陌生流量错误命中你的策略，属于路由污染而不只是垃圾配置；清理后必须用 commit SHA 的 Raw 固定链接回读确认残留为 0（只看 `git push` 成功不算验证，branch 地址有 5-6 分钟 CDN 缓存）。
9. 用户仍看到已删除内容时，先分别读取 GitHub API 内容和 Raw 内容判定是仓库状态还是 Surge/CDN 缓存；若仓库已正确而缓存未刷新，创建新的语义化文件路径（例如 `us-all-no-apple.list`）并用新 URL 验证后交付，避免继续复用旧缓存键。

### 规则集交付约定

- 分类文件按通信、银行、信用卡、券商、支付、购物、云平台等职责拆分；合并文件明确列出其包含的类别。
- 区分“无策略名的远程 RULE-SET 列表”和“带 `AT&T`/`BWG` 等策略名的完整 Surge 配置”：WiFi Calling 的 `AND + UDP 500/4500` 与 T-Mobile 专用 CIDR 属于策略绑定规则，不能默认为已包含在通用域名列表中。
- README 必须给出每个订阅 URL、Surge `RULE-SET` 示例、IP 动态性说明和安全边界。
- 远程回读必须核对实际内容、规则数量和用户点名的关键行，不能仅凭 `git push` 成功或单个 API 文件回读就声称订阅可用。

## Surge QUIC/UDP 语义（2026-08 官方手册验证）

### block-quic 全局参数（[General]）

```
block-quic = per-policy | all-proxy | all | always-allow   # 默认 per-policy
```

| 值 | 行为 |
|---|---|
| `per-policy`（默认） | 由每个策略自己的 block-quic 决定 |
| `all-proxy` | **覆盖**代理策略设置，阻止所有走代理的 QUIC |
| `all` | 连 DIRECT 的 QUIC 也阻止 |
| `always-allow` | 覆盖代理策略设置，全部放行 |

### block-quic 节点级参数（[Proxy]）

```
Name = anytls, host, port, block-quic=auto|on|off   # 默认 auto
```

- `auto`：按策略是否适合转发 QUIC 自动决定（AnyTLS 支持 UDP relay → auto 放行）
- `on`：阻止 QUIC（客户端回退 HTTPS/TCP）
- `off`：不阻止
- 省略 = 代理策略默认阻止 QUIC；DIRECT 等内置策略不阻止

### 让 QUIC 走通的最小改动

1. 注释全局 `block-quic = all-proxy`（恢复默认 per-policy）
2. 节点级去掉 `block-quic=on`（= auto）
3. `udp-policy-not-supported-behaviour = REJECT` 可保留——AnyTLS 支持 UDP 不会触发

⚠️ Surge 配置**只读红线**（2026-08-13 用户发怒后升级）：**可读可查，任何时候不能修改**。只有用户明确说"改吧/可以改"才算授权；"好"、"嗯"、"记住了"等模糊回应**不构成**授权——曾因把"好"当批准误改生效配置引发用户强烈不满（已恢复原样）。任何服务器（搬瓦工 VPS/NAS/ATT）同理：未经明确"修改"指示不得改配置/文件/服务。用户通常自己动手改，助手只给改法，只做查询/诊断。

### UDP relay 协议支持表（官方手册）

| 协议 | UDP relay |
|---|---|
| SOCKS5 / SOCKS5-TLS | 需 `udp-relay=true` |
| Shadowsocks | 需 `udp-relay=true` |
| Snell v3+ / VMess / Trojan / TUIC / Hysteria 2 / MASQUE / AnyTLS / WireGuard / Tailscale | 自动支持 |
| HTTP/2 CONNECT | 需 `udp-relay=true`（6.9.0+） |
| HTTP(S) / TrustTunnel / SSH | 不支持 |

关键结论：**AnyTLS 原生支持 UDP relay（UDP over TCP），无需换节点**。用户自建 AnyTLS 节点（VPS s-ui 入站 + ss2022 出口）服务端默认支持 UDP。

### WebRTC/STUN 泄露验证（2026-08-13 实测）

浏览器 WebRTC 泄露测试（browserleaks.com/webrtc）= 向 STUN 服务器发 UDP Binding
请求反射公网 IP。WebRTC UDP **不遵守 HTTP 代理设置**，是独立泄露向量；但 Surge TUN
增强模式接管 UDP → 反射 IP 应为代理出口。验证脚本（同款机制，只读 UDP）：
`surge-config-operations/scripts/stun_egress_test.py`；脚本不可用时手写也简单——
Binding Request 头 type=0x0001 + magic cookie 0x2112A442 + 12B txid，解析
XOR-MAPPED-ADDRESS（0x0020）属性。

判定：反射 IP = 代理出口（107.141.151.219 AT&T）= 无泄露；= 真实家宽
（49.65.142.146 南京电信）= 泄露；无响应 = 该路径被 `udp-policy-not-supported-behaviour
= REJECT` 掐了。
注意 browserleaks.com 页面 "Your IP Address" ≠ "WebRTC Public IP" 不一定是泄露：
**browserleaks.com 本身在 China.list 里** → DIRECT → 显示真实 IP，而 STUN 走 Google
规则 → 代理。先查网站的规则匹配（check_domain.py）再下结论。

## MASQUE（Surge 6.9.0+）

- 声明语法：`Name = masque, <host>, <port>, username=user, password=pass`
- 实现：HTTP/3 CONNECT（多路复用 TCP）+ CONNECT-UDP（RFC 9298/9297）
- 参数：username/password（HTTP Basic）、port-hopping、port-hopping-interval、alpn（默认 h3）、ecn
- **WARP 的 MASQUE 不兼容**：走 CONNECT-IP（RFC 9484）且 Cloudflare 实现不完全合规；Surge 只实现 CONNECT + CONNECT-UDP，没有 CONNECT-IP
- 机场那种带 private-key/public-key 的 WARP 风格 masque 节点（mihomo/sing-box 用）同样不兼容 Surge

## IPv6 开启（2026-08-12 实测成功）

### 前置判断：本地是否有公网 IPv6

- `ifconfig en0 | grep inet6 | grep -vE "fe80|fdcd"` — 有 `240e:` 等 2000::/3 GUA 才是真公网 IPv6；只有 `fdcd:`（ULA）没有默认路由 = 路由器没下发
- `netstat -rn -f inet6 | grep default` — 注意 **`route -n get -inet6 default` 在 macOS 会假报 "not in table"**，用 netstat 才是真的
- 若 Mac 有 GUA 但 `curl -6` 秒失败（0.2s HTTP 000）→ 典型症状：**Surge 增强模式在跑但 Surge 自己 ipv6=false/ipv6-vif=disabled**，utun 声明了更高优先级 IPv6 默认路由但不处理 IPv6 = 黑洞。这是 Surge 配置问题，不是路由器问题

### Surge 侧最小改动（用户已授权时）

```
[General]
ipv6 = true          # 从 false
ipv6-vif = auto      # 从 disabled；不要用 always（6.9 起官方警告，非 IPv6 环境强开会卡微信/淘宝）
```

规则/节点/DNS 全不用动：ChinaCIDR.list 等 RULE-SET 内含 IP-CIDR6（中国 IPv6 段 → DIRECT），海外域名因 paopao 屏蔽 AAAA 继续走 IPv4 代理。

### 生效 profile 的实际位置（关键！2026-08-13 修正）

- **实际生效配置在 Surge 的 iCloud 同步容器**：`~/Library/Mobile Documents/iCloud~com~nssurge~inc/Documents/JoelYang.conf`（Surge 只读这个）
- `~/Library/Mobile Documents/com~apple~CloudDocs/JoelYang.conf` 是 **8/12 22:10 的历史快照**（启 IPv6 后另存的副本），同目录 `JoelYang.conf.bak-ipv6-20260812221035` 是启 IPv6 前的备份——**都不是生效配置**，与生效版有 block-quic/节点 block-quic/m-team/MITM 证书差异
- `~/Library/Application Support/Surge/Profiles/` 是旧残留（Default/Kuromis/Surge Mac.conf），**不是**生效配置
- 手机端 Surge 改配置 → iCloud 同步到生效文件 → 改完需 reload
- iCloud 文件提供程序目录 `ls` 可能超时（按需下载卡住），改用 mdfind 定位、Python os.stat/open 直读
- **Surge HTTP API 没有写 profile 内容的端点**：PUT/POST /v1/profiles/current 无效（method not allowed 或静默不生效）。改法是直接编辑生效 .conf 文件（改前备份），然后 reload
- 改前备份：`cp JoelYang.conf JoelYang.conf.bak-$(date +%Y%m%d%H%M%S)`

### Reload 与验证

```bash
curl -s -X POST -H "X-Key: <密码>" http://10.0.0.2:6171/v1/profiles/reload   # 返回 {} = 成功
curl -s -H "X-Key: <密码>" http://10.0.0.2:6171/v1/profiles/current | grep -i ipv6
curl -6 -s -o /dev/null -w "%{http_code}" https://www.baidu.com    # 200 = 国内 IPv6 直连通
curl -s -x http://127.0.0.1:6152 https://api.ipify.org             # 海外出口应仍 107.141.151.219 (AT&T)
```

- 验证 VIF 接管：`netstat -rn -f inet6 | grep default` 出现 `fd00:6152:: via utun4` = Surge IPv6 网关生效（类似 IPv4 198.18.0.1）
- macOS `ping6` 常报 "nodename nor servname provided"（工具怪癖），用 `curl -6` 或 `ping -6` 实测

### ⚠️ Reload 引擎崩溃事故（2026-08-12）

iCloud 同步容器异常时 reload 会令 **Surge 引擎进程退出**（Dashboard UI 还在但引擎没了），症状：
- 6171/6152/6153 全部无监听，`curl -6`/代理全部 000，TUN 掉（vmenet0 无输出）
- 日志（`log show --predicate 'process == "Surge"' --last 3m`）出现 `ERROR (SGDDNS.m): Zone Not Found / Zone does not exist / container ID = "iCloud.com.nssurge.inc"`

- 恢复：`open -a Surge`（引擎重启，API 端口回来）。预防：手机端与 Mac 端 iCloud 同步异常时不要轻易 reload；观察期若反复崩溃，建议关闭 Surge iCloud 同步改手动管理 profile。

### DNS 层：AdGuardHome `aaaa_disabled` 陷阱（2026-08-12 实测）

国内域名（baidu/qq）拿不到 AAAA、返回 SOA 负缓存（`fake-for-negative-caching.adguard.com`）时，**先查 AdGuardHome 的 `aaaa_disabled`**——它会在 AdGuardHome 层全局拦截所有 AAAA 查询，**根本不转发给 paopaodns**，所以国内域名也被误伤：

```bash
# 10.0.0.6 (paopao DNS 服务器, Alpine, SSH: root@10.0.0.6:22 密码 <密码> 带句点)
grep aaaa_disabled /root/AdGuardHome/AdGuardHome.yaml   # true = 罪魁祸首
sed -i 's/aaaa_disabled: true/aaaa_disabled: false/' /root/AdGuardHome/AdGuardHome.yaml
docker restart adguardhome
# 改前备份: cp AdGuardHome.yaml AdGuardHome.yaml.bak-aaaa-$(date +%Y%m%d%H%M%S)
```

修复后行为：国内域名 AAAA 恢复（`240e:`），海外仍由 paopaodns 屏蔽（`IPV6=yes/CNAUTO=yes` 在 paopaodns 层实现，与 AdGuardHome 的 `aaaa_disabled` 是两层独立开关）。

**关键认知**：DNS 服务器自身**有没有 IPv6 地址，完全不影响**它解析/返回 AAAA 记录——解析是协议功能，查询走 IPv4 传输，客户端拿到 AAAA 后自己用 IPv6 连接目标。10.0.0.6 容器无 IPv6（纯 IPv4 bridge 172.19.0.2）也能正常给国内域名返回 `240e:`。

10.0.0.6 服务器架构：Alpine，adguardhome 容器（监听 53/80/443/3000，DoH server_name=adg.jhsweetheart.com，上游 tcp://10.0.0.6:5335 单条且无 fallback）+ paopaodns 容器（监听 5335/5304/7889），本机有公网 IPv6 `240e:3a3:1006:36d0:be24:11ff:fe8f:b9d0`，配置在 `/root/AdGuardHome/AdGuardHome.yaml` 与 `/root/PaoPaoDNS`。

完整 DNS 层实录（现象/根因/修复/10.0.0.6 速查表）见 `references/dns-ipv6-aaaa-2026-08.md`。

链路级只读体检（Surge 是否真在用加密 DNS、DoH 证书到期审计、单上游超时跨层归因、拦截误伤判读）见 `references/dns-chain-audit.md`。

完整实录（路由器页配置表、API 探测结论、崩溃日志细节）见 `references/ipv6-enable-2026-08.md`。
ECS 检测方法/结论（dig +subnet 判定、GeoDNS 等效、FakeIP 观察）见 `references/ecs-detection-2026-08.md`。

## Surge Ponte（内网穿透/Mesh 组网）

Ponte = Surge 私有 mesh 网络：Mac/Apple TV 可做服务端，iOS 仅客户端。**设备信息与密钥完全靠 iCloud CloudKit 同步**（container `iCloud.com.nssurge.inc`）——这是 Ponte 排障的第一入口。

### 典型故障与根因（2026-08-12 实测）

| 日志/现象 | 根因 | 修复 |
|---|---|---|
| `[SGDDNS] Failed to update DDNS record: CKError "Zone Not Found" (26/2036)` | CloudKit DDNS Zone 缺失 → Ponte 无法注册/发现设备（与 reload 引擎崩溃同因） | Surge Mac 设置 → 关闭 iCloud 同步 → 重启 Surge → 重开 iCloud 同步，强制重建 Zone |
| `[SGPonteServerChannel] Failed to start ponte channel: Ponte 服务启动失败，UDP 流量被阻拦` | `udp-policy-not-supported-behaviour = REJECT` 把 Ponte UDP 通道掐了（Ponte 走 UDP 6208，匹配到不支持 UDP 的策略即被 REJECT） | 该参数改 `DIRECT`；或检查 Ponte 配置的 NAT 穿透方式（直接 NAT 需 Full Cone；代理穿透需选支持 UDP 的代理；静态端口转发需公网 IP + 6208 UDP 放行） |

### 排查要点

- Ponte 监听端口：UDP 6208（`lsof -nP -iUDP:6208 | grep Surge`，IPv4+IPv6 双监听正常）
- macOS 应用防火墙：`/usr/libexec/ApplicationFirewall/socketfilterfw --getappblocked /Applications/Surge.app` 应显示 permitted；firewall 开启不是问题（Surge 已授权）
- API 无 ponte 端点（`/v1/ponte` 等 = unknown path）——Ponte 是 UI 功能，只能日志 + UI 排障
- 日志：`log show --predicate 'processImagePath CONTAINS "Surge"' --last 30m | grep -iE "ponte|CKError|SGDDNS"`（`A`/`E` 级行才是错误，`Df` 是调试噪音）
- 用 `DEVICE:MACMINI` 规则（`IP-CIDR,10.0.0.0/24,DEVICE:MACMINI`）存在 = 用户之前配置过 Ponte

详细实录见 `references/ponte-troubleshoot-2026-08.md`。

## 国内 App 慢排障（路由归属体检，2026-10 实测）

症状：国内 App「有的还是慢」——图片转圈/白屏，但主 API 正常。根因几乎都是**国内 CDN 域名被送到海外出口**。

诊断法（只读）：并发经 Surge 代理 6152 打一批国内 App 域名 → 读 `/v1/requests/recent` → 匹配每条记录的
`rule` 与 `policyName`。非 DIRECT 的就是嫌疑。51 域名实测脚本模式见本条末。

两个高发根因：
1. **FINAL 兜底指向海外节点**（如 `FINAL,AT&T,dns-failed`）：未收录的国内 CDN 全部出国。
   实测命中：`kwimgs.com`/`kwaicdn.com`(快手)、`mtimg.com`(美团)、`miimg.com`(小米) → FINAL → AT&T。
2. **国际规则误收国内域名且排在 China 之前**：`TikTok.list` 含 `DOMAIN-SUFFIX,snssdk.com` 与
   `ibytedtos.com`（字节**国内**抖音/对象存储域名，`snssdk.com` 本就在 China.list 里），因 TikTok 规则
   先命中被抢走 → AT&T。TikTok 国际版实为 `isnssdk.com`/`tiktokv.com`/`tiktokcdn.com`，豁免 snssdk 不影响 TikTok。

修法（用户授权后）：`[Rule]` **最顶部**（任何规则之前）加 6 条 `DOMAIN-SUFFIX,<域>,DIRECT` 抢回；
`FINAL,AT&T` → `FINAL,DIRECT`。AT&T 家宽只留给需要美国住宅 IP 的高可信规则（PayPal/银行/AdsPower）。

附带检查：`节点选择` select 组的默认项若为 AT&T（美国家宽），则 `Proxy.list` 全部通用域名走家宽，
带宽/稳定性劣于 BWG VPS——`X-Surge-Policy` 探测出口可确认（AT&T=108.230.34.31，BWG=64.64.237.34）。

### 视频 App「能刷列表、点播放就加载失败」= 视频 CDN 域漏抓（2026-11-01 实测）

症状指纹：列表/推荐流正常（内容 API 命中 DIRECT），**点进剧集播放即报加载失败**；同厂商其他 App 正常。
根因不是网络断，而是**视频流域名未被规则集收录、且 IP 兜底没接住**。实测红果漫剧（`com.kylin.read`）：

- 视频域 `*.qznovelvod.com` 在 China.list / ChinaMedia.list / ChinaCIDR.list / Proxy.list **全部 0 命中**
- 同一 App 不同 CDN 线路的子域会分叉：`v95-zjjx2tc-*`/`v5-se-bjtc-*` 解析到 222.186.163.x、
  101.227.94.55、58.216.46.x、175.6.204.x、114.80.149.x → 命中 `IP-CIDR(in China)` → **DIRECT**（能播）；
  `v95-se-zjwztc-*` 解析到 223.244.13.x / 223.247.67.x（安徽电信，**ChinaCIDR.list 未收录该段**）
  → 无 IP 兜底 → `FINAL` → `Final -> BWG -> Sub-BWG`（搬瓦工美国）→ 播放失败
- 判据三连（缺一不可）：① `/v1/requests/recent` 里该视频域 `policyName=Sub-BWG`、note 写 `Rule matched: FINAL`；
  ② 同一时刻同类子域 note 写 `Sub-rule matched: IP-CIDR(in China...)` 且 DIRECT；③ 出口对比实验
  `curl -H "X-Surge-Policy: DIRECT" http://<视频域>/` → 403/200 且 0.2~0.3s；`X-Surge-Policy: Sub-BWG` → HTTP 000 秒失败。
  国内 IP + 只服务大陆的 CDN，从美国出口必 000。
- 修法（用户自行在 Surge App 内应用）：`[Rule]` 最顶部加 `DOMAIN-SUFFIX,qznovelvod.com,DIRECT`，不依赖 IP 兜底。

**通用教训**：`IP-CIDR(in China)` 兜底只能救「解析到已收录国内网段」的请求，一旦 CDN 换段或调度到
未收录的 /24（城市级边缘节点经常如此），同一个 App 就会时好时坏。凡「国内视频/图片 CDN 域」一律
优先补 `DOMAIN-SUFFIX,...,DIRECT`，不要指望 CIDR 列表。字节系同源风险域还有 `volccdn.com`（火山 CDN，
当前整体落 Sub-BWG）、`ndcpp.com`（VCS 心跳，UDP 9681 落 Sub-BWG）。

**排查顺序**：先看 `FINAL` 实测落点（`curl -H "X-Surge-Policy"` 或 recent 的 FINAL 记录）→ 再按 App 抓
视频域（点播放那一刻拉 recent，过滤 sourceAddress=手机 IP）→ 最后做 DIRECT vs 兜底策略的出口对比。

### 双层故障：路由修好了 App 还是不行 → 必查 AGH 是否把 SDK 域名拦成 0.0.0.0

**指纹（2026-11-01 红果漫剧实测）**：点播放报加载失败，按 App 抓 150 秒，**零个视频域请求**，
但某个 SDK 域每秒重试数次（实测 `i.snssdk.com` 879 次/150s）。此时路由层已无误，问题在 DNS。

成因：HaGeZi's Pro / 1Hosts Lite / anti-AD / SkkMoe 等订阅会收录字节、腾讯系 SDK 域，
AGH 重启或过滤器每日更新后突然开始拦（本次过滤器时间戳 11-01 05:11）。Surge 拿到 `0.0.0.0` 后
按 cached DNS 记录去连 **`remote 127.0.0.1`**，连接必然失败；App 卡在 SDK 初始化/解锁，
根本走不到请求视频流那一步——所以只加 Surge 域名规则永远不会生效。

**判据（recent 的 notes 直读）**：
```
[DNS] Use cached DNS result for i.snssdk.com. A record count: 1
remote 127.0.0.1
```
`remote` 是 127.0.0.1 或 0.0.0.0 而非真实公网 IP，就是 DNS 被拦，不是路由问题。

**取证三步**：① `nslookup <域> 127.0.0.1`（在 10.0.0.6 上查 AGH）看是否 `0.0.0.0`；
② Cloudflare DoH 查公网记录，有 CNAME/A 则说明是真实服务域被误拦（不是真广告域）；
③ 在过滤器文件里定位规则：`grep -rn "||i.snssdk.com^" /root/AdGuardHome/data/filters/*.txt`。

**修法（AGH `@@` 例外规则，优先级最高）：按域放行，不要逐条列子域。** 同一个 App 会打大量子域变体
（`i.snssdk.com` / `is.snssdk.com` / `mssdk.zijieapi.com` / `polaris.zijieapi.com` / `ads3-normal.zijieapi.com` /
`mon11-misc-lq.fqnovel.com` / `tnc0-alisc1.zijieapi.com` …），逐个列子域必然是「放一个漏十个」，
用户会一轮轮回「还是不行」。直接上域级规则一次覆盖：

```
@@||snssdk.com^        @@||zijieapi.com^      @@||fqnovel.com^
@@||toutiaocloud.com^  @@||toutiaocloud.net^  @@||bdurl.net^
@@||bytedance.com^     @@||byteimg.com^       @@||pstatp.com^
@@||amemv.com^         @@||ecombdapi.com^
```

代价是这些域下的埋点与广告 SDK 一并放行；第三方广告（`doubleclick.net`、`googleadservices.com`）
仍被拦，验证时用这两条对照确认没把全局拦截弄坏。yaml 改法、sshpass 引号坑与回滚见
`references/dns-chain-audit.md` §2.5。

### 改完 AGH 必须让用户退出 Surge 进程，否则改多少条都无效

**本类问题最容易漏、也最消耗来回的一步。** AGH 放行后 Surge 仍用自己缓存里的 `0.0.0.0` 去连：

```
[DNS] Use cached DNS result for i.snssdk.com. A record count: 1
[Socket] Use the last successful address: 0.0.0.0
[Socket] Connected to address 0.0.0.0 in 0.0ms     ← 连空地址，瞬间"成功"
[Connection] Remote closed sending stream           ← 立刻断
```

判据：AGH 侧 `nslookup` 已返回真实 IP，而 recent 里该域 `remote` 仍是 `127.0.0.1` / `0.0.0.0`。

- 清缓存只有一种可靠办法：**退出 Surge 进程再打开**（菜单栏 → Quit Surge）。DNS 缓存活在进程内，
  重载配置无效；等 TTL 也不可靠（实测等满数分钟仍是旧值）。措辞必须说「退出 App 再打开」，
  说成「重载配置」或「等缓存过期」会让用户继续无效重试。
- **缓存按域逐个过期**，同一批放行之后会出现「4 个域已恢复真实 IP、另 4 个仍连 127.0.0.1」的中间态。
  别看一个域通了就宣布修好，也别看一个域没通就断言规则没生效——把所有目标域逐个打一遍，
  统计 `remote` 已变成公网 IP 的比例，全绿才给结论。
- 手机侧还要**杀进程重开 App**，App 自身也缓存失败状态。
- 改完 AGH 后先自查缓存是否已释放（Mac 上打一次该域，看 recent 的 `remote` 是否变成真实 IP），
  确认后再让用户测试，否则一定得到「还不行」。

**通用教训**："国内 App 播放失败"有两条独立故障链——路由层（视频域出国）与解析层（SDK 域被拦）。
两层会叠加，修好一层用户仍会回"还是不行"。先看 recent 里**有没有视频域请求**：没有就是解析层，
有但落海外就是路由层。

**交付方式**：这类多层故障一次性给完整清单——全部待放行的域、全部待加的 Surge 规则、验证命令、
回滚方式——执行完再回报。不要一轮只给一条规则让用户反复试，那会把一次二十分钟的排障拖成十几轮往返；
每轮回报都要带三样东西：改了什么（含备份路径）、实测验证结果表、下一步的唯一判据。

注意：API `/v1/profiles/current` 的 `profile` 字段是**运行时**配置（含 module 注入如 `always-raw-tcp-*`、
Apple WLOC 脚本），与 iCloud 本地 .conf 文件常有差异——改配置要改生效的主配置，别被本地快照误导。

## 配置合理性审计（只读体检）

用户问"看下我当前 surge 配置文件合理性 / 全局检测一下 / 根据本机网络环境判断"时走这条流水线，全程只读。结论按 P0/P1/P2/P3 陈述**证据、影响、位置**；**不出"待授权改动清单"、不追问是否授权**（Surge 由用户独占管辖，改不改自己决定）。完整命令与判读表见 `references/config-audit-playbook.md`。

1. 用 `/v1/profiles/current` 的 `name` 确定生效 profile（iCloud 容器里常有多份 `.conf`，profile 列表里的旧项会被误选）。
2. 本地 `.conf` 与运行时 `profile` 全文做归一化 diff（去注释、掩码 `policy-path`、剔 `ca-p12`）：**`[Rule]` 段必须逐行一致**，差异只允许出在 Module 注入（`always-real-ip` 追加、`always-raw-tcp-*`、`[MITM] hostname`、`[Script]`）。
3. `/v1/rules` 统计类型分布时过滤注释与空行（否则规则数虚增）。
4. `/v1/policy_groups` 逐组查成员数与伪节点（`2.86 G | 200.00 G` 这类是 Sub-Store 渲染的流量信息，不是节点）。
5. 40~50 个代表域名并发打 6152 → 回读 `/v1/requests/recent` 对照 `policyName`+`rule`；**`rule=FINAL` 的样本最能暴露兜底落点**。现成脚本：`scripts/route_sample.py`（内置五类分组清单、自动补探未收录域名确认 FINAL 落点、国内域名非 DIRECT 告警）。抽到 FINAL 为 0 条时不要写"兜底没问题"——recent 只有 200 条且常被单一设备的 TLS 请求占满，样本不代表全量，必须主动构造未收录域名（`example.com` / 随机不存在域）复现一次。
6. 出口验证必须用明文 http + `X-Surge-Policy`（https 下该头失效）。
7. 扫日志：脚本/规则源 404、多 DoH 空应答、`SGDDNS Zone Not Found`。判"多 DoH 抢答"不要用 `curl -H 'accept: application/dns-json' '.../dns-query?name=x&type=A'`（AGH 回 Bad Request、AliDNS 回 no 'dns' query parameter），用 `scripts/doh_compare.py` 走 POST wire-format 同时对比内网与公网上游的 ancount/rcode。
8. **安全扫描必做**：本机被 git 跟踪的 `.conf` 可能已推到公开仓库且带明文控制器密码——见 Pitfalls 6。

## DNS 链路体检（Surge → AdGuardHome → PaoPaoDNS）

用户问「检查网络链路 / paopaodns / adguardhome / DNS 解析」时走 `references/dns-chain-audit.md`。
三条硬结论的取法，都不要靠猜：

1. **Surge 到底有没有在用加密 DNS** —— 读 AGH 的 `data/querylog.json`，`"CP"` 字段直接给答案（`doh` 占绝对多数 = 在用）。不要用 tcpdump 或宿主 `ss -tn`：AGH 在容器命名空间里，宿主上看不到 443 的 ESTABLISHED，看到 0 条会误判成"没走 DoH"。
2. **DoH 证书还剩多久** —— `openssl s_client -connect 127.0.0.1:443 -servername <SNI>` 配 `x509 -noout -dates`，再查 `~/.acme.sh` / `crontab -l` / `systemctl list-timers` 有无续期。AGH 的证书常**手工内嵌在 `AdGuardHome.yaml` 的 `certificate_chain`**，不在 `/etc/letsencrypt`，因此**不会被通配符证书的 acme 续期覆盖**——三处续期痕迹全空 + 到期在 30 天内即 P0，到期后 Surge DoH 静默回落到明文 53，表现为"部分站点偶发异常"而不是报错。修复路线看 `adguardhome-doh-deploy` 的「DoH 证书的自动续期」章节：内嵌 PEM 必须先切 `certificate_path` / `private_key_path` 再接 acme.sh + `--reloadcmd`，否则每次续期都要动 yaml。体检阶段只陈述到期事实与影响，不动 AGH 配置。
3. **解析慢/失败归到哪层** —— AGH 日志 `exchange failed ... i/o timeout duration=2.00s` 属 `upstream_dns` 单上游无 fallback + PaoPao 对不存在域（`*.jddebug.com` 这类调试域）慢速 NXDOMAIN，同一条因果链会同时出现在 Surge 日志的 `DNS failed: <domain>` 里。**归因到 AGH 上游，不要写成 Surge 的问题。**

分层归因表：解析 p50 偏高 → AGH 缓存/PaoPao；个别域 2s 失败 → AGH 单上游；大量 SERVFAIL → AGH DNSSEC；明文 53 出现查询 → Surge DoH 断裂；国内外 IP 都错 → PaoPao 分流；解析对但连不上 → 与 DNS 无关，转 `proxy-chain-diagnostics`。

## 诊断陷阱

- `curl` 测 OpenAI 返回 403/421 是正常现象（非浏览器指纹），**不能**判断 app 是否可用；最终判据是手机 app 实测
- 系统日志 `quic-connection ... cancel` 不代表 Surge 拦截，app 自己放弃也会取消
- 改前改后都能用 → QUIC 不是根因，间歇问题多为节点链路抖动
- 服务端 UDP 验证：scp 拉 s-ui db 回本地 sqlite3 查 inbounds/outbounds；anytls 入站无 `udp` 字段 = 默认支持
- **`curl -6` 返回 200 不等于有 IPv6 出口**：Surge TUN + FakeIP 下会把 AAAA 请求映射成 `::ffff:198.19.x.x`（198.18.0.0/15 FakeIP 段的 IPv4-mapped 形式），连接照样成功。判据是 `curl -6 -v` 里 `Trying [...]` 的实际地址（形如 `::ffff:198.19.14.252` 就是假象），权威结论看 `scutil --nwi` 的 `IPv6 network interface information`（`No IPv6 states found` = 确实没有 IPv6 出口）。别只凭 HTTP 状态码下结论
- **macOS `arp -an` 可能整张表为空**，`ndp -an` 也常无输出：不能用 ARP 判邻居设备身份。改用 `route -n get <ip>` 看走哪个 interface、以及 Surge `/v1/devices` 的 identifier/displayIPAddress 对照。同理 `nc -z` 对不响应主机可能长时间挂起（曾把一条命令拖到 180s 超时），批量探端口一律用 `curl --connect-timeout 2` 或分批
- **TUN 接管下 `nc -z` 测跨境端口会返回伪造握手**：本机到美国 VPS 的 TCP 建连实测 0.000–0.060s，是代理层提前完成三次握手造成的假象，既不能当链路 RTT、也不能当丢包结论。跨境质量看 `ping`（该 IP 命中 DIRECT 规则时 ICMP 才可信）或从对端反向测；判容器/内网端口可达性时 `nc -zv` 仍有效。另外 ICMP 丢包 ≠ 链路丢包：Oracle 系实例常整段禁 ICMP（100% 丢包但 SSH 端口正常），非 CN2 线路的 20% ICMP 丢包也可能只是 ICMP 降优先级，下结论前要用 TCP 层（如 SSH 建连耗时）复核
- **IPv6 三层开关必须一起看**：PaoPao 的 `IPV6=yes`（正常返回 AAAA）、AGH 的 `aaaa_disabled`（过滤 AAAA）、Surge 的 `ipv6`/`ipv6-vif`（不发 IPv6 流量）。看到 PaoPao 回 AAAA 不要判成缺陷——那是上游信息完整性，压制发生在 AGH。改任一层都要同步另两层，否则要么泄漏要么误禁
- **访问自有服务器的裸 IP 全超时，先查有没有显式 DIRECT 规则**：`[Rule]` 里一旦缺了 `IP-CIDR,<ip>/32,DIRECT`（或被误删、或从未写过只是笔记里以为有），该 IP 的流量会一路落到 `FINAL` 策略上——`FINAL,AT&T` 时表现为 SSH 与裸 IP 端口全部静默超时，而同机的 **Cloudflare 橙云域名照常 200**（回源走 CF 自己的链路，不经你的规则）。这个组合就是它的唯一指纹：**橙云活 + 灰云与裸 IP 死 = 本地分流问题，不是服务器故障**。排查顺序是先到服务器侧排除服务器嫌疑（fail2ban/iptables 干净），再回来 `grep -nE '<ip>' "$CFG"; grep -nE '^FINAL' "$CFG"` 对账；分层判据见 `oracle-cloud-ops` 的「连不上 OCI：先分层定位」。修法是补回 DIRECT 规则，但配置只读——只出 diff 由用户自己应用

## SubStore 批量节点参数（Quick Setting Operator）

SubStore（NAS 10.0.0.3:3002）的 Quick Setting 可批量给订阅节点注入参数，刷新后 Surge 节点自动生效，比在 Surge 里逐个改高效且不丢。

支持 key：`useless` / `udp` / `scert` / `tfo` / `vmess aead` / `block-quic`（值 DEFAULT/ENABLED/DISABLED 或 auto/on/off）

Surge 集合推荐：`udp=ENABLED`（所有节点 udp-relay）、`block-quic=auto`、`useless=DISABLED`

- **作用域（2026-08-13）**：订阅级 `process` 只作用于该订阅节点；集合级 `process`
  作用于集合内所有订阅。需要区分配置时（如奶昔开 scert、自建不开），操作器加到
  订阅级，集合级留公共参数
- 机场节点带 SNI 伪装（奶昔 h265-stream.yximgs.com），握手报证书错误时开
  scert=ENABLED；自建节点有真实证书（skip-cert-verify=false 正确）保持 DEFAULT

SubStore 完整 API 操作见 `references/substore-api.md`。

## Surge HTTP API 探测（check_domain.py v10 学到）

- `/v1/policies` 的 **proxies 列表可能是空的**：policy-path（SubStore 输出）拉来的节点被 API 掩码，proxies 空 ≠ 节点挂了；`/v1/proxies` 路径返回 unknown path（正常）。它只含 `{"proxies": [], "policy-groups": [组名...]}`，**没有成员**。要拿每组成员用 `GET /v1/policy_groups`（唯一可用端点；`/v1/policies/<名>`、`/v1/policy_groups/<名>` 全是 unknown path，别反复试）。判断节点可用性用实时出口探测（check_domain.py），别只看 proxies len
- **`/v1/policy_groups` 的结构是 `{组名: [成员对象…]}`——值是 list 不是 dict**。成员字段只有 `name` / `isGroup` / `typeDescription` / `lineHash` / `enabled`，**没有 selected 字段**（当前选中项取不到，只能从 `/v1/requests/recent` 的 `policyName` 反推该组实际落点）。按 `{k:v['proxies']}` 那套写会直接 `AttributeError: 'list' object has no attribute 'get'`；要区分组与节点看 `isGroup`，叶子策略的 `typeDescription` 是协议名（Shadowsocks/AnyTLS/REJECT/DIRECT）
- **`/v1/devices` 是可用端点**（`/v1/dhcp`、`/v1/arp`、`/v1/dhcp/clients` 全是 unknown path）：返回 `{"devices":[{displayIPAddress, dhcpLastIP, dhcpGatewayEnabled, identifier(MAC), totalBytes, dhcpHostname, topHostBySingleCon…}]}`。网关模式下拿它盘点谁在被纳管、哪些设备 `dhcpGatewayEnabled=true`；再与 `/v1/requests/recent` 的 `sourceAddress`+`deviceName` 分布交叉，才能确证"设备流量真的过引擎"而不是只看 DHCP 租约
- `/v1/rules` 返回 `{"rules": ["DOMAIN-SUFFIX,3gppnetwork.org,AnyTLS-BWG", "IP-CIDR,208.54.0.0/16,AnyTLS-BWG,no-resolve", ...], "available-policies": [...]}` — rules 是逗号分隔字符串；**RULE-SET 行只有 list URL，内部 IP-CIDR 需要拉取远程 list 文件**（如 AIGC.list 的 `129.146.3.78/32` 在文件里，不在顶层）
- `/v1/requests/recent` 记录含 `policyName` / `originalPolicyName` / `remoteAddress` / `notes` / **`URL`**（没有 `host` 字段）：域名形如 `api.deepseek.com:443`，IP 形如 `93.179.102.140:443 (api.telegram.org)`，解析见 references；`remoteAddress` 是代理入口 IP（如 64.64.237.34），**不是**出口 IP（链式节点 AnyTLS-AT&T 出口是 108.230.34.31）
- `X-Surge-Policy` 头可强制走指定策略/策略组（探测组实际出口）**但只对明文 http 目标生效**：HTTPS/CONNECT 请求里该头被忽略，两个不同组会返回同一个出口 IP——据此判"两组配到了同一节点"是误判，必须用 `http://ifconfig.me/ip` 复核；**中文策略名的编码分两条路径，混用会假报"策略不存在"**：curl 命令行直接把中文原样写进 `-H "X-Surge-Policy: 节点选择"`（shell 传的就是 UTF-8 字节，Surge 能匹配）；只有 Python urllib/requests 这类按 latin-1 编码 header 的场景才用 `str.encode('utf-8').decode('latin-1')`。**不要用 Python 转好再交给 curl**——会二次编码成 mojibake，Surge 返回 `Requested policy unavailable … Policy xxx doesn't exist`，且报错里策略名是乱码。看到乱码即判编码问题，不要以为是策略名写错或组不存在。注意这也解释了为什么 ASCII 组名（AT&T/BWG/Final）一直正常：它们不受编码影响，只有中文组名会踩。
- Surge TUN 增强模式（vmenet0 198.18.0.1）接管所有系统流量：即使 DIRECT 探测也返回 Surge 当前出口，标注"非真直连"

完整实战细节（API 字段、规则类型优先级、IP/CIDR 静态匹配、验证案例表）见
`references/surge-api-probing.md`。

## Pitfalls

0. **用户偏好：配置/验证完成后直接存 mem0 + 更新 Obsidian 笔记，不要再问"要不要存/记"**（用户已明确多次：小事自己定，只在大事如改 Surge 配置/花钱/删数据前确认）。日常小决策自主执行。
1. **命名约定：提到 paopaodns 默认指 10.0.0.6 上的容器**；除非用户明确说"10.0.0.3 上的 paopaodns"才指 NAS 那套（两台机器各跑一个 paopaodns，别混淆）
2. **10.0.0.6 拉 Docker 镜像用 `docker.1ms.run/` 前缀**：daemon.json 里配置的 daocloud/dockerproxy/nju/sjtug 等加速源对 sliamb/paopaodns 返回 403 或 TLS 错误，直连 registry-1.docker.io 被 reset；`docker.1ms.run`（与 NAS 同款源）验证可用。判断镜像是否最新：对比镜像 ID 与 Docker Hub Digest
3. **奶昔订阅链接有效期短（5-10 分钟）**：链接过期后 refresh 返回 success，但下载集合报 `组合订阅 X 中不含有效节点`；容器日志显示拉到的是"请登录系统网站后台…开启订阅获取"。必须去机场官网重新生成链接更新到 SubStore，不是 SubStore 故障
4. SubStore 后端 API 带路径前缀（如 /T3B9dgzBzdRbBF8Aqx7P），裸 /api/... 会返回 SPA HTML 或 Cannot POST
5. 改 SubStore 集合用 PATCH /api/collection/:name 传完整 JSON data（先 GET 再改再 PATCH）
6. **被 git 跟踪的 Surge profile 是凭据泄漏源**：`surge/JoelYang.conf` 这类"顺手备份"进仓库的文件常带 `external-controller-access` 与 `http-api` 的**明文密码**（`ca-p12` 一般已脱敏成 `-`）。审配置时先 `grep -rlE "external-controller-access|http-api =|ca-passphrase" ~/scripts` + `gh repo view <repo> --json visibility`；命中 PUBLIC 仓库即 P0，处置是换密码 + 删文件 **且重写历史**（只提交删除，历史里仍可读，等于没删）。
7. **不要用裸 curl 拉 Sub-Store collection 判断节点池**：同一 policy-path，Surge 引擎拿到全部成员（自建 + 机场地区节点），裸 curl 只拿到自建那几个——据此会把满员的地区 smart 组误判成空组。成员与空组只认 `GET /v1/policy_groups`。
8. **不要因为 https 目标下两个策略组出口 IP 相同就断言配置错误**：`X-Surge-Policy` 在 HTTPS/CONNECT 上不生效，改用 `http://ifconfig.me/ip` 复核后再下结论。
