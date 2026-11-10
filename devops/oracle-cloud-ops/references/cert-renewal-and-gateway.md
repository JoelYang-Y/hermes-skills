# 证书续期与统一网关运维（OCI 双机实测）

2026-10-09 对 OCI-1 做的完整排查与修复，含两个高频陷阱。

## 陷阱 1：`sed -i` 不改单文件 bind mount（最坑的一个）

`unified-gateway-nginx` 把宿主机文件以**单文件**方式挂进容器：

```
/opt/vaultwarden/nginx/default.conf -> /etc/nginx/conf.d/default.conf
```

单文件 bind mount 绑定的是 **容器启动那一刻的 inode**。而 `sed -i` 的行为是
「写新文件 + rename 覆盖」，**换掉了 inode** → 宿主机文件已改，容器里看到的
仍是旧内容，`nginx -t` / reload 全部“成功”但**根本没生效**。

取证方法（inode 不一致即命中本陷阱）：

```bash
stat -c "%i" /opt/vaultwarden/nginx/default.conf          # 宿主机
 docker exec unified-gateway-nginx stat -c "%i" /etc/nginx/conf.d/default.conf
```

**正确做法（二选一）**：
- 改完必须 `docker restart <容器>` 让挂载重新绑定（本次采用，~2s 中断）
- 或用不换 inode 的写法：`cp new > path`（截断原 inode 写入）而非 `sed -i`

**推论**：以**目录**方式挂载的路径不受影响（`/etc/letsencrypt -> /etc/letsencrypt`
是目录挂载，里面文件可自由替换），所以「同一条 nginx 配置里，目录挂载的那几个
server 块能热更新、单文件挂载的那个不行」是正常现象，不是玄学。

## 陷阱 2：`certbot.timer` 在跑 ≠ 证书会自动续期

OCI-1 上 `certbot.timer` 为 `enabled`、每分钟都在跑，但：

```
/etc/letsencrypt/renewal/   → 空
certbot certificates        → No certificates found
/etc/letsencrypt/live/jhsweetheart.com/ → 普通文件而非 symlink
```

**判据**：certbot 正常签发的证书，`live/<域名>/` 下是**指向 `archive/` 的软链接**；
若是普通文件，说明是**手工拷进来的**，certbot 完全不认，`renew` 什么也不做
（表现为 `certbot renew` 输出 “No simulated renewals were attempted”，
容易被误读成“还没到期所以没续”）。

**自检三道**：`certbot certificates` 有输出 / `renewal/*.conf` 存在 / `live` 下是 symlink。
三条缺任一，就等于**没有续期机制**。

## OCI-1 证书体系现状（2026-10-09 修复后）

| 项 | 值 |
| :--- | :--- |
| 签发工具 | **acme.sh v3.1.5**（`/root/.acme.sh`，由 OCI-2 整目录拷贝而来） |
| 域名 | `jhsweetheart.com` + SAN `*.jhsweetheart.com` |
| 安装路径 | `/etc/letsencrypt/live/jhsweetheart.com/{fullchain,privkey,cert}.pem` |
| 续期定时 | `37 3,9,15,21 * * *`（acme.sh --cron） |
| 续期钩子 | `Le_ReloadCmd` = `docker exec unified-gateway-nginx nginx -s reload` |
| 认证方式 | `dns_cf`（CF_Token / CF_Account_ID 随证书 conf 携带） |

搬瓦工与 OCI-2 的对照：
- **OCI-2**：acme.sh + `dns_cf`，安装到 `/etc/ssl/oracle2/`，`Le_ReloadCmd='systemctl reload nginx'`（本次补上）
- **搬瓦工**：有 `/etc/cron.d/certbot`，证书在 `/usr/local/etc/`（CN=joel.jhsweetheart.com），OpenResty 容器读 `/usr/local/openresty/nginx/conf/ssl/fullchain.pem`

## 复用套路：把一套已验证的 acme.sh 迁到新机器

比重新安装+重新签发更快，且不消耗 LE 配额：

```bash
# 源机 → 本机 → 目标机（凭据随文件走，不落到输出里）
sshpass -p '…' ssh -p 59421 root@<源机> 'tar czf - -C /root .acme.sh' \
  | sshpass -p '…' ssh -p 59421 root@<目标机> 'mkdir -p /root/.acme.sh.incoming && tar xzf - -C /root/.acme.sh.incoming'
```

然后目标机：`mv` 就位 → 跑 `--install-cert` 指向本机路径 + 本机 reloadcmd →
`--install-cronjob`。注意 `--install-cert` 必须重跑，否则目标机会沿源机的
安装路径/重载命令（本次若不重跑就会去 reload 一个不存在的 nginx 服务）。

两份独立续期同一域名不会触发 LE 限额（重复证书限额为同一域名集每五 5 张，
两台机各自 ~60 天续一次）。

## 该机已知的非一致项（非故障，仅记录）

- OCI-1 宿主机 `nginx` 服务为 `inactive` —— 正常，TLS 由 `unified-gateway-nginx` 容器终结
- OCI-1 的 `certbot.timer` 仍 enabled 但无任何受管证书，属空转，无害
- `/usr/local/etc/{fullchain,privkey}.pem` 已不再被配置引用（旧 oracle 专用证书），仅作为备份保留
- OCI-1 容器重启后的 `vaultwarden` 会短暂显示 `health: starting`，约一分钟后转为 `healthy` 属正常
