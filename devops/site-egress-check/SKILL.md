---
name: site-egress-check
description: 查网站出口IP/走哪个节点时用 Surge API 脚本（paypal.com 出口检测）。
version: 0.2.0
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [surge, egress, policy, rules, ip, routing]
---

# 网站出口 IP 检测 — Surge 实时请求匹配

Determines which Surge policy (node/group) a given domain matches in the
user's live Surge config, then probes the actual egress IP through that
policy. Built for the user's Surge gateway setup.

Scripts (LOCAL — 始终本地运行，不依赖公网 URL):
- `scripts/check_domain.py` (also at ~/.hermes/scripts/) — 交互式域名出口检测
  (Surge /v1/requests/recent + X-Surge-Policy 强制策略探测出口 IP)
- `scripts/check-egress.sh` — **xykt/IPQuality 完整检测脚本** (v2026-08-09)，
  IP 类型/纯净度/Scamalytics/代理/流媒体解锁。macOS 必须用 Homebrew bash。
  常用: `-4 -n -p` 终端报告 / `-4 -n -j -o file.json` JSON。

## When to use

- User asks: 查 xx.com 出口 / 这网站走哪个节点 / 策略路由 / paypal 从哪出去
- User asks: 查出口 IP / 当前 IP 是什么 / egress
- Verifying which egress (AT&T home / Bandwagon VPS / DIRECT) a service
  sees before registering or doing risk-sensitive operations

## How it works (check_domain.py)

1. 通过 Surge HTTP 代理 (127.0.0.1:6152) 发起对域名的真实 HEAD 请求，
   触发 Surge 规则引擎产生请求记录
2. 查询 Surge API `GET /v1/requests/recent` (127.0.0.1:6171, X-Key `<密码>`，
   READ-ONLY)，从最近请求中匹配域名 → 得到命中规则 + 路由策略
3. 用 Surge 隐藏特性 `X-Surge-Policy` 请求头，强制请求走该策略访问
   ip-api.com → 拿到真实出口 IP + 归属地 + 运营商

## Usage

```bash
S=~/.hermes/skills/devops/site-egress-check/scripts
# check_domain.py 交互式: 输入域名逐个检测 (q 退出)
python3 "$S/check_domain.py"

# 非交互单次查询 (echo 管道)
echo "paypal.com" | python3 "$S/check_domain.py"

# check-egress.sh = IPQuality 完整检测（macOS 必须用 Homebrew bash）
PATH=/opt/homebrew/bin:$PATH /opt/homebrew/bin/bash "$S/check-egress.sh" -4 -n -p   # 终端报告
PATH=/opt/homebrew/bin:$PATH /opt/homebrew/bin/bash "$S/check-egress.sh" -4 -n -j -o /tmp/ipq.json  # JSON
```

## Key facts

- **paypal.com → DOMAIN-KEYWORD,paypal,AnyTLS-AT&T** → egress 107.141.151.219
  (US / AT&T / AS7018) — residential IP, ideal for bank risk checks.
- check_domain.py 实测 (2026-08-12): paypal.com → AnyTLS-AT&T →
  107.141.151.219 (United States California Pasadena, AT&T Enterprises)。
- Surge API 的 `X-Surge-Policy` 头可强制指定策略，用于探测策略真实出口。
- 脚本依赖: python3 (urllib 标准库), 本机 Surge 代理 6152 + API 6171。

## Pitfalls

- **DIRECT 探测假象 (2026-08-13 实测)**: TUN 增强模式下（默认路由是 utun），
  check_domain.py 的 DIRECT 分支禁用 HTTP 代理后仍会进 TUN 被规则二次匹配；
  它用的国外回显站（api.ip.sb/ipify/ifconfig.co/cip.cc）命中 Proxy.list → 节点选择，
  导致"强制 DIRECT 出口"显示 107.141.151.219（代理 IP）——**这不是真直连**。
  验证真实直连 IP 用国内回显站: `curl http://myip.ipip.net` → 49.65.142.146 南京电信。
  判断某站是否真直连：先看 check_domain.py 的命中策略，若 DIRECT 再对国内回显站
  实测对照（同策略下国内站显示 49.x 说明 DIRECT 正常）。
- 交互模式 EOFError 是正常退出（管道输入结束时）。
- Surge API READ-ONLY per user policy — never POST/modify anything.
- Airport (机场) 节点出口动态，每次探测结果可能变化。
- check-egress.sh 需 bash 4+ (macOS 用 /opt/homebrew/bin/bash)。
- 旧 check-site-egress.sh (Surge /v1/rules 规则匹配版) 已由 check_domain.py
  替代 (2026-08-12)，机制从"静态规则匹配"升级为"实时请求 + 强制策略探测"。

## Related

- `ip-quality-xykt` — full IP quality health check (scamalytics score,
  streaming unlock) for the egress IP this script identifies
- `proxy-chain-diagnostics` — broader Surge chain health (policies, ports,
  DNS, nodes)
- `ip-quality-check` — arbitrary IP lookup via public APIs
