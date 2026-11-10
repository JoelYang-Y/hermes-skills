# Surge 配置合理性审计 —— 只读体检手册

用户问"看下我当前 surge 配置文件合理性 / 配置有没有问题 / 帮我审一下"时用。
全程**只读**（可查可测，不改任何配置）。结论按 P0/P1/P2/P3 陈述**证据、影响、位置**；
**绝不输出"待授权改动清单"、绝不追问是否授权**——Surge 配置由用户独占管辖，改不改、怎么改由用户自己在 App 内决定。
（用户曾因助理反复就 Surge 改动征询授权而明确斥责，这条优先级高于一切"礼貌确认"习惯。）

## 0. 先确定审的是哪份配置

```bash
curl -s -H "X-Key: <key>" http://10.0.0.2:6171/v1/profiles/current | python3 -c "import sys,json;print(json.load(sys.stdin)['name'])"
curl -s -H "X-Key: <key>" http://10.0.0.2:6171/v1/profiles      # {"profiles":[...]} 可能有多个，旧的会被误选
ls -la ~/Library/Mobile\ Documents/iCloud~com~nssurge~inc/Documents/*.conf
```

要点：iCloud 容器里可能同时躺着多个 `.conf`，只有 `current.name` 指的那个是生效配置。
profile 列表里残留的旧 profile 往往还引用已被删除的策略组（如已下线的机场组名），
误切即断网——这类要单独点出来。

## 0b. 本机网络环境盘点（用户说"根据本机网络环境判断"时必做）

配置合理性不能只看规则，必须与本机实际链路对账。按顺序采集：

```bash
ifconfig | grep -E "^[a-z]|inet " | grep -B1 "inet "   # 有哪些接口带 v4 地址
netstat -rn -f inet | grep -E "^default"             # 可能有多条 default！
scutil --nwi                                          # 接口优先级顺序 = Surge 出站优先用哪条
route -n get <目标IP>                                 # 单目标走哪个 interface/gateway
```

| 观察 | 含义 |
|---|---|
| 多条 `default`（如 en0→10.0.0.1 与 en1→10.0.0.10 并存） | 备份路径存在。`scutil --nwi` 里排第一的才是当前出站口；报告写"双默认路由风险"时**必须同时给出两条链路的 ping 实测**（本机实测：有线 0.8ms 稳定 vs Wi-Fi 10.8ms 抖动），否则用户无法判断要不要处理 |
| 某条 default 的 gateway 恰好是 Surge DHCP 下发的网关 | Wi-Fi 侧可能从自己的 DHCP 拿租约、网关指回自己声明的地址，属可绕行余量 |
| `arp -an` 整表为空 / `ndp -an` 无输出 | macOS 上不能靠 ARP 判邻居身份，改用 `route -n get` + Surge `/v1/devices` |

**网关模式三件套（决定"设备流量到底过不过引擎"）**：

```bash
cat ~/Library/Application\ Support/com.nssurge.surge-mac/dhcpd/dhcpd.conf   # 看 option routers / range / 静态绑定
cat ~/Library/Application\ Support/com.nssurge.surge-mac/dhcpd/lease        # 活跃租约与 client-hostname
curl -s -H "X-Key: <key>" .../v1/devices                                    # 纳管设备 + dhcpGatewayEnabled
```

- `option routers` **未必是本机 IP**（实测下发 10.0.0.10，而本机是 10.0.0.2/10.0.0.37），不要据此断言配置错；先用 `/v1/requests/recent` 的 `sourceAddress` 分布证明设备流量确实进了引擎，再谈拓扑。
- recent 的 `sourceAddress` 是判定"谁在被纳管"的唯一硬证据：`10.0.0.11 iPhone 167 条` 这类分布比 lease 文件更可靠（租约只说明拿到 IP，不说明绕不绕引擎）。
- 报告里把"纳管设备数 / 活跃租约数"写进基础事实表，它是后面所有"共享单入口"类结论的分母。

**链路基准（一段表格，报告必带）**：各网关 ping、经代理的 2MB 吞吐与 TLS 握手、内网服务 HTTP 延迟。
实测方法：

```bash
for p in "AT&T" "BWG"; do printf "%-6s " $p;
  curl -s -o /dev/null -m 40 -x http://127.0.0.1:6152 -H "X-Surge-Policy: $p" \
   -w "down=%{size_download}B t=%{time_total}s speed=%{speed_download}B/s tls=%{time_appconnect}s\n" \
   "https://speed.cloudflare.com/__down?bytes=2000000"; done
```

吞吐结论只对当次时刻成立（家宽受同线路并发影响），报告里要标注测量时间，不要写成"家宽带宽窄"这种静态断言。

## 1. 本地文件 vs 运行时一致性

diff 前必须归一化，否则差异全是噪音：

```python
import re, difflib
def norm(t):
    out=[]
    for l in t.splitlines():
        s=l.strip()
        if not s or s.startswith('#'): continue
        if s.startswith(('ca-p12','ca-passphrase')): continue   # 运行时是 '-'，本地是私钥
        s=re.sub(r'policy-path=[^,]+','policy-path=X',s)        # 运行时是 https://masked/
        out.append(s)
    return out
```

**判定：`[Rule]` 段应逐行完全一致。** 差异只应出现在这四类 Module 注入上——
`always-real-ip` 追加项、`always-raw-tcp-keywords`/`-hosts`、`[MITM] hostname` 扩展、`[Script]` 追加块。
若规则段、策略组段出现差异，说明本地文件不是生效配置（或用户改了没 reload）——这是最优先结论。

## 2. 规模与结构

```bash
curl -s -H "X-Key: <key>" .../v1/rules > /tmp/rules.json   # 注释行和空行也会进列表
```

统计时按 `line.split(',')[0]` 计数并**过滤掉 `#` 开头与空串**，否则真实规则数会被注释虚增
（实测 181 行里只有 144 条有效规则）。

## 3. 策略组成员审计

```bash
curl -s -H "X-Key: <key>" .../v1/policy_groups
```

逐组打印成员数 + 前几个成员名。看三件事：

| 现象 | 含义 | 级别 |
|---|---|---|
| 成员数为 0 | regex 过滤没匹配到任何节点，组被选中即断网 | P0 |
| `2.86 G \| 200.00 G`、`Traffic Reset：…`、`Expire Date：…` | Sub-Store 把订阅流量/到期信息渲染成伪节点 | P2 |
| fallback 组首项是 REJECT | 节点缺失就整段拒绝，无软降级（安全优先的取舍，需告知而非修改） | P3 |

**不要用裸 curl 拉 Sub-Store collection 判断节点池**：同一 policy-path，Surge 拿到全部成员，
裸 curl 只拿到自建那几个，会把满员地区组误判为空组。

## 4. 路由抽样（最重要的一步）

选 35-40 个代表域名：高可信（paypal/银行/券商）、AI（chatgpt/claude/gemini/huggingface）、
平台（github/microsoft/apple/google/netflix/spotify/meta）、国内 CDN（抖音/快手/美团/小米）、
内网域名（`*.jhsweetheart.com`）、裸 IP。并发打 `127.0.0.1:6152`，然后回读 `/v1/requests/recent`：

```python
def name(u):
    u = u or ""
    return u.split("(")[-1].rstrip(")") if "(" in u else u.rsplit(":",1)[0]
```

打印 `host / policyName / originalPolicyName / rule` 四列对照。判读：

- 国内域名出现在非 DIRECT 策略 → 老问题复现（FINAL 落海外 / 国际规则抢走国内域名）
- 高可信业务不在设定出口 → 规则被前向规则覆盖
- **`rule` = FINAL 的样本要逐个看**：它们揭示兜底落到了哪个出口，通常是最有价值的一条结论

## 5. 出口验证（必须明文 http）

```bash
for p in "AT&T" "BWG"; do echo -n "$p -> ";
  curl -s -m 20 -x http://127.0.0.1:6152 -H "X-Surge-Policy: $p" http://ifconfig.me/ip; echo; done
```

**https 目标下该头不生效**，两组会返回同一 IP，据此判"两组指向同一节点"是误判。

## 6. 日志扫缺陷

```bash
log show --predicate 'processImagePath CONTAINS "Surge"' --last 24h 2>/dev/null \
  | grep -oE "Failed to update remote resource.*" | sort | uniq -c | sort -rn | head
log show --predicate 'processImagePath CONTAINS "Surge"' --last 24h 2>/dev/null \
  | grep -iE "SGDDNS|CKError|Empty DNS answer|Connection setup failed" | tail -20
```

| 日志特征 | 根因 | 处置 |
|---|---|---|
| `Failed to update remote resource: 404` 指向脚本/模块 URL | Module 脚本源已失效，对应功能静默失效（MITM hostname 仍留着，白白扩大拦截面） | 建议禁用该模块 |
| `Empty DNS answer ... from https://dns.alidns.com/dns-query` **或** 部分域名直接 NXDOMAIN | `encrypted-dns-server` 多 DoH 并列时，公网 DoH 的负应答/空应答会抢在内网 DoH 之前生效 | 只留内网 DoH，公网 DoH 降为 `dns-server` 引导 |
| `SGDDNS: Zone Not Found` | iCloud CloudKit DDNS Zone 缺失 | 与 Ponte 相关；**此状态下不要轻易 reload** |

## 7. IPv6 是否造成绕行

```bash
ifconfig en0 | grep inet6 | grep -v fe80        # 只有 fdcd: (ULA) = 无公网 IPv6
curl -6 -s -m 8 https://ipv6.icanhazip.com/      # 000 = 无 IPv6 出口
```

无 GUA 且 `curl -6` 失败时，`ipv6=false` / `ipv6-vif=disabled` **不存在绕行泄漏**，
`IP-CIDR6` 规则只是无效冗余（P3 精简项，不是缺陷）。有 GUA 却 `ipv6=false` 才要按 IPv6 章节处理。

⚠️ **`curl -6` 返回 200 不能推翻上面的结论**：Surge TUN + FakeIP 会把 AAAA 映射到
`::ffff:198.19.x.x`（FakeIP 段的 IPv4-mapped 形式），连接照样成功。必看 `curl -6 -v` 的
`Trying [...]` 实际地址；权威判据是 `scutil --nwi` 的 `IPv6 network interface information`
（`No IPv6 states found` = 真没有 IPv6 出口）。只凭状态码写"IPv6 已连通"是假阳性。

## 8. 安全扫描（每次必做，别跳过）

Surge profile 里天然带明文凭据：`external-controller-access`、`http-api` 的密码（形如 `Pass.@0.0.0.0:6171`），
以及 `[MITM] ca-passphrase` + `ca-p12`（完整根证书私钥）。

```bash
grep -rlE "external-controller-access|http-api =|ca-passphrase" ~/scripts --include="*.conf" --include="*.md"
cd ~/scripts && git ls-files | grep -i surge
git log --oneline -5 -- surge/<file>
gh repo view <owner>/<repo> --json name,visibility        # PUBLIC 就已经出事
curl -s -o /dev/null -w "%{http_code}" https://raw.githubusercontent.com/<owner>/<repo>/main/surge/<file>
```

命中即 P0，处置顺序：① 换控制器/API 密码并 reload；② 删文件 **且重写历史**（`git rm` 后只提交删除，历史里仍可读，等于没删）；③ 加 `.gitignore` 规则 `surge/*.conf`。
`ca-p12` 一般已在提交版里脱敏成 `-`，真正泄漏的常常是控制器密码——重点 grep 密码字段。

## 9. 常见缺陷清单（判读表）

| 缺陷 | 证据 | 影响 |
|---|---|---|
| FINAL 落到家宽 | `Final` 组首项 = `节点选择`，而后者首项 = AT&T；recent 里 IP 直连类记录 `rule=FINAL` 且 `policyName=Sub-AT&T` | 漏网流量（第三方遥测、DoT、IM 的 IP 直连）挤进住宅家宽，带宽窄、单入口 |
| 前向 IP-CIDR 覆盖 RULE-SET 同名条目 | 顶部 `IP-CIDR,<ip>/32,DIRECT` 与 `us-all.list` 里同一 IP 的策略相反 | 后者永不命中；同类资产出现两种口径 |
| 多 DoH 竞争 | 见 §6 | 国内子域偶发空应答 → DIRECT 连接失败 |
| 大流量业务走家宽 | `huggingface.co`/`hf.co`/电商 → AT&T | 模型下载、购物明显慢 |
| 双份同名 RULE-SET | 同一 `.list` 由两个上游各挂一次 | 规则量翻倍、更新变慢 |
| `update-interval=-1` | Sub-Store 组 | 节点不自动刷新，机场链接过期后无法更新且无告警 |
| 无效 Peer 兜底 | `RULE-SET,LAN` 排在已列全私网 CIDR 之后；`GEOIP,CN` 与 `ChinaCIDR.list` 高度重叠 | 无害冗余，可精简 |
| `PROCESS-NAME,"/Applications/Xxx.app/",组名` | 路径前缀形式 | Surge 接受该语法（运行时规则列表保留该行、`ps -Ao comm` 能看到该进程）即视为有效，不要因为"看起来像路径"就判为语法错误 |

## 10. 交付格式（用户偏好）

- 开头一段基础事实表：版本、生效 profile、配置文件路径、一致性结论、有效规则数、出口实测值。
- 先给抽样实测表证明规则**确实生效**，再谈缺陷——没有实测的"配置合理性"是空话。
- 缺陷按 🔴 P0 / 🟠 P1 / 🟡 P2 / 🟢 P3 分级，每条带**证据**（日志原文、规则行号、实测 policyName）。
- 单独一节列出"设计上正确、不需要改"的部分，避免用户以为全是问题。
- 结尾只声明"以上一条都没动"。**不要列"待授权改动清单"、不要问是否授权**——Surge 属用户独占管辖。
- 不要替用户改配置；**用户主动要改法时**才给可直接粘贴的 diff。
- 抽到 `rule=FINAL` 为 0 条时必须说明样本局限（recent 只有 200 条且可能被单一设备的 TLS 请求占满），
  并补一次主动构造：打 1-2 个未收录域名（如 `example.com`、随机不存在域）确认兜底落点，再下结论。
- 判读边界要显式写出来：拿不到证据的项（如某私有网关 IP 的设备归属）只能陈述"拓扑上必然成立"的事实，
  不要给设备身份下断言。
