# `platform.matrix` build failure — 2026-06-12 transcript

Session in which the user's `hermes update` was silently failing `platform.matrix`
refresh on every run for ~28 consecutive updates, while still reporting
`✓ Update complete!`. The user was being repeatedly notified in Telegram that
"the update failed" and asked me to look at it.

## Symptom (as user saw it)

Telegram notifications:
> ⚠️ Hermes 更新失败
> ...
> `~ hermes-agent==0.16.0 (from file:///Users/macmini/.hermes/hermes-agent)`

The user said: "为什么更新失败" / "又提示更新失败了" / "你眼瞎吗"

## My first (wrong) read

I looked at the `tail -30 update.log` and saw `✓ Code updated!` repeatedly, plus
`✓ Update complete!` at the end. I declared it healthy and the user pushed back:
"你眼瞎吗". I had missed the ⚠ in the middle of the log.

## Correct read (grep over the whole log)

```bash
grep -nE "fail|FAIL|error|ERROR|abort|fatal|✗ |⚠ " ~/.hermes/logs/update.log | grep -v "✓ " | tail -30
```

Returned 28 consecutive lines like:
```
71532:  ⚠ platform.matrix failed to refresh: pip install failed: __
71608:  ⚠ platform.matrix failed to refresh: pip install failed: __
...
72956:  ⚠ platform.matrix failed to refresh: pip install failed: __
```

The `__` is the logger swallowing everything after the first line of the error.

## Root cause (revealed by manual repro)

```bash
grep -A 6 '"platform.matrix"' ~/.hermes/hermes-agent/tools/lazy_deps.py
```

Output:
```python
"platform.matrix": (
    "mautrix[encryption]==0.21.0",
    "aiosqlite==0.22.1",
    "asyncpg==0.31.0",
    "aiohttp-socks==0.11.0",
),
```

Then:
```bash
~/.hermes/bin/uv pip install 'mautrix[encryption]==0.21.0' 'aiosqlite==0.22.1' 'asyncpg==0.31.0' 'aiohttp-socks==0.11.0' 2>&1 | tail -40
```

Revealed the real error:
```
File "/private/var/folders/0w/26c256_977z6s23j_y7dzyn00000gn/T/pip-build-env-xoa7xhhn/overlay/lib/python3.11/site-packages/cffi/setuptools_ext.py",
  line 26, in execfile
      exec(code, glob, glob)
    File "olm_build.py", line 51, in <module>
      subprocess.run(["make", "static"], cwd="libolm", check=True)
    File ".../subprocess.py", line 571, in run
        raise CalledProcessError(retcode, process.args,
subprocess.CalledProcessError: Command '['make', 'static']' returned
non-zero exit status 2.

hint: `python-olm` (v3.2.16) was included because `mautrix[encryption]` (v0.21.0) depends on `python-olm`
hint: Build failures usually indicate a problem with the package or the build environment
```

So the chain is:

```
platform.matrix (lazy backend in tools/lazy_deps.py)
  → mautrix[encryption]==0.21.0
    → python-olm==3.2.16 (transitive, pulled by [encryption] extra)
      → libolm (git submodule, not present in the sdist)
        → `make static` fails
```

The sdist of `python-olm==3.2.16` does NOT include the `libolm/` git
submodule. The build script assumes the submodule is present (via a
`git submodule update --init --recursive` in the source tree, which pip
does not run). The `make static` call then fails because there's no
`libolm/` directory to compile.

The error is **environment-specific** (depends on the python-olm sdist
not bundling libolm) but reproducible. It happens on any machine where
`mautrix[encryption]` is being installed for the first time from a
clean venv.

## Remediation options I offered the user

| Option | Effort | Effect |
|---|---|---|
| A. `hermes config set platforms.matrix.enabled false` (or equivalent in config.yaml) | 30 sec | Stops the ⚠ forever. User said they don't use Matrix bridge, so this is the right call. |
| B. `xcode-select --install` to get make + CLT, then `git submodule update --init --recursive` inside the python-olm source tree, then retry | ~10 min | Fixes python-olm class of failures permanently. Necessary if the user actually uses Matrix with E2EE. |
| C. Drop the `[encryption]` extra from `lazy_deps.py` and use plain `mautrix` | 5 min edit | Avoids python-olm entirely. E2EE doesn't work. |
| D. Wait for upstream | n/a | Slowest. |

## Why I had to read the whole log

Two structural reasons this hides in `tail -30`:

1. The update has ~30+ steps. A `✓ Update complete!` at the end visually
   overshadows a `⚠` in the middle. The eye is drawn to the bottom of the
   terminal output.
2. The truncation `pip install failed: __` makes the line look incomplete
   in a way that suggests a logging bug, not a real failure. The natural
   instinct is to scroll past it.

A whole-file grep for `⚠` makes both failure modes impossible to miss.

## Cross-references

- SKILL.md Mode E in hermes-operations — the triage workflow
- `~/.hermes/hermes-agent/tools/lazy_deps.py` — the source of truth for
  which platforms exist and what packages they pull
- `~/.hermes/logs/update.log` — append-only history; back up before
  truncating

## Tags

`platform.matrix`, `python-olm`, `mautrix`, `libolm`, `lazy backend`,
`make static`, `cffi`, `build failure`, `truncated log line`,
`whole-log grep discipline`
