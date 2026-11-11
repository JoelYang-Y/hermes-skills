---
name: lan-docker-inventory
description: Use when 要盘点/发布局域网 Docker 全量清单. 只读采集再脱敏发布.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [docker, inventory, compose, 脱敏, 局域网]
    related_skills: [nas-docker-ops, pve-ops, hermes-operations]
---

# 局域网 Docker 全量清单：采集与发布

把家里所有 Docker 主机（NAS / 虚拟机 / LXC）的容器、端口、挂载、网络、特权、env **键名**盘成一份可发布清单，并把 `docker run` 容器反推成等效 compose。目标产物可直接进公开仓库而不泄露任何值。

**本技能只描述方法。真正跑采集要登录主机、写文件，属执行动作，需按当时授权走。**

## When to Use（适用条件）

- 要回答「家里到底跑了多少容器 / 哪台机器上有什么」
- 要把散落的 `docker run` 收敛成 compose 版本
- 要把清单发布到公开仓库或交给别人接手

**不适用**：单台机器的容器巡检（用 `nas-docker-ops`）、Docker API 远程管理（本流程不暴露 API）。

## 前置依赖

- 目标主机 SSH 可达；privileged 容器需 sudo
- 采集脚本必须是 **POSIX sh**：Alpine 容器主机没有 bash，也没有 python3（实测原 bash+python3 版直接返回空包）
- 口令走 stdin（`ssh ... sudo -S`），**不写进命令行、不写进脚本**

## 输入 / 输出

| | 内容 |
|---|---|
| 输入 | 主机清单（IP + SSH 端口 + 账号）、sudo 方式 |
| 输出 | `inventory.json`（容器/端口/挂载/网络/特权/env 键名，**无任何值**）、`hosts/<host>.md` 逐机详解、`compose/<host>/*.yml` 等效 compose、`COLLECTION.md` 可复现脚本、`README.md` 总览 |

## 步骤

1. **扫存活**：网段 1–254 做 ICMP，记下存活主机；对每台探 22 / 2375 / 2376 / 3000 / 8080 / 9443，确认**没有任何主机暴露 Docker API**（暴露了就别继续，先报风险）。
2. **连上再判断能力**：不是每台活主机都有 docker —— PVE 宿主要有 `pct list` / `qm list` 才知道容器在哪台；LXC 里可能连 `docker.sock` 都没有。**「有 IP 就以为有 Docker」是最常见的误判。**
3. **只读采集**：`docker ps -a`、`docker inspect`（含 Config/Env/**键名**）、`docker network ls`、`docker volume ls`、`cat /etc/docker/daemon.json`、`docker info`。脚本用 POSIX sh，不落任何 env 值到产物目录。
4. **反推 compose**：对每个 `docker run` 容器，按 `inspect` 的端口/挂载/网络/特权逐项还原成等效 compose，文件头注明「原为 docker run，未在生产切换」——**生成 compose ≠ 已切换**，不要顺手重建容器。
5. **记录运行时特例**：非默认 `data-root`、`systemd disabled`（被厂商系统托管）、自定义 seccomp、`host` 网络、`privileged` + 设备直通（如 `/dev/dri/renderD128`）。这些是日后迁移最容易踩的点。
6. **发布前硬校验**（缺一不可）：
   - 全部 YAML 能解析通过
   - 密钥串复扫命中 **0**（含路径令牌，见下）
   - `inventory.json` 只含 env **键名**，不含任何值
7. **删原始采集数据**：`inspect.json` 含全部 env 值，只允许存在于 scratch，产出后立即删除。
8. **如实标注未覆盖**：认证失败的机器（统一口令被拒等）在文档里写成「未覆盖」，**不许推测其容器数量**。

## 脱敏要点

- 路径令牌（如反代的 backend path）等同于密码，必须替换成 `<PLACEHOLDER>`；实测就是在 compose 里漏过一个
- 口令/token/私钥/Cookie 一律占位符，不复用旧流程里的明文
- 端口、网段、容器名属于可发布事实，但公网 IP 与内网明文口令不写进公开产物

## 验证方法（只读优先）

- `docker ps -aq | wc -l` 与 `inventory.json` 条目数一致
- 每份 compose 用 `docker compose config -q`（或 YAML 解析）验语法
- 发布后从远端拉回文件树，数文件数 + 复扫密钥串，**以远端为准**，不看本地工作区
- 建议用「容器数 / 主机数 / 未覆盖主机数」三个数做交叉核对

## 风险与安全边界

- 全程只读；**不 stop / rm / up 任何容器**，不在生产上切 compose
- `docker inspect` 会吐出明文 env，原始文件必须删；产物目录里出现任何值即视为失败
- 发布到公开仓库前必须明白：**删 commit 不等于删掉历史**（见 `hermes-operations` 的凭据泄漏处置）
- 失败停止条件：出现无法认证的主机、或发现 Docker API 暴露 → 停手先报，不要绕过认证硬猜

## 回滚

- 本流程不改主机状态，**无需回滚**；若已误改 compose，用 `docker inspect` 快照反推还原，并明确告知「未在生产验证」
- 发布产物有问题：删本地目录重新生成，不 force push 覆盖历史

## 来源

- `@session:default/local-953d5472261684d92e07610e85444bf95d719a65fb3f573739b1784750613773`（2026-11-11 00:43 起，默认 profile 实测并推送 commit `5057ee2`，23 文件）。
- **第二手实测**：工具输出由我读取该会话获得，未自己复现。已核实的结果：20 容器 / 10 compose 项目、18 份 YAML 解析通过、密钥串复扫 0、`sub-store.yml` 路径令牌已占位符化、原始 inspect 数据已删。
- 未验证：其他网段/其他厂商 NAS 的可移植性；本流程只在「2 台 Docker 主机 + 1 PVE + 1 LXC」的实际拓扑上跑过。
