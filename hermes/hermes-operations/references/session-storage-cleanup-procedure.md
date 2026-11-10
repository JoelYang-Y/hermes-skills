# Session-Storage Cleanup — Reference & Session Transcript

Session date: 2026-07-10. Recorded on this machine (`macmini`). All commands verified working.

## Initial symptom (user's report)

> 删除⏸️ Desktop LevelDB 的 sessionOrder：35 条，未清
> ⏸️ sessions/ 目录：4854 个文件（493MB），未清

User believed:
- Desktop sidebar cache (`sessionOrder` in LevelDB) had 35 stale session IDs that wouldn't clear
- `~/.hermes/sessions/` had 4854 session transcripts / jsonl files / 493MB that needed deletion

## Initial inventory — what was actually true

```bash
$ ls ~/.hermes/sessions/ | wc -l
4854

$ ls ~/.hermes/sessions/ | sed 's/.*\.//' | sort | uniq -c
  36 jsonl
4818 json

$ du -sh ~/.hermes/sessions/
493M	/Users/macmini/.hermes/sessions/
```

**The user's "4854 jsonl" claim was wrong.** Only 36 were `.jsonl`; the other 4818 were `.json` (legacy `session_<id>.json` + `request_dump_*.json`).

## Cross-check against state.db

```python
import sqlite3
conn = sqlite3.connect('/Users/macmini/.hermes/state.db')
state_ids = {r[0] for r in conn.execute('SELECT id FROM sessions')}
from pathlib import Path
on_disk = {p.stem for p in Path('/Users/macmini/.hermes/sessions').iterdir() if p.suffix == '.jsonl'}

print(len(state_ids), 'state.db rows')
print(len(on_disk), '.jsonl on disk')
print(len(state_ids - on_disk), 'orphans (state.db has no file)')
print(len(on_disk - state_ids), 'unindexed (.jsonl without state.db row)')
```

Output:
- **9408** state.db sessions rows
- **36** .jsonl on disk
- **9372** orphans (state.db references jsonl that don't exist — virtual sessions for cron/telegram/CLI)
- **0** unindexed (every .jsonl file IS in state.db)

So state.db's 9408 rows are mostly legitimate virtual session rows; deleting 36 .jsonl files makes them all "orphan references" but they were already orphan in 9372 of 9408 cases (virtual sessions).

## Desktop LevelDB state — keys that exist

```bash
$ ls ~/Library/Application\ Support/Hermes/Local\ Storage/leveldb/
000003.log  CURRENT  LOCK  LOG  LOG.old  MANIFEST-000001

$ node inspect-desktop-leveldb.js ~/Library/Application\ Support/Hermes/Local\ Storage/leveldb
# Iterates via ClassicLevel. Full result:
```

47 keys total in the desktop LevelDB. **None of these are `hermes.desktop.sessionOrder`** — that key existed historically but LevelDB compaction had already cleaned it from the table. `strings 000003.log` showed many historical values, but the iterator shows the *current* state: no key for sessionOrder.

```
"hermes.desktop.sessionOrder.manual"      => "\x01false"
"hermes.desktop.sessionPreviews.v1"       => "\x01{}"
"hermes.desktop.lastSessionId"            => "\x0120260710_031757_f9a45f"
"hermes.desktop.workspaceOrder"           => ...
... (44 more, mostly UI state)
```

So the desktop sidebar showing 35 stale entries must have been reading them from `~/.hermes/sessions/` directly (file scan, not from LevelDB's sessionOrder). Clearing LevelDB alone wouldn't have hidden them — clearing the underlying jsonl + .json files would.

## User decision

Asked via `clarify`: confirm scope. User replied "都删了" (delete all). Confirmed back: "I'll clear both sidebar and 493MB sessions/, and leave state.db's sessions table untouched."

## Execution

### Step 1 — Backup both layers

```bash
TS=$(date +%Y%m%d_%H%M%S)
backup_root=~/.hermes/backups/session-cleanup-$TS
mkdir -p "$backup_root"
cp -a ~/.hermes/sessions/ "$backup_root/sessions/"
cp -a ~/Library/Application\ Support/Hermes/Local\ Storage/leveldb/ "$backup_root/leveldb-main/"
cp -a ~/Library/Application\ Support/Hermes/Partitions/hermes-embed/Local\ Storage/leveldb/ "$backup_root/leveldb-partition/"
```

Resulting backup size: 493M (all of sessions/), plus the LevelDB dirs.

### Step 2 — Verify no process holds sessions/ handles

```bash
$ lsof ~/.hermes/sessions/ 2>/dev/null
(empty — no process holds any session jsonl open)
```

### Step 3 — Delete the L1 files

```bash
$ rm -rf ~/.hermes/sessions/* 2>&1 | head -5
(empty — clean removal)
$ ls ~/.hermes/sessions/ | wc -l
0
$ du -sh ~/.hermes/sessions/
0B
```

### Step 4 — Write L2 (LevelDB) — guaranteed empty values

```javascript
// Node + classic-level
const { ClassicLevel } = require('classic-level');

const DIR = process.env.HOME + '/Library/Application Support/Hermes/Local Storage/leveldb';
const KEY_PREFIX = '_file://\x00\x01';  // Chromium LocalStorage origin + SOH separator + key

const db = new ClassicLevel(DIR, { valueEncoding: 'binary' });
await db.open();

// Guarantee an empty sessionOrder (even though key doesn't currently exist)
await db.put(Buffer.concat([Buffer.from(KEY_PREFIX), Buffer.from('hermes.desktop.sessionOrder')]),
             Buffer.from('\x01[]'));
// Same for sessionPreviews.v1
await db.put(Buffer.concat([Buffer.from(KEY_PREFIX), Buffer.from('hermes.desktop.sessionPreviews.v1')]),
             Buffer.from('\x01{}'));
// Delete lastSessionId
await db.del(Buffer.concat([Buffer.from(KEY_PREFIX), Buffer.from('hermes.desktop.lastSessionId')]));
await db.close();
```

Each `put` writes a new log entry; LevelDB's compaction will eventually reap the old value. Sidebar sees the latest (empty) value on next read.

### Step 5 — Verify

```bash
$ node ~/.hermes/skills/hermes/hermes-operations/scripts/inspect-desktop-leveldb.js \
    "$HOME/Library/Application Support/Hermes/Local Storage/leveldb" \
    | grep -E "sessionOrder|sessionPreviews|lastSessionId"
hermes.desktop.sessionOrder        => "\x01[]"
hermes.desktop.sessionPreviews.v1  => "\x01{}"
hermes.desktop.lastSessionId       => (null/gone)
```

## Why plyvel + brew leveldb did NOT work

Tried in order, all failed:

1. `pip install plyvel` against `/opt/homebrew/include/leveldb`:
   ```
   ImportError: dlopen(.../_plyvel.cpython-311-darwin.so, 0x0002):
     symbol not found in flat namespace '__ZTIN7leveldb10ComparatorE'
   ```
   plyvel 1.5.1 was compiled against an older leveldb where the C++ class had a different vtable layout.

2. `ctypes.CDLL('/opt/homebrew/lib/libleveldb.dylib')` + setting argtypes:
   ```
   Script exited with code -11 (SIGSEGV)
   ```
   Even minimal `leveldb_open` segfaults at C++ finalization. The brew-installed leveldb 1.23 has a newer C++ ABI.

3. `leveldbutil` (brew install ships it, version 1.23):
   ```
   $ /opt/homebrew/Cellar/leveldb/1.23_2/bin/leveldbutil --help
   Usage: leveldbutil command...
      dump files...         -- dump contents of specified files
   ```
   Read-only. No `put` or `del`. Inspect tool only.

4. **Node.js + `classic-level`** (v2):
   - `npm install classic-level` in a tmp dir (~1.5s, ~12 packages)
   - Pure-JS LevelDB implementation with RocksDB-style API
   - Supports both iter (read) and put/del (write)
   - Worked first try, every time

## Conclusion / what to verify post-cleanup

After reboot of the Desktop app, the sidebar should:
- Show empty (no sessions in `~/.hermes/sessions/` to enumerate)
- Show empty previews (sessionPreviews.v1 is `{}`)
- Not auto-open the last session (lastSessionId deleted)

If anything looks wrong, restore from backup:

```bash
cp -a ~/.hermes/backups/session-cleanup-20260710_041200/sessions/* ~/.hermes/sessions/
rm -rf ~/Library/Application\ Support/Hermes/Local\ Storage/leveldb/
cp -a ~/.hermes/backups/session-cleanup-20260710_041200/leveldb-main/ \
      ~/Library/Application\ Support/Hermes/Local\ Storage/leveldb/
```

## Files saved

```
~/.hermes/backups/session-cleanup-20260710_041200/
├── sessions/            (493M, 4854 files)
├── leveldb-main/        (~50KB)
└── leveldb-partition/   (~5KB)
```
