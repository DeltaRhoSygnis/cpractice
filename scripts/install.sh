#!/usr/bin/env bash
# Guided install checker: prints the next command; installs only with --yes.
# It never downloads or pipes remote code into a shell.
set -euo pipefail
SPEC='cpractice @ git+https://github.com/DeltaRhoSygnis/cpractice.git'
ASSUME_YES=0
usage() {
  cat <<'EOF'
Usage: scripts/install.sh [--yes]
Check for uv/pipx and a C compiler, then print the next command.
Without --yes nothing is installed; --yes runs the printed installer.
  -h, --help   show this help
      --yes    run the install command after printing it
EOF
}
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --yes) ASSUME_YES=1 ;;
    *) echo "unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done
is_termux() {
  [ -n "${TERMUX_VERSION:-}" ] && return 0
  case "${PREFIX:-}" in *com.termux*) return 0 ;; *) return 1 ;; esac
}
compiler_fix() {
  if is_termux; then echo "pkg install clang"
  elif [ "$(uname -s)" = "Darwin" ]; then echo "xcode-select --install"
  elif command -v apt-get >/dev/null 2>&1; then echo "sudo apt install build-essential"
  else echo "install gcc with your system package manager"; fi
}
find_compiler() {
  local candidate
  for candidate in "${CC_COMPILER:-gcc}" gcc cc clang; do
    command -v "$candidate" >/dev/null 2>&1 && { echo "$candidate"; return 0; }
  done
  return 1
}
if command -v uv >/dev/null 2>&1; then
  INSTALLER="uv"; COMMAND="uv tool install \"$SPEC\""
elif command -v pipx >/dev/null 2>&1; then
  INSTALLER="pipx"; COMMAND="pipx install \"$SPEC\""
else
  INSTALLER=""; COMMAND=""
fi
echo "CPractice guided installer"
echo "Python:     $(python3 --version 2>/dev/null || echo 'not found (3.12 or newer is required)')"
if COMPILER="$(find_compiler)"; then
  echo "C compiler: $COMPILER (cpractice doctor verifies compile and run)"
  [ "$COMPILER" = "gcc" ] || echo "  note: set CC_COMPILER=$COMPILER for grading and doctor"
else
  echo "C compiler: not found"; echo "  fix: $(compiler_fix)"
fi
echo
if [ -n "$INSTALLER" ]; then
  echo "Next command:"; echo "  $COMMAND"
else
  echo "No uv or pipx found. Install one first:"
  echo "  python3 -m pip install --user pipx"
  echo "  python3 -m pipx ensurepath"
  echo "Then rerun this script."
fi
echo

if [ "$ASSUME_YES" -ne 1 ]; then
  echo "Nothing was installed. Re-run with --yes to run the command above."
  exit 0
fi
if [ -z "$INSTALLER" ]; then
  echo "Cannot install without uv or pipx." >&2; exit 1
fi
echo "Running: $COMMAND"
if [ "$INSTALLER" = "uv" ]; then uv tool install "$SPEC"; else pipx install "$SPEC"; fi
echo; echo "Installed. Start it with: cpractice start"
if ! find_compiler >/dev/null 2>&1; then
  echo "Grading still needs a C compiler: $(compiler_fix)"
fi
