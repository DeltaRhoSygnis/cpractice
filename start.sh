#!/usr/bin/env bash
# One-command start for CPractice (Termux / local).
#   ./start.sh              # start on 127.0.0.1:8000
#   CPRACTICE_PORT=9000 ./start.sh
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

HOST="${CPRACTICE_HOST:-127.0.0.1}"
PORT="${CPRACTICE_PORT:-8000}"
URL="http://${HOST}:${PORT}"

# LAN hint for 0.0.0.0 binds: print every *useful* address so a laptop can
# reach the server over the phone's hotspot. Cellular interfaces (ccmni*)
# are deliberately skipped: a carrier-NAT address is not a front door.
print_lan_hints() {
  if command -v ip >/dev/null 2>&1 \
     && ip -4 -o addr show scope global 2>/dev/null | grep -q inet; then
    echo "LAN address(es) for other devices:"
    ip -4 -o addr show scope global 2>/dev/null | awk -v port="$PORT" \
      '$2 !~ /^ccmni/ { gsub(/\/[0-9]+$/, "", $4); print "  http://" $4 ":" port }'
  elif command -v ifconfig >/dev/null 2>&1; then
    # Linux without netlink access (e.g. unrooted Android/Termux): parse the
    # toybox/ifconfig "iface:"/"inet <addr> netmask ..." blocks instead.
    local lan_addrs
    lan_addrs=$(ifconfig -a 2>/dev/null | awk -v port="$PORT" '
      /^[^ \t]/ { iface = $1; sub(/:$/, "", iface) }
      /^[ \t]*inet / {
        ip = $2
        if (iface !~ /^ccmni/ && ip != "127.0.0.1") print ip
      }' | sort -u)
    if [ -n "$lan_addrs" ]; then
      echo "LAN address(es) for other devices:"
      echo "$lan_addrs" | sed "s|^|  http://|; s|$|:${PORT}|"
    fi
  fi
}

if curl -s -m 2 -o /dev/null "${URL}/api/health" 2>/dev/null; then
  echo "CPractice already running at ${URL}"
  if [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
    print_lan_hints
  fi
  exit 0
fi

echo "Starting CPractice at ${URL} ..."

# Report offline mode honestly: no key means no generation, but grading works.
# The application owns the provider registry, so ask it which credential is
# usable instead of listing credential names here.
ai_status="$(python3 - <<'PY' 2>/dev/null
import sys

sys.path.insert(0, ".")
try:
    from app.config import Settings
except Exception:
    print("unknown")
    raise SystemExit(0)

print("configured" if Settings().any_ai_key_configured else "offline")
PY
)"

if [ "$ai_status" = "offline" ]; then
  echo "No AI provider key found - AI generation and live hints are disabled."
  echo "Saved problem packages still load and every submission is still graded."
fi

if [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
  print_lan_hints
fi

exec uvicorn app.main:app --host "${HOST}" --port "${PORT}" "$@"
