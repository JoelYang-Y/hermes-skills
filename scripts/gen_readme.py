#!/usr/bin/env python3
"""根据仓库内技能目录重建 README.md 分类索引。

用法: gen_readme.py [仓库根目录]
默认仓库根 = 本脚本所在目录的上一级。
幂等：源目录不变时输出逐字节一致。
"""
import os
import re
import sys
import collections

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else
                       os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def frontmatter(path):
    """极简 YAML frontmatter 解析：只取顶层 key: value。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except OSError:
        return {}
    if not txt.startswith("---"):
        return {}
    m = re.search(r"^---\n(.*?)\n---", txt, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip("\"'")
    return out


def cell(s):
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


skills = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    # 跳过仓库自身的基础设施目录与隐藏目录
    if os.path.abspath(dirpath) == ROOT:
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "scripts"]
    else:
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
    if "SKILL.md" not in filenames:
        continue
    meta = frontmatter(os.path.join(dirpath, "SKILL.md"))
    rel = os.path.relpath(dirpath, ROOT)
    skills.append({
        "rel": rel,
        "name": meta.get("name") or os.path.basename(dirpath),
        "desc": meta.get("description", ""),
    })

groups = collections.defaultdict(list)
for it in skills:
    groups[it["rel"].split("/")[0] if "/" in it["rel"] else "_root"].append(it)

cat_desc = {}
for g in groups:
    if g == "_root":
        continue
    p = os.path.join(ROOT, g, "DESCRIPTION.md")
    if os.path.exists(p):
        cat_desc[g] = frontmatter(p).get("description", "")

top = sorted([g for g in groups if g != "_root"], key=lambda x: (-len(groups[x]), x))

lines = [
    "# Hermes Skills",
    "",
    "Hermes Agent 个人技能库（procedural memory），由本机 `~/.hermes/skills` 同步而来，按分类组织。",
    "",
    f"- 技能总数：**{len(skills)}**　分类数：**{len(top)}**",
    "- 每个技能目录：`SKILL.md`（YAML frontmatter `name` / `description`）+ 可选 `references/` `scripts/` `templates/` `assets/`",
    "- 已排除：`.archive` 归档技能、`.curator_backups` 备份、运行时缓存（`.hub` / `.usage.json` 等）",
    "- 同步入口：`scripts/sync.sh`（rsync 镜像 + 重建本索引 + 提交推送）",
    "",
    "## 分类总览",
    "",
    "| 分类 | 技能数 | 说明 |",
    "|---|---|---|",
]
for g in top:
    lines.append(f"| [{g}](./{g}/) | {len(groups[g])} | {cell(cat_desc.get(g))} |")
lines.append("")

for g in top:
    lines.append(f"## {g}")
    lines.append("")
    if cat_desc.get(g):
        lines += [f"> {cat_desc[g]}", ""]
    lines += ["| 技能 | 描述 |", "|---|---|"]
    for it in sorted(groups[g], key=lambda x: x["name"]):
        sub = it["rel"].count("/") > 1
        label = f'{it["name"]} `{it["rel"].split("/", 1)[1]}`' if sub else it["name"]
        lines.append(f'| [{label}](./{it["rel"]}/SKILL.md) | {cell(it["desc"])} |')
    lines.append("")

if "_root" in groups:
    lines += ["## 根级技能（未分类）", "", "| 技能 | 描述 |", "|---|---|"]
    for it in sorted(groups["_root"], key=lambda x: x["name"]):
        lines.append(f'| [{it["name"]}](./{it["rel"]}/SKILL.md) | {cell(it["desc"])} |')
    lines.append("")

lines += ["---", "", "本 README 由 `scripts/gen_readme.py` 自动生成，请勿手工编辑。"]

out = os.path.join(ROOT, "README.md")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"README 已重建：{len(skills)} 个技能 / {len(top)} 个分类 -> {out}")
print(f"STAT skills={len(skills)} cats={len(top)}")
