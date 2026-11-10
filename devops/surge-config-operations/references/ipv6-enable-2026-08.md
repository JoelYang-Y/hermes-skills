# IPv6 开启实录（2026-08-12，BE88U + Surge 6.9.0 build 12040）

完整复盘：从"路由器没开 IPv6"到"国内走 IPv6 直连、海外走 IPv4 代理"的完整链路。

## 用户网络拓扑（相关部分）

```
电信 10G + 联通 2.5G → RT-BE88U (10.0.0.1, Asuswrt-Merlin 3006.102.8)
  ├─ 光猫桥接 + PPPoE 拨号（接口选 PPP 的前提）
  └─ LAN: Mac mini (10.0.0.2, Surge 6.9.0 增强模式)
DNS 链: 客户端 → 10.0.0.1 (BE88U AdGuardHome, 海外域名污染源)
                → 10.0.0.6 (paopao: adguardhome:53 → paopaodns:5335, 反污染干净)
Surge 生效 profile: JoelYang (WebUI API 读取), 本地 Profiles 目录无此文件
```

## 路由器侧配置（BE88U IPv6 页）

| 设置 | 值 |
|---|---|
| 联机类型 | Native |
| 接口 | PPP（PPPoE 拨号；若光猫拨号则选 DHCP） |
| DHCP-PD | 启用（关键，电信/联通靠 DHCPv6-PD 委派前缀） |
| Accept Default Route | 启用 |
| Release prefix on exit | 启用 |
| WAN Prefix Length | 64 |
| LAN 自动配置 | Stateless (SLAAC) |
| 路由广播 (RA) | 启用 |
| IPv6 DNS | 自动（Mac 的 DNS 由 Surge 接管，不受影响） |

## Surge 侧改动

```ini
[General]
ipv6 = true          # 原 false
ipv6-vif = auto      # 原 disabled；绝不 always（6.9 官方警告）
```

规则 37 条无改动：
- 主配置无 IP-CIDR6（正常，Rabbit-Spec 风格靠 RULE-SET 内嵌 IP 段）
- ChinaCIDR.list (→DIRECT) 含完整中国 IPv6 段 2001:250::/30 等（5838 行）
- China.list / Proxy.list / Google.list 均含 IP-CIDR6
- LAN 内置含 ::1/128、fc00::/7、fe80::/10
- FINAL,节点选择,dns-failed 兜底未匹配 IPv6
- 无 GEOIP（正好没有 GEOIP 不匹配 IPv6 的坑）

分流效果（实测）：
- baidu via -6 → HTTP 200 in 0.042s（国内 IPv6 直连，240e: 电信）
- www.google.com AAAA 查询 10.0.0.6 → 0 条（paopao 屏蔽海外 AAAA，符合预期）
- 海外流量 → IPv4 代理 → 出口 107.141.151.219 (AT&T) 不变

## 关键发现：生效 profile 在 iCloud 云盘

- 位置：`~/Library/Mobile Documents/com~apple~CloudDocs/JoelYang.conf`
- `~/Library/Application Support/Surge/Profiles/` 只有 Default/Kuromis/Surge Mac.conf（2025 旧残留，误导排查）
- iCloud 云盘目录 `ls` 会超时（文件提供程序按需下载卡住），但 mdfind 能定位、Python 能直读
- 手机端 Surge 改配置走 iCloud 同步到该文件；Mac 端 reload 后生效
- 备份：`cp JoelYang.conf JoelYang.conf.bak-$(date +%Y%m%d%H%M%S)`

## 事故记录：reload 引擎崩溃（22:10:07）

触发：iCloud 同步容器异常（日志 `Zone Not Found` / `Zone does not exist` / container ID `iCloud.com.nssurge.inc`）+ reload

症状：
- Surge Dashboard (PID 14913) 还在，但引擎进程退出
- 6171/6152/6153 无监听，TUN (vmenet0) 掉，网络全断

恢复：`open -a Surge` → 引擎重启 (新 PID)，API 端口恢复，配置 ipv6=true 已生效。

## API 探测结论

| 端点 | 结果 |
|---|---|
| GET /v1/profiles | `{"profiles":["JoelYang"]}` |
| POST /v1/profiles/reload | 有效，返回 `{}` |
| POST /v1/profiles/check | 有效（配置校验） |
| PUT /v1/profiles/current (raw conf) | 静默不生效 |
| POST /v1/profiles/current (json) | method not allowed |
| POST /v1/reload 等猜测路径 | unknown path |

结论：**HTTP API 无写 profile 内容端点**，改配置 = 编辑 iCloud 云盘 .conf + reload。

## macOS IPv6 验证怪癖

- `route -n get -inet6 default` → 假报 "not in table"；用 `netstat -rn -f inet6 | grep default`
- `ping6 <ip>` → 常报 "nodename nor servname provided"；用 `curl -6` 或 `ping -6`
- Surge VIF IPv6 接管标志：路由表出现 `default fd00:6152:: via utun4`，utun4 有 `fd00:6152::1/127`
- 增强模式黑洞判定：有 GUA 但 curl -6 秒败 (0.2s) = Surge utun 抢路由但不处理 IPv6
