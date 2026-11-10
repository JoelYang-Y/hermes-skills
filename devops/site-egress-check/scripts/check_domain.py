#!/usr/bin/env python3
"""
check_domain.py — Surge 域名出口 IP 检测工具 (v3)

原理 (三步):
  1. 通过 Surge 代理发起 HTTPS 请求 (带 TLS SNI, 让规则引擎按域名精确匹配)
  2. 查询 Surge /v1/requests/recent, 找到该域名的连接记录, 读取:
       - rule: 命中的规则 (DOMAIN-SUFFIX / DOMAIN-KEYWORD / RULE-SET / FINAL 等)
       - policyName: 实际路由策略
       - notes: 完整决策链 (Policy decision path: 组 -> 最终节点)
  3. 用 X-Surge-Policy 强制走该策略访问 ip-api.com, 拿真实出口 IP/国家/ASN

v3 改进 (2026-08-12):
  - 规则类型识别: DOMAIN-SUFFIX (精确后缀) / DOMAIN-KEYWORD (关键词, 覆盖广)
  - 命中 DOMAIN-KEYWORD 时提示: 该关键词覆盖范围广, 服务的 IP 段流量可能
    走其他更精确的规则 (如 Telegram.list -> Telegram 组), App 与域名可能不同路
  - 支持输入纯关键词 (如 telegram) 也能匹配 recent 记录
  - 显示所有相关规则类型, 不只最新一条
"""
import os
import urllib.request
import json
import time
import sys
import ssl
import re

# Surge 代理与 API 配置
PROXY = 'http://127.0.0.1:6152'
API_URL = 'http://127.0.0.1:6171/v1/requests/recent'
API_KEY = os.environ.get('SURGE_API_KEY', '')  # 从环境变量取，不入库


def make_opener():
    """创建走 Surge 代理的 opener (忽略证书错误)"""
    proxy_handler = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ctx))


def parse_decision_path(notes):
    """从 notes 提取策略决策链, 如 'Policy decision path: 节点选择 -> AnyTLS-AT&T'"""
    for n in notes:
        m = re.search(r'Policy decision path:\s*(.+)', n)
        if m:
            return m.group(1).strip()
    return None


def parse_subrule(notes):
    """从 notes 提取子规则, 如 'Sub-rule matched: DOMAIN-KEYWORD telegram(in Proxy.list)'"""
    for n in notes:
        m = re.search(r'Sub-rule matched:\s*(.+)', n)
        if m:
            return m.group(1).strip()
    return None


def classify_rule(rule_str, sub_rule_str):
    """识别规则类型: DOMAIN-SUFFIX / DOMAIN-KEYWORD / DOMAIN / RULE-SET / IP-CIDR / FINAL"""
    text = f"{rule_str} {sub_rule_str}".upper()
    # 子规则以 . 开头 (如 .pornhub.com) = DOMAIN-SUFFIX; 以 ~ 开头 = DOMAIN-KEYWORD (Surge 语法)
    sub = (sub_rule_str or '').strip()
    if sub.startswith('.'):
        return 'DOMAIN-SUFFIX'
    if sub.startswith('~'):
        return 'DOMAIN-KEYWORD'
    if 'DOMAIN-SUFFIX' in text:
        return 'DOMAIN-SUFFIX'
    if 'DOMAIN-KEYWORD' in text:
        return 'DOMAIN-KEYWORD'
    if 'DOMAIN,' in text or text.startswith('DOMAIN '):
        return 'DOMAIN'
    if 'IP-CIDR' in text:
        return 'IP-CIDR'
    if 'RULE-SET' in text:
        return 'RULE-SET'
    if 'FINAL' in text:
        return 'FINAL'
    return 'OTHER'


def is_ip_input(s):
    """判断输入是否为 IP 段/IP 地址: 纯数字+点(/ 可选)"""
    s = s.strip()
    if not s:
        return False
    base = s.split('/')[0]
    if not base:
        return False
    return all(c.isdigit() or c == '.' for c in base) and '.' in base


def ip_in_cidr(ip_str, cidr_str):
    """判断 IP 是否在 CIDR 网段内 (用 ipaddress 库精确计算)"""
    try:
        import ipaddress
        ip = ipaddress.ip_address(ip_str.strip())
        net = ipaddress.ip_network(cidr_str.strip(), strict=False)
        return ip in net
    except Exception:
        return False


def static_rule_match_ip(ip_input):
    """读 Surge /v1/rules 静态匹配 IP/CIDR 规则, 返回 (rule, policy) 或 None.
    不依赖 recent 历史流量, 直接按规则引擎逐条匹配.
    支持: 完整 IP (129.146.3.78) / CIDR (129.146.3.78/32, 10.0.0.0/24)
    """
    import ipaddress as _ipa
    # 解析输入: 完整 IP 或 CIDR 网段
    is_full_ip = False
    full_ip_val = None
    cidr_input = None
    try:
        full_ip_val = _ipa.ip_address(ip_input.split('/')[0])
        is_full_ip = True
    except Exception:
        pass
    try:
        cidr_input = _ipa.ip_network(ip_input, strict=False)
    except Exception:
        pass

    try:
        req = urllib.request.Request('http://127.0.0.1:6171/v1/rules', headers={"X-Key": API_KEY})
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None

    for rule_str in data.get('rules', []):
        parts = [p.strip() for p in rule_str.split(',')]
        if not parts:
            continue
        rule_type = parts[0].upper()

        # 1) 直接 IP-CIDR 规则
        if rule_type in ('IP-CIDR', 'IP-CIDR6'):
            if len(parts) < 3:
                continue
            cidr_str = parts[1]
            policy = parts[2]
            try:
                net = _ipa.ip_network(cidr_str, strict=False)
            except Exception:
                continue
            if is_full_ip:
                if full_ip_val in net:
                    return (f'IP-CIDR {cidr_str}', policy)
            elif cidr_input is not None:
                if net.overlaps(cidr_input):
                    return (f'IP-CIDR {cidr_str}', policy)
            continue

        # 2) RULE-SET 远程 list: 拉取文件匹配 IP-CIDR 子规则
        if rule_type == 'RULE-SET' and len(parts) >= 3:
            list_url = parts[1]
            policy = parts[2]
            try:
                req_list = urllib.request.Request(list_url, headers={'User-Agent': 'Mozilla/5.0'})
                resp_list = urllib.request.urlopen(req_list, timeout=8)
                list_content = resp_list.read().decode('utf-8', errors='ignore')
            except Exception:
                continue
            for line in list_content.splitlines():
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('//'):
                    continue
                lparts = [p.strip() for p in line.split(',')]
                if not lparts or lparts[0].upper() not in ('IP-CIDR', 'IP-CIDR6'):
                    continue
                if len(lparts) < 2:
                    continue
                cidr_str = lparts[1]
                try:
                    net = _ipa.ip_network(cidr_str, strict=False)
                except Exception:
                    continue
                if is_full_ip:
                    if full_ip_val in net:
                        list_name = list_url.rstrip('/').split('/')[-1]
                        return (f'IP-CIDR {cidr_str}(in {list_name})', policy)
                elif cidr_input is not None:
                    if net.overlaps(cidr_input):
                        list_name = list_url.rstrip('/').split('/')[-1]
                        return (f'IP-CIDR {cidr_str}(in {list_name})', policy)
    return None


def probe_ip_egress(opener, policy_label):
    """强制走指定策略探测出口 IP, 返回 (ip, country, region, isp, asn) 或 None.
    DIRECT 时用无代理直连查询 (多源 fallback)
    """
    try:
        if policy_label == 'DIRECT' or 'DEVICE:' in str(policy_label):
            # 直连: 显式禁用代理 (urllib 默认读环境变量代理, 必须用 ProxyHandler({}) 覆盖)
            no_proxy = urllib.request.ProxyHandler({})
            direct_opener = urllib.request.build_opener(no_proxy)
            direct_ip = None
            # 按顺序尝试多个直连 IP API, 直到拿到 IP
            # ⚠️ TUN 增强模式下任何 HTTP 连接都会进 Surge TUN 被规则二次匹配,
            #    所以直连探测必须优先用国内回显站 (China.list → DIRECT);
            #    国外站 (ip.sb/ipify/ifconfig/cip.cc) 命中 Proxy.list → 节点选择,
            #    会显示代理出口 IP (2026-08-13 实测: 假直连 107.141.151.219)
            for api in ('http://myip.ipip.net', 'https://ip.sb', 'https://api.ipify.org',
                        'https://ifconfig.me/ip', 'https://ipinfo.io/ip', 'http://cip.cc'):
                try:
                    resp_d = direct_opener.open(api, timeout=4)
                    raw = resp_d.read().decode('utf-8', errors='ignore').strip()
                    # 从响应中提取 IPv4 (cip.cc 等返回带文本的响应)
                    import re as _re
                    m = _re.search(r'\b(\d{1,3}(?:\.\d{1,3}){3})\b', raw)
                    if m:
                        direct_ip = m.group(1)
                        break
                except Exception:
                    continue
            if direct_ip:
                # 用 ip-api.com 查详情 (直连)
                try:
                    resp_info = direct_opener.open(f"http://ip-api.com/json/{direct_ip}", timeout=5)
                    d = json.loads(resp_info.read().decode('utf-8'))
                    if d.get('status') == 'success':
                        asn_raw = d.get('as', '')
                        asn_num = asn_raw.split()[0] if asn_raw else ''
                        asn_org = ' '.join(asn_raw.split()[1:]) if asn_raw else ''
                        return (d.get('query', ''), d.get('country', ''), d.get('countryCode', ''),
                                d.get('regionName', ''), d.get('city', ''), d.get('isp', ''), asn_num, asn_org)
                except Exception:
                    pass
                return (direct_ip, '', '', '', '', '', '', '')
        # 代理策略: 用 X-Surge-Policy 强制走指定策略
        req_ip = urllib.request.Request("http://ip-api.com/json/")
        # 中文策略名 (如 节点选择) 需用 utf-8→latin-1 技巧编码, 否则 urllib latin-1 报错
        if any(ord(c) > 127 for c in str(policy_label)):
            policy_header = str(policy_label).encode('utf-8').decode('latin-1')
        else:
            policy_header = str(policy_label)
        req_ip.add_header("X-Surge-Policy", policy_header)
        resp_ip = opener.open(req_ip, timeout=5)
        d = json.loads(resp_ip.read().decode('utf-8'))
        if d.get('status') == 'success':
            asn_raw = d.get('as', '')
            asn_num = asn_raw.split()[0] if asn_raw else ''
            asn_org = ' '.join(asn_raw.split()[1:]) if asn_raw else ''
            return (d.get('query', ''), d.get('country', ''), d.get('countryCode', ''),
                    d.get('regionName', ''), d.get('city', ''), d.get('isp', ''), asn_num, asn_org)
    except Exception:
        pass
    return None


def check_domain_exit_ip(domain):
    opener = make_opener()

    # 判断输入类型: 完整域名 / 纯关键词 / IP 段
    is_ip = is_ip_input(domain)
    is_keyword = ('.' not in domain) and not is_ip
    probe_target = domain if (not is_keyword and not is_ip) else None

    if is_ip:
        print(f"\n🔍 [1/3] 检测到 IP 段输入: {domain}, 将直接匹配 Surge 的 IP-CIDR 规则...")
    else:
        print(f"\n🔍 [1/3] 正在通过 Surge 发起 {domain} 的 HTTPS 请求 (携带 SNI)...")
    try:
        # 用 HTTPS (带 TLS SNI) 触发规则引擎, 2 秒超时, 成败无关
        if probe_target:
            req = urllib.request.Request(f"https://{probe_target}", method='HEAD')
            opener.open(req, timeout=2)
        elif is_keyword:
            # 纯关键词: 自动补全常见 TLD 发请求, 提高规则命中率
            for tld in ('.com', '.org', '.net', '.io'):
                try:
                    req = urllib.request.Request(f"https://{domain}{tld}", method='HEAD')
                    opener.open(req, timeout=2)
                except Exception:
                    pass
    except Exception:
        pass

    time.sleep(0.5)  # 等 Surge 记账

    print(f"📊 [2/3] 正在查询 Surge 引擎, 获取命中策略...")
    try:
        req_api = urllib.request.Request(API_URL, headers={"X-Key": API_KEY})
        resp = urllib.request.urlopen(req_api, timeout=3)
        data = json.loads(resp.read().decode('utf-8'))

        # 收集所有匹配的记录 (含 URL / notes 里的域名 / SNI / IP-CIDR)
        candidates = []
        if is_ip:
            # IP 输入: 只匹配 IP-CIDR 规则, 用精确 CIDR 计算
            # 判断输入是否完整 IP 或 CIDR 网段 (如 10.0.0.3 / 10.0.0.0/24)
            import ipaddress as _ipa
            is_full_ip = False
            is_cidr_net = False
            full_ip_val = None
            try:
                full_ip_val = _ipa.ip_address(domain.split('/')[0])
                is_full_ip = True
            except Exception:
                pass
            try:
                _net = _ipa.ip_network(domain, strict=False)
                is_cidr_net = True
            except Exception:
                pass

            for r in data.get('requests', []):
                url = r.get('URL', '') or ''
                notes = r.get('notes', []) or []
                blob = f"{url} {' '.join(notes)}"
                if 'IP-CIDR' not in blob:
                    continue
                # 提取记录里的 IP-CIDR 网段 (如 172.16.0.0/12)
                for n in notes:
                    m = re.search(r'IP-CIDR\s*([0-9a-fA-F.:/]+)', n)
                    if not m:
                        continue
                    cidr_str = m.group(1).strip()
                    # 匹配条件:
                    #  - 完整 IP 输入: 用精确 CIDR 判断 (ip in network)
                    #  - CIDR 网段输入: 网段相等
                    #  - 部分 IP 段 (如 10.0.0): 前缀子串匹配 (提示可能不准)
                    if is_full_ip:
                        if ip_in_cidr(str(full_ip_val), cidr_str):
                            candidates.append(r)
                            break
                    elif is_cidr_net:
                        if domain.strip() == cidr_str:
                            candidates.append(r)
                            break
                    else:
                        if domain.lower() in blob.lower():
                            candidates.append(r)
                            break
            if not is_full_ip and not is_cidr_net and not candidates:
                print(f"   💡 提示: '{domain}' 是不完整 IP 段, 请尝试完整 IP (如 {domain}.0.3) 或 CIDR (如 {domain}.0.0/24)。")
        else:
            for r in data.get('requests', []):
                url = r.get('URL', '') or ''
                notes = r.get('notes', []) or []
                blob = f"{url} {' '.join(notes)}"
                if domain.lower() in blob.lower():
                    candidates.append(r)

        if not candidates:
            # IP 输入且 recent 无记录: 尝试静态规则匹配 (/v1/rules 不依赖历史流量)
            if is_ip:
                static_hit = static_rule_match_ip(domain)
                if static_hit:
                    static_rule, static_policy = static_hit
                    matched_rule = static_rule
                    matched_policy = static_policy
                    decision_path = None
                    sub_rule = static_rule
                    matched_ipcidr = static_rule
                    rule_type = 'IP-CIDR'
                    rule_types = {'IP-CIDR'}
                    print(f"🎯 命中规则: [{static_rule}]")
                    print(f"🛤️ 路由策略: [{static_policy}]")
                    print(f"📋 规则类型: IP-CIDR (静态规则匹配)")
                    print("   ✅ 命中【IP-CIDR 规则】(静态匹配, 无需历史流量)")
                    probe_policy = static_policy
                    group_name = None
                    main_result = probe_ip_egress(opener, probe_policy)
                    print("\n================ 最终检测结果 ================")
                    print(f"🌐 IP/网段: {domain}")
                    print(f"🛤️ 命中策略: {probe_policy}")
                    if main_result:
                        ip, country, cc, region, city, isp, asn_num, asn_org = main_result
                        print(f"🖥️ 出口:     {ip}")
                        if probe_policy == 'DIRECT' or 'DEVICE:' in str(probe_policy):
                            print(f"   ⚠️ Surge TUN 接管中, 此出口可能非真直连 (受 Surge 全局路由影响)")
                        print(f"   📍 {country} ({cc}) {region} {city} | {isp} | ASN {asn_num} {asn_org}".rstrip())
                    else:
                        print("   ❌ 策略探测失败")
                    print("==============================================")
                    return
            # IP 输入: 静态规则未命中 IP-CIDR, 但可能走 FINAL 兜底
            if is_ip:
                try:
                    req2 = urllib.request.Request('http://127.0.0.1:6171/v1/rules', headers={"X-Key": API_KEY})
                    resp2 = urllib.request.urlopen(req2, timeout=3)
                    data2 = json.loads(resp2.read().decode('utf-8'))
                    # FINAL 规则: 最后一条形如 "FINAL,<policy>,dns-failed" 或 "FINAL,<policy>"
                    final_policy = None
                    for rule_str in data2.get('rules', []):
                        parts = [p.strip() for p in rule_str.split(',')]
                        if parts and parts[0].upper() == 'FINAL' and len(parts) >= 2:
                            final_policy = parts[1]
                            break
                    if final_policy:
                        print(f"🎯 命中规则: [FINAL] (该 IP 无专门 IP-CIDR 规则, 走兜底)")
                        print(f"🛤️ 路由策略: [{final_policy}]")
                        print(f"📋 规则类型: FINAL (静态规则匹配)")
                        main_result = probe_ip_egress(opener, final_policy)
                        print("\n================ 最终检测结果 ================")
                        print(f"🌐 IP/网段: {domain}")
                        print(f"🛤️ 命中策略: {final_policy}")
                        if main_result:
                            ip, country, cc, region, city, isp, asn_num, asn_org = main_result
                            print(f"🖥️ 出口:     {ip}")
                            if final_policy == 'DIRECT' or 'DEVICE:' in str(final_policy):
                                print(f"   ⚠️ Surge TUN 接管中, 此出口可能非真直连 (受 Surge 全局路由影响)")
                            print(f"   📍 {country} ({cc}) {region} {city} | {isp} | ASN {asn_num} {asn_org}".rstrip())
                        else:
                            print("   ❌ 策略探测失败")
                        print("==============================================")
                        return
                except Exception:
                    pass
            if is_keyword:
                print("   💡 提示: 输入的是关键词而非完整域名, 可尝试输入完整域名 (如 telegram.org)。")
            if is_ip:
                print("   💡 提示: 该 IP 段可能在 recent 记录中没有命中记录 (服务未活动/窗口已过)。")
            return

        # 取最新一条做主结果, 同时统计所有出现的规则类型
        # 优先级: IP-CIDR (IP输入) > DOMAIN-SUFFIX 精确后缀 > 完整域名子规则 > 最新记录
        r = candidates[0]
        if is_ip:
            ipcidr_cands = []
            for c in candidates:
                c_notes = ' '.join(c.get('notes', []) or [])
                c_sub = parse_subrule(c.get('notes', []) or []) or ''
                c_rule = c.get('rule', '')
                if classify_rule(c_rule, c_sub) == 'IP-CIDR' or 'IP-CIDR' in c_notes:
                    ipcidr_cands.append(c)
            if ipcidr_cands:
                r = ipcidr_cands[0]
        else:
            # 非 IP 输入: 优先选规则更精确的记录
            def rule_priority(c):
                """返回优先级分数, 越低越优先"""
                c_notes = ' '.join(c.get('notes', []) or [])
                c_sub = parse_subrule(c.get('notes', []) or []) or ''
                c_rule = c.get('rule', '')
                ct = classify_rule(c_rule, c_sub)
                score = 10  # 默认 (最新记录)
                if ct == 'DOMAIN-SUFFIX':
                    score = 0     # 精确后缀最优
                elif ct == 'DOMAIN':
                    score = 1
                elif 'RULE-SET' in c_notes:
                    score = 2     # 规则集 (子规则可能含完整域名)
                elif ct == 'IP-CIDR':
                    score = 3
                elif ct == 'FINAL':
                    score = 9
                elif ct == 'DOMAIN-KEYWORD':
                    score = 6     # 关键词覆盖广, 优先级低
                return score

            candidates.sort(key=lambda c: (rule_priority(c), -c.get('id', 0)))
            r = candidates[0]
        matched_policy = r.get('policyName') or r.get('originalPolicyName')
        matched_rule = r.get('rule', 'N/A')
        notes = r.get('notes', []) or []
        decision_path = parse_decision_path(notes)
        sub_rule = parse_subrule(notes)

        # 提取命中的 IP-CIDR 规则 (如 "IP-CIDR 149.154.160.0/20")
        matched_ipcidr = None
        for n in notes:
            m = re.search(r'(IP-CIDR[0-9a-zA-Z.:/]+(?:\(in [^)]+\))?)', n)
            if m:
                matched_ipcidr = m.group(1)
                break

        # 统计所有候选记录里出现的规则类型
        rule_types = set()
        for c in candidates:
            c_rule = c.get('rule', '')
            c_notes = ' '.join(c.get('notes', []) or [])
            c_sub = parse_subrule(c.get('notes', []) or []) or ''
            rule_types.add(classify_rule(c_rule, c_sub))

        rule_type = classify_rule(matched_rule, sub_rule or '')

        print(f"🎯 命中规则: [{matched_rule}]")
        if sub_rule:
            print(f"🔎 子规则:   [{sub_rule}]")
        if matched_ipcidr:
            print(f"🌐 IP-CIDR:  [{matched_ipcidr}]")
        print(f"🛤️ 路由策略: [{matched_policy}]")
        if decision_path:
            print(f"🔗 决策链:   {decision_path}")
        print(f"📋 规则类型: {rule_type} (相关: {', '.join(sorted(rule_types)) if rule_types else rule_type})")

        # IP-CIDR 命中提示
        if rule_type == 'IP-CIDR' or matched_ipcidr:
            print("   ✅ 命中【IP-CIDR 规则】, 该 IP 段流量走精确路由。")

        # DOMAIN-SUFFIX 精确提示
        if rule_type == 'DOMAIN-SUFFIX':
            print("   ✅ 命中【后缀规则】(DOMAIN-SUFFIX), 精确匹配, 结果可靠。")

        # FINAL 兜底提示
        if rule_type == 'FINAL':
            print("   ⚠️ 命中【兜底规则】(FINAL), 该域名没有专门规则, 走默认策略。")

        # 已知服务的策略组映射: 关键词 -> 策略组名 (用于探测 App/IP 段实际出口)
        GROUP_HINTS = {
            'telegram': 'Telegram',
            'whatsapp': 'Telegram',   # WhatsApp 也常归入 Telegram 组 (Meta 类目)
            'youtube': 'Google',
            'google': 'Google',
            'netflix': 'Netflix',
            'disney': 'Disney',
            'tiktok': 'TikTok',
            'chatgpt': 'OpenAI',
            'openai': 'OpenAI',
            'paypal': 'PayPal',
        }
        group_name = None
        for kw, grp in GROUP_HINTS.items():
            if kw in domain.lower():
                group_name = grp
                break

        if group_name:
            print(f"   💡 检测到 {domain} 可能对应策略组 [{group_name}], 将额外探测该组的实际出口...")

    except Exception as e:
        print(f"❌ 无法连接 Surge API, 请检查密码或端口配置 ({e})")
        return

    print(f"🚀 [3/3] 正在探测策略 [{matched_policy}] 的真实出口 IP...")
    try:
        # 用最终实际策略 (决策链末段) 强制探测; 若策略是组名, 取决策链最后节点
        probe_policy = matched_policy
        if decision_path and '->' in decision_path:
            last_node = decision_path.split('->')[-1].strip()
            if last_node:
                probe_policy = last_node

        # 1) 探测域名实际命中策略
        main_result = probe_ip_egress(opener, probe_policy)

        # 2) 若有对应策略组, 额外探测组的实际出口 (App/IP 段路径)
        group_result = None
        if group_name and group_name != probe_policy:
            group_result = probe_ip_egress(opener, group_name)

        print("\n================ 最终检测结果 ================")
        print(f"🌐 域名: {domain}")
        print(f"🛤️ 域名命中策略: {probe_policy}")
        if decision_path:
            print(f"🔗 决策链:   {decision_path}")
        if main_result:
            ip, country, cc, region, city, isp, asn_num, asn_org = main_result
            print(f"🖥️ 域名出口:  {ip}")
            if probe_policy == 'DIRECT' or 'DEVICE:' in str(probe_policy):
                print(f"   ⚠️ Surge TUN 接管中, 此出口可能非真直连 (受 Surge 全局路由影响)")
            print(f"   📍 {country} ({cc}) {region} {city} | {isp} | ASN {asn_num} {asn_org}".rstrip())
        else:
            print("   ❌ 域名策略探测失败")

        if group_result:
            ip, country, cc, region, city, isp, asn_num, asn_org = group_result
            print(f"\n🛤️ 策略组 [{group_name}] (App/IP 段路径):")
            print(f"🖥️ 组出口:    {ip}")
            print(f"   📍 {country} ({cc}) {region} {city} | {isp} | ASN {asn_num} {asn_org}".rstrip())
        print("==============================================")

    except Exception as e:
        print(f"❌ 测速 IP 失败: {e}")


if __name__ == "__main__":
    print("==============================================")
    print("          Surge 域名出口 IP 检测工具          ")
    print("==============================================")
    try:
        while True:
            domain = input("\n👉 请输入要检测的域名或关键词 (如 www.youtube.com / telegram, 输入 q 退出): ").strip()
            if not domain:
                continue
            if domain.lower() in ['q', 'quit', 'exit']:
                print("👋 退出工具。")
                break

            # 自动处理用户可能带上的 http:// 头部或路径
            if domain.startswith("http://"):
                domain = domain[7:]
            elif domain.startswith("https://"):
                domain = domain[8:]
            # 非 IP 输入才截断路径 (IP/CIDR 如 127.0.0.0/8 不能截断)
            if not is_ip_input(domain):
                domain = domain.split('/')[0]

            check_domain_exit_ip(domain)
    except KeyboardInterrupt:
        print("\n👋 退出工具。")
