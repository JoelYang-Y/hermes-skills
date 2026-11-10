#!/usr/bin/env python3
# =============================================================================
# Hermes 全内网与云端全链路健康体检自动化脚本
# =============================================================================

import urllib.request
import time
import ssl
import sys

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

targets = [
    ("10.0.0.1 BE88U 华硕主路由", "http://10.0.0.1", "HTTP"),
    ("10.0.0.2 Surge Web (Mac mini)", "http://10.0.0.2:6171", "HTTP"),
    ("10.0.0.3 Qdrant (Mem0 向量库)", "http://10.0.0.3:6333/collections", "HTTP"),
    ("10.0.0.3 Sub-Store (订阅转换)", "http://10.0.0.3:3002", "HTTP"),
    ("10.0.0.3 Homelable (拓扑可视化)", "http://10.0.0.3:3003", "HTTP"),
    ("10.0.0.3 Uptime Kuma (服务监控)", "http://10.0.0.3:3005", "HTTP"),
    ("10.0.0.3 Beszel Hub (探针大屏)", "http://10.0.0.3:8095", "HTTP"),
    ("10.0.0.3 Emby Server (家庭影院)", "http://10.0.0.3:8096", "HTTP"),
    ("10.0.0.4 PVE 物理机 WebUI", "https://10.0.0.4:8006", "HTTPS"),
    ("10.0.0.5 DeepSeek Harness Web", "http://10.0.0.5:3000", "HTTP"),
    ("10.0.0.6 AdGuard Home 控制台", "http://10.0.0.6:3000", "HTTP"),
    ("甲骨文导航主站 (jhsweetheart.com)", "https://jhsweetheart.com", "HTTPS"),
    ("甲骨文 Vaultwarden (oracle.jhsweetheart.com)", "https://oracle.jhsweetheart.com", "HTTPS"),
    ("搬瓦工 1Panel (joel.jhsweetheart.com/Joel)", "https://joel.jhsweetheart.com/Joel", "HTTPS")
]

print(f"{'服务目标':<42} | {'协议':<6} | {'响应耗时':<10} | {'状态'}")
print("-" * 75)

all_ok = True
for name, url, proto in targets:
    start_t = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Hermes-HealthCheck/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=4) as res:
            cost = (time.time() - start_t) * 1000
            print(f"{name:<42} | {proto:<6} | {cost:6.1f}ms   | ✅ 正常 (HTTP {res.getcode()})")
    except urllib.error.HTTPError as he:
        cost = (time.time() - start_t) * 1000
        if he.code in [301, 302, 401, 403]:
            print(f"{name:<42} | {proto:<6} | {cost:6.1f}ms   | ✅ 正常 (HTTP {he.code})")
        else:
            print(f"{name:<42} | {proto:<6} | {cost:6.1f}ms   | ⚠️ 异常 (HTTP {he.code})")
            all_ok = False
    except Exception as e:
        cost = (time.time() - start_t) * 1000
        print(f"{name:<42} | {proto:<6} | {cost:6.1f}ms   | ❌ 失败 ({e})")
        all_ok = False

sys.exit(0 if all_ok else 1)
