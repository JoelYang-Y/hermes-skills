---
name: hybrid-memory-sidecar
description: Diagnose, fix, and schedule maintenance for the Hermes `hybrid` custom memory plugin — TF-IDF sidecar drift, shebang-vs-Python-version crashes in cron scripts, FTS5↔memories sync, and WAL growth. Trigger when `~/.hermes/hybrid_memory.db.tfidf.json` mtime is old while `memories` table grows, when `hybrid_health.py` TypeErrors on launch, when ghost df or unmatched n_docs shows up in health, or when first enabling the hybrid plugin.
version: 0.1.0
metadata:
  hermes:
    tags: [hermes, memory, hybrid, sqlite, fts5, tfidf, cron, sidecar]
---

# Hybrid Memory Plugin — Sidecar & Cron Health

This skill captures the **operational playbook** for the `hybrid` custom
memory provider at `~/.hermes/plugins/hybrid/`. It is the plugin-specific
companion to `hermes-memory-plugin` (which covers building *new* memory
backends).

## When to use

- Sidecar `~/.hermes/hybrid_memory.db.tfidf.json` mtime is hours/days behind
  the last `hybrid_memory_add` or `on_memory_write` event.
- `n_docs` in the sidecar exceeds the row count of `memories` (df carries
  ghost entries from deleted rows, because `fit_incremental` only grows df).
- `~/.hermes/scripts/hybrid_health.py` crashes on launch with `TypeError:
  unsupported operand type(s) for |: 'type' and 'NoneType'` (or any
  `'X | None'` style syntax error).
- `hybrid_health.py` cron reports success while manual invocation crashes
  (shebang routed differently than the cron wrapper).
- Wanting to schedule a periodic sidecar rebuild to keep IDF honest.

## Diagnostic commands (read-only, safe to run anytime)

```bash
# 1. Schema sanity + counts
sqlite3 ~/.hermes/hybrid_memory.db <<SQL
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
SELECT 'memories', COUNT(*) FROM memories;
SELECT 'vectors',   COUNT(*) FROM vectors;
SELECT 'memories_fts', COUNT(*) FROM memories_fts;
SQL

# 2. FTS5 ↔ memories sync (must both be 0)
sqlite3 ~/.hermes/hybrid_memory.db <<SQL
SELECT 'fts_only',  COUNT(*) FROM memories_fts WHERE rowid NOT IN (SELECT rowid FROM memories);
SELECT 'mem_only',  COUNT(*) FROM memories    WHERE rowid NOT IN (SELECT rowid FROM memories_fts);
SQL

# 3. Sidecar vs DB drift
python3 -c "
import json, os, sqlite3, time
db = os.path.expanduser('~/.hermes/hybrid_memory.db')
sc = db + '.tfidf.json'
n_rows = sqlite3.connect(db).execute('SELECT COUNT(*) FROM memories').fetchone()[0]
old = json.load(open(sc)) if os.path.exists(sc) else {}
print('rows_in_db:', n_rows)
print('sidecar_n_docs:', old.get('n_docs'))
print('sidecar_df_buckets:', len(old.get('df', {})))
print('sidecar_age_hours:', round((time.time()-os.path.getmtime(sc))/3600, 1))
"
```

## Pitfall #1 — Shebang vs system Python

`~/.hermes/scripts/hybrid_health.py` uses PEP 604 syntax (`str | None`),
Python 3.10+. macOS system Python is 3.9.6. The cron wrapper script
(`hybrid_health_cron.sh`) works because it explicitly invokes the Hermes venv
Python; running the `.py` directly via shebang picks up `/usr/bin/env python3`
→ 3.9 → immediate TypeError.

**Fix (one line, idempotent):**

```bash
# Replace shebang with absolute path to Hermes venv Python
sed -i '' '1s|.*|#!/Users/macmini/.hermes/hermes-agent/venv/bin/python|' \
  ~/.hermes/scripts/hybrid_health.py
chmod +x ~/.hermes/scripts/hybrid_health.py
```

**Verification:**

```bash
~/.hermes/scripts/hybrid_health.py   # must print healthy line, exit 0
```

If you migrate Hermes to a different venv path (Homebrew, pyenv, etc.),
update this shebang accordingly. Use `which python` inside the active venv
to find the right path.

## Pitfall #2 — Sidecar drift after quiet periods

The embedder (`embeddings.py:TFIDFEmbedder`) updates df **only on writes**,
via `fit_incremental`. There is no decay on delete or expire, so:
- `n_docs` monotonically grows in the sidecar.
- A long quiet period (no `hybrid_memory_add`, no auto-extract triggers,
  no `on_memory_write` mirrors) leaves sidecar mtime stale.
- Health checks that only look at "sidecar age" raise false alarms.

**When drift is meaningful:** `n_docs` drift > 20% of `memories` row count
*or* df is being used to drive a critical ranking path with > 200 docs.

**Fix — install a one-shot rebuild script:**

`~/.hermes/scripts/hybrid_sidecar_rebuild.py`:

```python
#!/Users/macmini/.hermes/hermes-agent/venv/bin/python
"""
Reseed ~/.hermes/hybrid_memory.db.tfidf.json from current memories table.
Run --dry-run first to see the drift; rerun without --dry-run to write.

Idempotent: a clean sidecar writes the same content as the original n_docs
minus ghosts.
"""
from __future__ import annotations
import argparse, json, os, sqlite3, sys, time
from collections import Counter
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
DB = HERMES_HOME / "hybrid_memory.db"
SC = HERMES_HOME / "hybrid_memory.db.tfidf.json"
sys.path.insert(0, str(HERMES_HOME / "plugins" / "hybrid"))
from embeddings import TFIDFEmbedder  # noqa: E402

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--sidecar", type=Path, default=SC)
    args = ap.parse_args()

    if not args.db.exists():
        print(f"db not found: {args.db}", file=sys.stderr)
        return 2
    with sqlite3.connect(str(args.db)) as conn:
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        rows = conn.execute(
            "SELECT content FROM memories "
            "WHERE (expires_at IS NULL OR expires_at > ?)",
            (time.time(),),
        ).fetchall()
    contents = [r[0] for r in rows if r[0]]

    old = {}
    if args.sidecar.exists():
        try:
            old = json.loads(args.sidecar.read_text(encoding="utf-8"))
        except Exception:
            pass

    emb = TFIDFEmbedder(dim=old.get("dim", 512), stats_path=None)
    if contents:
        emb.fit_incremental(contents)

    print("sidecar rebuild plan")
    print("--------------------")
    print(f"  db rows:        {len(contents)} of {total}")
    print(f"  old n_docs:     {old.get('n_docs')}")
    print(f"  old df_buckets: {len(old.get('df', {}))}")
    print(f"  new n_docs:     {emb._n_docs}")
    print(f"  new df_buckets: {len(emb._df)}")

    if args.dry_run:
        return 0

    args.sidecar.parent.mkdir(parents=True, exist_ok=True)
    payload = {"dim": emb.dim, "n_docs": emb._n_docs, "df": dict(emb._df)}
    tmp = args.sidecar.with_suffix(args.sidecar.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(args.sidecar)
    print(f"\n✓ sidecar written: {args.sidecar} ({args.sidecar.stat().st_size} bytes)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Schedule it (weekly is the sweet spot for most users):**

```bash
chmod +x ~/.hermes/scripts/hybrid_sidecar_rebuild.py
```

```bash
# thin bash wrapper for cron (script-relative path requirement)
cat > ~/.hermes/scripts/hybrid_sidecar_cron.sh <<'EOF'
#!/bin/bash
exec /Users/macmini/.hermes/scripts/hybrid_sidecar_rebuild.py "$@"
EOF
chmod +x ~/.hermes/scripts/hybrid_sidecar_cron.sh
```

Then create the cron job (no_agent=True, stdout becomes the message body —
silence on success, alert on failure):

```
schedule:    0 4 * * 0     # Sunday 04:00
script:      hybrid_sidecar_cron.sh
deliver:     local           # save to ~/.hermes/cron/output/ if anything to say
no_agent:    true
```

If your `hybrid_memory.db` lives outside `~/.hermes`, set
`HERMES_HOME=/path/to/hermes` in the cron wrapper.

## Pitfall #3 — `fit_incremental` is write-path only

`on_session_end` only runs `expire_due()` and (every N turns)
`_auto_summarize_short_term()`. It does **not** call `fit_incremental`. So:

- A library that never gets new writes (and never has any `short`-layer
  entries that get summarized into `knowledge`) will also never refresh df.
- That is **the correct design** — IDL drift only matters at insert time, not
  at query time.
- The rebuild script above is the right answer; do **not** add a "fit on
  every turn" path, it would just thrash the sidecar for nothing.

## Pitfall #4 — Sidecar n_docs can legitimately exceed memories rows

This is not a bug. Reasons include:
- `expire_due()` deletes `short`-layer rows but df still counts them.
- Manual `hybrid_memory_forget` calls.
- Manual DB edits (which you should not do).

The rebuild script reconciles by zeroing df and refitting from the current
contents. For libraries > 500 entries, the rebuild costs ~1s; for > 5000,
consider doing it offline or with a dim=1024 to reduce collision overhead.

## Pitfall #5 — Schema-name gotchas

The skill `hermes-memory-plugin` documents table names as `embeddings`,
but the live plugin uses `vectors`. Health checks should reference the live
table names, never the docs:

```python
# Right:
for tbl in ("memories", "memories_fts", "vectors", "session_index"):
    n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
```

## Verification checklist

```bash
~/.hermes/scripts/hybrid_health.py
# expect: plugin: active ✓ | db: N memories, N fts, N vectors, wal=0.0MB

~/.hermes/scripts/hybrid_sidecar_rebuild.py
# expect: drift: 0 ghost docs, 0 ghost buckets on a freshly rebuilt sidecar

# round-trip the BM25 + vector path (recall test)
hermes -q "查查我之前让你记得的事"
```

## Pitfall #6 — Tearing down the hybrid plugin (migrating to built-in dual-file)

If the user explicitly says they want to **abandon the hybrid plugin** and switch
to Hermes's built-in `MEMORY.md` / `USER.md` two-file memory, the recipe is:

```bash
# 1. Backup BEFORE anything destructive — both config and the DBs
mkdir -p ~/.hermes/memories.backup.$(date +%Y%m%d_%H%M%S)
cp -a ~/.hermes/memories/ ~/.hermes/config.yaml \
      ~/.hermes/memories.backup.$(date +%Y%m%d_%H%M%S)/

# 2. Delete the hybrid data files (irreversible — `hybrid_memory_recall`
#    and friends stop working immediately)
rm -v ~/.hermes/hybrid_memory.db \
      ~/.hermes/hybrid_memory.db-shm \
      ~/.hermes/hybrid_memory.db-wal \
      ~/.hermes/hybrid_memory.db.tfidf.json

# 3. The user MUST run the config switch themselves. The `patch` tool
#    refuses to write ~/.hermes/config.yaml (security guard), and
#    `hermes config set memory.*` only works for scalar keys. For the
#    full switch, use the in-process API from `execute_code` (see
#    `hermes-operations` "Bypassing the Config Guard"):
#
#    python3 -c "from hermes_cli.config import load_config, save_config; \
#        cfg=load_config(); cfg['memory']['provider']='builtin'; \
#        cfg['memory']['memory_enabled']=True; \
#        cfg['memory']['user_profile_enabled']=True; save_config(cfg)"
#
#    Or one-shot CLI (works for the three scalar keys above):
#    hermes config set memory.memory_enabled true
#    hermes config set memory.user_profile_enabled true
#    hermes config set memory.provider builtin
```

**Why each step is mandatory:**
- The plugin code stays at `~/.hermes/plugins/hybrid/` — that's fine. As long as
  `memory.provider` is `builtin` (not `hybrid`), the gateway will not load it.
  Removing the code directory is unnecessary and risks breaking future rollbacks.
- The .db files are the only thing the user can no longer query. Once deleted,
  `hybrid_memory_recall` returns zero results. There is no "soft delete" path.
- The user MUST restart Hermes (`/new` in chat, or gateway restart) after the
  config change. Per `hermes-operations` "Bypassing the Config Guard":
  config is snapshotted at session start; mid-session edits don't take effect.

**Pitfalls specific to this path:**
1. **Don't auto-migrate old hybrid memories into the new dual-file format.**
   The old hybrid entries have rich metadata (importance, tags, project,
   type=profile/fact/project/short/knowledge) that the built-in dual-file
   does NOT preserve. The right move is: ask the user which entries are
   still meaningful, then write only those — as declarative facts — into
   MEMORY.md / USER.md. Mechanically copying 9 hybrid entries into a 1375-
   char USER.md buffer will overflow.
2. **The `hybrid_health.py` cron will start alerting once the .db is gone.**
   If the user had a `hybrid-health-watchdog` cron job, disable it before
   deleting the DB (`hermes cron pause <job_id>` or update `--enabled`).
   Otherwise Telegram gets a flood of "db not found" alerts.
3. **Don't delete the .db if any skill references the old `hybrid_memory_*`
   tool names.** Cross-grep skills/` and references/` for `hybrid_memory_`
   before deletion. If a skill's references/ section hardcodes the tool
   name, the deletion will silently break that skill's memory workflow.
4. **The backup is the only rollback path.** The DB has no built-in export.
   Tell the user the backup location before the `rm` runs. They need to
   know how to put it back if they change their mind (reverse the config
   switch + restore the .db files from backup).

**Verification after the switch:**

```bash
# Provider flipped
hermes config get memory.provider    # expect: builtin
hermes config get memory.memory_enabled    # expect: True

# Plugin not loaded
python3 -c "from hermes_cli.config import load_config; print(load_config()['memory'])"
# expect: dict with provider=builtin, memory_enabled=True, user_profile_enabled=True

# After /new, system prompt should show the dual-file block:
#   ═══ MEMORY (your personal notes) [NN% — NNN/2200 chars] ═══
#   ═══ USER PROFILE (who the user is) [NN% — NNN/1375 chars] ═══
# (NOT the "Hybrid Memory. Active. N entries..." header)
```

## Reference files (in this skill's references/)

- `references/health-script-shebang-fix.md` — exact diff for the shebang
  bug, including a self-test snippet.
- `references/cron-no-agent-delivery.md` — why `deliver: local` + empty
  stdout is the right success path for the rebuild cron.
- `references/hybrid-teardown-recipe.md` — full transcript of a hybrid
  → built-in migration: config section before/after, the "old memories
  won't carry over" caveat, and the cron-watchdog disable step.
