#!/usr/bin/env python3
"""NAS 侧 UDP traceroute（raw ICMP 解析），绕开 Surge TUN 看真实物理链路。

用法（Mac 上）：
  B64=$(base64 -i traceroute_nas.py)
  sshpass -p '<密码>' ssh -p 10000 -o StrictHostKeyChecking=no 18332733294@10.0.0.3 \
    "echo '$B64' | base64 -d > /tmp/tr.py; echo '<密码>' | sudo -S python3 /tmp/tr.py"

2026-08-13 实测：
  国内: 10.0.0.1(BE88U) -> 100.98.94.1(电信接入) -> 58.213.x(南京电信) -> 218.2.x(江苏电信) -> 202.97.x(骨干) -> baidu 180.101.51.73
  节点: ... -> 59.43.x(国际出口 ~138ms) -> 搬瓦工 64.64.237.34
"""
import socket
import struct
import time


def tr(dst, hops=12):
    dst_ip = socket.gethostbyname(dst)
    print(f"traceroute to {dst} ({dst_ip})")
    raw = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    raw.settimeout(1.5)
    base = 40000
    for ttl in range(1, hops + 1):
        dport = base + ttl
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
        s.bind(("", dport))
        t0 = time.time()
        s.sendto(b"X" * 32, (dst_ip, dport))
        hop = "*"
        while True:
            try:
                data, addr = raw.recvfrom(512)
            except socket.timeout:
                break
            oihl = (data[0] & 0x0F) * 4
            icmp_type = data[oihl]
            # type 3 = port unreachable(终点), type 11 = TTL exceeded(中间跳)
            if icmp_type in (3, 11) and len(data) >= oihl + 8 + 20 + 8:
                eihl = (data[oihl + 8] & 0x0F) * 4
                udp_off = oihl + 8 + eihl
                d = struct.unpack("!H", data[udp_off + 2 : udp_off + 4])[0]
                if d == dport:
                    hop = addr[0]
                    break
        s.close()
        ms = 1000 * (time.time() - t0)
        print(f"{ttl:2d}  {hop:15s}  {ms:7.1f} ms")
        if hop == dst_ip:
            break


if __name__ == "__main__":
    tr("180.101.51.73")  # baidu 真实 IP（南京电信 CDN）
    print()
    tr("64.64.237.34")  # 搬瓦工节点 joel.jhsweetheart.com
