#!/usr/bin/env bash
# verify-trusted-proxies.sh
#
# End-to-end check that AGH (behind a reverse proxy) is honoring
# X-Real-IP / X-Forwarded-For from the proxy. Run this on the openresty host
# AFTER editing AdGuardHome.yaml and restarting AGH.
#
# Usage:
#   ./verify-trusted-proxies.sh <domain> <doh-path> <agh-password> [openresty-container]
#
# Example:
#   ./verify-trusted-proxies.sh dnspod.jhsweetheart.com /jhsweet_jh99421/dns-query '<密码>' 1Panel-openresty-JnD6
#
# What it does:
#   1. Logs into AGH via /control/login (cookie jar).
#   2. Sends a DoH query with fake X-Real-IP=8.8.8.8 through the openresty reverse proxy.
#   3. Reads /control/querylog and prints the `client` field.
#   4. Pass criterion: client == "8.8.8.8". Fail: client is some bridge gateway
#      like 172.19.0.1, meaning trusted_proxies is missing the bridge subnet.

set -euo pipefail

DOMAIN="${1:?usage: $0 <domain> <doh-path> <agh-password> [openresty-container]}"
DOH_PATH="${2:?usage: $0 <domain> <doh-path> <agh-password> [openresty-container]}"
AGH_PASSWORD="${3:?usage: $0 <domain> <doh-path> <agh-password> [openresty-container]}"
OPENRESTY="${4:-1Panel-openresty-JnD6}"

# A minimal DoH GET query for gateway.fe.apple-dns.cn A — same query used
# elsewhere in this skill. base64url-encoded.
QUERY="AAABAAABAAAAAAAAB2dhdGV3YXkCZmUJYXBwbGUtZG5zAmNuAAAcAAE"
COOKIES=$(mktemp)
trap "rm -f $COOKIES" EXIT

echo "==> Logging into AGH at 127.0.0.1:3000"
curl -sS -c "$COOKIES" -X POST http://127.0.0.1:3000/control/login \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"root\",\"password\":\"$AGH_PASSWORD\"}" >/dev/null

echo "==> Triggering one DoH query via openresty with X-Real-IP=8.8.8.8"
docker exec "$OPENRESTY" sh -c "
  curl -sS --resolve ${DOMAIN}:443:127.0.0.1 \
    -H 'Host: ${DOMAIN}' \
    -H 'X-Real-IP: 8.8.8.8' \
    -H 'X-Forwarded-For: 8.8.8.8' \
    -H 'accept: application/dns-message' \
    -o /dev/null -w 'DoH HTTP=%{http_code}  size=%{size_download}\n' \
    'https://${DOMAIN}${DOH_PATH}?dns=${QUERY}'
"

# Give AGH a moment to flush the in-memory query log.
sleep 2

echo "==> Reading /control/querylog to see what AGH recorded as the client"
RAW=$(curl -sS -b "$COOKIES" http://127.0.0.1:3000/control/querylog)
CLIENTS=$(printf '%s' "$RAW" | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data', [])
if not items:
    print('NO_LOG')
    sys.exit(0)
seen = set()
for it in items[:10]:
    c = it.get('client')
    p = it.get('client_proto')
    if c not in seen:
        print(f'  client={c}  proto={p}')
        seen.add(c)
")

echo "$CLIENTS"

if echo "$CLIENTS" | grep -q 'client=8\.8\.8\.8'; then
  echo "PASS: AGH trusts the proxy and honors X-Real-IP."
  exit 0
fi

if echo "$CLIENTS" | grep -qE 'client=172\.(19|17|28)\.[0-9]+\.[0-9]+'; then
  echo "FAIL: AGH is logging a docker bridge gateway IP, not X-Real-IP."
  echo "      Fix: add 172.19.0.0/16 (and any other bridge subnet openresty sits on)"
  echo "      to dns.trusted_proxies in AdGuardHome.yaml, then docker restart adguardhome."
  exit 1
fi

if echo "$CLIENTS" | grep -q 'NO_LOG'; then
  echo "INDETERMINATE: querylog is empty. Enable querylog in AdGuardHome.yaml"
  echo "      (querylog.enabled: true) and re-run, or verify the in-memory API"
  echo "      by hitting /control/querylog from a logged-in session."
  exit 2
fi

echo "INDETERMINATE: unexpected client values printed above."
exit 3
