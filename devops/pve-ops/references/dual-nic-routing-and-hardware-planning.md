# PVE 双网卡策略路由与算力节点架构规划指南

## 一、 双网卡架构：独立公网拨号 + 局域网高速互通（防冲突规范）

在一台 PVE 物理宿主机或其虚拟容器中实现「PPPoE 独立公网拨号」与「10.0.0.0/24 局域网互通」时，必须严格遵守以下网络规则：

### 1. 规避默认网关争抢 (Gateway Collision)
- **核心原则**：全局系统只能由 PPPoE 拨号接口 (`ppp0`) 持有默认网关 (`0.0.0.0/0`)。
- **LAN 网卡 (`eth0` / `vmbr0`) 配置**：仅指定 IP 和掩码（如 `10.0.0.7/24`），**绝对禁止在 LAN 接口配置 `gateway 10.0.0.1`**。
- **直连路由生效**：系统自动将目的地址为 `10.0.0.0/24` 的流量走 `eth0`，其余全部外网流量默认走 `ppp0`。

### 2. 策略路由（PBR）：强制“源进源出”，防止非对称回包
- **隐患**：当局域网设备通过 `eth0` 连接服务器时，若无策略路由，系统回包可能走默认路由 `ppp0`，导致 TCP 握手中断。
- **解决步骤**：
  1. 在 `/etc/iproute2/rt_tables` 添加专属路由表：
     ```bash
     100 lan_traffic
     ```
  2. 在网络配置 (`post-up`) 中注入策略路由规则：
     ```bash
     ip route add 10.0.0.0/24 dev eth0 src 10.0.0.7 table lan_traffic
     ip route add default via 10.0.0.1 dev eth0 table lan_traffic
     ip rule add from 10.0.0.7 table lan_traffic
     ```
  3. 放宽内核反向路径过滤 (`/etc/sysctl.conf`)：
     ```ini
     net.ipv4.conf.all.rp_filter = 2
     net.ipv4.conf.default.rp_filter = 2
     net.ipv4.conf.eth0.rp_filter = 2
     ```
     执行 `sysctl -p` 生效。

### 3. DNS 保护：防止 PPPoE 覆盖内网 DNS
- **隐患**：PPPoE 拨号默认通过 IPCP 拉取运营商 DNS，冲掉 `/etc/resolv.conf`，导致内网域名（如 AdGuardHome 10.0.0.6）解析失效。
- **对策**：在 PPPoE 配置文件中注释或关闭 `usepeerdns`，全局 DNS 锁定为内网 AdGuardHome (`10.0.0.6`)。

---

## 二、 Homelab 算力节点架构与 CPU 选型决策矩阵

### 1. 架构定位核心结论
- **全大核（All-P-Cores）优先**：PVE 虚拟化最忌讳大小核（Big.LITTLE / P+E）异构调度。全同构核心无需 CPU Pinning，VM/LXC 调度时延零抖动。
- **AVX-512 原生支持**：本地向量模型（Embedding `bge-m3` / Reranker）与 Qdrant 检索依赖 CPU 向量加速，原生 AVX-512 吞吐远高于普通 AVX2。
- **内存双通道铁律**：CPU 向量推理与 AVX 吞吐高度受限于内存带宽，必须配置双通道 DDR5。

### 2. 主流处理器在 PVE 算力底座下的对比

| 处理器型号 | 核心/线程 | AVX-512 | PVE 虚拟化适用度 | 场景定位与推荐等级 |
|:---|:---:|:---:|:---|:---|
| **Intel N100** | 4C / 4T (纯小核) | 无 | 适合轻量旁路 (DNS / 单微服务) | 当前主力，面临算力/内存上限瓶颈 |
| **AMD Ryzen 9 7945HX** | 16C / 32T (全大核) | 有 | **极佳（全同构+64MB大缓存）** | **算力中枢最优性价比之选（首选）** |
| **AMD Ryzen 7 8845HS/8945HS** | 8C / 16T (全大核) | 有 | 良好 (单片低功耗，780M核显) | 适合极致省电/静音，但核心较紧凑 |
| **Intel Core Ultra 5 235HX** | 6P+8E / 14T (无HT) | 无 | 差（无AVX-512，异构调度抖动） | 不推荐用于虚拟化算力中枢 |
| **AMD Ryzen 9 9955HX** | 16C / 32T (全大核) | 原生全血双512 | 顶级 | 仅跑向量/编译时性能溢出且有新品溢价 |

### 3. 推荐硬件配比（仅运行向量模型 + 上下文检索 + Agent 调度沙箱）
- **内存**：DDR5 5600MHz+ 双通道 **32GB (16G×2)** 或 **48GB (24G×2)**。
- **固态**：**1TB ~ 2TB NVMe PCIe 4.0**，必须为原厂 3D TLC 颗粒且具备**独立物理 DRAM 缓存**（如致态 TiPro7000 / 三星 990 Pro / 西数 SN850X），保障 PVE 高频快照与容器 I/O 寿命。
