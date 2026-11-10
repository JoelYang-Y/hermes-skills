# MiniMax API Key Diagnostic Reference

## Check if `.env` key is corrupted

```python
import os
from dotenv import dotenv_values

env = dotenv_values("/Users/macmini/.hermes/.env")
key = env.get("MINIMAX_API_KEY", "")

print(f"Length: {len(key)}")
print(f"Starts with '***': {key.startswith('***')}")
print(f"Full repr: {repr(key)}")
```

**Corrupted output** (key starts with `***`):
```
Length: 125
Starts with '***': True
Full repr: '***sk-cp-SqO-GKZHSX49viGF9TIITxiekDBm7uLE6U7uiDhv1K5gPlZMi_QpJg8Ub4IdrDvi6XKgWd1YZLeRnnAdT0VugrqIwqz9sVUZfLPItQmD5CZE1lsWqZXktuw'
```

**Fixed output** (key starts with `sk-cp-`):
```
Length: 125
Starts with '***': False
Full repr: 'sk-cp-SqO-GKZHSX49viGF9TIITxiekDBm7uLE6U7uiDhv1K5gPlZMi_QpJg8Ub4IdrDvi6XKgWd1YZLeRnnAdT0VugrqIwqz9sVUZfLPItQmD5CZE1lsWqZXktuw'
```

## Check raw `.env` line bytes

```bash
sed -n '14p' /Users/macmini/.hermes/.env | xxd | head -5
```

Corrupted line (multi-line value):
```
4d49 4e49 4d41 585f 4150 495f 4b45 593d  MINIMAX_API_KEY=***
7376 2d63 702d 5371 4f2d 474b 5a48 5358  ***sk-cp-SqO-GKZHSX
...  (continues on next line)
```

## How the corruption happened

The `.env` writer applied a display mask (`***`) to the key for UI purposes but wrote it back to the file on the same line as the real key, creating a multi-line value:
```
MINIMAX_API_KEY=***              ← display mask prefix
sk-cp-SqO-GKZHSX49viGF9TIITxiekDBm7uLE6U7uiDhv1K5gPlZMi_QpJg8Ub4IdrDvi6XKgWd1YZLeRnnAdT0VugrqIwqz9sVUZfLPItQmD5CZE1lsWqZXktuw
```

Python's `dotenv` library reads this as one value: the mask prefix plus the entire key.

## Also check line 13

```
MINIMAX_CN_API_KEY=sk-cp-...ktuw   ← also masked
```
Apply the same fix to line 13 if it has the `***` prefix or `...` truncation.

## Why restarting gateway is required

`get_env_value()` in `hermes_cli/config.py` checks `os.environ[key]` FIRST:

```python
def get_env_value(key: str) -> Optional[str]:
    if key in os.environ:
        return os.environ[key]      # ← returns stale corrupted value
    env_vars = load_env()
    return env_vars.get(key)        # ← never reached if env already set
```

If the gateway process started before the `.env` fix, `os.environ['MINIMAX_API_KEY']` still holds the corrupted `***...` value. A gateway restart forces re-read from the fixed `.env`.
