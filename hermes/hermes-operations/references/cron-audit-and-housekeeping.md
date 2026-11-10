# Cron Job Audit & Housekeeping

Periodic audit of all cron jobs to catch waste, staleness, and misconfiguration.

## Audit Checklist

### 1. List all jobs
```
cronjob(action='list')
```

### 2. For each job, check:

| Check | Signal | Fix |
|-------|--------|-----|
| **Redundant LLM** | Script does 100% of the work, agent just says `[SILENT]` | Add `no_agent: true` + `script: <path>` |
| **Stale provider references** | Script mentions exited vendors (MiniMax, Google, etc.) | Delete stale scripts; update remaining ones |
| **Stale skill dependencies** | Loaded skill has triggers for dead providers | Patch skill triggers; delete stale reference files |
| **Wrong delivery target** | `deliver: local` when user wants Telegram, or vice versa | Update deliver field |
| **Comment mismatch** | Script header says different frequency than cron schedule | Fix the comment |
| **Output bloat** | `cron/output/` accumulating old run logs | Prune old outputs (>30 days) |

### 3. Check script contents

For each job with a `script` field:
```bash
# Read the script
read_file ~/.hermes/scripts/<script_name>

# Scan for stale vendor keywords
rg -i 'minimax|gemini|google|vertex' ~/.hermes/scripts/
```

### 4. Verify last run output

Read the most recent output under `~/.hermes/cron/output/<job_id>/` to verify:
- No errors buried in apparently "ok" runs
- No stale provider names in output (e.g. MCP server list showing exited vendors)
- Output is going to the right channel

## Mem0 Memory Cleanup

When mem0 accumulates junk (one-off instructions, stale comparisons, preferences already in USER PROFILE):

### 1. Search comprehensively
```
mem0_search(query='all memories', top_k=50)
mem0_search(query='preferences configuration', top_k=20)
mem0_search(query='projects environment tools', top_k=20)
```

### 2. Categorize each entry

| Category | Action | Example |
|----------|--------|---------|
| One-time instruction | Delete | "直接干", "just run it" |
| One-time complaint (resolved) | Delete | "reply format looks strange" |
| One-time action | Delete | "restart all Hermes" |
| One-time Q&A | Delete | "which model is stronger" |
| Duplicate of USER PROFILE | Delete | "concise answers", "markdown format" |
| Stale vendor reference | Delete | "MiniMax vs DeepSeek comparison" |
| Core identity | Keep | Name, email |
| Environment/config | Keep | Network topology, provider choice |
| Reusable preferences | Keep | Memory management rules |

### 3. Batch delete
Delete all identified junk entries in one turn with parallel `mem0_delete` calls.

### 4. Verify
```
mem0_search(query='count all', top_k=20)
# Confirm only kept entries remain
```

## Directory Cleanup Pattern

For general `.hermes` cleanup:

1. `du -sh ~/.hermes/*/` — identify top space consumers
2. Drill into large directories to find stale content
3. Present findings as a table: path, size, reason, safety
4. Ask user, then batch-execute deletions
5. `du -sh ~/.hermes/` — verify reduction

### Common cleanup targets

| Path | Typical Size | Safe to Delete? |
|------|-------------|-----------------|
| `state-snapshots/*-pre-update/` | 500M–1G | ✅ After successful update |
| `audio_cache/*` | 30–50M | ✅ Old TTS files |
| `logs/*.log.{1,2,3}` | 10–50M | ✅ Rotated logs |
| `logs/gateway.error.log` | 10–50M | Truncate (tail -200) |
| `logs/gateway-exit-diag.log` | 1–5M | ✅ Diagnostic dump |
| `tmp/*` | 5–10M | ✅ Temporary files |
| `sessions/request_dump_*` | 1–3M | ✅ Debug dumps |
| `hermes-agent/` git stashes | 5–20M | `git stash clear` + `git gc --aggressive` |
