#!/usr/bin/env python3
"""Normalize and check the root GitNexus guidance block."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

START = b"<!-- gitnexus:start -->"
END = b"<!-- gitnexus:end -->"
ROOT_LIMIT = 8 * 1024
BLOCK_LIMIT = 2 * 1024
# Frozen from dev-log/branch-root/ticket03/baseline/manifest.json.
BASE_ROOT_BYTES = 10_226
REFERENCE = Path("docs/agents/gitnexus-operations.md")
REFERENCE_ANCHOR = "#operations"
RECOGNIZED_TEMPLATE_SHA256 = frozenset(
    {
        # Installed GitNexus 1.6.10 generated template and the frozen project
        # template from before compaction. Only identity and index counts vary.
        "837047f469f80be3b7afc556bd4129f76e934c6c5df89c04d0cdb0a155f951d2",
        "418f3c34a06d687b1a986fd7d632d61fd299b8b9d8e0b0644d420440f760dff3",
    }
)
_PROJECT_IDENTITY = re.compile(
    rb"(?m)^(This project is indexed by GitNexus as \*\*)[A-Za-z0-9._-]+"
    rb"(\*\*)(?: \([0-9,]+ symbols, [0-9,]+ relationships, [0-9,]+ execution flows\))?\.$"
)
_RESOURCE_IDENTITY = re.compile(rb"gitnexus://repo/[A-Za-z0-9._-]+/")

COMPACT_BLOCK = """<!-- gitnexus:start -->
# GitNexus — Code Intelligence

Before editing a symbol, run upstream impact and report callers, processes, and risk. Use MCP `impact(...)` or the CLI. HIGH or CRITICAL requires warning the user before edits. UNKNOWN remains unresolved; confirm callers in source before treating an empty result as safe. Search supplements graph analysis, never replaces it.

Before committing, run complete `detect_changes({scope: \"all\"})`. Partial or truncated output is unresolved, and zero means unseen, not unaffected. Rerun the analysis. **Doc-only commits are exempt from re-indexing.** This applies only when every changed path ends in `.md`; record the partial result in the commit message. Every other change requires complete analysis.

For unfamiliar code, use `query(...)`; use `context(...)` for symbol callers, callees, and flows. Rename through GitNexus. For security review, `explain(...)` requires a prior `analyze --pdg`. See [GitNexus operations](docs/agents/gitnexus-operations.md#operations) for commands, resources, index identity, and recovery.
<!-- gitnexus:end -->""".encode()

REQUIRED = (
    b"impact(",
    b"callers",
    b"processes",
    b"HIGH",
    b"CRITICAL",
    b"UNKNOWN",
    b"detect_changes",
    b"Partial or truncated",
    b"Doc-only commits are exempt from re-indexing.",
    b"every changed path ends in `.md`",
    b"partial result in the commit message",
    b"query(",
    b"context(",
    b"Rename through GitNexus",
    b"explain(",
    b"analyze --pdg",
)


class GuidanceError(RuntimeError):
    pass


def _block_bounds(data: bytes) -> tuple[int, int]:
    if data.count(START) != 1 or data.count(END) != 1:
        raise GuidanceError(
            "root guidance must contain exactly one GitNexus marker pair"
        )
    start = data.index(START)
    end = data.index(END)
    if end < start:
        raise GuidanceError("GitNexus markers are out of order")
    end += len(END)
    return start, end


def _is_generated_template(block: bytes) -> bool:
    normalized = block.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    normalized = _PROJECT_IDENTITY.sub(rb"\1<project>\2.", normalized)
    normalized = _RESOURCE_IDENTITY.sub(b"gitnexus://repo/<project>/", normalized)
    return hashlib.sha256(normalized).hexdigest() in RECOGNIZED_TEMPLATE_SHA256


def _replace_block(data: bytes) -> bytes:
    start, end = _block_bounds(data)
    current = data[start:end]
    if current == COMPACT_BLOCK:
        return data
    if not _is_generated_template(current):
        raise GuidanceError(
            "unrecognized generated GitNexus block; no files were changed"
        )
    return data[:start] + COMPACT_BLOCK + data[end:]


def _atomic_write(path: Path, data: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _read_root(root: Path) -> tuple[Path, bytes]:
    path = root / "AGENTS.md"
    data = path.read_bytes()
    data.decode("utf-8", errors="strict")
    return path, data


def _normalized_size(data: bytes) -> int:
    return len(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def _candidate_bytes(root: Path, path: Path, revision: str | None) -> bytes:
    if revision is None:
        data = (root / path).read_bytes()
    else:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path.as_posix()}"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise GuidanceError(f"cannot read {path} at {revision}: {detail}")
        data = result.stdout
    data.decode("utf-8", errors="strict")
    return data


def _check(root: Path, revision: str | None = None) -> list[str]:
    findings: list[str] = []
    try:
        data = _candidate_bytes(root, Path("AGENTS.md"), revision)
        start, end = _block_bounds(data)
        block = data[start:end]
    except (OSError, UnicodeError, GuidanceError) as exc:
        return [str(exc)]

    root_size = _normalized_size(data)
    block_size = _normalized_size(block)
    if root_size > ROOT_LIMIT or root_size * 5 > BASE_ROOT_BYTES * 4:
        findings.append(
            f"root budget is {root_size} bytes; maximum is {min(ROOT_LIMIT, BASE_ROOT_BYTES * 4 // 5)}"
        )
    if block_size > BLOCK_LIMIT:
        findings.append(
            f"managed block budget is {block_size} bytes; maximum is {BLOCK_LIMIT}"
        )
    if block != COMPACT_BLOCK:
        findings.append("managed block is not the normalized compact template")
    for phrase in REQUIRED:
        if phrase not in block:
            findings.append(
                f"managed block is missing required rule: {phrase.decode('utf-8')}"
            )

    try:
        reference_text = _candidate_bytes(root, REFERENCE, revision).decode("utf-8")
    except (OSError, UnicodeError, GuidanceError):
        findings.append(f"missing or unreadable operational reference: {REFERENCE}")
    else:
        if "## Operations" not in reference_text:
            findings.append(
                f"operational reference is missing anchor {REFERENCE_ANCHOR}"
            )
        if REFERENCE_ANCHOR.encode() not in block:
            findings.append(f"managed block must link to {REFERENCE}{REFERENCE_ANCHOR}")

    try:
        if _candidate_bytes(root, Path("CLAUDE.md"), revision) != data:
            findings.append("root mirror differs: AGENTS.md and CLAUDE.md")
    except (OSError, UnicodeError, GuidanceError):
        findings.append("missing root mirror: CLAUDE.md")
    return findings


def _changed_paths(root: Path, base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}", "--"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise GuidanceError(f"cannot inspect candidate changes: {detail}")
    return [
        item.decode("utf-8", errors="strict")
        for item in result.stdout.split(b"\0")
        if item
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--normalize", action="store_true", help="compact a recognized generated block"
    )
    action.add_argument(
        "--check",
        action="store_true",
        help="check budgets, obligations, link, and mirror",
    )
    action.add_argument(
        "--check-exemption",
        action="store_true",
        help="verify that a candidate contains Markdown paths only",
    )
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref")
    parser.add_argument(
        "--revision", help="check guidance files from this Git revision"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.repo_root.resolve()
    if args.revision and not args.check:
        raise SystemExit("--revision is only valid with --check")
    try:
        if args.normalize:
            path, before = _read_root(root)
            after = _replace_block(before)
            if after != before:
                _atomic_write(path, after)
            print("GitNexus guidance normalized (idempotent).")
            return 0
        if args.check_exemption:
            if not args.base_ref or not args.head_ref:
                raise GuidanceError(
                    "--check-exemption requires --base-ref and --head-ref"
                )
            paths = _changed_paths(root, args.base_ref, args.head_ref)
            if not paths:
                raise GuidanceError(
                    "Markdown-only exemption requires at least one changed path"
                )
            non_markdown = [path for path in paths if not path.endswith(".md")]
            if non_markdown:
                raise GuidanceError(
                    "Markdown-only exemption rejected; changed paths without .md suffix: "
                    + ", ".join(non_markdown)
                )
            print(f"Markdown-only exemption applies to {len(paths)} changed path(s).")
            return 0
        findings = _check(root, args.revision)
    except (OSError, UnicodeError, GuidanceError) as exc:
        print(f"ERROR: {exc}")
        return 1
    for finding in findings:
        print(f"ERROR: {finding}")
    if findings:
        return 1
    mode = f"revision {args.revision}" if args.revision else "working tree"
    print(f"GitNexus root guidance check passed ({mode}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
