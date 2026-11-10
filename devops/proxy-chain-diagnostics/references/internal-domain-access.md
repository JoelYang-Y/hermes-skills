# 内网域名与服务的可达性矩阵

回答「为什么这个内网服务打不开」时先查这里，不要直接怀疑服务本身。

## 链路

```
客户端（需跑 Surge）
  → Surge [Host] 命中映射（JoelYang.conf [Host] 段）
  → 目标 LAN IP:443（NAS 反代 nginx）
  → 后端容器端口
```

`[Host]` 段映射关系（只读参考，实际以配置文件为准）：

| 域名 | 指向 |
|---|---|
| adg.jhsweetheart.com | 10.0.0.6 |
| sub / kuma / topo / emby / movie / beszel / sync / qb / dsh / pve .jhsweetheart.com | 10.0.0.3（NAS 反代） |
| hs.jhsweetheart.com | 129.153.89.114（公网 VPS） |

即：**内网二级域名统一由 Surge [Host] 解析到 NAS 反代**，NAS nginx 再分发给后端容器。
后端服务自身可能还有一层鉴权（dsh 返回 401 要 token，emby/kuma/sub 返回 302 跳登录页）——
**401/302 都说明请求已成功抵达服务，不是故障。**

## 决策表：从某处访问某内网服务，走哪条路

| 场景 | 域名形式（`xxx.jhsweetheart.com`） | LAN IP:端口直连 |
|---|---|---|
| 设备跑着 Surge + 在家庭内网 | ✅ 可用 | ✅ 可用 |
| 设备跑着 Surge + 在外网 | ❌ 不可用（见下） | ❌ 不可用 |
| 设备未跑 Surge + 在家庭内网 | ❌ 无法解析 | ✅ 可用（零 DNS 依赖） |
| 设备未跑 Surge + 在外网 | ❌ | ❌ |

结论：**内网服务目前没有任何外网可达路径。** 需要远程访问时必须另建公网入口
（Cloudflare Tunnel 或境外 VPS 反代 + 隧道回家），不要试图靠改 Surge 规则解决。

## 为什么在外网不可用（规则顺序）

`JoelYang.conf` `[Rule]` 段中：

```
DOMAIN-SUFFIX,jhsweetheart.com,DIRECT            ← 在前，先命中
# Surge Ponte内网穿透
IP-CIDR,10.0.0.0/24,DEVICE:MACMINI,no-resolve   ← 在后，永远轮不到
```

内网域名先被 DOMAIN-SUFFIX 命中 `DIRECT`，Ponte 那条 `IP-CIDR,10.0.0.0/24` 隧道规则
**永远不会被匹配到**。所以在家庭内网外，`*.jhsweetheart.com` 内网服务全部不可达
（不只是某一个服务）。

> 这是既有配置行为。Surge 配置属用户红线「可读可查、任何时候不得修改」，
> 诊断时可以引用规则顺序解释现象，但不要改动配置。

## 验证命令

```bash
# 批量确认多个内网域名走同一链路（应全部指向同一个反代 IP）
for N in emby kuma sub dsh; do
  printf "%-8s -> %s\n" "$N" "$(dig +short $N.jhsweetheart.com | head -1)"
done

# 探到服务端口（带鉴权也 OK，401/302 都算通）
curl -sS -m 6 -k -o /dev/null -w '%{http_code}\n' https://emby.jhsweetheart.com/

# 判断某域名有没有公网记录 —— 必须走 DoH，本机 dig 会被 Surge TUN 接管
curl -s -H 'accept: application/dns-json' \
  'https://cloudflare-dns.com/dns-query?name=dsh.jhsweetheart.com&type=A'
```

## 排查顺序

1. 目标服务的容器/进程本身是否在跑（服务侧）
2. 带正确凭据直连 `LAN_IP:端口` 是否通 —— 通则服务侧无责，问题在解析/路由
3. 兄弟内网域名在同设备是否也打不开 —— 都打不开则是设备到内网的路径问题
4. 打不开时先问「在家还是在外」：外网下所有内网域名都不通，属预期
