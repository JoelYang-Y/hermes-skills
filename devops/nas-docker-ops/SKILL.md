---
name: nas-docker-ops
description: 用户问 Z4Pro NAS (10.0.0.3) Docker 容器状态/日志/重启时使用。
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [nas, docker, homelab, qdrant, mem0, syncthing, maintenance]
    related_skills: [remote-server-ops, mem0-oss-operations]
---

# NAS Docker Ops (极空间 Z4Pro)

管理 NAS (10.0.0.3) 上的 Docker 容器：状态、日志、重启、更新、磁盘健康。

## When to Use

- 用户问 NAS 上任何容器的状态 / 日志 / 重启 / 更新（qdrant-mem0、syncthing、emby、paopaodns 等）
- 用户问 NAS 磁盘空间、compose 项目、容器挂了怎么处理
- mem0 / Qdrant / Obsidian 同步 / DNS(paopao) 相关的容器侧排查


## 连接信息（已验证 2026-08-10）

```bash
# SSH（密码带尾随句点！）
sshpass -p '<密码>' ssh -p 10000 -o StrictHostKeyChecking=no 18332733294@10.0.0.3 "<cmd>"
# Docker 必须 sudo（docker.sock permission denied）
sshpass -p '<密码>' ssh -p 10000 -o StrictHostKeyChecking=no 18332733294@10.0.0.3 \
  "echo '<密码>' | sudo -S docker ps 2>/dev/null"
```

- 用户：`18332733294`，端口 `10000`（非 22）
- SSH 密码 = sudo 密码 = `<密码>`（**尾随句点，漏掉必 Permission denied**）
- 主机名：`Z4Pro-Z66F`，Linux 5.19.17-z4pro-generic，15 GiB RAM
- Homelable Web: http://10.0.0.3:3003 (JHSweetheart / <密码>)

## 容器清单（15 个，2026-08-10 实测）

| 容器 | 镜像 | 用途 |
|------|------|------|
| qdrant-mem0 | qdrant/qdrant:latest | mem0 向量库 (6333/6334) |
| syncthing | syncthing/syncthing:latest | Obsidian vault 双向同步 |
| paopaodns | sliamb/paopaodns:latest | DNS (10.0.0.6:53，反污染) |
| xream_sub-store | docker.1ms.run/xream/sub-store:latest | 订阅转换 |
| homelable-frontend | ghcr.io/pouzor/homelable-frontend:latest | 网络拓扑可视化 (3003) |
| homelable-backend | ghcr.io/pouzor/homelable-backend:latest | Homelable 后端 |
| embyserver | docker.1ms.run/amilys/embyserver:latest | 媒体服务器 |
| metatube | ghcr.io/metatube-community/metatube-server:latest | 元数据抓取 |
| moviepilot-v2 | docker.1ms.run/jxxghp/moviepilot-v2:latest | 影音管理 |
| chinesesubfinder | allanpk716/chinesesubfinder:latest | 中文字幕 |
| qbittorrent | johngong/qbittorrent:4.6.7-4.6.7.10 | BT 下载 |
| openspeedtest | docker.1ms.run/library/nginx:alpine | 内网测速 (原生中文, 6680/3004) |
| xhongc_music_tag_web | xhongc/music_tag_web:latest | 音乐标签 |
| deluan_navidrome | deluan/navidrome:latest | 音乐流媒体 |
| uptime-kuma | louislam/uptime-kuma:latest | 可用性监控与探针 (3005) |
| beszel-hub | henrygd/beszel:latest | 性能与容器监控中心 (8095) |
| beszel-agent | henrygd/beszel-agent:latest | 系统与容器采集探针 (45876) |

## Compose 项目位置

```bash
# 5 个 compose 项目（路径在 /tmp/zfsv3/... 下，极空间特殊挂载）
homelable:     /tmp/zfsv3/nvme14/18332733294/data/Docker/homelable/docker-compose.yml   (2 容器)
mem0:          /tmp/zfsv3/nvme14/18332733294/data/Docker/hermesmemory/docker-compose.yml (qdrant)
metatube:      /tmp/zfsv3/sata12/18332733294/data/docker/metatube/docker-compose.yml
paopaodns:     /tmp/zfsv3/nvme14/18332733294/data/Docker/PaoPaoDNS/docker-compose.yml
openspeedtest: /tmp/zfsv3/nvme14/18332733294/data/Docker/openspeedtest/docker-compose.yml
uptime-kuma:   /tmp/zfsv3/nvme14/18332733294/data/Docker/uptime-kuma/docker-compose.yml
beszel:        /tmp/zfsv3/nvme14/18332733294/data/Docker/beszel/docker-compose.yml
```

## 常用操作模板

```bash
# 全部容器状态
sshpass -p '<密码>' ssh -p 10000 18332733294@10.0.0.3 "echo '<密码>' | sudo -S docker ps --format '{{.Names}}\t{{.Status}}' 2>/dev/null"

# 单容器日志
... "echo '<密码>' | sudo -S docker logs --tail 100 <name> 2>&1"

# 重启容器（qdrant 重启 = mem0 短暂不可用，注意观察）
... "echo '<密码>' | sudo -S docker restart <name>"

# compose 项目重启/更新（改配置后或镜像更新时）
... "cd /tmp/zfsv3/nvme14/18332733294/data/Docker/homelable && echo '<密码>' | sudo -S docker compose up -d"
... "cd <compose_dir> && echo '<密码>' | sudo -S docker compose pull && docker compose up -d"

# 磁盘健康
... "df -h /data_s002 /data_s003"
```

## 关键服务健康检查

- Qdrant: `curl -s http://10.0.0.3:6333/collections`（mem0 依赖，先查它）
- Homelable: `curl -s http://10.0.0.3:3003`
- Syncthing: 容器 health 可能显示 "starting"（启动慢，属正常）；状态见 http://10.0.0.3:8384

## 陷阱

1. **密码带尾随句点** `<密码>` —— 漏句点 = Permission denied（多次踩坑）
2. **Docker 必须 sudo** —— 普通用户连 docker.sock 直接 permission denied
3. **compose 路径**在 `/tmp/zfsv3/...` 下（极空间虚拟挂载），别在别处找
4. **镜像前缀** `docker.1ms.run/` = 国内加速镜像源，别误判为第三方
5. **syncthing 健康检查**启动后短暂 "health: starting"，等 30s 再看
6. **syncthing 容器持续 "starting"/每 ~27s 重启（RestartCount 猛涨）≠ 容器问题**：极空间内置 autoBackup 服务有自己的宿主 syncthing（/zspace/applications/services/syncthing/），若其 setting 指向失效盘位（如 sata11 不存在），zbasic 守护每 27s 调 restart_syncthing.sh，stop 脚本 curl 失败后执行 `killall syncthing` **误杀 Docker 容器**。修复（2026-08-12 验证）：① setting 改为有效盘位（sata12）② **宿主 syncthing 端口不可改**（极空间 setup/install 脚本硬编码 22000），必须让 Docker 容器让出 22000 改映射 22002，Mac 端 config.xml 同步改 tcp://10.0.0.3:22002 ③ 启动宿主 start_syncthing.sh.appstore ④ 验证容器 RestartCount 停止增长 + ZSpaceSync 连上宿主 22000。判断标志：docker events 只有 die/start 无 kill/stop 事件、容器日志 "Received signal; exiting (signal=terminated)"、exitCode=0。容器重建参数备份在 /data_s002/syncthing/backup-20260812/syncthing-inspect.json。
7. 改 vault 的 NAS-Docker.md 时：容器清单以此技能实测表为准（vault 旧版漏 paopaodns）

## 验证步骤

1. `docker ps` 能列出 15 个容器 → 连接 OK
2. 新增/移除容器后：更新本技能容器清单 + vault NAS-Docker.md（两边同步）
