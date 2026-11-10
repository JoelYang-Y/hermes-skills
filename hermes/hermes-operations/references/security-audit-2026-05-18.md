# Security Audit — 2026-05-18

## System
- macOS (26.5), Hermes Agent on macmini
- Gateway PID 85768, single instance, running since 20:47

## Findings

### ✅ Passing Checks
- Gateway process: single instance, PID matches gateway.pid
- Git remote: HTTPS (correct)
- API Server binding: 127.0.0.1:8642 (not exposed externally)
- Telegram: connected, polling mode, auto-reconnect working
- Secret redaction: enabled (`redact_secrets: true`)
- File permissions on `.env` and `config.yaml`: 600 (correct)
- Approvals mode: manual (dangerous commands require confirmation)
- Command allowlist: active for destructive operations
- No unauthorized access attempts found in logs

### ⚠️ API Server No Authentication
- 729 repeated warnings in `errors.log` since 2026-05-17
- API Server key is empty — all requests accepted without auth
- Mitigation: bound to 127.0.0.1 only (not 0.0.0.0), so only local processes can reach it
- Risk assessment: LOW for local-only setup, but key should still be set
- **Action**: Set `API_SERVER_KEY` in `~/.hermes/.env`

### ⚠️ MINIMAX_API_KEY Masking Corruption
- Both `config.yaml` and `.env` use `***` masking for API keys
- Masking is corrupted: real key data exists after `***` marker in file
- The `.env` line appears as: `MINIMAX_API_KEY=***<real_key_hex_data>`
- This means dotenv parsing may read either the mask or partial key
- Real key visible in hex dump of file bytes around line 402
- **Action**: Regenerate MiniMax API key at provider, reconfigure cleanly

### ⚠️ Telegram Proxy
- Gateway logs show connection via `http://127.0.0.1:6152`
- This is a local proxy (likely macOS proxy/VPN software)
- Proxy not identified — not audited further
- **Action**: Confirm what is running on port 6152

## Commands Run During Audit

```bash
# Process check
ps aux | grep "hermes\|gateway" | grep -v grep
# Result: 1 gateway process (PID 85768)

# Gateway state
cat ~/.hermes/gateway_state.json
# Result: telegram connected, api_server connected, running

# Git remote
cd ~/.hermes/hermes-agent && git remote -v
# Result: HTTPS (correct)

# API Server test
curl http://127.0.0.1:8642/
# Result: 404 (server responding, no auth required)

# Port binding check
lsof -i :8642
# Result: python3.1 85768 macmini 31u IPv4 ... TCP localhost:8642 (LISTEN)

# Secret warnings count
grep -c "No API key configured" ~/.hermes/logs/errors.log
# Result: 729
```

## Related Files
- `~/.hermes/gateway_state.json`
- `~/.hermes/gateway.pid`
- `~/.hermes/config.yaml`
- `~/.hermes/.env`
- `~/.hermes/logs/gateway.log`
- `~/.hermes/logs/errors.log`
