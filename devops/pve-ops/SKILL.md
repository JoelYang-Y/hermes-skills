---
name: pve-ops
description: 用户问 PVE 物理机 (10.0.0.4)/LXC/虚拟机/企业源/体检优化时使用。
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [pve, proxmox, lxc, kvm, virtualization, debian13, maintenance]
    related_skills: [nas-docker-ops, vps-ops, remote-server-ops, deepseek-harness-ops]
---

# PVE Ops (Proxmox VE 物理宿主机 10.0.0.4)

管理 PVE 物理宿主机 (10.0.0.4) 及其上的 KVM 虚拟机与 LXC 容器：状态、健康度、软件源与系统优化。

## When to Use

- 用户问 PVE 物理机状态、CPU/内存/NVMe 存储占用、温度与硬件健康
- 用户问 PVE 上的虚拟机（VM 100 AdGuardHome）或 LXC 容器（CT 101 `Debian`，即 10.0.0.5 AI 节点，跑 muse2api）
- 需要给 LXC 改名、对齐 PVE 配置与容器内主机名时
- 软件源报错、企业源清理、国内清华镜像源切换、无订阅弹窗去除
- PVE 核心服务异常排查（pveproxy、pvedaemon、pvestatd）

## 连接信息（已验证 2026-08-15）

```bash
# 首选免密（Mac mini 的 ~/.ssh/id_ed25519.pub 已装入目标 root 的 authorized_keys 时）
ssh -o BatchMode=yes root@10.0.0.4 "<cmd>"

# 只能用密码时：密码放 600 权限临时文件走 -f，用完立即删除
# 勿用 sshpass -p '<密码>'——密码会出现在 ps 与 shell 历史（PVE 密码带尾随句点）
sshpass -f <600权限临时文件> ssh -o StrictHostKeyChecking=no root@10.0.0.4 "<cmd>"
```

> 下文命令里的 `sshpass -p '<密码>'` 属旧写法，执行时按上面的免密或 `-f` 形式替换。

- 主机 IP：`10.0.0.4`（主机名 `pve`）
- 用户：`root`，SSH 端口 `22`
- SSH 密码：`<密码>`（**统一尾随句点**）
- Web 控制台：`https://10.0.0.4:8006`（账号同 SSH，Realm 选择 Linux PAM）
- 系统版本：Proxmox VE 9.2.2（Debian 13 trixie，内核 7.0.2-6-pve，7.5 GiB RAM）

## 虚拟化实例清单

| VMID | 类型 | 实例名称 | 规格配置 | 运行 IP / 服务 |
|:---|:---:|:---|:---|:---|
| **100** | KVM 虚拟机 | `AdGuardHome` | 2 GiB RAM / 2G 盘 | `10.0.0.6` (DNS 防污染核心节点) |
| **101** | LXC 容器 | `Debian`（原 `DeepSeek-Harness`） | 4C / 4 GiB RAM / 20G 盘 | `10.0.0.5`：Docker 容器 `muse2api`（仅绑 10.0.0.5:18610）+ beszel-agent 45876；nginx 空壳已 disable；2026-11-21 第二手实测 |

## 软件源最佳实践 (Debian 13 deb822 规范)

PVE 9.x 基于 Debian 13，软件源采用 `/etc/apt/sources.list.d/*.sources` 文件格式：

1. **彻底禁用企业源**：
   删除 `/etc/apt/sources.list.d/pve-enterprise.sources` 避免更新报 401 认证错误。
2. **PVE 无订阅免费源** (`/etc/apt/sources.list.d/pve-no-subscription.sources`)：
   ```text
   Types: deb
   URIs: https://mirrors.tuna.tsinghua.edu.cn/proxmox/debian/pve
   Suites: trixie
   Components: pve-no-subscription
   Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
   ```
3. **Debian 基础与安全更新源** (`/etc/apt/sources.list.d/debian.sources`)：
   ```text
   Types: deb
   URIs: https://mirrors.tuna.tsinghua.edu.cn/debian
   Suites: trixie trixie-updates trixie-backports
   Components: main contrib non-free non-free-firmware
   Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

   Types: deb
   URIs: https://mirrors.tuna.tsinghua.edu.cn/debian-security
   Suites: trixie-security
   Components: main contrib non-free non-free-firmware
   Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
   ```

## 消除 WebUI 无订阅提示弹窗

修改 `/usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js` 并重启 `pveproxy`：
```bash
sed -i.bak -E 's/res\.data\.status\.toLowerCase\(\)\s*==\s*.active./false/g' /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js
systemctl restart pveproxy
```

## 常用运维命令

```bash
# 查看所有虚拟机与容器状态
sshpass -p '<密码>' ssh root@10.0.0.4 "qm list; echo '--- LXC ---'; pct list"

# 启动/停止/重启指定实例 (以 101 为例)
... "pct start 101"
... "pct restart 101"
... "qm start 100"

# 配置实例随宿主机开机自启动 (101 LXC / 100 KVM)
... "pct set 101 -onboot 1"
... "qm set 100 -onboot 1"

# 存储与 NVMe 健康状态
... "pvesm status; smartctl -H /dev/nvme0n1"

# 系统负载与硬件温度
... "uptime; free -h; sensors 2>/dev/null || cat /sys/class/thermal/thermal_zone*/temp"

# 查看核心服务状态
... "systemctl is-active pvedaemon pveproxy pvestatd"
```

## 避坑指南

1. **密码带尾随句点** `<密码>`：切勿遗漏句点。
2. **Debian 13 源格式**：PVE 9.x 采用 `.sources` deb822 结构，不要按传统单行格式直接写 `/etc/apt/sources.list`。
3. **单节点无需启动 corosync**：单机 PVE 下 `corosync.service` 为 inactive 属于设计预期，切勿强行启用。
4. **SSD TRIM 自动维护**：系统已内置 `fstrim.timer` 每周自动执行块回收，保持开启即可。
5. **实例自启动必须显式配置**：PVE 实例默认 `onboot: 0`，宿主机重启后不会自动唤醒。必须执行 `pct set <ID> -onboot 1`（LXC）或 `qm set <ID> -onboot 1`（KVM）固化自启，否则会导致全链路服务中断。
6. **LXC 主机名以 PVE 配置为准，改一边不够**：`pct config <ID>` 的 `hostname:` 在容器启动时经 UTS namespace 生效，与容器内 `/etc/hostname` 是两套东西。实测（10.0.0.5 / CT101，2026-11-21）：`pct config 101` 与 `pct list` 早已是 `Debian`，容器内 `hostname` 与 `/etc/hostname` 却仍是 `muse2api`。正确做法两边都改——PVE 侧 `pct set <ID> --hostname <name>`；容器内 `hostnamectl set-hostname <name>`，并把新名与 IP 的对应行写进 `/etc/hosts` 的 `# BEGIN PVE` 段。改前先备份 `/etc/hostname`、`/etc/hosts`（`.bak-YYYYMMDD-HHMMSS`）。
   - 事实：上述「PVE 新名 / 容器旧名」不一致为实测。
   - 推断（LXC/PVE 机制，**未做重启复测**）：只改容器内会被下次启动的 PVE 配置覆盖；只改 PVE 要重启后运行态才变。
   - 验收（只读、无需改动）：`pct config 101 | grep hostname`、`pct exec 101 -- hostname`、`pct exec 101 -- cat /etc/hostname` 三处一致即通过；重启复测会中断容器服务，**需另行批准**。
   - 风险/回滚：主机名变动会影响日志、依赖主机名的证书/SNI 与 `sudo` 告警；回滚＝还原两份备份并把 PVE 侧 `pct set <ID> --hostname` 改回旧名。
7. **带密码连接不留明文**：优先免密——把 Mac mini 的 `~/.ssh/id_ed25519.pub` 写进目标机 root 的 `authorized_keys`，用 `ssh -o BatchMode=yes` 验证确实不再走密码；只能用密码时，把密码放进 600 权限临时文件走 `sshpass -f <file>`，用完立即删除。不要用 `sshpass -p '<密码>'`：密码会出现在 `ps` 与 shell 历史。本技能上方的 `sshpass -p '<密码>'` 示例属反例，实际执行按免密或 `-f` 替换。
   - 已验证（第二手，2026-11-21）：10.0.0.5 已装 pubkey 且 `BatchMode=yes` 通过。
   - 待验证：`sshpass -f` 的具体写法、以及 10.0.0.4 是否已装 pubkey，本库无实测记录。验证方法：`ps -ef | grep sshpass` 不应看到密码；`grep sshpass ~/.bash_history` 应为空。

## 来源与版本

- v1.0.0（2026-08-15）：首次成文，PVE 9.2.2 / Debian 13 实测的连接、源配置与常用命令。
- v1.1.0（2026-11-21）：并入 server-keeper 投递的两条避坑（LXC 主机名、带密码连接不留明文）。素材为其在 10.0.0.5 / PVE CT101 的实测回报，属**第二手实测**，未经我复现；对方 staged 草稿 pending_id `9495125e` 未获批，本文件为唯一落盘版本。同批按 2026-11-21 核验结果校正 CT101 现役身份（已非 DeepSeek-Harness）。
- 事实 / 推断 / 待验证的划分见各条目内标注，不把机制推断写成实测结论。
