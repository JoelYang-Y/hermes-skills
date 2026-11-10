#!/usr/bin/env python3
"""STUN 反射测试 — 验证本机 WebRTC/UDP 流量是否被 Surge 代理。

原理: 浏览器 WebRTC 泄露测试 (browserleaks.com/webrtc) 通过向 STUN 服务器发
UDP Binding 请求反射公网 IP。本脚本做完全相同的事 (只读 UDP, 不发数据), 从
命令行判断本机 UDP 出口:
  - 反射 IP = 当前代理出口 (如 107.141.151.219 AT&T) => WebRTC 无泄露
  - 反射 IP = 真实家宽 (如 49.65.142.146 南京电信) => 泄露, UDP 没走代理
  - 无响应 => 该 STUN 路径被 REJECT (udp-policy-not-supported-behaviour)

用法: python3 stun_egress_test.py
2026-08-13 实测: TUN 增强模式下 5 个主流 STUN 服务器全部反射代理出口 IP。
"""
import socket, struct, random, time


def stun_binding(server, port=19302, timeout=5):
    """发送 STUN Binding 请求, 返回 (反射IP, 反射端口, rtt_ms)。"""
    txid = random.randbytes(12)
    # Binding Request 头: type=0x0001, len=0, magic cookie 0x2112A442, txid
    header = struct.pack('!HHI', 0x0001, 0, 0x2112A442) + txid
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    t0 = time.time()
    try:
        s.sendto(header, (server, port))
        data, _ = s.recvfrom(2048)
    except Exception:
        return None, None, None
    finally:
        s.close()
    rtt = (time.time() - t0) * 1000
    if len(data) < 20:
        return None, None, rtt
    # 解析属性: XOR-MAPPED-ADDRESS (0x0020)
    i = 20
    mapped = None
    while i + 4 <= len(data):
        atype, alen = struct.unpack('!HH', data[i:i + 4])
        aval = data[i + 4:i + 4 + alen]
        if atype == 0x0020 and alen >= 8:
            family = aval[1]
            port_xor = struct.unpack('!H', aval[2:4])[0]
            if family == 0x01:  # IPv4
                addr_xor = struct.unpack('!I', aval[4:8])[0]
                port = port_xor ^ (0x2112A442 >> 16)
                addr = socket.inet_ntoa(struct.pack('!I', addr_xor ^ 0x2112A442))
                mapped = (addr, port)
        i += 4 + (alen + 3) // 4 * 4
    return (mapped[0] if mapped else None), (mapped[1] if mapped else None), rtt


SERVERS = [
    ('stun.l.google.com', 19302),
    ('stun1.l.google.com', 19302),
    ('stun.cloudflare.com', 3478),
    ('global.stun.twilio.com', 3478),
    ('stun.stunprotocol.org', 3478),
]

if __name__ == '__main__':
    print("=== WebRTC 同款 STUN 反射测试（本机 UDP 出口） ===")
    for srv, prt in SERVERS:
        ip, mport, rtt = stun_binding(srv, prt)
        if ip:
            print(f"{srv}:{prt} → {ip}:{mport} (rtt {rtt:.0f}ms)")
        else:
            rtt_txt = f'{rtt:.0f}ms' if rtt is not None else '超时'
            print(f"{srv}:{prt} → 无响应/被拒 ({rtt_txt})")
