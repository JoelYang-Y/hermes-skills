# Surge Ponte 故障实录（2026-08-12）

用户报"Ponte 无法使用"。完整排查过程与结论，供后续 Ponte 排障复用。

## Ponte 是什么

- Surge 私有 mesh 网络 / 内网穿透：Mac、Apple TV 可做服务端，iOS 仅客户端
- 无额外服务器，设备信息和加密密钥通过 iCloud CloudKit 同步（container `iCloud.com.nssurge.inc`）
- 三种穿透方式：直接 NAT 穿透（需 Full Cone NAT）、代理 NAT 穿透（需支持 UDP 的代理）、静态端口转发（公网 IP + 路由器端口映射，UDP 6208）

## 现场日志（log show）

```
22:18:51 [SGPonteServer] Start ponte server…
22:18:53 [SGDDNS] Failed to update DDNS record: <CKError "Zone Not Found" (26/2036); server message = "Zone does not exist"; container ID = "iCloud.com.nssurge.inc">
22:11:38 [SGPonteServerChannel] Failed to start ponte channel: Ponte 服务启动失败，UDP 流量被阻拦。
22:09:44 [ERROR] ERROR (SGDDNS.m:68): <CKError "Zone Not Found" ...>
```

## 双根因判定

### 根因 1：CloudKit DDNS Zone 缺失（主因，与 reload 引擎崩溃同源）
- `Zone Not Found` 从引擎崩溃前（22:09）就存在，重启后持续出现 → 不是 IPv6 改动引起
- CloudKit 常规操作（query/modify-records）22:11 成功 → iCloud 连接本身正常，只有 Surge DDNS 专属 Zone 缺失
- 影响：Ponte 无法向 iCloud 注册自己 → 客户端发现不了设备

### 根因 2：UDP 被 REJECT
- 生效配置 `udp-policy-not-supported-behaviour = REJECT`
- Ponte UDP 6208 通道匹配到不支持 UDP 转发策略时被 REJECT
- 注意：当前 [Rule] 无全局 UDP REJECT（只有端口 500/4500 → AnyTLS-BWG 放行），问题在参数级回退行为

## 排除项（不是根因）

- macOS 应用防火墙已允许 Surge 传入：`socketfilterfw --getappblocked /Applications/Surge.app` = permitted
- Surge 监听 UDP 6208 正常（IPv4 10.0.0.2:6208 + IPv6 [240e:...]:6208）
- 配置里无全局 `AND,((PROTOCOL,UDP)),REJECT` 规则（记忆里旧快照有，生效配置没有）

## 建议修复顺序

1. **Surge Mac 设置 → iCloud 同步 → 关闭 → 重启 Surge → 重新开启**（强制重建 CloudKit Zone）
2. 若仍报 UDP 阻拦：`udp-policy-not-supported-behaviour` 从 REJECT 改 DIRECT
3. 验证：Ponte 界面设备在线；日志不再出现 `Zone Not Found` / `UDP 流量被阻拦`

## 教训

- 用户 iCloud 同步异常（Zone Not Found）时：不要 reload（会崩引擎）、Ponte 会不可用、手机端改配置不会同步过来——三者同源
- Ponte 排障先查日志里的 `SGPonte`/`SGDDNS`/`CKError`，UI 状态第二
- Surge API 无 ponte 端点，无法程序化查询 Ponte 状态
