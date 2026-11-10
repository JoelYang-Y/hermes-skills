#!/bin/bash
# Disambiguate WHY a public 443 HTTPS test fails when the inside-container test passes.
#
# The four causes this script distinguishes:
#   A. Server actually broken         (SYN-ACK absent, or ServerHello never sent)
#   B. Cloud security group / firewall (pcap empty for the public IP)
#   C. Client-network MITM            (server SYN-ACKs + ACKs ClientHello, then
#                                     client RSTs with no ServerHello → curl SSL_ERROR_SYSCALL)
#   D. SNI mismatch / ssl_reject_handshake (server sends 7-byte TLS Alert + FIN)
#
# Usage (run on the openresty host, with the user triggering a curl from outside):
#   sudo ./scripts/diag-public-443.sh --public-ip 1.2.3.4 --domain doh.example.com \
#       --out /tmp/diag.pcap
#
# After the test, the script reads its own pcap and prints a verdict.
# Requires: tcpdump, curl. Run from a host with /usr/sbin/iptables if you want
# the optional 8443 fallback test.

set -e

PUBLIC_IP=""
DOMAIN=""
PCAP=""
ENABLE_8443_FALLBACK=0
TCPD_TIMEOUT=10   # seconds to wait for traffic before giving up

while [[ $# -gt 0 ]]; do
  case "$1" in
    --public-ip)   PUBLIC_IP="$2"; shift 2 ;;
    --domain)      DOMAIN="$2"; shift 2 ;;
    --out)         PCAP="$2"; shift 2 ;;
    --with-8443)   ENABLE_8443_FALLBACK=1; shift ;;
    --timeout)     TCPD_TIMEOUT="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$PUBLIC_IP" || -z "$PCAP" ]]; then
  echo "need --public-ip and --out" >&2; exit 2
fi

rm -f "$PCAP"

# Step 1: start tcpdump before the user triggers the test.
echo "==> starting tcpdump on port 443 / $PUBLIC_IP for ${TCPD_TIMEOUT}s"
tcpdump -i any -nn -s 0 -w "$PCAP" \
    "tcp port 443 and host $PUBLIC_IP" -c 40 \
    >/tmp/diag-public-443.log 2>&1 &
TCPD_PID=$!

# Give tcpdump a moment to actually open the BPF.
sleep 1

# Step 2: prompt the operator to trigger the public test from outside.
echo "==> NOW: from a non-LAN host, run e.g.:"
echo "      curl -k -v --resolve ${DOMAIN:-example.com}:443:${PUBLIC_IP} https://${DOMAIN:-example.com}/"
echo

# Step 3: wait for traffic OR timeout.
echo "==> waiting up to ${TCPD_TIMEOUT}s for traffic..."
SECONDS_LEFT=$TCPD_TIMEOUT
while (( SECONDS_LEFT > 0 )); do
  if [[ -f "$PCAP" ]] && (( $(stat -c %s "$PCAP" 2>/dev/null || echo 0) > 24 )); then
    sleep 1   # give the final packets a moment to flush
    break
  fi
  sleep 1
  SECONDS_LEFT=$(( SECONDS_LEFT - 1 ))
done

kill "$TCPD_PID" 2>/dev/null || true
wait "$TCPD_PID" 2>/dev/null || true

if [[ ! -s "$PCAP" ]]; then
  echo
  echo "============================================================"
  echo "VERDICT: B — empty pcap"
  echo "  Nothing reached eth0. Likely cause: cloud security group,"
  echo "  Tencent Cloud firewall, ufw blocking, or upstream ISP."
  echo "  Verify with: curl from the public internet to any other"
  echo "  port you control. If 80 works but 443 doesn't, the SG"
  echo "  is filtering 443 specifically."
  echo "============================================================"
  if (( ENABLE_8443_FALLBACK )); then
    echo
    echo "==> --with-8443 requested but cause B means the public port is"
    echo "    blocked upstream — 8443 won't help. Open 443 in the SG first."
  fi
  exit 10
fi

echo
echo "==> captured packets:"
tcpdump -r "$PCAP" -nn 2>/dev/null
echo

# Step 4: classify the verdict from the captured packets.

# Did we see a 7-byte TLS Alert (alert 112 = unrecognized_name) before FIN?
HAS_ALERT_FIN=$(tcpdump -r "$PCAP" -nn 2>/dev/null \
  | awk '/Flags \[P\.\]/{if (length($0) < 60) print "YES"; exit}')
HAS_FIN=$(tcpdump -r "$PCAP" -nn 2>/dev/null | grep -c "Flags \[F\.\]" || true)
HAS_SYN_ACK=$(tcpdump -r "$PCAP" -nn 2>/dev/null | grep -c "Flags \[S\.\]" || true)
HAS_CLIENT_RST=$(tcpdump -r "$PCAP" -nn 2>/dev/null \
  | grep -E "Flags \[R\.\]|Flags \[R\][,\.]" \
  | grep -c ">$" || true)

echo "==> signature:"
echo "    SYN-ACK frames sent:   $HAS_SYN_ACK"
echo "    FIN frames sent:       $HAS_FIN"
echo "    short P. frames:       ${HAS_ALERT_FIN:-no}"
echo "    client RSTs:           $HAS_CLIENT_RST"
echo

# Cause D: server sent a short P. frame (TLS Alert, ~7 bytes) then FIN.
if [[ -n "$HAS_ALERT_FIN" || $HAS_FIN -ge 1 ]]; then
  # Look for a P. frame smaller than 60 chars (heuristic for 7-byte TLS Alert)
  SHORT_P=$(tcpdump -r "$PCAP" -nn 2>/dev/null \
    | awk '/Flags \[P\.\]/{ if (length($0) < 60) print }' | head -1)
  if [[ -n "$SHORT_P" ]]; then
    echo "============================================================"
    echo "VERDICT: D — SNI mismatch / ssl_reject_handshake on"
    echo "  Server sent a short TLS Alert frame then FIN. This is the"
    echo "  1Panel default vhost (00.default.conf) rejecting an SNI it"
    echo "  doesn't recognize."
    echo
    echo "  Fix: ensure the client sends SNI=your-domain, not bare IP."
    echo "    Use:  curl --resolve <your-domain>:443:$PUBLIC_IP -k \\"
    echo "           https://<your-domain>/"
    echo "============================================================"
    exit 30
  fi
fi

# Cause C: SYN-ACK was sent, client RST'd before any server-side FIN.
if (( HAS_SYN_ACK >= 1 )) && (( HAS_CLIENT_RST >= 1 )) && (( HAS_FIN == 0 )); then
  echo "============================================================"
  echo "VERDICT: C — client-network MITM"
  echo "  Server SYN-ACKed normally and ACKed the ClientHello, but"
  echo "  the client RST'd before the server could send ServerHello."
  echo "  This is the classic signature of a transparent HTTPS"
  echo "  proxy on the client's path: home router, ISP DPI, corporate"
  echo "  firewall, or Surge-style local proxy doing TLS interception."
  echo
  echo "  Server is fine. Test from a different network (mobile hotspot,"
  echo "  a VPN, a different WiFi) and the failure will go away."
  echo "============================================================"
  if (( ENABLE_8443_FALLBACK )); then
    echo
    echo "==> --with-8443 requested; run the openresty 8443 vhost recipe in"
    echo "    the skill (Pitfall 'Cause C test — the instant portable bypass')"
    echo "    to give the user a working URL via non-standard port."
  fi
  exit 20
fi

# Cause A: server never sent SYN-ACK, or SYN-ACK without a follow-up ACK,
# or ServerHello was malformed. Use openresty error log to confirm.
if (( HAS_SYN_ACK == 0 )); then
  echo "============================================================"
  echo "VERDICT: A — server not accepting the connection"
  echo "  No SYN-ACK frames from the server. Check:"
  echo "    - ufw allow 443  (use /usr/sbin/iptables -L ufw-user-input)"
  echo "    - openresty listening: ss -tlnp | grep 443"
  echo "    - /www/sites/<site>/log/error.log  for TLS handshake errors"
  echo "    - cert chain: openssl x509 -in fullchain.pem -noout -subject"
  echo "============================================================"
  exit 40
fi

echo "============================================================"
echo "VERDICT: inconclusive — packets captured but signature didn't"
echo "match A, C, or D cleanly. Inspect $PCAP manually with:"
echo "  tcpdump -r $PCAP -nn -A"
echo "============================================================"
exit 1
