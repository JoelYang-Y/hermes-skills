# Update: fetch timeout, entry point, and lazy-backend refresh

Migrated out of SKILL.md to stay under the 100k char cap (2026-09-27).

## Contents
1. Mode E — `platform.X failed to refresh` (lazy backend build failure)
2. Mode F / G detail — HTTP/2 fetch stall and update entry point (2026-09-27 case)

---

### Mode E: `platform.X failed to refresh` (Lazy Backend Build Failure)

#### Symptom
`hermes update` finishes with `✓ Update complete!` and `✓ Service restart requested` — looks healthy. But `~/.hermes/logs/update.log` contains repeated ⚠ lines like:
```
⚠ platform.matrix failed to refresh: pip install failed: __
  File "/private/var/folders/.../setuptools/..."
  ...
```
appearing **for many consecutive updates** (we've seen 28+ in a row). Each one says "Backends keep their previously-installed version; rerun `hermes update` once the upstream issue is resolved." Rerunning does nothing — same failure.

#### Root Cause
The `tools/lazy_deps.py` registry maps a platform name (e.g. `platform.matrix`) to a tuple of pip packages that get installed on-demand the first time that platform is enabled. The failure log line `pip install failed: __` is **truncated by the logger** — the real error is below it. Common root causes:

1. **C-extension build failure from a missing system toolchain.** The most common offender is `mautrix[encryption]` → `python-olm` → tries to `make static` inside a libolm git submodule. Fails with `subprocess.run(['make', 'static'])` non-zero exit. macOS fix: `xcode-select --install` (provides make + CLT headers). On a clean machine, libolm's bundled submodule may also need a manual `git submodule update --init --recursive` inside the python-olm source tree.
2. **PyPI package renamed or removed.** A new Hermes version references a package no longer on the index. Fix: track the upstream issue and wait for a fix, OR disable the platform in `config.yaml` (see option A below).
3. **Version pin conflict.** `lazy_deps.py` pins specific versions that may not resolve on the current Python. Fix: update the pin or install a newer `mautrix` without the `[encryption]` extra (which avoids pulling `python-olm` entirely).

#### Triage Workflow

**Step 1 — Find the failing backend's package list:**
```bash
grep -A 6 '"platform.matrix"' ~/.hermes/hermes-agent/tools/lazy_deps.py
# Reveals the full pip pin tuple, e.g.:
#   "platform.matrix": (
#       "mautrix[encryption]==0.21.0",
#       "aiosqlite==0.22.1",
#       "asyncpg==0.31.0",
#       "aiohttp-socks==0.11.0",
#   ),
```

**Step 2 — Reproduce the install manually to get the FULL error (not the truncated log line):**
```bash
~/.hermes/bin/uv pip install 'mautrix[encryption]==0.21.0' 'aiosqlite==0.22.1' 'asyncpg==0.31.0' 'aiohttp-socks==0.11.0' 2>&1 | tail -40
```
The log only shows `pip install failed: __` because the logger swallows everything after the first failure. The manual install reveals the actual stack trace.

**Step 3 — Pick a remediation path:**

| Path | When to choose | Tradeoff |
|---|---|---|
| **A. Disable the platform in `config.yaml`** | You don't actually use this platform (e.g. Matrix bridge) | Cleanest. Add `platforms.matrix.enabled: false` or equivalent. Stops the ⚠ forever. |
| **B. Install `xcode-select --install` and retry** | The error is `make` / C compilation / missing headers | ~5 min on macOS. Fixes the python-olm class of failures permanently. |
| **C. Install without the failing extra** | The bad package is in an extra like `[encryption]` | Hack: requires editing `lazy_deps.py` to drop the extra. |
| **D. Wait for upstream fix** | The package was renamed/removed upstream | Slowest. |

For platform.matrix specifically, the historical fix has been B (install CLT). For a new platform that was just added and references a removed PyPI package, A is the right call.

**Why this trips people up:**
- The update reports `✓ Update complete!` — the failure is non-fatal. People think "the update worked" and never check the log.
- The `⚠` symbol is easy to skim past, especially when surrounded by `✓` lines.
- The `__` in the log line is misleading — it looks like the logger is broken, but it's actually truncating for compactness. Always re-run the install manually to see the real error.

#### Verification
After remediation, trigger a fresh refresh and confirm the ⚠ is gone:
```bash
# Re-run the full update (forces a fresh backend refresh)
~/.hermes/hermes-agent/venv/bin/hermes update 2>&1 | tail -20
# Then grep the log for the platform name:
tail -50 ~/.hermes/logs/update.log | grep "platform.matrix"
# Should NOT show "failed to refresh"
```

For a known reference transcript (full error from the mautrix/python-olm build failure on this machine, 2026-06-12), see `references/platform-matrix-build-failure-2026-06-12.md` (includes the full uv pip stack trace, the lazy_deps.py registry entry, and the A/B/C/D remediation table).

#### Pitfall: there's no `hermes backends refresh` subcommand
If you try to force-refresh backends in isolation, you'll discover:
```bash
hermes backends refresh --all
# → "argument command: invalid choice: 'backends'"
```
There is **no** `hermes backends` subcommand. The lazy-backend refresh is an internal step of `hermes update`'s full pipeline, and it's only triggered when the update actually pulls new commits. The "Already up to date!" early-exit path **skips the refresh entirely** — so to actually exercise a backend refresh you need new commits in `origin/main`, or you can run the manual `uv pip install` from Step 2 above.

---


---

## Mode F detail — HTTP/2 fetch stall, measured 2026-09-27

### Observed symptom chain
Cron job `Hermes 自动更新检查` (0 */6 * * *) alerted every 6h:
`git fetch timed out after 300s with no response from the remote`; local checkout sat
896 commits behind.

### Measurements that isolated the cause
| probe | result |
|---|---|
| `curl https://github.com` | 200 in 0.6s (bypassed nothing — it is short) |
| `curl .../info/refs?service=git-upload-pack` | 200 but 8.2s to first byte |
| `git ls-remote` (default HTTP/2) | hangs, 30s+ no response |
| `git ls-remote` (`-c http.version=HTTP/1.1`) | rc=0 in 8.8s |
| `GIT_CURL_VERBOSE` HTTP/2 trace | POST sent, `upload completely sent off: 109 bytes`, then silence |
| codeload tarball throughput | 8.4 MB/s (bandwidth is fine) |
| `git fetch --no-tags origin main` after fix | rc=0, 1m33s first run, then 1-13s |

### Gotchas hit while diagnosing
- `git rev-list --count HEAD..origin/main` grows while you work — this repo merges constantly
  (916 → 919 commits within minutes). Do not treat a rising count as a regression.
- The update's fetch runs nested (`git fetch origin main` → `git -c fetch.negotiationAlgorithm=noop
  fetch origin --no-tags --no-write-fetch-head --recurse-submodules=no --filter=blob:none --stdin`);
  seeing those args in `ps` does not mean the update code passed them.
- `pgrep -fl dashboard` may miss a live dashboard process whose cmdline is a long `python3 -I -c` blob;
  confirm with `ps -p <pid>`.
- A monitoring command containing gateway lifecycle words can be blocked by the gateway's own safety
  guard (`Blocked: command ... cannot restart ... gateway from inside the gateway process`) — that is
  protection firing, not a broken tool. Phrase probes without those verbs.

### Post-update verification (this case)
919 commits applied (v0.21.5+2453.gd0288be → +3372.g60e531c). `hermes gateway status` →
`✓ Service definition matches the current Hermes install`, `✓ Gateway is supervised by launchd`.
mem0 was NOT pruned: `sentence_transformers / fastembed / onnxruntime / spacy / mem0` all import, and a
live `mem0_search` returned hits. Residual: a dashboard process may need a relaunch
(`manual restart still pending`).
