#!/usr/bin/env python3
"""Report tests that reference the files changed by the current candidate.

Advisory only: the report lists test files that mention a changed product
file (by path, by import specifier, or through a curated surface mapping)
so the author can run them or record why they stay unexecuted. The lookup
never decides lane scope and never fails a lane on its own.

The default candidate is the working tree: uncommitted changes plus
untracked, non-ignored files, matching the lane runner's candidate
fingerprint. Pass ``--base`` (and optionally ``--head``) to replay an
explicit commit range instead.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SURFACE_FILE = Path(__file__).with_name("test_reference_surfaces.json")

TEST_DIRS = ("backend/tests/", "frontend/tests/", "local-runtime/tests/")
TEST_SUFFIXES = (".py", ".ts", ".tsx", ".mts", ".js", ".jsx")
TEST_NAME_HINTS = ("test_", ".test.", ".spec.", "_test.")
_SCAN_EXCLUDE = ("__pycache__/", "node_modules/")

# Quote/slash boundaries collapse so that `Path("a") / "b" / "c.md"`,
# import specifiers, and plain "a/b/c.md" strings all match one key.
_SLASH_BOUNDARY = re.compile(r"[\'\"]?\s*/\s*[\'\"]?")
_QUOTE = re.compile(r"[\'\"]")


def normalize_source(text: str) -> str:
    """Collapse quote and whitespace around path separators."""

    return _SLASH_BOUNDARY.sub("/", text)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip()[:200]}"
        )
    return result.stdout


def changed_files(
    root: Path, base: str | None = None, head: str | None = None
) -> list[str]:
    """Return repo-relative paths changed by the candidate.

    With ``base`` the candidate is the commit range ``base..head`` (head
    defaults to HEAD). Without it, the candidate is the working tree:
    uncommitted changes plus untracked, non-ignored files.
    """

    if base:
        spec = f"{base}..{head or 'HEAD'}"
        out = _git(root, "diff", "--name-only", spec)
    else:
        out = _git(root, "diff", "--name-only", "HEAD")
        out += _git(root, "ls-files", "--others", "--exclude-standard")
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def scan_test_files(root: Path) -> dict[str, str]:
    """Return {repo-relative path: normalized content} for test files."""

    tests: dict[str, str] = {}
    for test_dir in TEST_DIRS:
        base = root / test_dir.rstrip("/")
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            rel = path.relative_to(root).as_posix()
            if not path.is_file() or path.suffix not in TEST_SUFFIXES:
                continue
            if not any(hint in path.name for hint in TEST_NAME_HINTS):
                continue
            if any(part in rel for part in _SCAN_EXCLUDE):
                continue
            try:
                tests[rel] = normalize_source(
                    path.read_text(encoding="utf-8", errors="replace")
                )
            except OSError:
                continue
    return tests


def load_surfaces(root: Path) -> dict[str, list[str]]:
    """Load the curated prefix -> consumer-glob mapping when present."""

    surface_file = root / "scripts" / SURFACE_FILE.name
    if not surface_file.is_file():
        return {}
    try:
        payload = json.loads(surface_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    surfaces = payload.get("surfaces", {}) if isinstance(payload, dict) else {}
    return {str(k): list(v) for k, v in surfaces.items() if isinstance(v, list)}


def _match_keys(path: str) -> list[str]:
    """Path keys to search for, never shorter than two segments.

    The full path matches direct references; progressively shorter suffixes
    match import specifiers that omit the repo prefix and extension.
    """

    segments = path.split("/")
    keys: list[str] = []
    for start in range(len(segments)):
        suffix = "/".join(segments[start:])
        keys.append(suffix)
        stem = suffix.rsplit("/", 1)[-1]
        if "." in stem:
            strip = len(stem) - len(stem.rsplit(".", 1)[0])
            keys.append(suffix[: len(suffix) - strip])
        if stem.endswith(".py"):
            # Python imports reference modules with dots: app.models.user.
            keys.append(suffix[:-3].replace("/", "."))
    return [key for key in dict.fromkeys(keys) if "/" in key or "." in key]


def _expand_surface_globs(root: Path, patterns: list[str]) -> set[str]:
    expanded: set[str] = set()
    for pattern in patterns:
        try:
            if pattern.endswith("/**"):
                base_dir = root / pattern[: -len("/**")]
                hits = base_dir.rglob("*") if base_dir.is_dir() else ()
            else:
                hits = root.glob(pattern)
            for hit in hits:
                if hit.is_file():
                    expanded.add(hit.relative_to(root).as_posix())
        except (OSError, ValueError):
            continue
    return expanded


def match_references(
    changed: list[str],
    tests: dict[str, str],
    *,
    root: Path | None = None,
    surfaces: dict[str, list[str]] | None = None,
) -> dict[str, list[tuple[str, str]]]:
    """Return {changed path: [(test path, kind)]} for every match found."""

    product_changes = [p for p in changed if not p.startswith(TEST_DIRS)]
    if not product_changes:
        return {}

    surface_hits: dict[str, set[str]] = {}
    if surfaces and root is not None:
        expanded: dict[str, set[str]] = {}
        for prefix, patterns in surfaces.items():
            expanded[prefix] = _expand_surface_globs(root, patterns)
        for path in product_changes:
            for prefix, consumers in expanded.items():
                if path.startswith(prefix):
                    surface_hits.setdefault(path, set()).update(consumers)

    matches: dict[str, list[tuple[str, str]]] = {}
    for path in product_changes:
        keys = _match_keys(path)
        pattern = re.compile("|".join(re.escape(key) for key in keys)) if keys else None
        hits: list[tuple[str, str]] = []
        if pattern is not None:
            for test_rel, content in tests.items():
                # Defensive normalization: scan_test_files already normalized,
                # but hand-assembled inputs may not be.
                if pattern.search(normalize_source(content)):
                    hits.append((test_rel, "path"))
        for consumer in sorted(surface_hits.get(path, ())):
            if consumer not in {t for t, _ in hits}:
                hits.append((consumer, "surface"))
        if hits:
            matches[path] = sorted(hits)
    return matches


def _print_report(
    matches: dict[str, list[tuple[str, str]]], candidate_size: int
) -> None:
    if not matches:
        return
    total = sum(len(hits) for hits in matches.values())
    print(f"[test-reference-lookup] candidate files: {candidate_size}")
    for path, hits in matches.items():
        print(f"[test-reference-lookup] {path}")
        for test_rel, kind in hits:
            print(f"[test-reference-lookup]   {kind:7} {test_rel}")
    print(
        f"[test-reference-lookup] matches: {total} test file(s) across "
        f"{len(matches)} changed file(s); advisory — run them or record why they stay unexecuted"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument(
        "--base", help="replay an explicit commit range instead of the worktree"
    )
    parser.add_argument(
        "--head", default=None, help="range end (default HEAD, requires --base)"
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit JSON")
    parser.add_argument(
        "--strict", action="store_true", help="exit 2 when any match is reported"
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    try:
        candidate = changed_files(root, base=args.base, head=args.head)
        tests = scan_test_files(root)
        matches = match_references(
            candidate, tests, root=root, surfaces=load_surfaces(root)
        )
    except (RuntimeError, OSError) as exc:
        print(f"[test-reference-lookup] WARN lookup skipped: {exc}", file=sys.stderr)
        return 0

    if args.as_json:
        payload = {
            "candidate_files": len(candidate),
            "matches": {
                path: [{"test": t, "kind": k} for t, k in hits]
                for path, hits in matches.items()
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_report(matches, len(candidate))

    if args.strict and matches:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
