# Surge HTTP API 诊断速查

只读用法。所有请求带 `-H 'X-Key: <密码>'`（basic auth 会 401）。端口 6171。

## 端点与返回形状

### GET /v1/profiles/current
```json
{"profile": "[General]\nloglevel = notify\n..."}
```
返回**运行中** profile 的全文。桌面端 `~/Library/Mobile Documents/iCloud~com~nssurge~inc/Documents/`
下可能同时存在多份 conf（如 JoelYang.conf 与 JoelYang-Surge6.conf），**磁盘上的那份不一定是正在跑的**。
先用这个端点确认运行态，再做任何「配置文件与运行态不一致」的判断。

### GET /v1/policies
```json
{"proxies": [], "policy-groups": ["节点选择", "AI", "AT&T", "BWG", ...]}
```
只是名字清单。`proxies` 通常为空数组——**不要**期望在这里拿到节点参数或延迟；节点名/延迟不在此端点。

### GET /v1/policy_groups
```json
{"AT&T": [{"isGroup": false, "name": "REJECT", "typeDescription": "REJECT", "lineHash": "POLICY::...", "enabled": true},
          {"isGroup": false, "name": "Sub-AT&T", "typeDescription": "AnyTLS", ...}], ...}
```
**判断策略组健康的主力端点**：给出每个组的成员列表与**顺序**、类型、enabled。
`typeDescription` 反映运行态类型（`Fallback 策略组` / `Smart 策略组` / `手动选择策略组`），
可以用来发现「配置文件写的是 select，运行时被改成 Fallback」这类漂移。

### GET /v1/requests/recent
返回最近 200 条，字段（注意大小写，写错只会得到 None）：

| 字段 | 含义 |
|------|------|
| `URL`（大写） | `host:port` 或 URL |
| `rule` | 命中的规则，如 `RULE-SET AIGC.list` / `FINAL` |
| `policyName` / `originalPolicyName` | 最终策略 / 原始策略（**取证要用 originalPolicyName**） |
| `failed` / `rejected` / `completed` | 结果标志 |
| `remark` | 如 `Rejected by rule` |
| `notes[]` | 逐行事件，含 `Sub-rule matched`、`Policy decision path: AI -> AT&T -> REJECT`、`Connect failed`、`TLS ...` |
| `startDate` / `completedDate` | Unix epoch 秒（浮点） |
| `sourceAddress` / `deviceName` / `pid` / `processPath` | 来源识别 |

没有 `time`、`url`（小写）、`statusCode`、`error` 这些字段——按那些名字取一律 None。

## 判据表：失败形态 → 病因

| 现象 | notes 特征 | 结论 |
|------|-----------|------|
| 秒失败（~0.01s） | `remark=Rejected by rule`，`Policy decision path: X -> AT&T -> REJECT` | 策略组落到 REJECT：组的成员里有 REJECT 且真节点探测不可用。**不是网络不通** |
| 超时（数秒~数十秒） | `Connect failed` / `Connection timeout` | 真节点不可达：入口 IP/端口、中转、或落地机故障 |
| TLS 层失败 | `Proxy TLS handshake` 报错 | 节点证书/SNI/密钥问题 |
| 成功 | `TCP connection established` + `Proxy TLS handshake completed` | 链路通，问题在应用层 |

Fallback 组的成员顺序里若 `REJECT` 排在真节点之前，节点一旦探测失败就整组变 REJECT，
用户感知是「秒失败」而非「卡住」——这个区别能立刻把「配置/节点问题」与「网络问题」分开。

## 已知不存在或未验证的路径

- `/v1/status`、`/v1/connections`、`/v1/proxies`、`/v1/policies/{name}`、`/v1/policy_groups/{name}` 均 `unknown path`。
- `POST /v1/policy_groups/test` 存在但参数形状未确定（`{"groupNames":[...]}` 返回 `{"available":[]}`）。
  不要靠它测节点延迟，改用实际流量判定：直接 `curl` 目标域名，再看 `requests/recent` 的 notes。

## 代理端口做判据时的陷阱

`curl -x http://127.0.0.1:6152` 与默认路径（TUN）不是同一条判定链：代理端口有独立认证与
规则二次匹配，`-x` 得到 000 时链路未必坏。下结论前必须用**默认路径**（不带 `-x`）跑同一个目标做对照。
