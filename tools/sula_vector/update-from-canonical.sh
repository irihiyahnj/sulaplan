#!/usr/bin/env bash
# update-from-canonical.sh — refresh a Sula vector project's tooling from the canonical source.
#
# Usage:
#   update-from-canonical.sh --project-root <path> [--canonical <git-url-or-local-path>]
#
# Default canonical: https://github.com/irihiyahnj/sula-vector.git
#
# This script is operator-level (not a per-project skill). It clones the canonical
# Sula source to a temp directory and runs migrate.py against the target project.
# Idempotent: refreshes tools/sula_vector/ files in-place and updates AGENTS.md
# (sentinel-protected) without re-doing fragment migration that's already done.

set -euo pipefail

usage() {
  cat <<EOF
usage: $(basename "$0") --project-root <path> [--canonical <git-url-or-local-path>]

Refreshes <project-root>/tools/sula_vector/ from the canonical Sula source.

Default canonical: https://github.com/irihiyahnj/sula-vector.git
Pass --canonical /local/path/to/sula-vector to update from a local clone instead.
EOF
}

PROJECT_ROOT=""
CANONICAL="https://github.com/irihiyahnj/sula-vector.git"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root) PROJECT_ROOT="$2"; shift 2;;
    --canonical)    CANONICAL="$2"; shift 2;;
    -h|--help)      usage; exit 0;;
    *) echo "unknown arg: $1" >&2; usage; exit 1;;
  esac
done

[[ -z "$PROJECT_ROOT" ]] && { usage; exit 1; }
[[ -d "$PROJECT_ROOT" ]] || { echo "project-root not found: $PROJECT_ROOT" >&2; exit 2; }

if [[ -d "$CANONICAL" ]]; then
  CANONICAL_DIR="$CANONICAL"
  echo "using local canonical: $CANONICAL_DIR"
else
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  echo "fetching canonical from $CANONICAL ..."
  git clone --depth=1 "$CANONICAL" "$TMP/canonical" >/dev/null 2>&1
  CANONICAL_DIR="$TMP/canonical"
fi

MIGRATE="$CANONICAL_DIR/tools/sula_vector/migrate.py"
[[ -f "$MIGRATE" ]] || { echo "canonical missing migrate.py at $MIGRATE" >&2; exit 3; }

echo
echo "running migrate.py against $PROJECT_ROOT"
echo "(idempotent: refreshes tooling and AGENTS.md sentinels; does not duplicate existing fragments)"
echo
python3 "$MIGRATE" --project-root "$PROJECT_ROOT"

echo
echo "verify boot:"
echo "  python3 $PROJECT_ROOT/tools/sula_vector/render.py $PROJECT_ROOT --for-agent"
