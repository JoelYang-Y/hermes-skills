# DNS 层 IPv6 发现实录（2026-08-12，10.0.0.6 paopao DNS 服务器）

Surge 侧 IPv6 开好后，国内域名（baidu/qq）仍拿不到 AAAA 的排查实录。

## 现象

```
nslookup -type=AAAA www.baidu.com 10.0.0.6
*** Can't find www.baidu.com: No answer
Authoritative answers can be found from:
www.baidu.com
    origin = fake-for-negative-caching.adguard.com   ← AdGuardHome 负缓存特征
```

同时对照：
- 10.0.0.1 (BE88U AdGuardHome) 对 baidu AAAA 返回真实 `240e:` ✅
- 10.0.0.6 对 google AAAA 返回 No answer ✅（海外屏蔽符合设计）
- 10.0.0.6 对 baidu **A 记录**正常（180.101.51.73）✅ → 只有 AAAA 被拦

## 根因：AdGuardHome `aaaa_disabled: true`

10.0.0.6 上的 adguardhome 容器配置 `/root/AdGuardHome/AdGuardHome.yaml`：

```yaml
dns:
  upstream_dns:
    - tcp://10.0.0.6:5335   # → paopaodns
  aaaa_disabled: true        # 罪魁祸首：全局拦截 AAAA，不转发给 paopaodns
```

`aaaa_disabled` 在 AdGuardHome 层生效（面板对应"DNS 设置 → 屏蔽 AAAA 记录"），**先于 paopaodns 的 mosdns 分流逻辑**，所以国内域名也被误伤。paopaodns 本身 env 全对（IPV6=yes / CNAUTO=yes / CNFALL=yes / ADDINFO=yes）——问题不在它。

## 修复

```bash
# SSH 10.0.0.6:22 root / <密码>（尾随句点）
cp /root/AdGuardHome/AdGuardHome.yaml /root/AdGuardHome/AdGuardHome.yaml.bak-aaaa-$(date +%Y%m%d%H%M%S)
sed -i 's/aaaa_disabled: true/aaaa_disabled: false/' /root/AdGuardHome/AdGuardHome.yaml
docker restart adguardhome
```

验证（修复后）：
- baidu AAAA → `240e:e9:6002:...` ✅（国内双栈恢复）
- qq AAAA → `240e:e1:a800:120::76` ✅
- google AAAA → No answer ✅（海外屏蔽保留——那是 paopaodns 层实现的，不受此开关影响）
- Mac `curl -6 https://www.baidu.com` → HTTP 200 in 0.036s ✅

## 关键认知：DNS 服务器有无 IPv6 不影响解析 AAAA

10.0.0.6 容器**没有 IPv6 地址**（`paopaodns_default` 网络 172.19.0.2 纯 IPv4 bridge，容器内仅 ::1 loopback；Docker bridge 默认不启用 IPv6；NAS 宿主机 10.0.0.3 有 240e: 但容器不共享）——**但这完全不影响它解析/返回 AAAA 记录**：

- DNS 查询走 IPv4 (10.0.0.6:53) 到达，服务器用 IPv4 上游查 AAAA，IPv4 返回给客户端。解析 AAAA 是协议功能，与服务器自身有无 IPv6 无关
- 客户端拿到 `240e:` 后用**自己的** IPv6 地址连接目标——那是路由器（BE88U SLAAC 下发）和客户端的事
- 唯一需要服务器有 IPv6 的场景：监听 `[::]:53` 给 IPv6-only 客户端服务——家里设备全走 IPv4 局域网访问 10.0.0.6，不涉及

## 10.0.0.6 服务器速查

| 项 | 值 |
|---|---|
| 系统 | Alpine Linux, hostname=localhost |
| SSH | root@10.0.0.6:22，密码 <密码>（带句点） |
| adguardhome 容器 | adguard/adguardhome，挂载 /root/AdGuardHome，监听 53/80/443/3000，DoH server_name=home.jhsweetheart.com，上游 tcp://10.0.0.6:5335 |
| paopaodns 容器 | sliamb/paopaodns，挂载 /root/PaoPaoDNS，监听 5335/5304/7889，ENV: IPV6=yes/CNAUTO/CNFALL/ADDINFO |
| 本机 IPv6 | 有公网 `240e:3a3:1006:36d0:be24:11ff:fe8f:b9d0`，容器端口映射含 [::]:53/443/3000 |
| AdGuardHome 面板 | https://10.0.0.6 或 :3000（用户 root，密码在 yaml bcrypt） |

⚠️ 注意：10.0.0.6 与 NAS 10.0.0.3 是**两台不同机器**（NAS SSH 用户 18332733294 端口 10000；10.0.0.6 是 root:22）。NAS 上也跑着一个 paopaodns 容器（映射 5335/5304），但那是另一套，别混淆。
