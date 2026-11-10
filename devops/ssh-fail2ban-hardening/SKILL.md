---
name: ssh-fail2ban-hardening
description: 为机队任意主机部署或维护 fail2ban SSH 防爆破时使用（ignoreip 白名单需跨主机同步）。
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [fail2ban, ssh, hardening, security, firewall, fleet]
    related_skills: [att-ops, vps-ops, oracle-cloud-ops, pve-ops]
---

# 机队 SSH 防爆破加固（fail2ban）

给用户的任意主机（AT&T 家宽 / 搬瓦工 VPS / 甲骨文 OCI / PVE 物理机）挂 fail2ban 的标准流程。

这是一项**机队级**操作，不是单机操作：`ignoreip` 白名单是整个机队的互信表，任何一台主机被加入或被改 IP，其余所有主机的白名单都要联动更新。

## When to Use

- 用户说「给 X 装 fail2ban」「主机加固」「防爆破」
- 新主机上线并暴露 SSH 端口（尤其是家宽 WAN 直暴的机器）
- 改了某台主机的公网 IP、或新增了监控/备份跳板机
- 发现某台主机 `fail2ban` 已装但白名单不全

## 必达基线（用户既定规范）

- 监控 SSH 端口，`maxretry = 3`，`findtime = 10m`，`bantime = 1d`，`increment = true`
- `ignoreip` 至少包含：`127.0.0.1/8`、`::1`、以及**全部对等主机**（家宽 + 各 VPS + 备份源）
- 开机自启：`systemctl enable fail2ban`

## 执行流程

### 1. 先收集全部对等主机的当前 IP，再动手

**白名单必须在你启用 fail2ban 之前就写全。** 先启用再补白名单的窗口里，对等主机的正常探测可能被误封；而如果本机是唯一入口，误封自己会直接丢失访问。

家宽类 IP 是**动态**的，不要照拄技能里记的旧 IP，当场向用户核实或用 `dig +short <主机名>` 解析。

### 2. 安装

```bash
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq fail2ban
```

### 3. 写 `jail.local`（不是 `jail.conf`）

用 [templates/jail.local](templates/jail.local) 改完后的内容写入 `/etc/fail2ban/jail.local`。

**必须写 `jail.local`**：`jail.conf` 属于软件包，`apt upgrade` 会覆盖掉你的修改；`jail.local` 优先级更高且不会被包管理器碰。

### 4. 启用并验证

```bash
systemctl daemon-reload
systemctl enable fail2ban
systemctl restart fail2ban
sleep 3
systemctl is-active fail2ban                # active
fail2ban-client status                      # 列出 jail
fail2ban-client status sshd                 # jail 内计数与日志源
fail2ban-client get sshd ignoreip           # 白名单是否真的生效
```

### 5. 回报基线

交付时报告：服务状态、jail 名、四参数值、白名单逐条展开。用户重视事实取证，不要只说「装好了」。

## Pitfalls

1. **现代 Debian/Ubuntu 必须 `backend = systemd`**——它们默认只写 journald，没有 `/var/log/auth.log`。用默认的 `auto`/`file` 后端时 fail2ban 启动成功、但 filter 永远检不到日志，表现是“装了但从不封人”。验证时看 `fail2ban-client status sshd` 里的 `Journal matches` 才有日志源。

2. **刚 `restart` 后立刻查 socket 会报错**——`Failed to access socket path: /var/run/fail2ban/fail2ban.sock. Is fail2ban running?`。这是守护进程还没起来，不是配置错。`sleep 2~3` 后重查即正常；不要因这句话去改配置或重启第二遍。

3. **用 `fail2ban-client get sshd ignoreip` 验证白名单，不要重读配置文件**——配置写对了不等于解析生效（语法错、`jail.local` 被其他文件覆盖、服务未 reload 都会让实际白名单与文件不一致）。只有 client 返回的列表才是生效值。

4. **主机可能只有 `nft` 没有 `iptables`**——这不需要“修”。fail2ban 会自动用 nftables 后端，功能等价，不要为了“修复”去装 iptables，那会多出一层可能冲突的规则。

5. **不要启用 `ufw`**——已有 Docker 或既有 iptables/nftables 规则链的主机上，ufw 会覆盖链导致端口直接不通。端口放行统一由原生 nftables/iptables 或云厂商安全组管控（用户的硬性约束）。

6. **改主机 IP 或新增主机后必须回头同步全机队白名单**——白名单漏一台，下一次它的巡检/备份就会被封在门外，而且表现为“探针突然不通”这种跨主机的诡异故障，很难联想到 fail2ban。变更后逐台 `fail2ban-client get sshd ignoreip` 核一遍。

7. **用 `sshpass` 而非交互登录执行**——脚本化部署时命令会因等密码而挂死。同时注意密码的统一格式（用户所有设备均带尾随句点）。

## 验证步骤

1. `systemctl is-active fail2ban` → `active`
2. `fail2ban-client status sshd` → jail 存在，`Journal matches: _SYSTEMD_UNIT=ssh.service`
3. `fail2ban-client get sshd ignoreip` → 回环 + 全部对等主机都在
4. 变更后回归：从一台对等主机 SSH 过去确认未被封
