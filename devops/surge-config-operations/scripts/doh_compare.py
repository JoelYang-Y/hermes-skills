#!/usr/bin/env python3
"""多 DoH 上游对比探针：判定 encrypted-dns-server 并列时哪个上游先答/答错。

为什么需要它：`curl -H 'accept: application/dns-json' '.../dns-query?name=x&type=A'` 会被
AdGuardHome 回 `Bad Request`、被 AliDNS 回 `no 'dns' query parameter found`——GET+JSON 形式
不可靠。必须 POST application/dns-message（wire format）才是两边都认的路径。

用法：
  python3 doh_compare.py --upstreams https://adg.example.com/dns-query,https://dns.alidns.com/dns-query
  python3 doh_compare.py --domains www.baidu.com,kr.kwimgs.com,github.com

判读：同一域名若内网 DoH 返回 ancount>0/rcode=0 而上游公网 DoH 返回 rcode=3(NXDOMAIN) 或
ancount=0，则多 DoH 并列会让负面应答抢先生效 —— 对应日志里的 `Empty DNS answer` 或偶发解析失败。
"""
import argparse, ssl, struct, sys, urllib.request


def build_query(name, qtype=1, tid=b"\xab\xcd"):
    qs = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    return tid + b"\x01\x00" + b"\x00\x01\x00\x00\x00\x00\x00\x00" + qs + struct.pack(">HH", qtype, 1)


def ask(url, name, qtype=1, insecure=True):
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url, data=build_query(name, qtype),
        headers={"content-type": "application/dns-message", "accept": "application/dns-message"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            body = r.read()
            ancount = struct.unpack(">H", body[6:8])[0]
            rcode = body[3] & 0x0F
            return {"ok": True, "ancount": ancount, "rcode": rcode, "bytes": len(body)}
    except Exception as e:
        return {"ok": False, "err": f"{type(e).__name__}: {e}"}


RC = {0: "NOERROR", 2: "SERVFAIL", 3: "NXDOMAIN", 5: "REFUSED"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstreams", default="https://adg.jhsweetheart.com/dns-query,https://dns.alidns.com/dns-query")
    ap.add_argument("--domains", default="www.baidu.com,github.com,kr.kwimgs.com,speedv6.m.jd.com")
    ap.add_argument("--strict-tls", action="store_true", help="校验证书（内网自签时不要开）")
    a = ap.parse_args()

    ups = [u.strip() for u in a.upstreams.split(",") if u.strip()]
    doms = [d.strip() for d in a.domains.split(",") if d.strip()]
    print(f"{'upstream':46} {'domain':26} result")
    print("-" * 100)
    bad = 0
    for d in doms:
        for u in ups:
            r = ask(u, d, insecure=not a.strict_tls)
            if r["ok"]:
                tag = RC.get(r["rcode"], str(r["rcode"]))
                flag = "" if (r["rcode"] == 0 and r["ancount"] > 0) else "  <-- 负面/空应答"
                if flag:
                    bad += 1
                print(f"{u:46} {d:26} ancount={r['ancount']:<3} rcode={r['rcode']}({tag}){flag}")
            else:
                print(f"{u:46} {d:26} ERR {r['err']}")
    print(f"\n负面/空应答 {bad} 条。若内网 DoH 正常而上游公网 DoH 出负面应答，说明多 DoH 并列会被它抢答。")


if __name__ == "__main__":
    main()
