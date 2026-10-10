#!/usr/bin/env bash
# CPractice - Codespace / local setup script.
# Installs Python dependencies and runs preflight environment checks.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> CPractice setup"
echo "    python: $(python --version 2>&1)"
echo "    gcc:    $(gcc --version 2>&1 | head -1)"

# --- Python dependencies ---------------------------------------------------
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

# --- Preflight checks ------------------------------------------------------
echo "==> Preflight checks"

# 1. Compiler present?
if ! command -v "${CC_COMPILER:-gcc}" >/dev/null 2>&1; then
  echo "    [!] C compiler '${CC_COMPILER:-gcc}' not found on PATH" >&2
  exit 1
fi
echo "    [ok] C compiler available"

# 2. Compile + execute a probe program to confirm the runner can execute
#    binaries in this filesystem (shared storage on Android is noexec).
PROBE_DIR="$(mktemp -d)"
trap 'rm -rf "$PROBE_DIR"' EXIT
cat > "$PROBE_DIR/probe.c" <<'EOF'
#include <stdio.h>
int main(void) { printf("probe-ok\n"); return 0; }
EOF
if "${CC_COMPILER:-gcc}" -std="${CC_STANDARD:-c11}" -o "$PROBE_DIR/probe" "$PROBE_DIR/probe.c" 2>"$PROBE_DIR/err"; then
  if out="$("$PROBE_DIR/probe" 2>/dev/null)" && [ "$out" = "probe-ok" ]; then
    echo "    [ok] compiled binaries execute in this environment"
  else
    echo "    [!] compiled binary built but could not execute (noexec filesystem?)" >&2
    exit 1
  fi
else
  echo "    [!] probe compilation failed:" >&2
  cat "$PROBE_DIR/err" >&2
  exit 1
fi

# 3. Verify exec-capable scratch space for workspaces.
WS="${WORKSPACES_DIR:-workspaces}"
mkdir -p "$WS"

# 4. .env presence (not fatal - AI features need it).
if [ -f .env ]; then
  echo "    [ok] .env present"
else
  echo "    [i]  no .env yet - copy .env.example and add GOOGLE_API_KEY for AI features"
fi

echo "==> Setup complete. Start the app with:"
echo "    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
