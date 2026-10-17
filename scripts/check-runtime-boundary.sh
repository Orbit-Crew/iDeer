#!/usr/bin/env bash
set -euo pipefail

# The convergence is complete: control-plane code must use the DeerFlow
# runtime. Reject any reintroduction of direct legacy runtime imports.
# The scan is the gate: degrade to an explicit failure when ripgrep is
# missing rather than silently scanning nothing (08-M4 false green).
if ! command -v rg >/dev/null 2>&1; then
  printf 'ERROR: ripgrep (rg) is required by check-runtime-boundary.sh but was not found on PATH; install ripgrep so the boundary scan cannot silently pass.\n' >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mapfile -t imports < <(rg -l '^[[:space:]]*(from ideer|import ideer)' "$repo_root/backend/app" -g '*.py' | sort || true)

printf 'backend/app direct ideer import files: %s\n' "${#imports[@]}"
if (( ${#imports[@]} )); then
  printf '%s\n' "${imports[@]}"
fi

baseline="${RUNTIME_BOUNDARY_MAX_IMPORT_FILES:-0}"
if (( ${#imports[@]} > baseline )); then
  printf 'ERROR: runtime boundary grew from %s to %s files\n' "$baseline" "${#imports[@]}" >&2
  exit 1
fi
printf 'OK: boundary is not larger than baseline (%s)\n' "$baseline"
