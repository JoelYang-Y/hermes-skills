#!/bin/sh
# 搬瓦工入站连接盘点：按本地服务端口聚合对端 IP + SSH 登录审计。
# 用法: sshpass -p '...' ssh -p 59421 root@64.64.237.34 'sh -s' < scripts/conn_inventory.sh
#
# 关键事实：`ss -tn state established` 被 state 过滤器去掉了 State 列，
# 列序为 Recv-Q Send-Q Local Peer → Peer 是 $4（不是 $5）。用错列不会报错，只会得到假结果。
PORTS="443 59421 32636 21174 12726 18848 18849 18850 45876"

for p in $PORTS; do
  n=$(ss -tn state established "sport = :$p" 2>/dev/null | tail -n +2 | wc -l)
  [ "$n" -gt 0 ] || continue
  echo "=== 入站端口 $p（$n 条 ESTABLISHED）==="
  ss -tn state established "sport = :$p" 2>/dev/null | tail -n +2 \
    | awk '{print $4}' | sed -E 's/:[0-9]+$//' | sort | uniq -c | sort -rn | head -12
done

echo "=== conntrack 源 IP Top 10 ==="
conntrack -L 2>/dev/null | grep -oE 'src=[0-9.]+' | sort | uniq -c | sort -rn | head -10

echo "=== SSH 成功登录（最近 15 条）==="
last -15 -i 2>/dev/null | head -16

echo "=== SSH 失败登录（最近 15 条）==="
lastb -15 -i 2>/dev/null | head -16

echo "=== fail2ban sshd ==="
fail2ban-client status sshd 2>/dev/null | head -8
