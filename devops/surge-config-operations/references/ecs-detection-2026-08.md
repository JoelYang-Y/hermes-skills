# ECS（EDNS Client Subnet）检测实录（2026-08-12）

用户链路：Surge DoH (home.jhsweetheart.com → 10.0.0.6:443) → AdGuardHome (10.0.0.6:53) → paopaodns (5335) → 223.5.5.5 / DNSCrypt。

## 结论

**链路无 ECS 功能**，但国内 CDN 返回的 IP 仍是南京本地——靠 GeoDNS（查询来源 IP 就近）等效实现，国内场景无需改。

## 检测方法

```bash
# 对照：不带 subnet
dig +time=3 +tries=1 @10.0.0.6 www.baidu.com A
# 带不同 subnet（应返回不同 IP 才说明 ECS 生效）
dig +time=3 +tries=1 @10.0.0.6 www.baidu.com A +subnet=1.2.3.0/24      # 北京联通
dig +time=3 +tries=1 @10.0.0.6 www.baidu.com A +subnet=202.96.0.0/24    # 上海电信
dig +time=3 +tries=1 @10.0.0.6 www.baidu.com A +subnet=49.115.0.0/16    # 新疆
dig +time=3 +tries=1 @10.0.0.6 www.baidu.com A +subnet=8.8.8.0/24       # 美国
# 观察：所有返回相同 IP（180.101.51.73 / 180.101.49.44）+ 响应无 CLIENT-SUBNET 回显
```

判定：
- **无 ECS**：任意 subnet 返回完全相同的 IP + 响应不带 CLIENT-SUBNET 选项
- 有 ECS：不同 subnet 返回不同 IP（CDN 按终端位置调度）+ 响应回显 CLIENT-SUBNET

## 配置侧证据

```yaml
# /root/AdGuardHome/AdGuardHome.yaml
dns:
  edns_client_subnet:
    custom_ip: ""
    enabled: false        # ← 未启用
    use_custom: false
```

上游 223.5.5.5 也不回显 ECS 选项 → 整条链（Surge DoH → AdGuardHome → paopaodns → 223.5.5.5）都不传 ECS。

## 为什么没 ECS 也拿到南京 IP

```
180.101.51.73 | Nanjing Jiangsu | AS134756 CHINANET Nanjing Jishan IDC
180.101.49.44 | Nanjing Jiangsu | AS134756 CHINANET Nanjing Jishan IDC
AAAA 240e:e9:6002:1ac:: | 江苏电信段
```

paopaodns 出口本身是南京电信（DNSCrypt 出口 58.212.0.208 / 上游 223.5.5.5），CDN（百度）按 DNS 查询来源 IP 就近调度——**GeoDNS 基于出口 IP，不是 ECS**。效果上"返回南京附近"✅ 但机制不同。

## 若要真 ECS

- paopao 上游开 ECS（需上游支持并回显），或换支持 ECS 的 DoH
- 当前国内 CDN 场景无必要（效果已达标）；US 卡申请等场景走代理 IPv4 出口，与 ECS 无关

## 附：Surge FakeIP 观察

- 本机 `curl https://www.baidu.com` 显示 `remote_ip: 198.19.14.252` = Surge FakeIP（198.18/15 段），**不是真实 IP**——Surge 用 DNS 返回的真实 IP（南京 180.101.x.x）在底层连接，FakeIP 只是给应用的虚拟地址
- 判定真实出口时勿被 FakeIP 误导，用 `curl -6` 真实连接测试或代理出口查询
