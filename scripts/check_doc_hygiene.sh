#!/usr/bin/env bash
# Unified documentation-hygiene gate: one command that runs the three
# documentation governance entries against the working tree and aggregates
# their results.
#
# Entries:
#   documents    scripts/check_documents.py --repo-root <root>: read-only
#                document contract checker (inventory, metadata, links,
#                authority, routes, and its own protected-fingerprint rule).
#   guidance     scripts/sync_agent_guidance.py --check --repo-root <root>:
#                AGENTS.md / CLAUDE.md mirror consistency.
#   fingerprints Independent sha256 re-verification of the 67 protected file
#                fingerprints registered in the tracked durable policy
#                docs/governance/document-policy.json
#                (protected_files.fingerprints; captured from the governance
#                baseline at 867f67096 and re-registered with the policy).
#                The script reads only the tracked policy, so it runs in
#                every checkout (CI included) and never depends on the
#                git-ignored .scratch/ or dev-log/ baseline captures — there
#                is deliberately no skip path for missing baseline files.
#
# Exit codes: 0 all entries pass; 1 at least one entry failed; 2 usage error.
# Output: entry output lines carry a [doc-hygiene:<entry>] prefix; the
# DOC_HYGIENE_SUMMARY line is the aggregate verdict (PASS when all green,
# FAIL with the failed entry list otherwise).

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON_BIN=${PYTHON:-python3}
POLICY_PATH="docs/governance/document-policy.json"

usage() {
  cat <<'EOF'
Usage: scripts/check_doc_hygiene.sh

Runs the three documentation governance entries against the working tree:
  documents     scripts/check_documents.py
  guidance      scripts/sync_agent_guidance.py --check
  fingerprints  protected file sha256 re-verification (document-policy.json)

Exit codes: 0 all pass, 1 any entry failed, 2 usage error.
EOF
}

FAILED_ENTRIES=()

# Runs one entry, streams its combined output with an entry prefix, records
# failures without aborting so every entry still runs and the summary is
# complete.  PIPESTATUS[0] keeps the real exit code of the wrapped command.
run_entry() {
  local entry=$1
  shift
  echo "DOC_HYGIENE_ENTRY entry=${entry} command=$*"
  local status=0
  "$@" 2>&1 | sed -e "s/^/[doc-hygiene:${entry}] /" || status=${PIPESTATUS[0]}
  if [[ $status -eq 0 ]]; then
    echo "DOC_HYGIENE_RESULT entry=${entry} status=PASS"
  else
    echo "DOC_HYGIENE_RESULT entry=${entry} status=FAIL exit=${status}"
    FAILED_ENTRIES+=("${entry}")
  fi
  return 0
}

# Entry 3: re-verify the protected file fingerprints from the tracked policy.
# Semantics mirror check_documents.py's protected-fingerprint-mismatch rule:
# a missing file and a hash mismatch are both failures.
entry_fingerprints() {
  "$PYTHON_BIN" - "$ROOT_DIR" "$POLICY_PATH" <<'PYEOF'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
policy_path = root / sys.argv[2]
try:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
except (OSError, ValueError) as exc:
    print(f"cannot read policy {policy_path}: {exc}")
    sys.exit(2)

protected = policy.get("protected_files") or {}
fingerprints = protected.get("fingerprints")
if not isinstance(fingerprints, list) or not fingerprints:
    print("policy protected_files.fingerprints must be a non-empty list")
    sys.exit(2)

mismatches = 0
missing = 0
for entry in fingerprints:
    path = str(entry.get("path", ""))
    expected = str(entry.get("sha256", ""))
    try:
        data = (root / path).read_bytes()
    except OSError:
        print(f"MISSING {path}")
        missing += 1
        continue
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        print(f"MISMATCH {path}: expected {expected}, got {actual}")
        mismatches += 1

total = len(fingerprints)
ok = total - mismatches - missing
print(
    f"protected fingerprints: checked {total}, "
    f"match {ok}, mismatch {mismatches}, missing {missing}"
)
sys.exit(1 if (mismatches or missing) else 0)
PYEOF
}

case ${1:-} in
  "") ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

cd "$ROOT_DIR"

run_entry documents "$PYTHON_BIN" "$ROOT_DIR/scripts/check_documents.py" --repo-root "$ROOT_DIR"
run_entry guidance "$PYTHON_BIN" "$ROOT_DIR/scripts/sync_agent_guidance.py" --check --repo-root "$ROOT_DIR"
run_entry fingerprints entry_fingerprints

if [[ ${#FAILED_ENTRIES[@]} -eq 0 ]]; then
  echo "DOC_HYGIENE_SUMMARY entries=3 failed=0 status=PASS"
  exit 0
fi
echo "DOC_HYGIENE_SUMMARY entries=3 failed=${#FAILED_ENTRIES[@]} status=FAIL failed_entries=${FAILED_ENTRIES[*]}"
exit 1
