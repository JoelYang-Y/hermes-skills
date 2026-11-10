# Surge HTTP API 探测 — check_domain.py 实战笔记 (2026-08-12)

从 check_domain.py v1→v10 迭代中学到的 Surge API 用法与坑。适用于所有
"查域名/IP 走哪个策略、真实出口 IP 是多少" 的任务。

## API 端点

| 端点 | 用途 | 返回 |
|------|------|------|
| `GET /v1/requests/recent` | 最近请求记录（实时匹配，上限 200 条） | `{"requests": [{id, URL, policyName, originalPolicyName, remoteAddress, rule, notes, ...}]}` |
| `GET /v1/rules` | 当前规则列表（静态匹配，不依赖历史流量） | `{"rules": ["DOMAIN-SUFFIX,3gppnetwork.org,AnyTLS-BWG", ...], "available-policies": [...]}` |
| `GET /v1/policy_groups` | **每组成员列表**（唯一能拿到成员名的端点） | `{"<组名>": [{isGroup, name, typeDescription, lineHash, enabled}, ...]}` |
| `GET /v1/policies` | 只有组名，没有成员 | `{"proxies": [], "policy-groups": ["节点选择", "AI", ...]}` |
| `GET /v1/profiles/current` | 生效 profile（全文 + 名字）| `{"profile": "[General]\n...", "name": "<profile名>"}` |

对照：`/v1/proxies`、`/v1/policies/<name>`、`/v1/policy_groups/<name>`、`/v1/policy/<name>`
全部 `{"error":"unknown path"}`；`POST /v1/policies/test?policy=X` 返回
`{"error":"invalid parameters"}`。**不要反复试策略组详情端点**，成员只从 `/v1/policy_groups` 整表取。

`/v1/policy_groups` 判读要点：空成员数组 = 该组被选中即断网（regex 过滤没匹配到任何节点）；
出现 `2.86 G | 200.00 G`、`Traffic Reset：2 Days Left`、`Expire Date：…` 这类条目 =
Sub-Store 把订阅流量/到期信息渲染成了**伪节点**，会混在策略组里被误选。

认证: header `X-Key: <密码>`（用户 Surge 只读 API 密码，尾随句点）。

## 关键字段语义

- `policyName` / `originalPolicyName` — 实际路由策略（组名或节点名）
- `remoteAddress` — 代理入口 IP（如 64.64.237.34 搬瓦工），**不是**出口 IP！
  链式节点 (AnyTLS-AT&T = 搬瓦工入口 + ATT 出口) 出口要看强制策略探测
- `notes` — 含规则匹配过程:
  - `Sub-rule matched: DOMAIN-KEYWORD telegram(in Proxy.list)` — RULE-SET 内子规则
  - `Rule matched: RULE-SET Proxy.list`
  - `Policy decision path: 节点选择 -> AnyTLS-AT&T` — 完整决策链（组->最终节点）
- `URL` 字段注意：记录里**没有 `host` 字段**。域名流量形如 `api.deepseek.com:443`，
  IP 流量形如 `93.179.102.140:443 (api.telegram.org)`。解析：
  `name = u.split("(")[-1].rstrip(")") if "(" in u else u.rsplit(":", 1)[0]`。
  只看 `host` 会全部取到 None，误判成"请求没被记录"。
- `rule` 为 null 的记录是 DNS 查询/未匹配完成的条目，统计策略分布时要剔除

## 规则类型识别

- RULE-SET 子规则前缀: `.pornhub.com` = DOMAIN-SUFFIX；`DOMAIN-KEYWORD x` = KEYWORD；
  `IP-CIDR x.x.x.x/xx` = IP-CIDR
- 优先级排序（用于多记录时选精确者）: DOMAIN-SUFFIX > DOMAIN > RULE-SET > IP-CIDR
  > DOMAIN-KEYWORD > FINAL。`DOMAIN-KEYWORD porn` 覆盖广，会误配 `pornhub` 类域名，
  精确 `.pornhub.com` 应优先

## X-Surge-Policy 强制策略探测

- 带 `X-Surge-Policy: <策略名>` 的请求会无视规则强制走该策略，用于探测其真实出口
- **协议限制（关键坑）**：经代理（6152）发起的 **HTTPS/CONNECT** 请求里该头**不生效**——
  两个不同组的探测会返回**同一个**出口 IP，看起来像"两个策略组配到了同一节点"。
  判 BWG/AT&T 这类链式节点必须打**明文 http** 目标：
  `curl -x http://127.0.0.1:6152 -H "X-Surge-Policy: BWG" http://ifconfig.me/ip`。
  用 `https://api.ipify.org` / `cloudflare/cdn-cgi/trace` 得到的 IP 不可信（实测两组都给
  108.230.34.31，改 http 后 BWG=64.64.237.34、AT&T=108.230.34.31，配置其实完全正确）。
  结论：**https 目标下两组 IP 相同不能作为配置错误的证据**。
- 支持策略组名（如 `Telegram`、`节点选择`）→ 走组当前选中节点
- **中文策略名坑**: urllib HTTP header 默认 latin-1，中文报 `UnicodeEncodeError`。
  解法: `str(policy).encode('utf-8').decode('latin-1')` 再放 header
- DIRECT 探测: TUN 增强模式 (vmenet0 198.18.0.1) 接管所有系统流量，
  即使无代理请求也返回 Surge 当前出口 → 标注 "非真直连"
- 探测目标: `http://ip-api.com/json/` 免费、返回 query/country/countryCode/
  regionName/city/isp/as（AS 号+机构名）；轻量场景用 `http://ifconfig.me/ip` 只要出口 IP

## 节点池规模：只认 API，不认裸 curl

Sub-Store 按请求方 UA/头裁剪 collection 输出。同一个 policy-path URL，Surge 引擎拿到
144 个成员（自建 + 机场地区节点），裸 `curl` 只拿到自建 3 个——此时按名称 regex 过滤的
地区 smart 组看起来全空，会得出"六个地区组都没节点"的错误结论（实测六组分别有
23/10/27/12/24/8 个成员）。**判断成员与空组只用 `GET /v1/policy_groups`**。

## IP/CIDR 静态匹配（不依赖历史流量）

`/v1/rules` 顶层只有少量直接 IP-CIDR（如 `IP-CIDR,208.54.0.0/16,AnyTLS-BWG,no-resolve`）。
多数 IP 在 RULE-SET 远程 list 文件内（如 AIGC.list 含 `129.146.3.78/32`）:
1. 先匹配顶层 IP-CIDR
2. 未命中 → 遍历 RULE-SET 规则，拉取 list URL 匹配文件内 IP-CIDR（行格式同规则）
3. 仍未命中 → 读 `FINAL,<policy>` 兜底（规则最后一条）

用 `ipaddress` 库精确判断（`ip in network` / `network.overlaps`），
不要用子串匹配（`10.0.0` 会误匹配 `172.16.0.0/12` 等）。

## 输入处理

- 域名: HTTPS HEAD 请求带 TLS SNI 触发规则（HTTP 会 TCP-fallback 匹配不准）
- 纯关键词（无 TLD）: 自动补全 `.com/.org/.net/.io` 发请求；输入 `129.146.3.78/32`
  的 CIDR 时**不要** `split('/')[0]` 截断（main 输入清理里要区分 IP 输入）
- 不完整 IP 段（如 `149.154`）: 提示用户补全完整 IP/CIDR

## 验证过的实际案例

| 输入 | 命中 | 策略 | 出口 |
|------|------|------|------|
| paypal.com | DOMAIN-KEYWORD paypal | AnyTLS-AT&T | 107.141.151.219 (US AT&T) |
| tello.com | DOMAIN-SUFFIX tello.com | AnyTLS-AT&T | 107.141.151.219 |
| pornhub | `.pornhub.com`(GlobalMedia.list) | HongKong 02 | 103.102.4.7 (US LA Jinx) |
| telegram 域名 | DOMAIN-KEYWORD telegram(Proxy.list) | AnyTLS-AT&T | 107.141.151.219 |
| telegram App 组 | (额外探测 Telegram 组) | Telegram 组 | 154.92.130.90 (HK Stacks) |
| 129.146.3.78/32 | AIGC.list 内 IP-CIDR | AI | 107.141.151.219 |
| 208.54.0.1 | 顶层 IP-CIDR | AnyTLS-BWG | 64.64.237.34 |
| 8.8.8.8 | FINAL | 节点选择 | 107.141.151.219 |
| 10.0.0.3 | LAN | DEVICE:MACMINI | — |

## 双路径结论（telegram 之谜）

同名服务可能有多条规则路径: telegram **域名**走 Proxy.list 的
DOMAIN-KEYWORD → 美国家宽；Telegram App 的 **IP 段**走 Telegram.list 的
IP-CIDR → 香港。两者都是 Surge 真实路由。脚本显示两条路径对比
（域名出口 vs 策略组出口）避免用户困惑。
