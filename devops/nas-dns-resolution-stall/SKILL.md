---
name: nas-dns-resolution-stall
description: "Use when Z4Pro NAS 域名解析超时. 只读定位 resolved 无效 DNS."
version: 1.0.0
author: skill-keeper
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [nas, dns, systemd-resolved, z4pro, troubleshooting]
    related_skills: [nas-docker-ops, proxy-chain-diagnostics, adguardhome-doh-deploy]
---

# Z4Pro NAS 域名解析卡顿（resolved 无效 DNS）

把「NAS 上解析要等好几秒」定位到 `systemd-resolved` 里排在最前的无响应 DNS 地址，备份后只注释该行并复测时延。

## When to Use（适用条件）

- Z4Pro NAS（主机别名 NAS，10.0.0.3）上主机或容器解析慢：`nslookup` 先空等数秒再返回，`resolvectl status` 的 Global DNS 首位是 `100.66.66.66` 之类无响应地址。
- 不适用：Surge 侧 DNS 污染/节点问题（用 `proxy-chain-diagnostics`）；AGH/PaoPaoDNS 上游策略问题（查 10.0.0.6 侧，不动 NAS host）。

## 前置依赖

- NAS 的 SSH 凭据取既有凭据来源（如 `~/.hermes/.nas_backup.env`），**只读取值，不复制进技能或日志**；需 sudo。
- **这是生产写入，需 Joel 对精确目标与变更另行批准**；执行前必须备份。

## 输入 → 输出

- 输入：NAS 主机名、要复测的域名（实测用 `api.telegram.org`）。
- 输出：`/run/systemd/resolve/resolv.conf` 只剩 `nameserver 10.0.0.6`；同一域名 `nslookup` 在 0.1s 内返回。

## 步骤（2026-11-22 23:39 实测）

1. **只读定位**：`resolvectl status` 看 Global DNS 顺序；`cat /etc/systemd/resolved.conf.d/nblink.conf`。实测该文件由极空间 `NodeBabyLinkService` 写入，含 `Domains=~link` 与 `DNS=100.66.66.66`，后者被提升为全局首选且无响应。
2. **记录修改前时延**：`time nslookup -type=A <域名>`，确认是「先超时再回」而不是解析失败。
3. **备份**：`cp -a "$f" "$f.bak-$(date +%Y%m%d-%H%M%S)"`，回显备份路径。
4. **只注释、不删除**：`sed -i 's/^DNS=100.66.66.66/#DNS=100.66.66.66/' "$f"`。保留文件其余内容，避免厂商服务重建时把整段配置判为缺失。
5. **生效**：`systemctl restart systemd-resolved` → `resolvectl dns kvmbr0 10.0.0.6` → `resolvectl flush-caches`。
6. **验证**：`grep nameserver /run/systemd/resolve/resolv.conf` 应只剩 `10.0.0.6`；`time nslookup -type=A <域名>` 应 <0.1s（实测 0.06s 返回 149.154.166.110）；抽查容器（如 MoviePilot）的 `resolv.conf` 只指向 10.0.0.6。

## 风险与安全边界

- 重启 `systemd-resolved` 会造成秒级解析中断；不要在正在做大流量解析的窗口执行。
- 极空间服务可能在升级/重启后**重写该文件**，超时复发（推断，未复现）；复发时按同一行再注释即可。
- 不删除配置文件、不改 Surge（永久只读）、不动 AGH/PaoPaoDNS 上游策略。
- 不把 SSH 口令、sudo 口令写入命令历史或技能；用临时文件并在结束删除。

## 失败停止条件

- 备份未生成或路径回显缺失 → 停，不修改。
- 注释后 `resolvectl` 仍显示 `100.66.66.66`，或 `nslookup` 仍超时 → 停，按回滚恢复并报告实际输出。
- 需要改动 `[Resolve]` 其他字段或删除文件 → 超出本规程，停下请 Joel 决定。

## 回滚

1. `cp -a "$f.bak-<时间戳>" "$f"` 恢复原文件。
2. `systemctl restart systemd-resolved` + `resolvectl flush-caches`。
3. 复查 `resolvectl status` 与原文件内容一致。

## 来源

- `@session:default/local-6d935a9ccaff1fc6fb8957e56d23210b66cfe5554f4a83c29d892dd23d0de0fe`（2026-11-22 23:03「检查 Surge 配置 IPv6 国内外分流」会话末段；**第二手实测**：工具输出由我在该会话中读取，未自行复现）。
- 事实：`nblink.conf` 内容、备份名 `nblink.conf.bak-20261122-233940`、`resolv.conf` 只剩 10.0.0.6、`api.telegram.org` 0.06s 返回，均来自该会话真实工具输出。
- 推断/待验证：极空间升级后是否重写该文件、重启 `systemd-resolved` 的具体中断时长，未复现。
- 边界：该会话同段还做过 NAS 侧 sudo 写入，已由用户当次批准；本技能只记录规程，不构成再次执行授权。
