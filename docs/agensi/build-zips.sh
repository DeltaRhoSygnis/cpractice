#!/usr/bin/env bash
# Build submission-ready zips for the Agensi marketplace.
#
# Rules enforced by Agensi (see docs/agensi/FEASIBILITY.md):
#   - exactly one top-level folder in the archive, named after the skill
#   - SKILL.md at the root of that folder
#   - text files only: no binaries, no symlinks
#   - no .DS_Store / Thumbs.db
#
# Usage:  ./build-zips.sh [skill-name ...]
# Output: dist/<skill-name>.zip

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$HERE/skills"
DIST_DIR="$HERE/dist"

command -v zip >/dev/null 2>&1 || {
  echo "error: 'zip' is not installed" >&2
  exit 1
}

mkdir -p "$DIST_DIR"

targets=("$@")
if [ ${#targets[@]} -eq 0 ]; then
  targets=()
  # Only the published listing is built by default. The other folders are
  # drafts kept for reference and must never reach the marketplace.
  if [ -f "$SKILLS_DIR/deterministic-autograder/SKILL.md" ]; then
    targets+=("deterministic-autograder")
  fi
fi
if [ ${#targets[@]} -eq 0 ]; then
  echo "no skills found in $SKILLS_DIR" >&2
  exit 1
fi

for name in "${targets[@]}"; do
  dir="$SKILLS_DIR/$name"
  if [ ! -f "$dir/SKILL.md" ]; then
    echo "error: $name has no SKILL.md" >&2
    exit 1
  fi

  # name in frontmatter must match the folder name, or the skill never loads
  fm_name="$(sed -n 's/^name:[[:space:]]*//p' "$dir/SKILL.md" | head -1)"
  if [ "$fm_name" != "$name" ]; then
    echo "error: $name has frontmatter name '$fm_name'" >&2
    exit 1
  fi

  out="$DIST_DIR/$name.zip"
  rm -f "$out"
  (
    cd "$SKILLS_DIR"
    zip -r -q "$out" "$name" \
      -x "*/.DS_Store" -x "*/Thumbs.db" -x "*/__MACOSX/*" -x "*/.git/*"
  )
  echo "built $out"
done
