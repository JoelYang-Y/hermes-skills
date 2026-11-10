---
name: parallel-web-search
description: Run web search across Tavily (mcp_tavily_tavily_search) and minimax coding plan (mcp_minimax_coding_plan_web_search) in parallel and merge/dedupe the results. Load this for ANY "search the web for X" task — Eason's standing preference is to query both backends and present a unified, source-attributed result.
version: 1.0.0
author: Hermes Agent
license: MIT
tags: [search, tavily, minimax, mcp, parallel]
---

# Parallel Web Search (Tavily + minimax)

## When to Use

Eason's standing preference: **every web search runs against both Tavily AND minimax in parallel**, then results are merged and deduplicated. This skill is the playbook for that flow.

Load it whenever the user says:
- "搜一下 X" / "search for X" / "找一下 X"
- "what's new with X" / "look up X"
- "查一下 Y" / "research Z"
- Any factual question where the answer depends on recent web content

If only one source is needed (e.g. a known-stale query where one backend is known to fail), drop the other — but default to BOTH.

## Why Two Backends

| Backend | Strengths | Limits |
|---------|-----------|--------|
| **Tavily** (`mcp_tavily_tavily_search`) | Tuned for LLMs; structured snippet length; `search_depth: advanced` for research; can filter by time range; accurate on English content | 1000 free queries/month for new accounts; per-call cost past that |
| **minimax coding plan** (`mcp_minimax_coding_plan_web_search`) | Strong on Chinese sources (qq.com, so.html5.qq.com, 36kr, etc.); no monthly cap; returns long snippets that include full text | Sometimes less precise on English-only queries; can return low-quality pages |

Combined coverage of both = ~30% more useful content per query than either alone (Tavily catches what minimax misses, and vice versa).

## The Recipe

### Step 1: Fire both in the same tool-call block

Both are MCP tools, both run inside Hermes — call them in the **same parallel block** (one `function_calls` block with both `mcp_tavily_tavily_search` and `mcp_minimax_coding_plan_web_search`), NOT sequentially. Tavily is typically 2-3s, minimax is 1-2s; parallel saves wall time.

```python
# Pseudo-tool-call block (do this in ONE assistant turn, not two)
mcp_tavily_tavily_search(query="...", search_depth="advanced", max_results=8, time_range="week")
mcp_minimax_coding_plan_web_search(query="...")
```

### Step 2: Tavily parameters to use

- `query` — required, 3-5 keyword Chinese or English
- `search_depth` — `advanced` for real research, `basic` for quick lookups
- `max_results` — 5-8 is a good default; more is rarely useful
- `time_range` — `day` / `week` / `month` / `year` for recency-bound queries; omit for evergreen

### Step 3: minimax parameters

- `query` — required; 3-5 keywords work best
- No `max_results` parameter exposed in the current MCP tool — returns ~5 by default

### Step 4: Merge and dedupe

Both backends return `{ "results": [...] }` with `url`, `title`, `content`/`snippet` fields. Dedup by URL (or by host if URLs are session-tokenised like YouTube):

```
seen_urls = set()
merged = []
for r in (tavily_results + minimax_results):
    key = r.get("url") or r.get("link")
    if key and key not in seen_urls:
        seen_urls.add(key)
        merged.append(r)
```

For YouTube/Sina/qq.com URLs that change per-session, dedup by title-prefix + host instead.

### Step 5: Synthesize for the user

Don't just paste the two raw result lists side by side. Group findings by **topic**, attribute the source for each claim, and lead with the highest-confidence / most-recent fact. Use bullet lists, not pipe tables (Telegram doesn't render them).

Suggested response shape:

```
## [Topic] — 综合速览（Tavily + minimax 双源整合）

[1-2 sentence lead with the single most important fact, attributed]

### [Subtopic 1]
- [fact] — [source name]
- [fact] — [source name]

### [Subtopic 2]
- ...
```

## Anti-Patterns

- ❌ **Calling them sequentially in two turns** — wastes 2-3s of wall time per query, and breaks the parallelism
- ❌ **Only using one backend "to be safe"** — explicitly against Eason's preference; always run both
- ❌ **Pasting both raw result lists** — synthesize, don't dump
- ❌ **Hardcoding Tavily API key in subprocess scripts** — the MCP is configured; use the tool
- ❌ **Forgetting `time_range` on a recency query** — without it you get 5-year-old blogspam

## When Tavily is unavailable

If the `mcp_tavily_tavily_search` tool is missing or returns auth errors, fall back to `tavily_search` via `execute_code` and Python:

```python
from hermes_tools import ...  # NOT available
```

…actually, the MCP tool is the only path. If Tavily MCP is broken, the user must reinstall it via:
```bash
hermes mcp add tavily --url "https://mcp.tavily.com/mcp/?tavilyApiKey=tvly-..."
```
(See `native-mcp` skill for the expect-recipe to drive the `hermes mcp add` prompt non-interactively.)

## Quick TL;DR for the agent

> Search = `mcp_tavily_tavily_search` + `mcp_minimax_coding_plan_web_search` in one parallel block, then merge by URL and synthesize by topic. Both backends. Always.
