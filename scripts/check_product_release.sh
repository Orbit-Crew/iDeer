#!/usr/bin/env bash
# Gate team releases on a product maintenance ref and a version record.
set -euo pipefail
release_tag=${1:?Usage: check_product_release.sh ideer-VERSION}
if [[ ! $release_tag =~ ^ideer-([0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?)$ ]]; then
  echo 'Team releases require an ideer-VERSION tag.' >&2
  exit 1
fi
release_version=${BASH_REMATCH[1]}
release_head=$(git rev-parse "$release_tag^{commit}")
if [[ $release_head != "$(git rev-parse HEAD)" ]]; then
  echo 'Release validation must run on the tagged candidate.' >&2
  exit 1
fi
product_refs=$(git for-each-ref --contains "$release_head" --format='%(refname)' 'refs/heads/product/offline-*' 'refs/remotes/origin/product/offline-*')
if [[ -z $product_refs ]]; then
  echo 'Release candidate is not contained in a product/offline-* maintenance branch.' >&2
  exit 1
fi
release_record="docs/releases/$release_tag.md"
if [[ ! -f $release_record ]] || ! git ls-files --error-unmatch "$release_record" >/dev/null 2>&1; then
  echo "Missing committed release version record: $release_record" >&2
  exit 1
fi
# ripgrep is preferred in CI, but fall back to grep when it is unavailable
# (e.g. minimal runner images) so the gate still validates record content.
if command -v rg >/dev/null 2>&1; then
  _release_grep() { rg -q "$@"; }
  _release_grep_i() { rg -qi "$@"; }
else
  _release_grep() { grep -Eq "$@"; }
  _release_grep_i() { grep -Eqi "$@"; }
fi
for required_field in upstream_baseline product_branch verification_command verification_result; do
  if ! _release_grep "^${required_field}: .+" "$release_record"; then
    echo "Release record missing field: $required_field" >&2
    exit 1
  fi
done
if ! _release_grep '^verification_result: passed$' "$release_record" || _release_grep_i '^verification_command: (none|historical|not run)' "$release_record"; then
  echo 'Release record requires a current successful verification command and result.' >&2
  exit 1
fi
if ! git diff --quiet HEAD -- "$release_record"; then
  echo 'Release record has uncommitted changes.' >&2
  exit 1
fi
record_upstream=$(sed -n 's/^upstream_baseline: //p' "$release_record")
if ! git cat-file -e "$record_upstream^{commit}" 2>/dev/null; then
  echo 'Release record names an unknown upstream baseline.' >&2
  exit 1
fi
record_branch=$(sed -n 's/^product_branch: //p' "$release_record")
if [[ ! $record_branch =~ ^product/offline-[A-Za-z0-9._-]+$ ]] || ! git merge-base --is-ancestor "$release_head" "origin/$record_branch"; then
  echo 'Release record does not name the containing origin product branch.' >&2
  exit 1
fi
bash scripts/verify_versions.sh "$release_version"
