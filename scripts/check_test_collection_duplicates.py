#!/usr/bin/env python3
"""Guard: pytest collection must not collect the same test name twice.

Ticket #66 (batch 6): the backend test tree carried same-basename root and
subdirectory copies of many test files, so the standard lane collected and ran
every shared test name twice. This guard asserts the post-deduplication
invariant: within the standard lane's collection scope, no (test module
basename, class, test function name) key may be produced by two different
files.

Scope follows the lane runner: `backend/tests/` minus `backend/tests/blocking_io`
(the strict Blockbuster lane owns that directory exclusively and the standard
lane ignores it). Pass `--all` to include `tests/blocking_io/` in the analysis.

Exit code 0 when no duplicate collection exists; exit code 1 with a report of
every duplicated key otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
EXCLUDED_DIRS = ("blocking_io",)

PLUGIN_SOURCE = """\
import json, os

def pytest_collection_finish(session):
    items = [
        {
            "nodeid": item.nodeid,
            "path": str(item.path),
            "name": item.name,
        }
        for item in session.items
    ]
    with open(os.environ["COLLECTION_DUPLICATES_OUTPUT"], "w", encoding="utf-8") as stream:
        json.dump(items, stream)
"""


def collect_items() -> list[dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="collection-duplicates-") as temp_dir:
        plugin_path = Path(temp_dir) / "collection_duplicates_plugin.py"
        output_path = Path(temp_dir) / "items.json"
        plugin_path.write_text(PLUGIN_SOURCE, encoding="utf-8")
        command = [
            "uv", "run", "--no-sync", "pytest",
            "tests", "--collect-only", "-q", "-p", "collection_duplicates_plugin",
        ]
        env = os.environ.copy()
        env.setdefault("UV_CACHE_DIR", "/tmp/deer-flow-uv-cache")
        env["PYTHONPATH"] = os.pathsep.join([temp_dir, ".", "tests", env.get("PYTHONPATH", "")])
        env["COLLECTION_DUPLICATES_OUTPUT"] = str(output_path)
        result = subprocess.run(
            command, cwd=BACKEND_ROOT, capture_output=True, text=True, timeout=300, env=env
        )
        if not output_path.exists():
            print(result.stdout[-2000:], result.stderr[-2000:], sep="\n", file=sys.stderr)
            raise SystemExit(f"collection failed (exit {result.returncode}); no items captured")
        return json.loads(output_path.read_text(encoding="utf-8"))


def duplicate_key(item: dict[str, str], excluded: tuple[str, ...]) -> tuple[str, str] | None:
    """(test-module basename, class-qualified test name) for an item, if in scope."""
    path = Path(item["path"])
    relative = path.relative_to(BACKEND_ROOT)
    if any(part in excluded for part in relative.parts[:-1]):
        return None
    # class-qualified name from the nodeid ("tests/.../f.py::Class::test[ids]" or
    # "tests/.../f.py::test[ids]"), so same-named methods of different classes in
    # one file are distinct tests, not duplicate collection.
    qualified = "::".join(item["nodeid"].split("::")[1:])
    if "[" in qualified:  # strip parametrize ids — the test identity is the function
        qualified = qualified.split("[", 1)[0]
    return path.name, qualified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="include tests/blocking_io in the analysis")
    parser.add_argument("--json", metavar="PATH", help="also write the full duplicate report as JSON")
    args = parser.parse_args()
    excluded = () if args.all else EXCLUDED_DIRS

    items = collect_items()
    by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in items:
        key = duplicate_key(item, excluded)
        if key is not None:
            by_key[key].add(str(Path(item["path"]).relative_to(BACKEND_ROOT)))

    duplicates = {
        f"{basename}::{name}": sorted(paths)
        for (basename, name), paths in sorted(by_key.items())
        if len(paths) > 1
    }
    total = len(items)
    if args.json:
        Path(args.json).write_text(json.dumps({
            "collected_items": total,
            "duplicate_keys": duplicates,
        }, indent=1))

    if not duplicates:
        print(f"OK: {total} collected tests, no duplicate test-name collection in standard lane scope")
        return 0
    print(f"FAIL: {total} collected tests, {len(duplicates)} duplicate test-name keys "
          f"across {sum(len(p) for p in duplicates.values())} files")
    for key, paths in duplicates.items():
        print(f"  {key}: {' <-> '.join(paths)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
