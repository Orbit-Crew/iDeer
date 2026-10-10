#!/usr/bin/env bash
set -euo pipefail

# The convergence is complete: control-plane code must use the DeerFlow
# runtime. Reject any reintroduction of direct legacy runtime imports.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if command -v rg >/dev/null 2>&1; then
  mapfile -t imports < <(rg -l '^[[:space:]]*(from ideer|import ideer)' "$repo_root/backend/app" -g '*.py' | sort || true)
else
  mapfile -t imports < <(grep -Rl -E '^[[:space:]]*(from ideer|import ideer)' "$repo_root/backend/app" --include='*.py' | sort || true)
fi

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
