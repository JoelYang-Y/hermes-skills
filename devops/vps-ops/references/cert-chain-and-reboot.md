# 搬瓦工 VPS 证书链与重启恢复（实测）

## 续期机制：1Panel 内置定时任务（不是 certbot/acme.sh）

搬瓦工上 `acme.sh` 不存在，`/etc/letsencrypt/renewal/` 为空，`/etc/cron.d/certbot`
在 systemd 主机上是**空转**（它只服务于非 systemd 场景）。真正的续期者是：

```
1panel-agent：The scheduled certificate update task ...
              Update the SSL certificate for the [joel.jhsweetheart.com] domain
              ... has been successfully updated            （每日 06:00）
/usr/local/s-ui/sui：inbound/anytls[AT&T] reloaded TLS certificate   （随后 06:00:21）
```

即 **1Panel 定时证书任务续签 → 写 `/usr/local/etc/{fullchain,privkey}.pem` → s-ui
重载 AnyTLS 入站证书**。链路上的代理入站是自动的，无人工介入。

## 缺口：容器内的 ssl 副本不同步

tlS 由 `1Panel-openresty-NmV4` 容器终结，它读的是：

```
宿主机 /opt/1panel/apps/openresty/openresty/conf/ssl/  →  容器 /usr/local/openresty/nginx/conf/ssl/
```

**1Panel 的续签任务不会更新这个目录**。后果：`/usr/local/etc/fullchain.pem`
已是 2027-01-03，而对外提供的仍是 2026-11-03 的旧证书，且**从日志上看不出任何异常**
（任务确实报 success）。表现为“续期一切正常，但证书就是会到期”。

诊断命令（两份指纹必须一致，不一致即命中本缺口）：

```bash
openssl x509 -noout -fingerprint -sha256 -enddate -in /usr/local/etc/fullchain.pem
docker exec 1Panel-openresty-NmV4 sh -c \
  'openssl x509 -noout -fingerprint -sha256 -enddate -in /usr/local/openresty/nginx/conf/ssl/fullchain.pem'
```

注意：容器内镜像**没有 openssl 命令行**是不能用的（`nginx:alpine` 就没有）；
OpenResty 镜像自带，可直接 exec。

## 兼底方案：sync-1panel-ssl.sh + cron

已部署 `/usr/local/bin/sync-1panel-ssl.sh`，cron `30 6 * * *`（晚于 1Panel 的 06:00 续签）。
设计要点，复用时应保留：

1. **幂等**：先 `cmp -s`，内容一致直接 `exit 0`，不产生任何输出与重载
2. **先校验后重载**：容器内 `nginx -t` 通过才 `nginx -s reload`
3. **失败回滚**：保留 `.prev`，`nginx -t` 挂掉时拷回去
4. **同一密钥对才能安全替换**：动手前必须比对公钥（`openssl x509 -pubkey` vs
   `openssl pkey -pubout`）——本次两张证书公钥一致，才敢直接替换；
   若公钥不同则必须先确认新私钥可用，否则一换就把 HTTPS 搞挂。

该目录是**目录挂载**（不是单文件挂载），所以 `cp` 覆盖能直接被容器看到，
不需要重启容器（对比 OCI-1 的单文件挂载陷阱）。

## 重启与自启基线

- 重启恢复约 **55–60 秒**；`1Panel-openresty-NmV4` 为 `restart: always`，自动回来
- 8 个必须复核的节点端口：`59421 80 443 18848 18849 18850 21174 32636`
- 全部服务 `enabled`：`ssh` / `s-ui` / `1panel-core` / `docker` / `fail2ban` / `cron`
- 升级含 docker 包时用**后台脱离式**跑（`nohup ... &` + 轮询日志），
  因为 dockerd/sshd 重启可能切断 SSH；本次实际 90 秒跑完，退出码 0
- 自定义 xanmod 内核包会被 `apt-get upgrade` 扣下不装，需 `apt-get install` 显式安装，
  再重启一次才生效

## 主站域名证书的误判陷阱

`jhsweetheart.com` 走 Cloudflare 代理，外网 `curl -v` 看到的是 **CF 边缘证书**
（到期日与源站完全不同，如 Dec 12 vs Nov 17），不能用来判断源站证书状态；
要测源站证书必须用 **DNS-only 的子域**（如 `oracle.jhsweetheart.com`、`gatus.jhsweetheart.com`）。
