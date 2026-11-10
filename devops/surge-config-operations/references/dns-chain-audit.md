# DNS 链路只读体检 —— Surge → AdGuardHome → PaoPaoDNS

用户问「检查网络链路 / paopaodns / adguardhome / DNS 解析 / 解析变慢」时用。全程只读。
结论按层归因，不要把 AGH 上游问题说成 Surge 问题，也不要把 PaoPao 回 AAAA 说成缺陷。

## 链路与端口（实测拓扑）

```
客户端 / Mac mini
  └─ Surge encrypted-dns-server → https://adg.jhsweetheart.com/dns-query  (443, 严格 TLS 校验)
       └─ AdGuardHome 10.0.0.6:53/443/3000   (Docker bridge 172.19.0.2)
            └─ upstream_dns: tcp://10.0.0.6:5335   (单条，fallback_dns 为空)
                 └─ PaoPaoDNS 容器: mosdns :53  (= 宿主 5335)
                      ├─ unbound       :5301  递归
                      ├─ unbound       :5304  forward
                      └─ dnscrypt-proxy :5302
```

映射要点：PaoPao 容器内 `DNSPORT=53` → 宿主 `5335`；AGH 用 **TCP** 连它，所以宿主上只有 UDP 通不算通。

## 0. 取数铁律

- **所有 10.0.0.6 检查合并进一次 SSH 调用**（`cmd1; cmd2; cmd3` 串联）。既省往返，也避免连续短连接撞 sshd 限流（表现为 `Permission denied` 而密码本身没错，遇到等 20s 重试一次即可）。
- 该机是 Alpine 精简环境：统计一律用 `grep` / `sed` / `awk` 处理 querylog，**不要为了一个数字去装 python3 / sqlite3 / dig**。域名解析用 `nslookup -port=<p> <domain> <server>`（注意 busybox nslookup 的参数顺序，写错会静默返回空）。
- 本机 `dig @10.0.0.6` **不能用来判断 AGH 真实应答**：Surge `hijack-dns = *:53` 截走所有 53 端口查询。要么走 DoH（443 不被劫持），要么 ssh 到 10.0.0.6 本机查。

## 1. 验证 Surge 真的在用加密 DNS（最高价值一步）

不要用 tcpdump / `ss -tn`：AGH 在容器网络命名空间里，宿主上 `ss -tn | grep :443` 是 0 条，容易误判成"没用 DoH"。

querylog 的 `CP` 字段直接给答案：

```bash
tail -2000 /root/AdGuardHome/data/querylog.json \
  | grep -oE '"CP":"[^"]*"' | sort | uniq -c
tail -2000 /root/AdGuardHome/data/querylog.json \
  | grep -oE '"IP":"[^"]*"' | sort | uniq -c | sort -rn | head
```

判读：`"CP":"doh"` 占绝对多数 + `"IP"` 是 Mac mini 的 10.0.0.2 → 加密 DNS 生效。
客户端 IP 为 docker 网关 `172.19.0.1` 或 `"CP":""` 的是容器内自查询，不算客户端流量。

## 2. 解析质量与拦截判读（纯 shell）

```bash
tail -50000 /root/AdGuardHome/data/querylog.json > /tmp/q.log
wc -l < /tmp/q.log                                                    # 总查询
awk 'END{}' /dev/null; echo $(grep -c '"IsFiltered":true' /tmp/q.log) / $(wc -l < /tmp/q.log) | awk '{printf "blocked=%.1f%%\n", $1/$3*100}'
grep -oE '"Text":"[^"]*"' /tmp/q.log | sort | uniq -c | sort -rn | head -10        # 命中规则 Top
grep '"IsFiltered":true' /tmp/q.log | grep -oE '"QH":"[^"]*"' | sed 's/"QH":"//;s/"//' | sort | uniq -c | sort -rn | head -12
grep -oE '"Upstream":"[^"]*"' /tmp/q.log | sort | uniq -c | sort -rn | head -5    # 上游分布
grep -oE '"Elapsed":[0-9]+' /tmp/q.log | sed 's/"Elapsed"://' | sort -n \
  | awk '{a[NR]=$1} END{printf "p50=%.2fms p90=%.2fms p99=%.2fms max=%.2fms n=%d\n", a[int(NR*.5)]/1e6, a[int(NR*.9)]/1e6, a[int(NR*.99)]/1e6, a[NR]/1e6, NR}'
rm -f /tmp/q.log
```

`Elapsed` 单位是**纳秒**。健康基线：p50 < 0.5ms、p99 < 5ms。`max` 冲到 1900ms+ 说明有上游超时个案（见 §4），不要拿 max 当整体性能结论。

`Upstream` 只出现内网上游、没有外部 DoH → AGH 没绕开 PaoPao。

**拦截是否误伤**按域名性质分两类，不要一刀切说"拦得多就是问题"：

| 模式 | 判读 |
|---|---|
| `mcs.zijieapi.com` / `pc-mon.zijieapi.com` / `tnc0-*` / `log0-misc-*.amemv.com` | 字节系监控与日志，拦截正确 |
| `mdt.qq.com` / `beacon.qq.com` / `trace.qq.com` / `stat6.y.qq.com` / `tp2p.kg.qq.com` | 腾讯遥测与统计，拦截正确 |
| `adash*.taobao.com` / `amdc.alipay.com` / `audid-api.taobao.com` / `cm.bilibili.com` / `api-adservices.apple.com` / `ca.iadsdk.apple.com` | 广告 SDK 统计，拦截正确 |
| **`dns.weixin.qq.com.cn` / `aedns.weixin.qq.com` / `badjs.weixinbridge.com`** | **误伤候选**：微信自有 DNS/EDNS 就近调度与错误上报被通用广告规则收走。功能不崩，但 CDN 调度降级 |

拦截率 30% 上下是正常的（国内 App 遥测密度高）；要用"命中的是哪些域"来判质量，不用比例判。

## 2.5 放行规则（user_rules）编辑实操

过滤器订阅（HaGeZi Pro / 1Hosts Lite / anti-AD / SkkMoe）每日更新会突然开始拦 SDK 域名。
放行写在 `user_rules`，`@@` 例外规则优先级最高，按**域级**放行（`@@||zijieapi.com^`），
不要逐条列子域——同一 App 会打几十个子域变体，列一条漏十条。

**改法（不做 sed，拉回本地改再推回）**：

```bash
scp root@10.0.0.6:/root/AdGuardHome/AdGuardHome.yaml ./agh.yaml
# 本地用 python 在 user_rules 列表末尾追加，保持既有缩进与单引号风格：
#   - '@@||zijieapi.com^'
scp ./agh.yaml root@10.0.0.6:/root/AdGuardHome/AdGuardHome.yaml
ssh root@10.0.0.6 "chmod 600 /root/AdGuardHome/AdGuardHome.yaml \
  && docker restart adguardhome && sleep 7 && docker ps --format '{{.Names}} {{.Status}}'"
```

改前必备份：`cp AdGuardHome.yaml AdGuardHome.yaml.bak-<原因>-$(date +%Y%m%d%H%M%S)`；
多轮改动就留多份，能回到任一中间态。

**坑一：sshpass 远程命令里不能拼 `'"'"'`**。为在远程单引号串里塞单引号而拼出的转义序列会提前
闭合本地引号，把 sshpass 的密码参数打散，报 `Permission denied` 两三次后退出——看起来像密码错或
撞限流，实际是本地 shell 解析问题。要么整条远程命令用双引号包，要么走上面的 scp + 本地编辑。

**坑二：连续短连接会被 sshd 限流**，同样表现为 `Permission denied`。等 10~20s 重试一次即可，
不要当成密码失效反复试——反复试才会真被记住。

**坑三：改完必须验两层**，只验一层会误判：
① 域名侧 `nslookup <域> 127.0.0.1`（在 10.0.0.6 上跑）不再返回 `0.0.0.0`；
② DoH 侧 `scripts/doh_compare.py --domains <域,...>` 看 `rcode=0` 且 `ancount>0`。
再回头查 Surge 的 recent——它的 DNS 缓存可能还在用旧 `0.0.0.0`（见主 SKILL.md 同名章节）。

**保留拦截的对照项**：`doubleclick.net`、`googleadservices.com` 改完仍应是 `0.0.0.0`，
用来证明没有把全局拦截一并弄坏。

**回滚**：备份 cp 回原位 + `docker restart adguardhome`。

## 3. DoH 证书到期审计（最容易漏，到期即断）

```bash
echo | openssl s_client -connect 127.0.0.1:443 -servername <SNI> 2>/dev/null \
  | openssl x509 -noout -subject -dates -issuer
grep -c 'BEGIN CERTIFICATE' /root/AdGuardHome/AdGuardHome.yaml   # >1 = 证书已内嵌进 yaml
ls -la /root/.acme.sh 2>/dev/null; crontab -l | grep -iE 'acme|renew'
systemctl list-timers | grep -iE 'acme|cert'
```

判读：`certificate_chain` 内嵌 = 手工维护，不落在 `/etc/letsencrypt`，**不会**被通配符证书的 acme 续期覆盖。三处续期痕迹全空 + 到期日在 30 天内 = **P0**。

到期后的表现是静默降级，不是报错：Surge 的 `encrypted-dns-server` TLS 校验失败 → 回落 `dns-server = 10.0.0.6`（明文 53）或第二个公网 DoH → 失去内网 DoH 的分流与拦截能力，用户感受到的是"部分站点偶发异常/变慢"。

同时校验三件事是否对齐：AGH yaml 的 `tls.server_name` == `encrypted-dns-server` URL 的主机名 == Surge `[Host]` 里指向 10.0.0.6 的那条记录。三者一致时 DoH 引导不依赖任何外部解析，冷启动也稳。

## 4. 单上游超时的跨层归因

AGH 日志形态：

```
dnsproxy: exchange failed upstream=tcp://10.0.0.6:5335 question=";....jddebug.com." duration=2.00200132s
err="... read tcp 172.19.0.2:51668->10.0.0.6:5335: i/o timeout"
```

含义：`upstream_dns` 单条 + `fallback_dns: []`，PaoPao 对不存在域（`*.jddebug.com`、`dig.bdurl.net` 这类调试/遥测域）不快速返 NXDOMAIN 而是等递归超时。同一条因果链会同时出现在 Surge 24h 日志的 `DNS failed: <domain>` 里。

**归因写法**：这是 AGH 上游配置问题，不是 Surge 问题，也不是 PaoPao 宕机。

对照检查：`upstream_dns` 是否只有一条、`fallback_dns` 是否为空、`upstream_timeout` / `fastest_timeout` 是不是 1s（比上游实际 2s 超时更短的激进值）。

## 5. AGH 配置必读字段

```bash
grep -nE 'upstream_dns|fallback_dns|upstream_mode|upstream_timeout|fastest_timeout|aaaa_disabled|enable_dnssec|cache_|server_name|port_https|edns_client_subnet' /root/AdGuardHome/AdGuardHome.yaml
sed -n '/^filters:/,/^whitelist_filters:/p' /root/AdGuardHome/AdGuardHome.yaml
```

- `aaaa_disabled: true` = AGH 层全局拦 AAAA，与 Surge `ipv6=false` 语义一致。
- `cache_optimistic: true` + `cache_size` 256MB → p50 亚毫秒的来源，不是异常。
- `enable_dnssec: true` 配单一 TCP 上游：上游结果不带 RRSIG 时退化为非验证态，属潜在延迟源；正常不该出现 SERVFAIL。
- 过滤器按 id 对账：querylog 的 `FilterListID` 就是 yaml 里的 `id`，用它把命中规则反查到具体订阅（如 SkkMoe）。
- 容器 EXPOSE 了 67-68/udp、443/udp、853、5443、6060 但没有 `0.0.0.0:` 前缀 = 未映射到宿主，无实际暴露面；别再当"端口开放"报。

## 6. PaoPaoDNS 内部结构

```bash
docker exec paopaodns sh -c 'netstat -lnup | grep -E ":53|:5301|:5302|:5304"'
docker exec paopaodns sh -c 'ps aux | grep -E "mosdns|unbound|dnscrypt" | grep -v grep'
docker exec paopaodns sh -c 'cat /proc/1/environ | tr "\0" "\n" | grep -iE "IPV6|CN|ECS|MARK"'
```

实测分工：mosdns `:53`（宿主 5335）做入口与分流 → unbound `:5301` 递归 / `:5304` forward / dnscrypt-proxy `:5302`。

分流环境变量：`CNAUTO=yes`（按响应 IP 判国内）、`CNFALL=yes`、`CN_TRACKER=yes`、`USE_MARK_DATA=yes`、`IPV6=yes`。

**`IPV6=yes` 是正常值，不要当缺陷**：PaoPao 返回 AAAA 是上游信息完整性，压制发生在 AGH 的 `aaaa_disabled`。三层各有一个 IPv6 开关，改任一层都要同步另两层。

分流正确性抽查：`155.231.x`（江苏淘宝）、`180.101.x`（江苏百度）、`58.217.x`（江苏腾讯）、`140.82.121.x`（GitHub）= GeoDNS 就近准确。若国内域拿到明显境外 IP，才是 PaoPao 分流或污染问题。

## 7. 分层归因表

| 现象 | 归到哪层 | 依据 |
|---|---|---|
| 解析 p50 > 5ms | AGH 缓存或 PaoPao | `Elapsed` 分布 |
| 个别域 2s 失败 | AGH 单上游 | `exchange failed ... i/o timeout` |
| 大量域 SERVFAIL | AGH DNSSEC 或上游 | AGH `dnsproxy` 日志 |
| 明文 53 上出现查询 | Surge DoH 断裂 | querylog `CP` 非 `doh` |
| 国内外 IP 都不对 | PaoPao 分流/污染 | 对比 `nslookup -port=5335` 直查 |
| 解析正确但连不上 | 与 DNS 无关 | 转 `proxy-chain-diagnostics` |

## 8. 报告要交代的边界

区分"实测"与"推断"：设备身份、容器内进程归属这类拿不到直接证据的，写明"未能最终确认"，不要用拓扑反推当成事实。DNS 链路里可确证的是：querylog 的 CP/IP/Upstream/Elapsed、证书 dates、`nslookup` 直查结果、`nc -zv` 端口可达。
