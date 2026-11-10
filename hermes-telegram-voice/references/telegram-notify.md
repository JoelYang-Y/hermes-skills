# Sending Telegram Notifications from Hermes Cron Jobs

This environment has a broken SSL stack (`LibreSSL SSL_connect: SSL_ERROR_SYSCALL`). The standard `urllib.request.urlopen` fails with `EOF in violation of protocol`. Workaround: use `ssl.SSLContext` with `check_hostname=False` and `verify_mode=ssl.CERT_NONE`.

## Bot Token Location

**NOT in `config.yaml`** — look in `~/.hermes/.env`:
```
TELEGRAM_BOT_TOKEN=839977...uzlM
TELEGRAM_ALLOWED_USERS=1910087142
```

`config.yaml` only has `telegram: reactions: false` etc., no token.

## Python (tested — works around SSL bug)

```python
import urllib.request, urllib.parse, ssl

bot_token = "839977...uzlM"   # read from ~/.hermes/.env
chat_id = "1910087142"
text = """❌ *Hermes 更新检查失败*

📋 *检查结果*：无法连接到 GitHub仓库

🔍 *错误信息*：
LibreSSL SSL_connect: SSL_ERROR_SYSCALL in connection to github.com:443

💡 *原因*：网络问题（SSL 连接失败），可能是临时的网络波动

⏰ 时间：2026-06-07 04:15:25"""

url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(url, data=data.encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
    print(resp.read().decode())
```

## Shell via curl (alternative — also affected by SSL bug on this machine)

```bash
curl -s -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d "chat_id=<CHAT_ID>&text=<URL-ENCODED TEXT>&parse_mode=Markdown"
```

curl also fails with SSL error on this machine.

## Markdown Notes

- Use `*bold*`, `_italic_`, ``` `code` ```
- Do NOT use `!` or `>` at start of line — Telegram interprets them as legacy format markers
- Keep code blocks simple