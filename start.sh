#!/usr/bin/env bash
# One-command start for CPractice (Termux / local).
#   ./start.sh              # start on 127.0.0.1:8000
#   CPRACTICE_PORT=9000 ./start.sh
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

HOST="${CPRACTICE_HOST:-127.0.0.1}"
PORT="${CPRACTICE_PORT:-8000}"
URL="http://${HOST}:${PORT}"

if curl -s -m 2 -o /dev/null "${URL}/api/health" 2>/dev/null; then
  echo "CPractice already running at ${URL}"
  exit 0
fi

echo "Starting CPractice at ${URL} ..."
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}" "$@"
