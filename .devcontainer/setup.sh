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

# 5. Codespaces secrets. GitHub injects these into the environment when the
#    container is built with the secret present. We never print the values.
echo "==> Codespaces secrets"
check_secret() {
  local name="$1" purpose="$2"
  if [ -n "${!name:-}" ]; then
    echo "    [ok] $name is set (${purpose})"
  else
    echo "    [!]  $name is NOT set (${purpose})"
    echo "         -> GitHub > Settings > Codespaces > Secrets, then rebuild."
  fi
}
check_secret "KENARI_API_KEY" "OpenCode provider"
check_secret "GEMINI_API_KEY" "Gemini / AI Studio"

# The app expects GOOGLE_API_KEY. If only GEMINI_API_KEY is present, persist
# the alias so the application sees it. Stored in .env (gitignored), never
# echoed to the terminal.
if [ -z "${GOOGLE_API_KEY:-}" ] && [ -n "${GEMINI_API_KEY:-}" ]; then
  if [ ! -f .env ]; then
    cp .env.example .env 2>/dev/null || true
  fi
  if [ -f .env ] && ! grep -q "^GOOGLE_API_KEY=." .env; then
    # Rewrite the GOOGLE_API_KEY line with the secret value.
    if grep -q "^GOOGLE_API_KEY=" .env; then
      python3 - "$GEMINI_API_KEY" <<'PY'
import pathlib, sys
path = pathlib.Path(".env")
key = sys.argv[1]
lines = path.read_text().splitlines()
lines = [f"GOOGLE_API_KEY={key}" if l.startswith("GOOGLE_API_KEY=") else l for l in lines]
path.write_text("\n".join(lines) + "\n")
PY
      echo "    [ok] GOOGLE_API_KEY populated in .env from GEMINI_API_KEY"
    fi
  fi
  export GOOGLE_API_KEY="$GEMINI_API_KEY"
fi

echo "==> Setup complete. Start the app with:"
echo "    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
