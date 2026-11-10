---
name: open-webui-macos
description: Install and run open-webui on macOS (Mac mini) using pyenv + venv, bypassing PyPI Python version metadata restrictions and resolving runtime dependency issues.
version: 1.0.0
author: Hermes Agent
license: MIT
tags: ["open-webui", "macos", "pyenv", "python", "homebrew"]
related_skills: []
---

# open-webui on macOS

## Prerequisites

- macOS (this guide was written for Mac mini)
- Homebrew installed
- Internet connection

## The Problem

`pip install open-webui` fails on modern Python versions due to PyPI metadata restrictions, and even when it installs, the app fails at runtime with missing `greenlet`.

## Installation Steps

### 1. Install pyenv

```bash
brew install pyenv
```

Add to `~/.zshrc` if not already present:
```bash
echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc
source ~/.zshrc
```

### 2. Install Python 3.11 via pyenv

open-webui's PyPI package metadata declares `<3.13.0a1`, which blocks Python 3.13 and 3.14 at pip install time. Python 3.11 is the recommended workaround.

```bash
pyenv install 3.11.12
```

### 3. Create a virtual environment with Python 3.11

```bash
python3.11 -m venv ~/open-webui-env311
```

Or using the full pyenv path:
```bash
~/.pyenv/versions/3.11.12/bin/python3 -m venv ~/open-webui-env311
```

### 4. Activate the venv and install open-webui

```bash
~/open-webui-env311/bin/pip install --upgrade pip
~/open-webui-env311/bin/pip install open-webui
```

### 5. Install greenlet (runtime dependency)

**IMPORTANT:** open-webui uses async SQLAlchemy which requires greenlet. This is NOT automatically installed as a dependency and causes runtime failure:

```
ValueError: the greenlet library is required to use this function
No module named 'greenlet'
```

Fix:
```bash
~/open-webui-env311/bin/pip install greenlet
```

### 6. Start open-webui

```bash
cd ~
~/open-webui-env311/bin/open-webui serve
```

The app will start on **http://localhost:8080**. On first access, register an admin account.

## Troubleshooting

### Symptom: `pip install open-webui` fails with version conflict

**Cause:** PyPI metadata for open-webui restricts `python_version < 3.13.0a1`. Python 3.13 and 3.14 are rejected even if the package might technically work.

**Fix:** Use Python 3.11 via pyenv (step 2 above).

### Symptom: Runtime error `ValueError: the greenlet library is required`

**Cause:** greenlet is a runtime dependency of open-webui's async SQLAlchemy usage, but is not listed as a formal dependency so pip doesn't install it automatically.

**Fix:** `pip install greenlet` (step 5 above).

### Symptom: `pyenv: python3.11: command not found` after installation

**Cause:** pyenv not initialized in current shell.

**Fix:** Run `eval "$(pyenv init -)"` or start a new terminal session.

### Verify Python version

```bash
~/open-webui-env311/bin/python --version
# Should output: Python 3.11.x
```

### Check if open-webui is running

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080
# 200 = running, 000 = not running
```

## Recovery / Re-bootstrap (canonical)

The **current canonical** install path is the bundled bootstrap script, not the manual pyenv flow above. It is idempotent: it re-creates the venv, the launcher, the launchd plist, and re-runs the alembic migrations on every run.

```bash
bash ~/.hermes/hermes-agent/scripts/setup_open_webui.sh
```

What the script does (and the manual flow does NOT):
- Installs into `~/.local/open-webui-venv` (NOT `~/open-webui-env311` — that older path is from the manual flow and is now legacy)
- Writes a launcher at `~/.local/bin/start-open-webui-hermes.sh` that exports the right env vars (Hermes API base URL, API key, offline mode, RAG disabled, etc.)
- Registers a **launchd plist** at `~/Library/LaunchAgents/ai.openwebui.hermes.plist` with `KeepAlive: true` — launchd auto-restarts the service if it dies
- Configures it to talk to the Hermes OpenAI-compatible API at `http://127.0.0.1:8642/v1` (the `API_SERVER_KEY` in `~/.hermes/.env` is the bearer token)
- Runs `hermes gateway restart` itself before bringing Open WebUI up

### When the service has "crashed" (HTTP 000, no process)

**Before this session:** assumed something was wrong with the venv or app config.

**Root cause usually seen:** the `~/.local/` tree gets wiped (manual cleanup, time-machine restore, etc.) and the launchd plist points at a launcher that no longer exists. Launchd tries to start the service, the launcher script 404s, launchd gives up after retries, and the port sits empty.

**Fix:** just re-run the bootstrap. Don't try to diagnose or hand-fix:

```bash
bash ~/.hermes/hermes-agent/scripts/setup_open_webui.sh
```

Watch the log to confirm a clean start (alembic migrations + `Uvicorn running on http://0.0.0.0:8080`):

```bash
tail -f ~/.hermes/logs/openwebui.log
```

Cold start takes ~30s because alembic walks ~30 schema upgrades. The `error.log` will show the migration steps; that's normal, not an error.

### Diagnose launchd state

```bash
# Is the plist registered and what state is it in?
launchctl list | grep openweb
# Look for PID + last-exit-status. PID 0 / negative exit = crash loop.

# Is the plist even present?
ls -la ~/Library/LaunchAgents/ai.openwebui.hermes.plist

# Manually start the service in the foreground to see real errors
bash ~/.local/bin/start-open-webui-hermes.sh
# (use terminal(background=true), NOT shell &)
```

If you see `address already in use` from a manual foreground launch, the plist-managed service is already up — check `lsof -iTCP:8080 -sTCP:LISTEN` instead of double-launching.

### Verifying the API link to Hermes

```bash
# Web UI itself
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/         # expect 200
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/health   # expect 200

# The OpenAI-compatible API it serves to the browser
curl -sS http://127.0.0.1:8080/api/v1/models -H "Authorization: Bearer $API_SERVER_KEY"
# expect: {"data":[...]} — if you get 401, the API key in ~/.hermes/.env was rotated
# and the webui needs to be told the new key (admin UI → External Connections) OR
# the launcher needs to be re-sourced.
```

## Upgrading
## Upgrading

```bash
# 1. Kill the running instance
lsof -i :8080 | grep LISTEN | awk '{print $2}' | xargs kill
# 2. Upgrade in the venv (include greenlet in upgrade)
~/open-webui-env311/bin/pip install --upgrade open-webui greenlet

# 3. Restart in background — always use terminal(background=true), NOT shell-level &
~/open-webui-env311/bin/open-webui serve   # terminal(background=true)
# 4. Verify: curl -s -o /dev/null -w "%{http_code}" http://localhost:8080  → 200
```

**Shell-level `&` does NOT work** — Hermes will reject it with "Foreground command uses '&' backgrounding. Use terminal(background=true)." Always use `terminal(background=true)` for the daemon step.

## Connecting OpenWebUI to Hermes (API Server)

Hermes exposes an OpenAI-compatible API on port **8642**, but requires an API key:

**1. Add to `~/.hermes/.env`:**
```
API_SERVER_KEY=your-secret-key
```

**2. Restart Hermes gateway** so api_server picks up the key:
```bash
ps aux | grep hermes | grep gateway # find PID
kill <PID>
# then restart via whatever startup method is configured
```

**3. Verify api_server is listening:**
```bash
lsof -i :8642 -n # should show LISTEN on127.0.0.1:8642
```

**4. In OpenWebUI admin settings → External API → add endpoint:**
- URL: `http://127.0.0.1:8642`
- API Key: the `API_SERVER_KEY` value you set

Without `API_SERVER_KEY`, api_server refuses to start with: `API_SERVER_KEY is required for the API server`.

**Note:** The venv `~/open-webui-env311` already exists from the initial install. If it exists, skip steps 1–3 of the Installation section and go straight to upgrade command above.

## Architecture Notes

- Uses dedicated venv (`~/open-webui-env311`) rather than system Python or conda
- Python 3.11 via pyenv (not Homebrew Python) to have precise version control
- Homebrew's Python 3.14 is set as system default in `~/.zshrc` but open-webui uses the venv's 3.11
- greenlet is the only known missing runtime dep not caught by pip
- Always include `greenlet` in the upgrade command — it is a runtime dep that breaks silently if not upgraded alongside open-webui

## Verification

After startup, open-webui should be accessible at **http://localhost:8080**. First-run requires registration. After that, you can connect Ollama (local models) or configure external API providers (MiniMax, OpenAI, etc.) in the admin settings.
