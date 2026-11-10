# Vendor Exit Cleanup

When a user fully exits a provider/vendor stack (e.g. Google Cloud, MiniMax, OpenAI), stale references persist across many locations. This reference captures the systematic cleanup pattern.

## Step-by-Step

### 1. Find all references

```bash
# Search for vendor keywords across the entire .hermes tree
rg -il 'vendor_pattern1|vendor_pattern2' ~/.hermes/ --ignore-case
```

Common locations to check:
- `~/.hermes/scripts/` — any scripts that call the vendor's API
- `~/.hermes/skills/<vendor>/` — vendor-specific skill directories
- `~/.hermes/cron/output/` — cron job output may reference vendor MCP servers
- `~/.hermes/config.yaml` — active config (comments are safe)
- `~/.hermes/.env` — API keys (masked or unmasked)
- Built-in skills' trigger lists (e.g. `hermes-operations` triggers referencing `gcloud`, `vertex`, `setup_adc.sh`)
- mem0 memories — search for vendor names, API keys, project IDs

### 2. Categorize by type

| Type | Action |
|------|--------|
| Script files calling vendor API | Delete |
| Skill directories (vendor-specific) | Delete entire directory |
| Skill trigger entries (built-in skills) | Patch to remove stale triggers |
| Skill reference files (vendor-specific) | Delete via `skill_manage remove_file` |
| Skill umbrella items referencing vendor | Patch to remove the line |
| mem0 memories with vendor references | Delete via `mem0_delete` |
| Cron job outputs mentioning vendor | No action needed — they age out naturally |
| config.yaml comments | Safe to leave (informational) |
| .env API keys | Manual cleanup (security-sensitive) |

### 3. Execute deletions

Prefer batch operations. For skills, use `skill_manage patch` and `skill_manage remove_file`. For directories, `rm -rf`. For mem0, batch `mem0_delete` calls.

### 4. Verify

```bash
# Confirm zero references remain
rg -il 'vendor_pattern' ~/.hermes/ --ignore-case
# Should return nothing (or only harmless comments in config.yaml)
```

Delete the vendor's skills from the loaded list if they appear in `skills_list`.

## Known Cleanups (this machine)

- **2026-07-12**: Exited MiniMax. Removed: `parallel_search.py`, `telegram_voice_minimax.py`, `minimax/` skill dir, `minimax-platform` skill, mem0 entries.
- **2026-07-12**: Exited Google Cloud/Gemini/Vertex. Removed: `google-ai-studio-gemini-setup/`, `google-vertex-gemini-setup/` skill dirs, Vertex triggers from `hermes-operations`, `verifying-provider-config.md`, `setup_adc.sh` references.
