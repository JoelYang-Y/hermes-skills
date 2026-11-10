---
name: mem0-oss-operations
description: Use when mem0_search returns empty or user says 检查记忆系统.
version: 0.1.0
metadata:
  hermes:
    tags: [hermes, memory, mem0, qdrant, oss, troubleshooting]
---

# Mem0 OSS Self-Hosted — Operations & Troubleshooting

Operational playbook for this user's permanent semantic memory backend (mem0
OSS mode). **Since 2026-08-10 mem0 is the ONLY memory store**: the built-in
dual-file MEMORY.md/USER.md were emptied (0 bytes, cleared 2026-08-10) and the
system-prompt MEMORY/USER PROFILE blocks are rendered from mem0 data. The
older claim that "MEMORY.md is the authoritative notes file" is OUTDATED — do
not treat the files as authoritative, and do not restore content into them
unless the user explicitly asks to migrate back. Every mem0_search / mem0_add /
mem0_update / mem0_delete runs
through this stack:

- **Vector store:** Qdrant @ 10.0.0.3:6333 (NAS Z4Pro). Active collection
  `hermes_memories_v2_hybrid` (512-dim, dense+bm25, since 2026-08-09).
  Backup: `hermes_memories_v2` (pre-hybrid-upgrade copy, kept read-only —
  do NOT treat its counts as live). Legacy/aux: `hermes_memories` (1536-dim,
  empty — do not use), `hermes_memories_v2_entities` (graph entities),
  `hermes_memories_v2_hybrid_entities` (graph entities for hybrid),
  `mem0migrations`.
- **Embedder:** `BAAI/bge-small-zh-v1.5` via sentence-transformers, runs
  locally inside the **runtime venv**. Since 2026-09-25 that is the
  PM-managed install venv (`~/.hermes/installs/<install-id>/environments/
  <env-id>/venv`, Python 3.14.x) — NOT `~/.hermes/hermes-agent/venv`, which
  is the legacy hand-built checkout venv (Python 3.11, kept around but no
  longer what the gateway imports from). Model cached
  under ~/.cache/huggingface/hub/.
- **Extraction LLM:** deepseek-v4-flash via api.deepseek.com (OpenAI-compatible).
  NOTE: 2026-08-15 修复——旧配置 `deepseek-chat` 在 DeepSeek API 上已歧义
  (匹配 deepseek-chat 与 deepseek-chat-v2.5 → 400 "Model ID is ambiguous")，
  必须用 API /models 当前返回的完整 ID (`deepseek-v4-flash`/`deepseek-v4-pro`)。
- **Config:** `~/.hermes/mem0.json` — `mode: oss`; the `oss` block holds
  vector_store/embedder/llm; top-level `user_id`/`agent_id` identify the
  principal. Current canonical user_id: `zhaoyang`.

## When to use

- User says 检查记忆系统 / "check memory system" / 检索全部记忆 / 记忆完整性.
- mem0_search returns "No relevant memories found" but memories plausibly
  exist.
- After editing mem0.json, switching mem0 modes, or migrating data.

## Quick health check

Run the packaged probe (exit 0 = healthy, prints every check):

```bash
~/.hermes/skills/hermes/mem0-oss-operations/scripts/mem0_oss_health.py
```

It checks: Qdrant reachability + collection counts, user_id distribution in
the active collection vs mem0.json, local embedder encode, and an end-to-end
mem0 SDK search with the configured user_id.

**Run it with the RUNTIME venv python, not the legacy checkout venv:**

```bash
# 权威来源：facts.json 的 packages.venv.environment 才是活跃 runtime
RT=$(python3 -c "
import glob, json, os
for f in glob.glob(os.path.expanduser('~/.hermes/installs/*/facts.json')):
    v = json.load(open(f)).get('packages', {}).get('venv', {}).get('environment')
    if v: print(v); break
")
$RT/bin/python ~/.hermes/skills/hermes/mem0-oss-operations/scripts/mem0_oss_health.py
```

**NEVER select the venv with `ls -d ~/.hermes/installs/*/environments/*/venv | head -1`.**
That sorts alphabetically, so once a SECOND environment exists (PM rebuilds create a
new env id alongside the old one) it silently returns the OLD environment, which still
has the embedder deps installed — the probe prints HEALTHY while the live gateway is
broken. Verified 2026-10-23: old env `47a7d6e…` (deps intact) vs live env `d41e4747…`
(all five deps missing). `ls -dt | head -1` (newest mtime) happens to work but is still
inferior to facts.json; use facts.json as the source of truth and fall back to `-dt`.

Running it with the legacy 3.11 venv python is the trap: that venv still
carries sentence-transformers locally, so the probe prints HEALTHY while the
live gateway fails to import the embedder. A green probe on the wrong
interpreter is a false negative — always confirm which venv the running
gateway uses (`hermes doctor` → "Runtime venv staged ... (active in this
process)") and probe THAT one.

Manual read-only equivalent:

```bash
curl -s http://10.0.0.3:6333/collections   # point counts per collection

# scroll points — NOTE: text lives in payload["data"] (also
# text_lemmatized/hash/created_at), NOT text/content/memory. Reading the
# wrong keys returns empty strings and looks like "data loss" — it isn't.
# Use the ACTIVE collection hermes_memories_v2_hybrid (v2 is the old backup).
curl -s -X POST http://10.0.0.3:6333/collections/hermes_memories_v2_hybrid/points/scroll \
  -H "Content-Type: application/json" \
  -d '{"limit": 10, "with_payload": true, "with_vector": false}'
```

## Pitfall #1 — user_id mismatch makes mem0_search return EMPTY (the big one)

**Symptom:** mem0_search → "No relevant memories found" while Qdrant holds
healthy points and unfiltered vector search scores well (0.4–0.6).

**Root cause:** the plugin resolves the search-filter user_id as (see
`plugins/memory/mem0/__init__.py`):
1. `user_id` from mem0.json — **but the literal string `hermes-user` is
   treated as unset** (it is `_DEFAULT_USER_ID`). A setup-wizard default that
   "looks configured" is silently ignored.
2. Falls back to the gateway-native id from kwargs: Telegram numeric id
   (1910087142), Discord snowflake, etc. — different per platform.
3. Hardcoded `hermes-user` (CLI with no auth).

So with `user_id: "hermes-user"` in mem0.json, a Telegram session searches
with user_id=1910087142 while Qdrant rows carry `hermes-user` / `zhaoyang` →
0 filtered hits. Writes from different channels also fragment the store.

**Fix (verified 2026-08-09):**
1. Pick ONE canonical user_id. This user chose `zhaoyang` (the id their
   platform-era rows already used). Avoid the `hermes-user` literal and avoid
   bare Telegram numeric ids when the user also runs CLI/desktop sessions.
2. Edit `~/.hermes/mem0.json` → top-level `"user_id": "<canonical>"` (back up
   first).
3. Backfill every existing point in the active collection:

```python
from qdrant_client import QdrantClient
client = QdrantClient(host="10.0.0.3", port=6333)
scroll = client.scroll(coll, limit=1000, with_payload=True, with_vectors=False)
changed = [p.id for p in scroll[0] if p.payload.get("user_id") != "zhaoyang"]
if changed:
    client.set_payload(coll, {"user_id": "zhaoyang"}, points=changed)
```

4. **Restart required** (see Pitfall #4): `/new` in chat or gateway restart.
5. Verify with the probe script, or a mem0 SDK search using
   `filters={"user_id": ...}`.

## Pitfall #2 — qdrant_client ≥1.17/1.18: `client.search` is gone

Use `client.query_points(collection, query=vec, limit=N, query_filter=...,
with_payload=True).points` — each hit has `.score` and `.payload`.
`client.search` raises AttributeError on qdrant_client 1.18.0.

## Pitfall #3 — mem0 SDK init: expanded config + mandatory filters

- `Memory.from_config` expects the **expanded** oss block
  (`{"version": "v1.1", "vector_store": {...}, "embedder": {...},
  "llm": {...}}`), NOT the raw mem0.json dict (which wraps everything in
  mode/oss/user_id). Passing the raw dict makes it construct an *openai*
  embedder and fail on missing api_key.
- `m.search(query, filters={"user_id": ...})` **requires** filters to contain
  at least one of user_id/agent_id/run_id, else ValueError. The plugin's
  `_read_filters()` passes `{"user_id": self._user_id}` — mirror that in any
  manual verification.

## Pitfall #4 — config edits are session-snapshotted

mem0.json (and config.yaml) are read at session start. Mid-session edits do
NOT affect the running gateway or the in-play mem0_search instance — always
tell the user to `/new` or restart the gateway, and verify in a fresh
session.

## Pitfall #5 — mem0.json collection_name lives under vector_store.config

`vector_store` top level only holds `provider`/`config`; the collection name
is `oss.vector_store.config.collection_name`. Reading
`oss.get("vector_store", {}).get("collection_name", fallback)` silently
returns the fallback (old `hermes_memories_v2`) and the probe checks the
WRONG collection — the health script had exactly this bug (fixed 2026-08-10).
Correct read:

```python
coll = oss["vector_store"]["config"]["collection_name"]  # hermes_memories_v2_hybrid
```

## Pitfall #6 — qdrant_client scroll payloads are pydantic Records

`client.scroll(...)` returns `Record` objects whose `.payload` is a pydantic
model, NOT a dict: `p.payload.get("user_id")` raises
`AttributeError: 'Record' object has no attribute 'get'`. Convert first:

```python
pl = p.payload.model_dump() if hasattr(p.payload, "model_dump") else dict(p.payload)
```

Also: mem0_search result `id` is a UUID, while the Qdrant payload `hash` is
the dedup key — don't expect them to match.

## Full-integrity check (beyond the probe)

When the user asks 检索全部记忆 / 完整性 / 列出所有记忆, in addition to the probe
script:
0. **Scroll IS the enumeration** — `mem0_search` is semantic top-k (ranked,
   capped, returns overlapping hits across queries) and cannot list the store.
   For a full list, scroll the ACTIVE collection with `limit=300`, read
   payload["data"], sort by id. Verified 2026-08-15: 53 points listed in one
   pass this way; the earlier claim that "3-4 mem0_search passes enumerate"
   is WRONG for the OSS store.
1. Scroll the ACTIVE collection (`limit=1000, with_payload=True`): verify
   every point's `user_id` matches mem0.json, and required payload keys
   (`data`, `hash`, `created_at`, `updated_at`, `text_lemmatized`) exist on
   100% of points.
2. Dump all `data` values and eyeball coverage (cats, credit-card/ITIN, DNS,
   Surge, NAS...) — confirms no silent loss.
3. Run 3-5 mem0_search probes from different angles (猫 / 美卡ITIN / DNS /
   NAS备份); healthy scores run ~0.3–0.8.
4. Cross-check the backup collection (`hermes_memories_v2`) still exists and
   carries pre-upgrade rows (~69 on 2026-08-10) — it is the rollback copy.
5. Point counts legitimately change between runs (auto-extract writes a few
   entries per session); a few points more/less is NOT data loss.

## Backup & restore (Qdrant → local disk)

**Why:** the NAS full-backup cron (Sunday 03:00) is same-machine — if the NAS
dies, both the live store AND its backup die with it. Since 2026-08-10 this
user also runs a local-Mac backup as the independent fallback.

**Packaged script:** `scripts/backup_qdrant_local.py` (this user's live copy:
`~/.hermes/scripts/hermes_backup_local.py`, cron Sunday 04:30, no-agent,
deliver=local, keeps last 4).

What it does (verified 2026-08-10, counts 44/169 matched live):
- REST-scrolls ALL points (payload **+ vectors**) from the ACTIVE collections
  (`hermes_memories_v2_hybrid` + `hermes_memories_v2_hybrid_entities`) — use
  `with_vector: true` so the dump is restore-capable; hybrid sparse vectors
  serialize fine as `{indices, values}`.
- Copies `mem0.json`, `config.yaml`, `.env` alongside.
- Writes to `~/hermes-backups-local/<YYYYMMDD_HHMMSS>/` with a sha256
  manifest; exit 0 = counts match live, exit 2 = mismatch, exit 3 = failure.
- Keeps the newest N dirs (default 4), prunes the rest.

**Restore path (if the NAS dies):** the collection JSONs are Qdrant-standard
point structures, so recreate the collection on any reachable Qdrant and
upsert `points` from the dump via `PUT /collections/<name>/points`. The
mem0.json copy carries the exact embedder/llm config to recreate the store.

**Verify a backup run:** check exit code and the printed per-collection
`live=N backed_up=N` lines — they must be equal. Point counts legitimately
drift between runs; mismatch at backup time is the signal, not growth over
time.

## Verification checklist

```bash
~/.hermes/skills/hermes/mem0-oss-operations/scripts/mem0_oss_health.py  # exit 0, all [ok]
# then in a fresh session: mem0_search("用户的猫") must return rows
```

## Pitfall #7 — mem0ai version pinning: two files MUST match, lazy refresh skips satisfied specs

> **Stale as of Hermes 0.21.5 (2026-09):** `tools/lazy_deps.py` no longer
> exists — the PM rewrite moved the pin to `pyproject.toml`
> (`optional-dependencies.mem0`) plus the recorded extras in
> `~/.hermes/installs/<id>/facts.json` (`packages.venv.extras`). Check
> `hermes memory status` and `facts.json` before trusting the paths below;
> see Pitfall #9 for the current dependency story.

**Symptom:** manually upgraded mem0ai (e.g. `pip install mem0ai==2.0.18`), but the
next `hermes update` lazy refresh silently reinstalls the old pinned version.

**Root cause:** mem0 is a lazy-installed cloud memory provider whose version is
pinned in **two places that must stay in sync** (enforced by tests):
- `hermes-agent/tools/lazy_deps.py` → `LAZY_DEPS["memory.mem0"] = ("mem0ai==X",)`
- `hermes-agent/pyproject.toml` → `mem0 = ["mem0ai==X"]`
- `plugins/memory/mem0/plugin.yaml` `pip_dependencies: mem0ai>=2.0.10,<3` is only
  a LOWER bound — do NOT edit it when bumping the pin.

**Fix (verified 2026-08-15, 2.0.10 → 2.0.18):** bump BOTH pins to the same target
version. The lazy refresh only installs `_missing_specs()` — specs already
satisfied by the installed version are skipped, so the upgrade survives
`hermes update`.

**Verify:**
```bash
~/.../venv/bin/python -c "
from tools.lazy_deps import feature_specs
from packaging.requirements import Requirement
from importlib.metadata import version
specs = feature_specs('memory.mem0')
req = Requirement(specs[0]); cur = version('mem0ai')
print(cur in req.specifier)   # True = will not be re-pinned
"
```

**Note:** these are local edits to the hermes-agent checkout; `hermes update` may
report a stash/restore or conflict if upstream also touches those files. The local
pin can be dropped once upstream bumps past the target.

## Pitfall #8 — write-path verification: infer=True may return empty results legitimately

When verifying mem0 after an upgrade, `add(..., infer=True)` can return
`{"results": []}` even though the backend is healthy — mem0's extraction LLM
deduplicates/skips content too similar to existing memories (NOT a failure).
Use these two probes together:
- `infer=False` + a unique marker string → confirms raw Qdrant write path
- `infer=True` + content with a distinctive fact (IP/port/marker) → confirms
  LLM extraction path
Clean up each test point via `b.delete(id)` afterwards; verify the final
`points_count` returns to the pre-test value.

## Pitfall #9 — a runtime-environment rebuild silently strips mem0's embedder deps

**Symptom:** every `mem0_search` returns `Mem0 backend not initialized: No
module named 'sentence_transformers'`; gateway.error.log repeats `ERROR
plugins.memory.mem0: Mem0 backend failed to initialize (oss mode)`. Qdrant is
reachable and the points are intact, so the error text's "check that qdrant is
running" hint misleads.

**Root cause:** Hermes's `mem0` extra declares ONLY `mem0ai==2.0.10`
(`pyproject.toml` → `optional-dependencies.mem0`); the embedder's runtime deps
live in mem0ai's own optional extras (`sentence-transformers` under
`mem0ai[extras]`, plus `fastembed`/`onnxruntime` for the sparse BM25 leg and
`spacy` for lemma handling). They were hand-installed into the legacy venv, so
any rebuild of the runtime environment (install/environment migration,
`hermes update`, PM re-sync) produces an environment where the plugin loads but
the backend cannot initialize. Verified 2026-09-26: a 2026-09-25 migration from
the 3.11 checkout venv to the PM-managed 3.14.7 venv dropped all three.

**Repair (the venv has NO pip — it is PM-managed, so use uv):**

```bash
RT=$(ls -d ~/.hermes/installs/*/environments/*/venv | head -1)
uv pip install --python "$RT/bin/python" \
  "sentence-transformers>=5.0.0" fastembed onnxruntime spacy
# spaCy's English pipeline is a SEPARATE wheel, never pulled by the `spacy`
# package itself; mem0 loads en_core_web_sm for lemmas.
uv pip install --python "$RT/bin/python" \
  "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
```

Verified 2026-09-26 on Python 3.14.7 (all four legs installed, e2e search
clean): sentence-transformers 6.1.0, torch 2.14.0, transformers 5.17.0,
fastembed 0.8.1, onnxruntime 1.30.0, spacy 3.8.16, en_core_web_sm 3.8.0.

**Success signal beyond "no traceback":** the e2e probe must stop printing
`fastembed not installed - BM25 keyword search disabled` and `Failed to load
spaCy ... model`, and hybrid scores RISE (measured: 'NAS 备份' 0.679 → 0.730,
'ITIN 美卡' 0.549 → 0.749) because the bm25 sparse leg rejoins the fusion.
Flat scores with a clean import means the sparse leg is still missing.

**Diagnose what is missing per leg** (the plugin still loads, so silent
degradation is the risk):

```bash
$RT/bin/python -c "
for m in ('sentence_transformers','fastembed','onnxruntime','spacy','torch'):
    try: mod=__import__(m); print('  OK  ', m, getattr(mod,'__version__','?'))
    except Exception as e: print('  MISS', m, type(e).__name__)
"
```

**Observation trap (2026-09-26, cost one wasted debugging round):** the
runtime venv path contains TWO 32-hex strings
(`~/.hermes/installs/<32hex>/environments/<32hex>/venv`). Hermes's secret
redaction (`security.redact_secrets: true`) mistakes them for keys, so tool
output renders them as `‹****›` — sometimes inserting a newline and making
the rest of the line look truncated (e.g. a log line reading
`venv: �� ===`). **The FILE is intact; only the displayed copy is mangled.**
Never conclude "my script wrote garbage" from rendered text: verify with
length/boolean probes instead — `wc -c < file` vs `len(open(f,'rb').read())`,
`b'20a5fc77' in raw`, hash prefixes — and trust those.

Without `sentence-transformers` the backend is dead (dense leg needs it).
Without `fastembed`/`onnxruntime` mem0 logs "BM25 keyword search disabled" and
the `hermes_memories_v2_hybrid` collection silently degrades to dense-only
(it defines a `bm25` sparse vector — check
`GET /collections/<name>` → `sparse_vectors`). Without `spacy`, lemma handling
is unavailable.

**Effects are process-cached:** installing the deps does NOT fix the running
gateway — the alive process keeps failing until it restarts. Verify from a
fresh process first (`$RT/bin/python` + `Memory.from_config` + `search(...,
filters={'user_id': ...})`), then have the user restart the gateway
(`hermes gateway start` / `/new`) and re-probe `mem0_search`.

**Recheck after every `hermes update`** — PM syncs the venv to `uv.lock`,
which has no entry for these packages, so a re-sync can prune them again.

**Recurrence is real, and `hermes update` is not the only trigger.** On
2026-10-23 18:03 a PM rebuild created a brand-new environment
(`d41e4747…`, Python 3.14.9) whose venv had all five deps missing; the gateway
restarted at 18:06 onto it and the 18:15 tidy cron died on
`No module named 'sentence_transformers'`. Diagnose by comparing the
`facts.json` venv against the sibling environments — do NOT trust the first
venv glob hit. On
2026-09-28 18:09 a plain PM runtime *rebuild* (new environment id, no update
involved) produced a venv missing the same five deps; the 18:15 memory-tidy
cron then died on `No module named 'sentence_transformers'`. The guard cron
(`mem0_health_guard.sh`, `20 */6 * * *`) only samples at :20 past every sixth
hour, so a :09 rebuild leaves an ~11-minute blind window. Two consequences:
(a) never conclude "the guard is broken" from a failure inside that window —
check the guard log timestamp first; (b) if the tidy cron must run before the
guard fires, repair inline with the uv recipe above.

**Fixed daily collision on this host (verified 2026-11-03 / 11-04 / 11-06):** the PM
rebuild fires at **06:00** and creates a fresh environment whose venv has all five
deps missing; the memory-tidy cron fires at **06:15**, so it loses this race every
time (~15 min window). gateway.error.log shows exactly one
`Mem0 backend failed to initialize` per affected tick. Expect it, verify the env
dir mtime (`stat -f %Sm …/environments/<id>`) against the cron run time before
debugging anything else, and repair inline — the `20 */6` guard at 06:20 covers the
same break five minutes later, so a failed 06:15 report is NOT a guard failure.

**Repair the deps from the cron session itself** when `mem0_search` is dead:
the shipped helper `scripts/mem0_tidy_ops.py` (this skill) wraps the OSS SDK
for enumeration, append-merge (`get` → concatenate → `update`) and delete, so
the tidy job does not have to re-derive `Memory.from_config` (expanded v1.1
block + mandatory `filters={'user_id': ...}`) every six hours. Note that
`Memory.update(memory_id, data)` replaces the point text verbatim in OSS mode
(no LLM rewrite — verify with `stored_len == new_len`), while `m.search`
returns overlapping entity hits, so enumerate with a Qdrant `scroll`, not
search.

**Existing processes are not healed by installing packages** — BUT the blast
radius is ONE session, not the whole process. `initialize()`
(`~/.hermes/plugins/mem0/__init__.py`) runs once per SESSION and is the only
place `self._backend = self._create_backend()` happens, so the session that
was already running when the deps vanished keeps `_backend=None` for its
remaining turns, while the **next session re-initialises and self-heals**.
Verified 2026-10-14: gateway.error.log carried exactly one
`Mem0 backend failed to initialize` line per session start (all at the :15
6-hourly cron tick), and sessions after each repair were healthy on the same
long-lived gateway PID. So do NOT restart the gateway reflexively — repair,
verify from a fresh process, and let the next session pick it up.

**Hard rule: never restart the gateway from inside a cron run.** Cron agents
execute as children of the `ai.hermes.gateway` PID (confirm with
`ps -o ppid,command -p $PPID` walking up, or `launchctl list | grep
ai.hermes.gateway`); a kickstart/kill SIGTERMs your own run before the final
response is delivered, so the user gets no notification at all. Repair
inline, report, and restart from a shell OUTSIDE the gateway only if a fresh
session still fails.

## Related skills

- `memory-maintenance` — cleanup/consolidation of MEMORY.md, USER.md, and
  mem0 entries (hygiene, not health). Disambiguate: this skill is
  diagnostics/ops.
- `hybrid-memory-sidecar` — the *hybrid* plugin (TF-IDF sidecar), a different
  memory backend entirely; do not confuse the two.
- `hermes-memory-plugin` — building NEW memory provider plugins.
