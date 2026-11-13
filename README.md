# Hermes Skills

Hermes Agent 个人技能库（procedural memory），由本机 `~/.hermes/skills` 同步而来，按分类组织。

- 技能总数：**109**　分类数：**19**
- 每个技能目录：`SKILL.md`（YAML frontmatter `name` / `description`）+ 可选 `references/` `scripts/` `templates/` `assets/`
- 已排除：`.archive` 归档技能、`.curator_backups` 备份、运行时缓存（`.hub` / `.usage.json` 等）
- 同步入口：`scripts/sync.sh`（rsync 镜像 + 重建本索引 + 提交推送）

## 分类总览

| 分类 | 技能数 | 说明 |
|---|---|---|
| [mlops](./mlops/) | 19 | Knowledge and Tools for Machine Learning Operations - tools and frameworks for training, fine-tuning, deploying, and optimizing ML/AI models |
| [devops](./devops/) | 16 |  |
| [creative](./creative/) | 12 | Creative content generation — ASCII art, hand-drawn style diagrams, and visual design tools. |
| [hermes](./hermes/) | 10 |  |
| [productivity](./productivity/) | 10 | Skills for document creation, presentations, spreadsheets, and other productivity workflows. |
| [software-development](./software-development/) | 8 |  |
| [research](./research/) | 6 | Skills for academic research, paper discovery, literature review, domain reconnaissance, market data, content monitoring, and scientific knowledge retrieval. |
| [autonomous-ai-agents](./autonomous-ai-agents/) | 4 | Skills for spawning and orchestrating autonomous AI coding agents and multi-agent workflows — running independent agent processes, delegating tasks, and coordinating parallel workstreams. |
| [gaming](./gaming/) | 2 | Skills for setting up, configuring, and managing game servers, modpacks, and gaming-related infrastructure. |
| [github](./github/) | 2 | GitHub workflow skills for managing repositories, pull requests, code reviews, issues, and CI/CD pipelines using the gh CLI and git via terminal. |
| [mcp](./mcp/) | 2 | Skills for working with MCP (Model Context Protocol) servers, tools, and integrations. Includes the built-in native MCP client (configure servers in config.yaml for automatic tool discovery) and the mcporter CLI bridge for ad-hoc server interaction. |
| [media](./media/) | 2 | Skills for working with media content — YouTube transcripts, GIF search, music generation, and audio visualization. |
| [social-media](./social-media/) | 2 | Skills for interacting with social platforms and social-media workflows — posting, reading, monitoring, and account operations. |
| [apple](./apple/) | 1 | Apple/macOS-specific skills — iMessage, Reminders, Notes, FindMy, and macOS automation. These skills only load on macOS systems. |
| [consumer-tech](./consumer-tech/) | 1 |  |
| [data-science](./data-science/) | 1 | Skills for data science workflows — interactive exploration, Jupyter notebooks, data analysis, and visualization. |
| [leisure](./leisure/) | 1 |  |
| [red-teaming](./red-teaming/) | 1 |  |
| [smart-home](./smart-home/) | 1 | Skills for controlling smart home devices — lights, switches, sensors, and home automation systems. |

## mlops

> Knowledge and Tools for Machine Learning Operations - tools and frameworks for training, fine-tuning, deploying, and optimizing ML/AI models

| 技能 | 描述 |
|---|---|
| [audiocraft-audio-generation `models/audiocraft`](./mlops/models/audiocraft/SKILL.md) | AudioCraft: MusicGen text-to-music, AudioGen text-to-sound. |
| [axolotl `training/axolotl`](./mlops/training/axolotl/SKILL.md) | Axolotl: YAML LLM fine-tuning (LoRA, DPO, GRPO). |
| [clip `models/clip`](./mlops/models/clip/SKILL.md) | OpenAI's model connecting vision and language. Enables zero-shot image classification, image-text matching, and cross-modal retrieval. Trained on 400M image-text pairs. Use for image search, content moderation, or vision-language tasks without fine-tuning. Best for general-purpose image understanding. |
| [dspy `research/dspy`](./mlops/research/dspy/SKILL.md) | DSPy: declarative LM programs, auto-optimize prompts, RAG. |
| [evaluating-llms-harness `evaluation/evaluating-llms-harness`](./mlops/evaluation/evaluating-llms-harness/SKILL.md) | lm-eval-harness: benchmark LLMs (MMLU, GSM8K, etc.). |
| [fine-tuning-with-trl `training/trl-fine-tuning`](./mlops/training/trl-fine-tuning/SKILL.md) | TRL: SFT, DPO, PPO, GRPO, reward modeling for LLM RLHF. |
| [huggingface-hub](./mlops/huggingface-hub/SKILL.md) | HuggingFace hf CLI: search/download/upload models, datasets. |
| [llama-cpp `inference/llama-cpp`](./mlops/inference/llama-cpp/SKILL.md) | llama.cpp local GGUF inference + HF Hub model discovery. |
| [modal-serverless-gpu `cloud/modal`](./mlops/cloud/modal/SKILL.md) | Serverless GPU cloud platform for running ML workloads. Use when you need on-demand GPU access without infrastructure management, deploying ML models as APIs, or running batch jobs with automatic scaling. |
| [obliteratus `inference/obliteratus`](./mlops/inference/obliteratus/SKILL.md) | OBLITERATUS: abliterate LLM refusals (diff-in-means). |
| [outlines `inference/outlines`](./mlops/inference/outlines/SKILL.md) | Outlines: structured JSON/regex/Pydantic LLM generation. |
| [peft-fine-tuning `training/peft`](./mlops/training/peft/SKILL.md) | Parameter-efficient fine-tuning for LLMs using LoRA, QLoRA, and 25+ methods. Use when fine-tuning large models (7B-70B) with limited GPU memory, when you need to train <1% of parameters with minimal accuracy loss, or for multi-adapter serving. HuggingFace's official library integrated with transformers ecosystem. |
| [pytorch-fsdp `training/pytorch-fsdp`](./mlops/training/pytorch-fsdp/SKILL.md) | Expert guidance for Fully Sharded Data Parallel training with PyTorch FSDP - parameter sharding, mixed precision, CPU offloading, FSDP2 |
| [segment-anything-model `models/segment-anything`](./mlops/models/segment-anything/SKILL.md) | SAM: zero-shot image segmentation via points, boxes, masks. |
| [serving-llms-vllm `inference/serving-llms-vllm`](./mlops/inference/serving-llms-vllm/SKILL.md) | vLLM: high-throughput LLM serving, OpenAI API, quantization. |
| [stable-diffusion-image-generation `models/stable-diffusion`](./mlops/models/stable-diffusion/SKILL.md) | State-of-the-art text-to-image generation with Stable Diffusion models via HuggingFace Diffusers. Use when generating images from text prompts, performing image-to-image translation, inpainting, or building custom diffusion pipelines. |
| [unsloth `training/unsloth`](./mlops/training/unsloth/SKILL.md) | Unsloth: 2-5x faster LoRA/QLoRA fine-tuning, less VRAM. |
| [weights-and-biases `evaluation/weights-and-biases`](./mlops/evaluation/weights-and-biases/SKILL.md) | W&B: log ML experiments, sweeps, model registry, dashboards. |
| [whisper `models/whisper`](./mlops/models/whisper/SKILL.md) | OpenAI's general-purpose speech recognition model. Supports 99 languages, transcription, translation to English, and language identification. Six model sizes from tiny (39M params) to large (1550M params). Use for speech-to-text, podcast transcription, or multilingual audio processing. Best for robust, multilingual ASR. |

## devops

| 技能 | 描述 |
|---|---|
| [adguardhome-doh-cert-renewal](./devops/adguardhome-doh-cert-renewal/SKILL.md) | Use when 给 AdGuardHome DoH 证书签发或自动续期。 |
| [att-ops](./devops/att-ops/SKILL.md) | 用户问 ATT/美国家宽/AnyTLS 出口时使用，管理美国家宽服务器（公网 IP 动态，须先核实）。 |
| [docker-management](./devops/docker-management/SKILL.md) | Manage Docker containers, images, volumes, and Compose. |
| [kanban-orchestrator](./devops/kanban-orchestrator/SKILL.md) | Decomposition playbook + anti-temptation rules for an orchestrator profile routing work through Kanban. The "don't do the work yourself" rule and the basic lifecycle are auto-injected into every kanban worker's system prompt; this skill is the deeper playbook when you're specifically playing the orchestrator role. |
| [lan-docker-inventory](./devops/lan-docker-inventory/SKILL.md) | Use when 要盘点/发布局域网 Docker 全量清单. 只读采集再脱敏发布. |
| [linux-icmp-hardening](./devops/linux-icmp-hardening/SKILL.md) | Use when 让自有 Linux 主机不被 ping 探测. 只丢 echo-request. |
| [nas-docker-ops](./devops/nas-docker-ops/SKILL.md) | 用户问 Z4Pro NAS (10.0.0.3) Docker 容器状态/日志/重启时使用。 |
| [oracle-cloud-ops](./devops/oracle-cloud-ops/SKILL.md) | 用户问甲骨文云 OCI/oci/oci2 运维、部署或清退自托管服务时使用。 |
| [proxy-chain-diagnostics](./devops/proxy-chain-diagnostics/SKILL.md) | 用户问代理/翻墙/节点/DNS 污染/Telegram 连不上时使用，一键诊断 Surge 链路。 |
| [pve-ops](./devops/pve-ops/SKILL.md) | 用户问 PVE 物理机 (10.0.0.4)/LXC/虚拟机/企业源/体检优化时使用。 |
| [server-readonly-inspection](./devops/server-readonly-inspection/SKILL.md) | 对已确认的三台自有服务器做固定只读健康巡检时使用；只通过白名单脚本，不接受任意命令，不执行修复。 |
| [site-egress-check](./devops/site-egress-check/SKILL.md) | 查网站出口IP/走哪个节点时用 Surge API 脚本（paypal.com 出口检测）。 |
| [surge-config-operations](./devops/surge-config-operations/SKILL.md) | 用户问 Surge UDP/QUIC/MASQUE 节点配置或 SubStore 批量参数时使用。 |
| [vps-ops](./devops/vps-ops/SKILL.md) | 用户问搬瓦工 VPS/节点/AnyTLS/s-ui/1Panel 时使用，密码方式管理 VPS。 |
| [watchers](./devops/watchers/SKILL.md) | Poll RSS, JSON APIs, and GitHub with watermark dedup. |
| [webhook-subscriptions](./devops/webhook-subscriptions/SKILL.md) | Webhook subscriptions: event-driven agent runs. |

## creative

> Creative content generation — ASCII art, hand-drawn style diagrams, and visual design tools.

| 技能 | 描述 |
|---|---|
| [ascii-art](./creative/ascii-art/SKILL.md) | ASCII art: pyfiglet, cowsay, boxes, image-to-ascii. |
| [baoyu-article-illustrator](./creative/baoyu-article-illustrator/SKILL.md) | Article illustrations: type × style × palette consistency. |
| [baoyu-comic](./creative/baoyu-comic/SKILL.md) | Knowledge comics (知识漫画): educational, biography, tutorial. |
| [comfyui](./creative/comfyui/SKILL.md) | Generate images, video, and audio via diffusion workflows. |
| [excalidraw](./creative/excalidraw/SKILL.md) | Hand-drawn Excalidraw JSON diagrams (arch, flow, seq). |
| [html-artifact](./creative/html-artifact/SKILL.md) | Build self-contained HTML files to explain, plan, or review. |
| [ideation](./creative/creative-ideation/SKILL.md) | Generate project ideas via creative constraints. |
| [ip-as-logo](./creative/ip-as-logo/SKILL.md) | Use when creating minimalist cute IP character mascot logos. |
| [pixel-art](./creative/pixel-art/SKILL.md) | Pixel art w/ era palettes (NES, Game Boy, PICO-8). |
| [pretext](./creative/pretext/SKILL.md) | Build creative browser demos with DOM-free text layout. |
| [sketch](./creative/sketch/SKILL.md) | Throwaway HTML mockups: 2-3 design variants to compare. |
| [touchdesigner-mcp](./creative/touchdesigner-mcp/SKILL.md) | Control TouchDesigner via twozero MCP. |

## hermes

| 技能 | 描述 |
|---|---|
| [bot-tooling-provisioning](./hermes/bot-tooling-provisioning/SKILL.md) | Use when 为某 Bot 扩装技能/MCP. 先验通道, 凭据由用户输入. |
| [cron-delivery-verification](./hermes/cron-delivery-verification/SKILL.md) | Use when 建/验收 cron 投递与脚本任务. 不信字段, 显式地址. |
| [cross-bot-skill-intake](./hermes/cross-bot-skill-intake/SKILL.md) | Use when 其他 bot 投递经验要求沉淀. 收/审/写三档+边界. |
| [hermes-daily-status-cron](./hermes/hermes-daily-status-cron/SKILL.md) | 模式——给 Hermes 配置一个每天固定时间、纯 shell采集的健康日报 cron job，推送到 Telegram 等渠道。零 LLM 开销、脚本 stdout 直接投递。 |
| [hermes-operations](./hermes/hermes-operations/SKILL.md) | Hermes Agent platform operations and maintenance — gateway management, full-stack restart (macOS launchd / Linux systemd / s6), auto-update fixes, memory indexing, mem0 platform quirks (event_id vs memory_id, stale injected snapshots), MEMORY+USER injection, and platform troubleshooting. Covers SSH/HTTPS git remotes, PID file race conditions, gateway restart, and QMD supplementary memory setup. |
| [hermes-system-optimization](./hermes/hermes-system-optimization/SKILL.md) | 用于 Hermes 全系统深度体检、Mem0 记忆精简及服务链路打通。 |
| [mem0-oss-operations](./hermes/mem0-oss-operations/SKILL.md) | Use when mem0_search returns empty or user says 检查记忆系统. |
| [mem0-tiered-tidy-cron](./hermes/mem0-tiered-tidy-cron/SKILL.md) | Use when 做每日 mem0 记忆库分级整理(删碎片/合并). L1-L4+快照回滚. |
| [session-digest-memory-cron](./hermes/session-digest-memory-cron/SKILL.md) | Use when 建/改每日会话→mem0 记忆提取 cron. 只读素材+查重写入. |
| [telegram-group-mention-silent](./hermes/telegram-group-mention-silent/SKILL.md) | Use when 群里 @Bot 无响应. 查白名单+隐私模式. |

## productivity

> Skills for document creation, presentations, spreadsheets, and other productivity workflows.

| 技能 | 描述 |
|---|---|
| [collective-wisdom-install](./productivity/collective-wisdom-install/SKILL.md) | Browse, install, or share team skills with consent. |
| [email-imap-mcp-setup](./productivity/email-imap-mcp-setup/SKILL.md) | Use when 接入邮箱到 Hermes(IMAP/MCP). 选型+认证+策略+坑. |
| [linear](./productivity/linear/SKILL.md) | Linear: manage issues, projects, teams via GraphQL + curl. |
| [mail-inbox-readonly-triage](./productivity/mail-inbox-readonly-triage/SKILL.md) | Use when 做邮箱只读巡检/分级推送. 先元数据后正文, 不改已读. |
| [microsoft-office](./productivity/microsoft-office/SKILL.md) | Create, read, and edit Word, PowerPoint, and Excel files. |
| [nano-pdf](./productivity/nano-pdf/SKILL.md) | Edit text in existing PDFs via natural-language prompts. |
| [ocr-and-documents](./productivity/ocr-and-documents/SKILL.md) | Extract text, tables, images, and color-styled text (red highlights, etc.) from PDFs/scans/PPTs using pymupdf and marker-pdf. Trigger on PDF/PPT text extraction, OCR, red-text / 加红 / 高亮 extraction, or scanned-document reading. |
| [petdex](./productivity/petdex/SKILL.md) | Install and select animated petdex mascots for Hermes. |
| [session-librarian](./productivity/session-librarian/SKILL.md) | Organize sessions by prompt: find, rename, archive, prune. |
| [tui-widgets](./productivity/tui-widgets/SKILL.md) | Author live widget apps for the Hermes TUI dock. |

## software-development

| 技能 | 描述 |
|---|---|
| [codex-deepseek-provider](./software-development/codex-deepseek-provider/SKILL.md) | 把 Codex CLI 接到 DeepSeek 等第三方模型时使用。 |
| [open-webui-macos](./software-development/open-webui-macos/SKILL.md) | Install and run open-webui on macOS (Mac mini) using pyenv + venv, bypassing PyPI Python version metadata restrictions and resolving runtime dependency issues. |
| [pocock-codebase-design](./software-development/pocock-codebase-design/SKILL.md) | 深模块化软件设计规范，小接口隐藏复杂逻辑，杜绝代码熵增与泥球架构。 |
| [pocock-diagnosing-bugs](./software-development/pocock-diagnosing-bugs/SKILL.md) | 严谨的假设驱动缺陷诊断流程，杜绝盲目试错，构建红灯复现与回归闭环。 |
| [pocock-domain-modeling](./software-development/pocock-domain-modeling/SKILL.md) | 维护统一领域语言与 CONTEXT.md 规范，建立精准术语字典，大幅提升 Agent 理解效率。 |
| [pocock-grilling](./software-development/pocock-grilling/SKILL.md) | 在动手编码或复杂架构决策前，对需求与边界进行深度审问式对齐，彻底杜绝 Agent 误解。 |
| [subagent-driven-development](./software-development/subagent-driven-development/SKILL.md) | Execute plans via delegate_task subagents (2-stage review). |
| [writing-plans](./software-development/writing-plans/SKILL.md) | Write implementation plans: bite-sized tasks, paths, code. |

## research

> Skills for academic research, paper discovery, literature review, domain reconnaissance, market data, content monitoring, and scientific knowledge retrieval.

| 技能 | 描述 |
|---|---|
| [blogwatcher](./research/blogwatcher/SKILL.md) | Monitor blogs and RSS/Atom feeds via blogwatcher-cli tool. |
| [ip-quality-xykt](./research/ip-quality-xykt/SKILL.md) | 检测IP纯净度/评分/流媒体解锁时用 xykt/IPQuality 脚本（IPv4 only 全局默认）。 |
| [parallel-web-search](./research/parallel-web-search/SKILL.md) | Run web search across Tavily (mcp_tavily_tavily_search) and minimax coding plan (mcp_minimax_coding_plan_web_search) in parallel and merge/dedupe the results. Load this for ANY "search the web for X" task — Eason's standing preference is to query both backends and present a unified, source-attributed result. |
| [polymarket](./research/polymarket/SKILL.md) | Query Polymarket: markets, prices, orderbooks, history. |
| [research-paper-writing](./research/research-paper-writing/SKILL.md) | Write ML papers for NeurIPS/ICML/ICLR: design→submit. |
| [rss-feeds](./research/rss-feeds/SKILL.md) | Read RSS, Atom, JSON feeds; discover feeds behind a page. |

## autonomous-ai-agents

> Skills for spawning and orchestrating autonomous AI coding agents and multi-agent workflows — running independent agent processes, delegating tasks, and coordinating parallel workstreams.

| 技能 | 描述 |
|---|---|
| [dynamic-workflow](./autonomous-ai-agents/dynamic-workflow/SKILL.md) | Orchestrate large fan-out work as a plan-in-code "workflow" so the agent's context holds only the final verified answer, not the exhaust of hundreds of intermediate steps. Use for codebase-wide sweeps, large migrations, multi-angle research, and any task too big for one context window where the split strategy is known enough to script. Includes the adversarial-convergence verification recipe (independent attempts + refuters, keep only surviving claims). |
| [hermes-agent](./autonomous-ai-agents/hermes-agent/SKILL.md) | Use, configure, theme, extend, and orchestrate Hermes Agent. |
| [local-dsh-coding](./autonomous-ai-agents/local-dsh-coding/SKILL.md) | 代码开发、Bug 修复、重构、复杂脚本、测试、代码审查或构建任务时，评估调用 Mac 本机 DeepSeek Harness；普通聊天和信息查询不调用。 |
| [merge-reconciler](./autonomous-ai-agents/merge-reconciler/SKILL.md) | Neutral third-party resolution of agent merge conflicts. |

## gaming

> Skills for setting up, configuring, and managing game servers, modpacks, and gaming-related infrastructure.

| 技能 | 描述 |
|---|---|
| [minecraft-modpack-server](./gaming/minecraft-modpack-server/SKILL.md) | Host modded Minecraft servers (CurseForge, Modrinth). |
| [pokemon-player](./gaming/pokemon-player/SKILL.md) | Play Pokemon via headless emulator + RAM reads. |

## github

> GitHub workflow skills for managing repositories, pull requests, code reviews, issues, and CI/CD pipelines using the gh CLI and git via terminal.

| 技能 | 描述 |
|---|---|
| [github-issue-to-pr](./github/github-issue-to-pr/SKILL.md) | Carry a GitHub issue to a verified PR with honest CI state. |
| [github-pr-workflow](./github/github-pr-workflow/SKILL.md) | GitHub PR lifecycle: branch, commit, open, CI, merge. |

## mcp

> Skills for working with MCP (Model Context Protocol) servers, tools, and integrations. Includes the built-in native MCP client (configure servers in config.yaml for automatic tool discovery) and the mcporter CLI bridge for ad-hoc server interaction.

| 技能 | 描述 |
|---|---|
| [mcporter](./mcp/mcporter/SKILL.md) | Use the mcporter CLI to list, configure, auth, and call MCP servers/tools directly (HTTP or stdio), including ad-hoc servers, config edits, and CLI/type generation. |
| [native-mcp](./mcp/native-mcp/SKILL.md) | MCP client: connect servers, register tools (stdio/HTTP). |

## media

> Skills for working with media content — YouTube transcripts, GIF search, music generation, and audio visualization.

| 技能 | 描述 |
|---|---|
| [heartmula](./media/heartmula/SKILL.md) | HeartMuLa: Suno-like song generation from lyrics + tags. |
| [spotify](./media/spotify/SKILL.md) | Spotify: play, search, queue, manage playlists and devices. |

## social-media

> Skills for interacting with social platforms and social-media workflows — posting, reading, monitoring, and account operations.

| 技能 | 描述 |
|---|---|
| [reddit-reading](./social-media/reddit-reading/SKILL.md) | Read Reddit: subreddits, search, threads, users. No browser. |
| [xitter](./social-media/xitter/SKILL.md) | Interact with X/Twitter via the x-cli terminal client using official X API credentials. Use for posting, reading timelines, searching tweets, liking, retweeting, bookmarks, mentions, and user lookups. |

## apple

> Apple/macOS-specific skills — iMessage, Reminders, Notes, FindMy, and macOS automation. These skills only load on macOS systems.

| 技能 | 描述 |
|---|---|
| [apple-platform](./apple/apple-platform/SKILL.md) | Apple platform automation: Notes, Reminders, iMessage, FindMy, and macOS desktop computer use. Covers all native macOS/iOS app interactions via CLI tools and AppleScript. |

## consumer-tech

| 技能 | 描述 |
|---|---|
| [hardware-buying-advisory](./consumer-tech/hardware-buying-advisory/SKILL.md) | 用户问某硬件/配件/穿戴设备怎么样、值不值得买时用：先核实当前在用型号，再按官网核价核规格，最后给结构化结论与明确取舍。 |

## data-science

> Skills for data science workflows — interactive exploration, Jupyter notebooks, data analysis, and visualization.

| 技能 | 描述 |
|---|---|
| [jupyter-live-kernel](./data-science/jupyter-live-kernel/SKILL.md) | Iterative Python via live Jupyter kernel (hamelnb). |

## leisure

| 技能 | 描述 |
|---|---|
| [find-nearby](./leisure/find-nearby/SKILL.md) | Find nearby places (restaurants, cafes, bars, pharmacies, etc.) using OpenStreetMap. Works with coordinates, addresses, cities, zip codes, or Telegram location pins. No API keys needed. |

## red-teaming

| 技能 | 描述 |
|---|---|
| [godmode](./red-teaming/godmode/SKILL.md) | Jailbreak LLMs: Parseltongue, GODMODE, ULTRAPLINIAN. |

## smart-home

> Skills for controlling smart home devices — lights, switches, sensors, and home automation systems.

| 技能 | 描述 |
|---|---|
| [openhue](./smart-home/openhue/SKILL.md) | Control Philips Hue lights, scenes, rooms via OpenHue CLI. |

## 根级技能（未分类）

| 技能 | 描述 |
|---|---|
| [adguardhome-doh-deploy](./adguardhome-doh-deploy/SKILL.md) | Deploy AdGuard Home with public DoH/DoT behind a reverse proxy (openresty or nginx) using a shared Let's Encrypt certificate. Covers container port mapping, AGH TLS settings, reverse-proxy vhost for both UI and DoH endpoint, anti-scanner random paths, and the `Root YR` intermediate cert gotcha that breaks nginx upstream verification. |
| [file-image-pdf-processing](./file-image-pdf-processing/SKILL.md) | 处理 Telegram 或本地文件、图片、PDF，提取内容或识别扫描页时使用；文本层优先，按需原生视觉，禁止自动装依赖和收费云 OCR。 |
| [hermes-desktop-plugins](./hermes-desktop-plugins/SKILL.md) | Write desktop app plugins that add UI panes and commands. |
| [hermes-telegram-voice](./hermes-telegram-voice/SKILL.md) | Auto TTS for Telegram — MiniMax primary, Edge TTS fallback on exhaustion, midnight quota reset. Fully transparent to users. |
| [hermes-themes](./hermes-themes/SKILL.md) | Author a Hermes color theme that skins every surface. |
| [hybrid-memory-sidecar](./hybrid-memory-sidecar/SKILL.md) | Diagnose, fix, and schedule maintenance for the Hermes `hybrid` custom memory plugin — TF-IDF sidecar drift, shebang-vs-Python-version crashes in cron scripts, FTS5↔memories sync, and WAL growth. Trigger when `~/.hermes/hybrid_memory.db.tfidf.json` mtime is old while `memories` table grows, when `hybrid_health.py` TypeErrors on launch, when ghost df or unmatched n_docs shows up in health, or when first enabling the hybrid plugin. |
| [skill-curation](./skill-curation/SKILL.md) | 需要将已经验证的方法论、维护操作或重复工作沉淀成可复用 Skill 时使用；先提出草案，再申请本次写入批准。 |
| [yuanbao](./yuanbao/SKILL.md) | Yuanbao (元宝) groups: @mention users, query info/members. |

---

本 README 由 `scripts/gen_readme.py` 自动生成，请勿手工编辑。
