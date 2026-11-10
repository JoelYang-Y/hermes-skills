#!/usr/bin/env python3
"""Surge 路由抽样：并发打一批域名经 6152，回读 /v1/requests/recent 对账 policyName+rule。

用法：
  SURGE_KEY='...' python3 route_sample.py                  # 内置分类清单（约 50 域名）
  SURGE_KEY='...' python3 route_sample.py --domains a.com,b.com
  SURGE_KEY='...' python3 route_sample.py --file /tmp/domains.txt
  SURGE_KEY='...' python3 route_sample.py --proxy 127.0.0.1:6152 --api 127.0.0.1:6171

输出：三张表 ——(1) 路由对照 (2) FINAL 命中明细 (3) 国内域名非 DIRECT 告警。
局限：/v1/requests/recent 只保留最近约 200 条，并发量不要超；跑完会顺带把未收录域名
探一次以确认 FINAL 兜底落点（--no-final-probe 可关）。
"""
import argparse, json, os, subprocess, sys, time, urllib.request
import concurrent.futures as cf

DEFAULT_DOMAINS = {
    "美国金融": ["paypal.com", "api.paypal.com", "capitalone.com", "chase.com", "sofi.com",
                 "ibkr.com", "tello.com", "t-mobile.com", "venmo.com", "wise.com"],
    "AI": ["chatgpt.com", "api.openai.com", "claude.ai", "api.anthropic.com",
           "gemini.google.com", "huggingface.co", "hf.co", "openrouter.ai"],
    "开发/平台": ["github.com", "api.github.com", "raw.githubusercontent.com", "apple.com",
                  "microsoft.com", "google.com", "www.youtube.com", "www.netflix.com",
                  "spotify.com", "api.telegram.org", "x.com", "nyti.ms", "www.nytimes.com"],
    "国内": ["baidu.com", "www.qq.com", "www.taobao.com", "www.bilibili.com", "www.douyin.com",
             "kwimgs.com", "mtimg.com", "api.deepseek.com", "www.aliyun.com", "www.jd.com"],
    "内网": ["adg.jhsweetheart.com", "sub.jhsweetheart.com", "dsh.jhsweetheart.com",
             "emby.jhsweetheart.com", "start.jhsweetheart.com"],
}
CN_HINTS = ("qq.com", "baidu", "taobao", "jd.com", "bilibili", "douyin", "aliyun", "weibo",
            "163.com", "csdn", "zhihu", "mi.com", "xiaomi", "kwimgs", "mtimg", "snssdk")


def api(base, key, path):
    req = urllib.request.Request(base + path, headers={"X-Key": key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def host_of(u):
    u = u or ""
    return u.split("(")[-1].rstrip(")") if "(" in u else u.rsplit(":", 1)[0]


def probe(dom, proxy, scheme="https"):
    try:
        subprocess.run(["curl", "-k", "-s", "-o", "/dev/null", "-m", "8", "-x", f"http://{proxy}",
                        f"{scheme}://{dom}/"], capture_output=True, timeout=12)
    except Exception:
        pass
    return dom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=os.environ.get("SURGE_KEY"), required=False)
    ap.add_argument("--api", default="127.0.0.1:6171")
    ap.add_argument("--proxy", default="127.0.0.1:6152")
    ap.add_argument("--domains", default=None)
    ap.add_argument("--file", default=None)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--no-final-probe", action="store_true")
    a = ap.parse_args()
    if not a.key:
        sys.exit("需要 --key 或环境变量 SURGE_KEY（取自 [General] external-controller-access / http-api）")

    if a.domains:
        groups = {"自定义": [d.strip() for d in a.domains.split(",") if d.strip()]}
    elif a.file:
        with open(a.file) as f:
            groups = {"自定义": [l.strip() for l in f if l.strip() and not l.startswith("#")]}
    else:
        groups = DEFAULT_DOMAINS

    doms = [d for v in groups.values() for d in v]
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(lambda d: probe(d, a.proxy), doms))
    if not a.no_final_probe:
        # 确认兜底落点：未收录域名
        for d in ("example.com", "nope-%d.invalid" % int(time.time())):
            probe(d, a.proxy)
    time.sleep(1.5)

    items = api(f"http://{a.api}", a.key, "/v1/requests/recent").get("requests", [])
    by_host = {}
    for it in items:
        h = host_of(it.get("URL"))
        if h and h not in by_host:
            by_host[h] = it
    print(f"probing={len(doms)} recent={len(items)} elapsed={time.time()-t0:.1f}s\n")

    print(f"{'domain':40} {'policyName':14} {'rule'}")
    print("-" * 92)
    for grp, ds in groups.items():
        print(f"## {grp}")
        for d in ds:
            it = by_host.get(d)
            if not it:
                cand = [k for k in by_host if d in k or k in d]
                it = by_host.get(cand[0]) if cand else None
            if it:
                print(f"{d:40} {str(it.get('policyName')):14} {str(it.get('rule'))[:34]}")
            else:
                print(f"{d:40} {'—':14} NO RECENT RECORD")

    finals = [i for i in items if str(i.get("rule", "")).upper() == "FINAL"]
    print(f"\n## rule=FINAL 命中 {len(finals)} 条（0 条时不要直接写\"无兜底问题\"，先看样本局限）")
    for i in finals[:15]:
        print(f"  {host_of(i.get('URL')):38} -> {i.get('policyName')}  [{i.get('sourceAddress')}]")

    bad = [i for i in items if any(c in host_of(i.get("URL")) for c in CN_HINTS)
           and i.get("policyName") != "DIRECT"]
    print(f"\n## 国内域名非 DIRECT 告警 {len(bad)} 条")
    for i in bad[:15]:
        print(f"  !! {host_of(i.get('URL')):38} {i.get('policyName')}  rule={i.get('rule')}")


if __name__ == "__main__":
    main()
