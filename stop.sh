#!/usr/bin/env bash
# Stop the local CPractice server.
set -uo pipefail
if pkill -f "uvicorn app.main:app" 2>/dev/null; then
  echo "CPractice stopped"
else
  echo "CPractice is not running (or pkill unavailable)"
fi
