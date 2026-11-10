#!/bin/bash
# Run end-to-end DoH verification against a deployed AdGuard Home + openresty setup.
# Designed to run from the openresty host (uses --resolve with 127.0.0.1 and the
# host's own openssl/perl/od).
#
# Usage:
#   ./scripts/verify-doh.sh \
#     --domain doh.example.com \
#     --doh-path /q-234f55d7bc2a240b/ \
#     --ui-path /ag-e452e056f281/ \
#     [--upstream 127.0.0.1:8443]
#
# Exits 0 if all checks pass, non-zero on first failure.

set -e

DOMAIN=""
DOH_PATH=""
UI_PATH=""
UPSTREAM_RESOLVE="127.0.0.1"
AGH_CONTAINER="adguardhome"
OR_CONTAINER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)    DOMAIN="$2"; shift 2 ;;
    --doh-path)  DOH_PATH="$2"; shift 2 ;;
    --ui-path)   UI_PATH="$2"; shift 2 ;;
    --upstream)  UPSTREAM_RESOLVE="$2"; shift 2 ;;
    --agh)       AGH_CONTAINER="$2"; shift 2 ;;
    --or)        OR_CONTAINER="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$DOMAIN" || -z "$DOH_PATH" || -z "$UI_PATH" ]]; then
  echo "missing --domain / --doh-path / --ui-path" >&2; exit 2
fi

if [[ -z "$OR_CONTAINER" ]]; then
  OR_CONTAINER=$(docker ps --format '{{.Names}}' | grep -i openresty | head -1)
  [[ -z "$OR_CONTAINER" ]] && { echo "no openresty container" >&2; exit 1; }
fi

PASS=0; FAIL=0
check() { if "$@"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi; }

# 1. AGH cert chain length (3 certs = the gotcha-applicable case)
echo "[1] AGH fullchain cert count"
COUNT=$(docker exec "$AGH_CONTAINER" sh -c "grep -c 'BEGIN CERTIFICATE' /opt/adguardhome/cert/fullchain.pem" 2>/dev/null || echo "?")
echo "    count=$COUNT"
check [[ "$COUNT" == "3" ]]

# 2. AGH started HTTPS server
echo "[2] AGH 'starting https server' in log"
check docker logs --tail 30 "$AGH_CONTAINER" 2>&1 | grep -q "starting https server"

# 3. openresty -t
echo "[3] openresty config syntax"
check docker exec "$OR_CONTAINER" openresty -t >/dev/null 2>&1

# 4. Root path → 404
echo "[4] GET /  → expect 404"
HTTP=$(curl -sS -m 5 --resolve "$DOMAIN:443:$UPSTREAM_RESOLVE" -o /dev/null -w '%{http_code}' "https://$DOMAIN/" 2>/dev/null || echo 000)
echo "    HTTP $HTTP"
check [[ "$HTTP" == "404" ]]

# 5. UI path → 302
echo "[5] GET $UI_PATH  → expect 302"
HTTP=$(curl -sS -m 5 --resolve "$DOMAIN:443:$UPSTREAM_RESOLVE" -o /dev/null -w '%{http_code}' "https://$DOMAIN$UI_PATH" 2>/dev/null || echo 000)
echo "    HTTP $HTTP"
check [[ "$HTTP" == "302" ]]

# 6. DoH POST (RFC 8484 wireformat) for example.com A
echo "[6] DoH POST example.com A"
RAW=$(perl -e 'print pack("H*", "123401000001000000000000076578616d706c6503636f6d0000010001")')
RESP_FILE=$(mktemp)
HTTP=$(curl -sS -m 8 --resolve "$DOMAIN:443:$UPSTREAM_RESOLVE" \
  -H "content-type: application/dns-message" \
  --data-binary "$RAW" \
  -o "$RESP_FILE" \
  -w '%{http_code}|%{content_type}|%{size_download}' \
  "https://$DOMAIN$DOH_PATH" 2>/dev/null || echo "000|?")
echo "    HTTP $HTTP"

LEN=$(stat -c %s "$RESP_FILE" 2>/dev/null || wc -c < "$RESP_FILE")
if [[ "$LEN" -ge 12 ]]; then
  QR=$(( ( $(od -An -tu2 -N2 -j2 "$RESP_FILE" | tr -d ' ') >> 15 ) & 1 ))
  RCODE=$(od -An -tu1 -N1 -j3 "$RESP_FILE" | tr -d ' ')
  ANCOUNT=$(od -An -tu2 -N2 -j6 "$RESP_FILE" | tr -d ' ')
  echo "    QR=$QR RCODE=$RCODE ANCOUNT=$ANCOUNT"
  check [[ "$QR" == "1" && "$RCODE" == "0" && "$ANCOUNT" -ge 1 ]]
else
  echo "    FAIL: response too short"
  FAIL=$((FAIL+1))
fi
rm -f "$RESP_FILE"

# 7. DoH GET (RFC 8484 GET method)
echo "[7] DoH GET example.com A (base64url)"
RAW=$(perl -e 'print pack("H*", "123401000001000000000000076578616d706c6503636f6d0000010001")')
B64=$(printf '%s' "$RAW" | base64 | tr -d '\n' | tr '+/' '-_' | tr -d '=')
RESP_FILE=$(mktemp)
HTTP=$(curl -sS -m 8 --resolve "$DOMAIN:443:$UPSTREAM_RESOLVE" \
  -H "accept: application/dns-message" \
  -o "$RESP_FILE" \
  -w '%{http_code}|%{size_download}' \
  --get --data-urlencode "dns=$B64" \
  "https://$DOMAIN$DOH_PATH" 2>/dev/null || echo "000|?")
echo "    HTTP $HTTP"
check [[ "${HTTP%%|*}" == "200" ]]
rm -f "$RESP_FILE"

echo
echo "passed: $PASS  failed: $FAIL"
[[ "$FAIL" -eq 0 ]]
