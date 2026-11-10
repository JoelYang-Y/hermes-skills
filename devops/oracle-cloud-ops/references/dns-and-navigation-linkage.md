# Cloudflare DNS 与导航站联动要点

## 1. Cloudflare API 凭据找回（用户说"给过你 token"时）

- **优先从 10.0.0.6 的 acme.sh 读**：token 已持久化在 `/root/.acme.sh/account.conf` 的
  `SAVED_CF_Token`（约 53 字符；`SAVED_CF_Account_ID` 可能为空，不影响使用）：
  ```bash
  CF_TOKEN=$(ssh root@10.0.0.6 "grep '^SAVED_CF_Token=' /root/.acme.sh/account.conf | cut -d= -f2 | tr -d \"'\"")
  ZID=$(curl -s -H "Authorization: Bearer $CF_TOKEN" \
    "https://api.cloudflare.com/client/v4/zones?name=jhsweetheart.com" | jq -r '.result[0].id')
  ```
  这条路径已实测能查 zone、列记录、删记录，不要因为看到 account.conf 里没别的东西就断定没存。
- **不要用 `/user/tokens/verify` 判断 token 有效性**：这是 scoped token（Zone:DNS:Edit），
  verify 接口返回 `result: null`，按 `d.get('result',{}).get('status')` 解析会抛
  `AttributeError: 'NoneType' object has no attribute 'get'`，看上去像 token 失效，实际完全可用。
  判据是能不能列出 zones / dns_records。
- token 也可能出现在历史会话的工具调用参数里：`session_search(query="Cloudflare API token")`。
  Zone ID：`754217bcbdaa0e8cc89b6e279ba54276`。
- 用后即焚：用完 `rm /tmp/.cftok /tmp/.cfzid`，输出里避免整段回显 token。

## 2. 添加 DNS 记录（Python + urllib，幂等）

```python
api(method, path, body):  # headers: Authorization: Bearer <TOKEN>
# 1) GET /zones/{ZONE}/dns_records?per_page=100&type=A 拉现有，按 name 建 dict 跳过重复
# 2) POST /zones/{ZONE}/dns_records {"type":"A","name":"<sub>.jhsweetheart.com","content":"<IP>","ttl":1,"proxied":False}
# 3) 复核列出全部 A 记录
```

- 新服务域名一律 Proxied=False（直连 VPS IP，免 CDN 干扰运维端口）。
- **验证要在服务器侧做**：`ssh oci2 "python3 -c 'import socket; print(socket.gethostbyname(...))'"` + `curl https://<sub>.jhsweetheart.com`。Mac 本地 dig/curl 可能因 Surge/mDNSResponder 缓存 NXDOMAIN 而假失败（gatus 通但同批其他域名 000），不是 DNS 没生效。本地刷新需 `sudo dscacheutil -flushcache`（无 sudo 密码时提示用户即可）。

## 3. 导航站 v2 联动（startpage-dashboard-ops 更新版）

- 导航站项目已升级为 `~/scripts/startpage-v2/`（Vite + TS + Tailwind）。
- **主数据源是 `src/config/site.config.ts` 的 `SITE_CONFIG.cards`**（只改 `src/data/config.json` 有不生效的历史记录）。稳妥做法是**两处同改**；注意 config.json 里数组最后一项没有尾逗号，字符串替换删最后一项时要连前一项的 `},` 一起吃掉并改回 `}`。
- 新卡片：图标下载到 `public/icons/`（先 curl 验证 200；dify 用 `simple-icons:dify`、gatus 用 `mdi:heart-pulse`、headscale 用 `simple-icons:tailscale`、n8n 用 walkxcode `n8n.png`）→ 在 site.config.ts cards 数组按 category 插入 → `npm run build` → rsync dist/ 到 `oci:/opt/startpage/` → 验证（页面 JS 渲染，抓 `assets/index-*.js` grep 卡片名）→ git push（dist 被 .gitignore 忽略，只提交 src/ 与 public/）。
