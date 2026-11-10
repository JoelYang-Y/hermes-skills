---
name: hermes-telegram-voice
description: Auto TTS for Telegram — MiniMax primary, Edge TTS fallback on exhaustion, midnight quota reset. Fully transparent to users.
triggers:
  - auto TTS voice telegram
  - minimax tts exhausted fallback edge
  - telegram voice auto reply
---

# Hermes Telegram Voice TTS

Auto-generates Telegram voice bubbles on agent replies. Fully transparent — no manual intervention needed.

## Architecture: Fail-Driven Fallback

MiniMax has **no public quota/balance API** (all `/remaining`, `/quota`, `/balance` endpoints return 404). Detection is therefore **fail-driven**: MiniMax fails with 1004/login fail → mark exhausted → auto-fallback to Edge TTS.

```
Normal:  MiniMax TTS → success → send voice bubble
         ↓ fail (1004 / quota)
Exhausted: mark ~/.hermes/.minimax_tts_exhausted → Edge TTS → send
         ↓
00:00 cron: reset exhaustion flag
         ↓
Next request: try MiniMax again → success → normal / still fail → re-exhaust
```

## Exhaustion Tracking (file-based)

File: `~/.hermes/.minimax_tts_exhausted` (created when exhausted, deleted at midnight reset).

**Note:** `reset_minimax_tts_exhaustion()` is NOT implemented anywhere in the codebase. Any Python cron/task runner that tries to import this non-existent function will crash with `NameError` (module-level import) or `ImportError` (the `hermes_constants` chain also fails on Python 3.9 due to PEP 604 `Path | None` syntax). **Always use shell for the reset action.**

**Cron/agent must use direct file I/O — never an import:**

## Midnight Reset Cron

Job: `"MiniMax TTS 零点额度刷新重置"`
- Schedule: `0 0 * * *` (00:00 Asia/Shanghai)
- job_id: `16a2d411378f`
- Action: **direct shell command only** — do NOT attempt to import or call `reset_minimax_tts_exhaustion()` from Python (that function does not exist anywhere in the codebase and will raise `NameError` or `ImportError`). The cron job's Python context shares the same broken import chain (Python 3.9 + `hermes_constants` PEP 604 syntax) so even if the function existed, importing it would fail. **Always use shell.**

  Shell form (canonical — use this even from a Python-capable cron runner):
  ```bash
  test -f ~/.hermes/.minimax_tts_exhausted && rm -f ~/.hermes/.minimax_tts_exhausted && echo "MiniMax exhaustion flag cleared -- MiniMax will be tried again." || echo "MiniMax exhaustion flag was already clear (no action needed)."
  ```

  Python form (fallback only — same `os.path.exists`/`os.remove` pattern, runs via `terminal()` or shell):
  ```python
  import os
  flag = os.path.expanduser("~/.hermes/.minimax_tts_exhausted")
  if os.path.exists(flag):
      os.remove(flag)
      print("MiniMax exhaustion flag cleared -- MiniMax will be tried again.")
  else:
      print("MiniMax exhaustion flag was already clear (no action needed).")
  ```
  Always use the hermes venv Python (`/Users/macmini/.hermes/hermes-agent/venv/bin/python`), not system Python 3.9 (fails on PEP 604 `Path | None` syntax in `hermes_constants`).

- Verifies: next TTS request will attempt MiniMax again

## MiniMax API Facts

- Primary endpoint: `https://api.minimax.chat/v1/text_to_speech` (MiniMax TTS v1 API — returns raw audio/mpeg)
- Legacy endpoint: `https://api.minimaxi.com/v1/t2a_v2` (older v2 API, returns JSON with hex-encoded audio)
- API Key env: `MINIMAX_API_KEY` (125-char `sk-cp-` format)
- Config model: `speech-2.8-hd` (configured in `config.yaml tts.minimax.model`)
- Voice: `female-yujie` (configured in `config.yaml tts.minimax.voice_id`)

## `.env` API Key Corruption — Critical Root Cause

**Symptom**: auto-TTS fails with `1004 login fail`, key length appears correct (125 chars), but MiniMax rejects auth.

**Root cause**: The `.env` file has a `***` masking marker on the same line as the key, but dotenv parses the entire continuation as one value:

```
# WRONG — this is what the file actually contains:
MINIMAX_API_KEY=***\nsk-cp-SqO-GKZHSX49viGF9TIITxiekDBm7uLE6U7uiDhv1K5gPlZMi_QpJg8Ub4IdrDvi6XKgWd1YZLeRnnAdT0VugrqIwqz9sVUZfLPItQmD5CZE1lsWqZXktuw
```

dotenv reads this as ONE value: `***sk-cp-SqO-GKZHSX49...` (125 chars, starts with `***`). The leading `***` is included in the auth token, causing rejection.

**Diagnosis**:
```python
import os
from dotenv import dotenv_values
env = dotenv_values("/Users/macmini/.hermes/.env")
key = env.get("MINIMAX_API_KEY", "")
print(f"Starts with: {repr(key[:4])}")  # Shows '***' if corrupted
print(f"Length: {len(key)}")             # Still 125 even when corrupted
```

**Fix**: Edit `~/.hermes/.env` line 14 — remove the `***` mask marker and put the full key on ONE line:
```
MINIMAX_API_KEY=sk-cp-SqO-GKZHSX49viGF9TIITxiekDBm7uLE6U7uiDhv1K5gPlZMi_QpJg8Ub4IdrDvi6XKgWd1YZLeRnnAdT0VugrqIwqz9sVUZfLPItQmD5CZE1lsWqZXktuw
```

Also fix line 13 (`MINIMAX_CN_API_KEY`) the same way if present.

**Why the bug persists**: `get_env_value()` in `hermes_cli/config.py` checks `os.environ[key]` FIRST before `.env`. If the corrupted value was already loaded into the environment, it returns that immediately without falling back to the (fixed) `.env` file. **After fixing `.env`, restart the gateway** to force re-load.

## Edge TTS Fallback Voice

Fallback voice: `pedge-edge-turboplus` (configured in `tools/tts_tool.py`). This is Hermes's built-in Edge TTS voice.

## Hermes Config for Auto TTS

```yaml
# config.yaml
tts:
  provider: minimax   # primary
  minimax:
    model: speech-2.8-hd
    voice_id: female-yujie
voice:
  auto_tts: true   # auto-generate voice on ALL agent replies
```

## Quick Test

```bash
# Test MiniMax TTS directly
curl -X POST "https://api.minimaxi.com/v1/t2a_v2" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -F "model=speech-2.8-hd" \
  -F "text=测试" \
  -F "stream=false" \
  -o /tmp/test_tts.mp3

# Check exhaustion flag
ls -la ~/.hermes/.minimax_tts_exhausted 2>/dev/null && echo "EXHAUSTED" || echo "OK"

# Manually clear exhaustion (if needed)
rm -f ~/.hermes/.minimax_tts_exhausted
```

## Appendix: MiniMax TTS Pipeline (execute_code)

For use inside `execute_code` blocks when you need to programmatically generate voice:

### Full Pipeline (execute_code)

```python
from hermes_tools import web_search
import urllib.request, subprocess, json, os

# 1. Call MiniMax TTS via MCP
# (use mcp_minimax_official_text_to_audio in the agent's tool context)

# 2. Download audio — must add User-Agent header or get HTTP 403:
url = "<Audio URL from MiniMax response>"
req = urllib.request.Request(
    url,
    headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
)
output_path = "/tmp/tts_output.mp3"
with urllib.request.urlopen(req, timeout=60) as response:
    with open(output_path, 'wb') as f:
        f.write(response.read())

# 3. Convert to OGG/Opus for Telegram
ogg_path = output_path.replace(".mp3", ".ogg")
subprocess.run([
    "ffmpeg", "-i", output_path,
    "-c:a", "libopus", "-b:a", "32k", "-vbr", "on",
    "-y", ogg_path
], check=True)

# 4. Cache cleanup — keep max 10 OGG files
cache_dir = os.path.dirname(ogg_path)
files = sorted(os.listdir(cache_dir), key=lambda f: os.path.getctime)
if len(files) > 10:
    for f in files[:-10]:
        os.remove(os.path.join(cache_dir, f))
```

### Key Discoveries

- MiniMax audio URLs have signed expiry — generate and download promptly
- Download **requires** `User-Agent` header, otherwise HTTP 403
- Telegram voice bubble format: OGG with **libopus** encoder, 32kbps VBR
- Wrong format: `[[audio URL]]` sends a link, not a voice bubble
- Correct format: `MEDIA:/path/to/file.ogg` sends a real voice bubble

## Appendix: MiniMax Image Generation → Telegram

Generate images with MiniMax and deliver to Telegram:

### Pipeline

```python
# 1. Generate image
mcp_minimax_official_text_to_image(
    prompt="<description>",
    aspect_ratio="1:1",  # 1:1, 16:9, 4:3, 3:2, 2:3, 3:4, 9:16, 21:9
    n=1,
    model="image-01",
    output_directory="/Users/macmini/.hermes/image_cache"
)

# 2. Download — must add User-Agent header or get HTTP 403:
import urllib.request
req = urllib.request.Request(
    image_url,
    headers={'User-Agent': 'Mozilla/5.0'}
)
with urllib.request.urlopen(req, timeout=60) as response:
    with open(output_path, 'wb') as f:
        f.write(response.read())

# 3. Verify resolution
# ffmpeg -i <path> 2>&1 | grep "Stream"
# Output: Stream #0:0: Video: mjpeg, yuvj444p(pc), 1024x1024 [...]

# 4. Send to Telegram (two messages)
send_message(action="send", message="<description>", target="telegram")
send_message(action="send", message="MEDIA:<path>", target="telegram")
# Note: action="send" requires BOTH target AND message
```

### Key Discoveries

- Download **requires** `User-Agent` header, otherwise 403
- MiniMax fixed output: 1024×1024 square images
- Image cache `/Users/macmini/.hermes/image_cache/`, auto-cleanup when >50 files (removes oldest 10)

## Sending Telegram Notifications from Cron

See `references/telegram-notify.md` for the SSL-workaround pattern used to send Telegram messages from Hermes cron jobs (this environment has a broken SSL stack that requires `ssl.SSLContext` with cert verification disabled).

## Troubleshooting Gateway TTS

**Symptom: auto_tts fails with "1004 login fail"**
1. Key length check — should be 125 chars:
   `python3 -c "from dotenv import dotenv_values; print(len(dotenv_values('/Users/macmini/.hermes/.env')['MINIMAX_API_KEY']))"`
2. If key is wrong length, the key in .env is masked/corrupt. Check .env file directly.
3. Restart gateway to reload code changes: `rm -f ~/.hermes/gateway.pid && hermes gateway run`

**Symptom: multiple gateway instances (PID race)**
- `ps aux | grep hermes` — look for multiple `gateway/run.py` processes
- Kill extras: `kill <PID>`
- Remove stale PID file: `rm -f ~/.hermes/gateway.pid`
- Restart: `hermes gateway run` (from `~/.hermes/hermes-agent/`)

**Symptom: Telegram completely unresponsive (no replies, no error)**
This is usually the gateway itself being dead — not a TTS issue at all.
1. Check gateway log age — if no new lines in minutes, gateway is dead:
   `tail -3 ~/.hermes/logs/gateway.log`
2. Check API server reachable: `curl -s http://127.0.0.1:8642/health`
3. If health returns nothing → gateway is dead. See `hermes-operations` skill
   "Gateway Restart" section for launchd restart procedure on macOS.

**Symptom: quota/auth errors after key fix**
- MiniMax may be out of quota, not auth-fail
- Check exhaustion flag: `ls ~/.hermes/.minimax_tts_exhausted`
- If exhausted, manually clear: `rm -f ~/.hermes/.minimax_tts_exhausted`
- Or wait for 00:00 cron reset
