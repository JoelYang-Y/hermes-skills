---
name: pve-ops
description: 用户问 PVE 物理机 (10.0.0.4)/LXC/虚拟机/企业源/体检优化时使用。
version: 1.0.0
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
- 用户问 PVE 上的虚拟机（VM 100 AdGuardHome）或 LXC 容器（CT 101 DeepSeek-Harness）
- 软件源报错、企业源清理、国内清华镜像源切换、无订阅弹窗去除
- PVE 核心服务异常排查（pveproxy、pvedaemon、pvestatd）

## 连接信息（已验证 2026-08-15）

```bash
# SSH 连接（密码带尾随句点！）
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no root@10.0.0.4 "<cmd>"
```

- 主机 IP：`10.0.0.4`（主机名 `pve`）
- 用户：`root`，SSH 端口 `22`
- SSH 密码：`<密码>`（**统一尾随句点**）
- Web 控制台：`https://10.0.0.4:8006`（账号同 SSH，Realm 选择 Linux PAM）
- 系统版本：Proxmox VE 9.2.2（Debian 13 trixie，内核 7.0.2-6-pve，7.5 GiB RAM）

## 虚拟化实例清单

| VMID | 类型 | 实例名称 | 规格配置 | 运行 IP / 服务 |
|:---|:---:|:---|:---|:---|
| **100** | KVM 虚拟机 | `AdGuardHome` | 2 GiB RAM / 2G 盘 | `10.0.0.6` (DNS 防污染核心节点) |
| **101** | LXC 容器 | `DeepSeek-Harness` | 4C / 4 GiB RAM / 20G 盘 | `10.0.0.5`（旧 DeepSeek Harness 部署记录；当前 Hermes 已改本机 DSH，不再向此处委派；远程当前状态未核验） |

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
