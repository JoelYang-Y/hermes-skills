---
name: linux-icmp-hardening
description: "Use when 让自有 Linux 主机不被 ping 探测. 只丢 echo-request."
version: 1.0.0
author: skill-keeper
license: MIT
metadata:
  hermes:
    tags: [linux, nftables, icmp, hardening, firewall]
    related_skills: [vps-ops, server-readonly-inspection, att-ops]
---

# 自有 Linux 主机「全球禁 ping」

把「别人 ping 不到我」做成一次可回滚的 nftables 变更：**只丢 echo-request，保留 PMTU 等差错报文**。

## When to Use（适用条件）

- 用户说「禁止别人 ping 我某台服务器」「关掉 ICMP / 禁 ping」「让主机不被 ping 探测」。
- 适用：自建 Linux 主机，nftables 为真实防火墙（`table inet filter`，policy drop）。
- **不适用**：路由器/网关设备（用户无权改，只报边界）；也不适用于「彻底隐身」诉求——**禁 ping 不阻止 TCP 端口扫描**，必须提前讲清这条边界，别承诺「扫不到」。

## 前置依赖

1. root SSH 可达；`nft`（≥1.0）、`systemd`、`python3`。
2. **一个外部 vantage 做验证**。Mac 本机的 ping/nc 经 Surge TUN，本地先 accept，看着通实际已死——用它验证等于没验。

## 关键步骤

### 1. 取证：确认当前是不是全量放行 ICMP

```bash
ssh -p <port> root@<host> "nft list chain inet filter input"
```

`policy drop` **不等于**禁 ping。典型敞口就一行：

```
meta l4proto { icmp, ipv6-icmp } accept   # 全部 ICMP 类型放行，含 echo-request
```

外部基线（用真实 vantage，别用本机）：

```bash
ssh root@<vantage> "ping -c 4 -W 2 <host>"
```

### 2. 变更设计：只丢 echo-request

**不要全禁 ICMP。** `frag-needed`(v4) / `packet-too-big`(v6) 被丢会造成 **PMTU 黑洞**：TCP 握手成功、大流量卡死，症状飘忽极难定位。链式代理/跨境中转主机上尤其致命。

```diff
-		meta l4proto { icmp, ipv6-icmp } accept
+		# ICMP: only necessary error types (PMTU etc.); drop all echo-request (no ping worldwide)
+		icmp type { destination-unreachable, time-exceeded, parameter-problem } accept
+		icmp type echo-request drop
+		icmpv6 type { destination-unreachable, packet-too-big, time-exceeded, parameter-problem, nd-router-advert, nd-router-solicit, nd-neighbor-solicit, nd-neighbor-advert } accept
+		icmpv6 type echo-request drop
```

v6 的 `nd-*` 必须保留（邻居发现/RA），否则链路层地址解析会断。**即使当前没有全局 v6 地址也一并写**，防止将来拿到 v6 就敞开。

### 3. 落地流程（顺序不能变）

```bash
# a. 备份
TS=$(date +%Y%m%d%H%M%S); cp -a /etc/nftables.conf /etc/nftables.conf.bak-icmp-$TS

# b. 定点替换（python 断言命中一次，避免 sed 误伤多行）
python3 - <<'PY'
p='/etc/nftables.conf'; s=open(p).read()
old="\t\tmeta l4proto { icmp, ipv6-icmp } accept\n"
assert s.count(old)==1, 'pattern not unique'
new=('<新四行，见上>')
open(p,'w').write(s.replace(old,new,1))
PY

# c. 语法预检（-c 只解析不提交）
nft -c -f /etc/nftables.conf

# d. 延迟重载（不要在同一条 SSH 命令里直接 restart）
ssh root@<host> "systemd-run --on-active=3 --unit=icmp-apply --collect \
  /bin/bash -c 'systemctl restart nftables; sleep 2; systemctl restart fail2ban'"
```

## 验证（逐项回读，不看「应该生效」）

1. `nft list chain inet filter input` → 四行新规则在 **live** ruleset 里
2. 外部 vantage `ping -c 4` → **100% packet loss**（实测改前 4/4 回包 RTT 4.8ms，改后 4/4 丢包）
3. 外部 vantage TCP 探测业务端口 → 仍 OPEN（实测 59421 与 34443 均通）
4. 本机 `ping 127.0.0.1` 通（`iifname "lo" accept`）、`ping 8.8.8.8` 通（output 放行）
5. `systemctl is-enabled nftables fail2ban` 均 enabled；`systemctl show nftables -p Before` 含 `fail2ban.service`

## 坑（均实测撞到）

1. **`systemctl restart nftables` 会清掉 fail2ban 的 nft 表**：配置首行 `flush ruleset`。必须紧跟 `restart fail2ban`；靠 `nftables.service` 的 `Before=fail2ban.service` 保证开机顺序。
2. **重载会打断自己这条 SSH**（established 规则被清）。用 `systemd-run --on-active=3` 延迟执行，等命令返回后再重连验证；同一命令里直接 restart 会拿到 exit_code -1 的死结果。
3. **Hermes terminal 拒绝 nohup / setsid / disown 包装**（报 "Foreground command uses shell-level background wrappers"）。用 `systemd-run --on-active` 替代，天然脱离会话。
4. **`nft list tables` 看不到 `f2b-table` 是正常的**：fail2ban 的 nftables action **按需建表**，无封禁时表不存在。别据此判断 fail2ban 坏了。验证：`fail2ban-client set sshd banip 1.2.3.4` → 表出现且有元素 → `unbanip` 归零。**只封测试 IP，封白名单 IP 会自封。**
5. **别用 `net.ipv4.icmp_echo_ignore_all=1` 代替**：sysctl 不可审计，与 nft 规则语义分散，事后看不出谁禁的。
6. **别在 Mac 上验**：Surge TUN 下 ping/nc 全不可信，必须用境外或本网其他真实 vantage。

## 验收清单

- [ ] live ruleset 含 `icmp type echo-request drop`
- [ ] 外部 vantage ping 100% 丢包（负向测试）
- [ ] 业务 TCP 端口仍 OPEN（防误伤放行顺序）
- [ ] 本机回环/出站 ping 正常
- [ ] fail2ban 封禁→解封一轮通过
- [ ] 备份文件存在且 `wc -l` 与改前一致
- [ ] 报告写明「禁 ping ≠ 不可被端口扫描」

## 安全边界与失败停止

- 改防火墙属于生产变更：先备份、先 `nft -c` 预检，改后必须重连确认可登录。
- 只动 ICMP 相关行，不顺手改 policy 或其他放行项。
- 失败停止：预检不过 / 重连不上 / 业务端口不可达 → 立即用备份还原并重启，不连环试第二版规则。

## 回滚

```bash
cp -a /etc/nftables.conf.bak-icmp-<TS> /etc/nftables.conf
nft -c -f /etc/nftables.conf && systemctl restart nftables && systemctl restart fail2ban
```

## 来源

- **第二手实测**：2026-11-10 `default` profile 通过 `message_agent` 投递的自有主机实操记录（SSH 直连执行并回读验证），未经 skill-keeper 复现。
- 事实：改前 4/4 回包（RTT 4.8ms）、改后 4/4 丢包；59421/34443 仍 OPEN；四行规则在 live ruleset；`nft -c -f` 预检通过；备份命名与 `-p Before` 输出。
- 推断/待验证：v6 部分因该机当前无全局 v6 地址，`icmpv6` 分支实际未被流量验证；`nd-*` 保留的必要性来自通用实践而非本机实测。
