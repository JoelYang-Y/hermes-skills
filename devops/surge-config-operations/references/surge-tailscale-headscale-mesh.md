# Surge 原生 Tailscale / Headscale 私网网格配置与排障实录

本文档总结 2026-08-20 实测打通的自建 Headscale + DERP 私网中继与 Surge 客户端（iOS / macOS）集成标准架构及排障速查。

---

## 1. 核心架构与协议机制

- **控制端 (Control Plane)**：自建 Headscale v0.29.3 运行于甲骨文 2 号机 (`129.153.89.114`)，反代域名 `https://hs.jhsweetheart.com`。
- **中继 (DERP / STUN)**：内嵌 DERP 监听公网 UDP `3478`。
- **子网网关 (Subnet Router)**：家庭 PVE 物理机 (`100.64.0.5`) 宣告 `10.0.0.0/24`，直通家庭局域网全部设备（NAS/Harness/DNS/路由器）。
- **客户端接入**：Surge iOS (5.20+) / Mac (6.7+) 内置 Tailscale L3 协议栈，直接声明 `tailscale` 策略。

---

## 2. Surge 节点声明语法（必须两段式）

若单行声明会报 `错误: 字段 section-name 必须被提供 (SGSettingsModelErrorDomain:0)`。标准写法如下：

```ini
[Proxy]
Tailscale = tailscale, section-name=my-mesh, test-url=http://100.64.0.1

[Tailscale my-mesh]
control-url = https://hs.jhsweetheart.com
auth-key = hskey-auth-mxmA84ZlfQu2-IZ_o804HLqA7jaUdKaoh4yDeCUiR-ZZbldYaews8f1VnUuzTQBUZUwBtL8eJ137S
```

---

## 3. 常见故障排查表 (Troubleshooting Matrix)

| 故障现象 | 根因定位 | 解决方案 |
|---|---|---|
| **测速亮红灯 / 报错超时** | Surge 默认向 `gstatic.com` 测速，私网节点默认不代理外网公网流量 | 在策略中设置 `test-url = http://100.64.0.1`（或私网内任一 HTTP 服务，如 `http://10.0.0.3:3005`） |
| **开启后手机所有外网断网** | 误勾选了「使用 Exit Node」 | 私网节点仅作内网互联，**必须关闭「使用 Exit Node」** |
| **Empty DNS answer 报错** | 公共 DNS（如阿里 DoH）缺少对新子域名的解析或受缓存影响 | 1. 确认 Cloudflare 已添加直连 A 记录 (`hs.jhsweetheart.com -> 129.153.89.114`)；<br>2. 在 Surge `[Host]` 静态绑定 `hs.jhsweetheart.com = 129.153.89.114` 彻底杜绝污染 |
| **能连 100.64 私网但连不上 10.0.0.x 局域网** | PVE 宿主机虽然开启转发，但缺少针对 Tailscale 来源 IP 的 NAT MASQUERADE，导致局域网设备回包给路由器默认网关丢弃 | 在 PVE 物理宿主机注入：<br>`iptables -t nat -A POSTROUTING -s 100.64.0.0/10 -o vmbr0 -j MASQUERADE`<br>`iptables -I FORWARD -i tailscale0 -o vmbr0 -j ACCEPT` |
| **规则被 Ponte 拦截** | 规则表中 `DEVICE:MACMINI` 覆盖了 `10.0.0.0/24` | 规则按自上而下匹配；将 `100.64.0.0/10` 专属分配给 Tailscale，或配置 `Fallback` 策略组实现双活容灾 |

---

## 4. 路由分流规则标准模板

```ini
[Rule]
# 访问全网私有网格设备（100.64.0.x）
IP-CIDR,100.64.0.0/10,Tailscale,no-resolve

# 访问家庭 10.0.0.x 局域网（通过 PVE Subnet Router 转发）
IP-CIDR,10.0.0.0/24,Tailscale,no-resolve

FINAL,DIRECT
```
