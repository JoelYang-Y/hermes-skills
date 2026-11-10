# SubStore API 操作速查（NAS 10.0.0.3:3002）

SubStore 跑在 NAS Docker 容器 `xream_sub-store`（镜像 `docker.1ms.run/xream/sub-store:latest`，端口 3002→3001）。
**后端 API 带路径前缀**（容器 Env `SUB_STORE_FRONTEND_BACKEND_PATH`，本用户为 `/T3B9dgzBzdRbBF8Aqx7P`）——裸 `/api/...` 会返回 SPA HTML 或 `Cannot POST`。

## API 端点（base = http://10.0.0.3:3002/T3B9dgzBzdRbBF8Aqx7P）

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/collections` | GET | 列出所有集合（含 Quick Setting 参数） |
| `/api/collection/:name` | GET | 读单个集合完整 JSON（响应在 `data` 字段） |
| `/api/collection/:name` | PATCH | 更新集合（传完整 data JSON，先 GET 再改再 PATCH） |
| `/api/subs` | GET | 列出订阅（含 url、process） |
| `/api/utils/refresh?sub=<name>` | GET | 触发订阅刷新（返回 `{"status":"success"}` 只表示调用成功，不代表拉到节点） |
| `/download/collection/<name>?target=SurgeMac` | GET | 拉集合产物（Surge 配置文本） |

## Quick Setting Operator 支持的 key（源码验证 2026-08）

`useless` / `udp` / `scert` / `tfo` / `vmess aead` / `block-quic`，值 DEFAULT/ENABLED/DISABLED（block-quic 另支持 auto/on/off）。
映射到 Surge 节点参数：udp→`udp-relay=true`、scert→`skip-cert-verify=true`、tfo→`tfo=true`、block-quic→`block-quic=`。

用户 Surge 集合已配：`useless=DISABLED, udp=ENABLED, block-quic=auto`（2026-08-11 更新）。

## 更新 Docker 容器（镜像升级）

```bash
# 1. 拉新镜像
sshpass -p '<密码>' ssh -p 10000 18332733294@10.0.0.3 "echo '<密码>' | sudo -S docker pull docker.1ms.run/xream/sub-store:latest"
# 2. 删旧容器（数据在挂载卷，不丢）
# 3. 重建（参数与原容器一致）
sudo docker run -d --name xream_sub-store --restart always \
  -e TZ=Asia/Shanghai \
  -e SUB_STORE_FRONTEND_BACKEND_PATH=/T3B9dgzBzdRbBF8Aqx7P \
  -v /tmp/zfsv3/sata12/18332733294/data/docker/substore:/opt/app/data \
  -p 3002:3001 docker.1ms.run/xream/sub-store:latest
# 4. 验证版本
curl -s http://10.0.0.3:3002/ | grep -oE 'meta name="version" content="[^"]+"'
```

注意：容器非 compose 管理（`com.docker.compose.*` label 为空），必须 docker run 重建。

## 陷阱

1. **机场订阅链接有效期短（奶昔 5-10 分钟）**：过期后 refresh 返回 success 但下载集合报
   `{"error":{"code":"INTERNAL_SERVER_ERROR","message":"组合订阅 Surge 中不含有效节点"}}`；
   容器日志显示拉到的是 `请登录系统网站后台…开启订阅获取` 文本。**必须去机场官网重新生成链接**，不是 SubStore 故障。
2. Surge 事件里的 `资源更新失败: 服务器返回异常状态码 500` 通常就是这个原因（订阅链接过期），别误判为 SubStore 故障。
3. 集合 process 里的 Quick Setting Operator 是**批量注入**的最佳位置——在 SubStore 改一次，订阅刷新后所有节点自动带参数，比在 Surge 里逐个改高效且不丢。
4. 用户 Surge 里 smart 策略组（HongKong/Singapore 等）的 `policy-path` 指向 SubStore 产物；SubStore 侧参数只影响这些订阅节点，**不影响自建 AnyTLS 节点**（那两个在 Surge 里手动配置）。
