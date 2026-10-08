#!/usr/bin/env python3
"""Candidate-pinned collector CLI for auditable disclosure reading sessions."""

import argparse
import contextlib
import fnmatch
import fcntl
import functools
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath


TASKS = (
    "ui",
    "chat",
    "knowledge",
    "permissions",
    "tests",
    "runtime",
    "upstream",
    "history",
)
ANSWER_FIELDS = (
    "entry",
    "constraints",
    "authorities",
    "relevant_decisions",
    "validation",
    "unknowns",
)
FORBIDDEN_PARTS = {".git", ".scratch", "dev-log", "specs"}
MAX_SEARCH_MATCHES = 1000
MAX_SESSION_SECONDS = 300
EVALUATOR_MATERIAL = {
    "docs/governance/document-policy.json",
    "docs/governance/disclosure-scoring-rubric-2026-10-07.md",
    "docs/governance/disclosure-review-fixes-2026-10-06.md",
    "docs/governance/disclosure-reading-collector-2026-10-07.md",
    "docs/specs/2026-10-07-progressive-disclosure-readability-recovery-spec.md",
    "scripts/score_disclosure_readability.py",
    "scripts/disclosure_reading_collector.py",
    "scripts/report_disclosure_costs.py",
    "scripts/run_disclosure_reading_session.py",
    "backend/tests/unit/scripts/test_score_disclosure_readability.py",
    "backend/tests/unit/scripts/test_disclosure_reading_collector.py",
    "backend/tests/unit/scripts/test_report_disclosure_costs.py",
}


class UsageError(Exception):
    pass


def fail(message):
    raise UsageError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


@contextlib.contextmanager
def record_lock(path, *other_paths):
    paths = sorted({Path(item).resolve() for item in (path, *other_paths)})
    with contextlib.ExitStack() as stack:
        for target in paths:
            lock_path = Path(f"{target}.lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = stack.enter_context(lock_path.open("a", encoding="utf-8"))
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            stack.callback(fcntl.flock, lock_file.fileno(), fcntl.LOCK_UN)
        yield


def write_record(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(record, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def serialized_record_update(function):
    @functools.wraps(function)
    def wrapped(args, *positional, **named):
        other_paths = (args.retry_of,) if getattr(args, "retry_of", None) else ()
        with record_lock(args.record, *other_paths):
            return function(args, *positional, **named)

    return wrapped


def is_readable(path):
    try:
        data = path.read_bytes()
        data.decode("utf-8")
        return b"\0" not in data
    except (OSError, UnicodeError):
        return False


def candidate_files(root):
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            fail(
                f"candidate contains a symlink outside its root: {path.relative_to(root)}"
            )
        raw = resolved.read_bytes()
        rel = path.relative_to(root).as_posix()
        rows.append(
            {
                "path": rel,
                "bytes": len(raw),
                "sha256": digest(raw),
                "readable_text": is_readable(resolved),
                "exclusion": exclusion_reason(rel),
            }
        )
    return rows


def build_manifest(root, out):
    root = root.resolve(strict=True)
    if not root.is_dir():
        fail("candidate root is not a directory")
    rows = candidate_files(root)
    excluded = [
        {"path": row["path"], "sha256": row["sha256"], "reason": row["exclusion"]}
        for row in rows
        if row["exclusion"]
    ]
    body = {"format": 2, "root_name": root.name, "files": rows, "exclusions": excluded}
    body["exclusion_sha256"] = digest(canonical_json(excluded))
    body["manifest_sha256"] = digest(canonical_json(body))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"files": len(rows), "manifest_sha256": body["manifest_sha256"]}))


def load_manifest(path, root, verify_tree=False):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    claimed = manifest.pop("manifest_sha256", None)
    if claimed != digest(canonical_json(manifest)):
        fail("manifest digest mismatch")
    manifest["manifest_sha256"] = claimed
    by_path = {row["path"]: row for row in manifest["files"]}
    if verify_tree:
        actual = candidate_files(root)
        if actual != manifest["files"]:
            fail("candidate contents differ from frozen manifest")
    return manifest, by_path


def load_record(path):
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("status") != "started":
        fail("session is not open for reads")
    return record


def require_root_guidance(record, path=None, start=None, end=None, line_count=None):
    if not record["events"]:
        if path != "AGENTS.md" or start != 1 or end != line_count:
            fail(
                "first content access must read the complete AGENTS.md at the candidate root"
            )
        record["started_monotonic"] = time.monotonic()
    elif (
        not record["events"][0]["ranges"]
        or record["events"][0]["ranges"][0]["path"] != "AGENTS.md"
    ):
        fail("session root guidance event is missing")


def forbidden_path(rel):
    lowered = [part.casefold() for part in PurePosixPath(rel).parts]
    return (
        any(part in FORBIDDEN_PARTS for part in lowered)
        or any("handoff" in part for part in lowered)
        or exclusion_reason(rel) is not None
    )


def exclusion_reason(rel):
    """Keep benchmark prompts, scoring rules, and scoring implementations out of reader access."""
    key = PurePosixPath(rel).as_posix()
    parts = PurePosixPath(key).parts
    if any(part.casefold() in FORBIDDEN_PARTS for part in parts) or any(
        "handoff" in part.casefold() for part in parts
    ):
        return "private-session-or-spec-material"
    if key in EVALUATOR_MATERIAL:
        return "evaluation-or-scoring-material"
    if any(
        part.casefold()
        in {
            "benchmark",
            "benchmarks",
            "eval",
            "evaluation",
            "evaluations",
            "zero_agent_eval_cases",
            "grading",
            "scoring",
            "rubrics",
        }
        for part in parts
    ):
        return "evaluation-or-scoring-material"
    filename = PurePosixPath(key).name.casefold()
    if any(
        term in filename
        for term in (
            "rubric",
            "answer_key",
            "answer-key",
            "grading_anchor",
            "adjudicat",
        )
    ):
        return "evaluation-or-scoring-material"
    if any(
        part.casefold() in {"tests", "test", "fixtures", "fixture", "scripts"}
        for part in parts
    ) and any(
        term in filename
        for term in ("score", "scoring", "rubric", "answer", "grading", "adjudicat")
    ):
        return "evaluation-or-scoring-material"
    return None


def permitted_path(root, requested, by_path):
    rel = PurePosixPath(requested)
    if (
        rel.is_absolute()
        or not rel.parts
        or any(part in ("", ".", "..") for part in rel.parts)
    ):
        fail("read requires a safe, candidate-relative path")
    if forbidden_path(key := rel.as_posix()):
        fail("path is forbidden for evaluation")
    if key not in by_path or not by_path[key]["readable_text"]:
        fail("path is not a readable text file in this candidate")
    path = root.joinpath(*rel.parts)
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        fail("resolved path escapes candidate root")
    raw = resolved.read_bytes()
    if digest(raw) != by_path[key]["sha256"]:
        fail("read file hash differs from frozen manifest")
    return key, raw


_ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+|$)(.*?)\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")


def markdown_headings(raw):
    """List Markdown ATX and Setext headings, ignoring fenced code blocks."""
    lines = raw.decode("utf-8").splitlines()
    found = []
    fence_char = None
    fence_size = 0
    for index, line in enumerate(lines):
        fence = _FENCE.match(line)
        if fence_char is not None:
            if (
                fence
                and fence.group(1)[0] == fence_char
                and len(fence.group(1)) >= fence_size
                and not fence.group(2).strip()
            ):
                fence_char = None
                fence_size = 0
            continue
        if fence:
            fence_char = fence.group(1)[0]
            fence_size = len(fence.group(1))
            continue
        setext = _SETEXT.match(line)
        if setext and index > 0:
            start = index - 1
            previous = lines[start]
            if (
                previous.strip()
                and not _ATX_HEADING.match(previous)
                and not _FENCE.match(previous)
            ):
                while start > 0:
                    candidate = lines[start - 1]
                    if (
                        not candidate.strip()
                        or _ATX_HEADING.match(candidate)
                        or _FENCE.match(candidate)
                        or _SETEXT.match(candidate)
                    ):
                        break
                    start -= 1
                found.append(
                    {
                        "level": 1 if setext.group(1).startswith("=") else 2,
                        "title": " ".join(part.strip() for part in lines[start:index]),
                        "line": start + 1,
                        "end_line": index + 1,
                    }
                )
                continue
        atx = _ATX_HEADING.match(line)
        if atx:
            title = atx.group(2).strip()
            title = re.sub(r"[ \t]+#+[ \t]*$", "", title)
            found.append(
                {
                    "level": len(atx.group(1)),
                    "title": title,
                    "line": index + 1,
                    "end_line": index + 1,
                }
            )
    stack = []
    for item in found:
        while stack and stack[-1]["level"] >= item["level"]:
            stack.pop()
        stack.append({"level": item["level"], "title": item["title"]})
        item["path"] = [part["title"] for part in stack]
    return found


def section_range(headings, heading_path, line_count):
    if (
        not isinstance(heading_path, list)
        or not heading_path
        or any(not isinstance(part, str) or not part.strip() for part in heading_path)
    ):
        fail("heading path must be a non-empty array of titles")
    matches = [item for item in headings if item["path"] == heading_path]
    if not matches:
        fail("heading path not found")
    if len(matches) > 1:
        fail("heading path is duplicate; select a unique complete title hierarchy")
    selected = matches[0]
    end = line_count
    for item in headings:
        if item["line"] > selected["line"] and item["level"] <= selected["level"]:
            end = item["line"] - 1
            break
    return selected["line"], end


def unique_byte_count(events):
    ranges = {}
    for event in events:
        for item in event["ranges"]:
            ranges.setdefault(item["path"], set()).update(
                range(item["start"], item["end"] + 1)
            )
    total = 0
    for name, selected in ranges.items():
        data = Path(events[0]["root"], name).read_bytes()
        lines = data.splitlines(keepends=True)
        total += sum(len(lines[index - 1]) for index in selected)
    return total


@serialized_record_update
def start_session(args):
    root = args.root.resolve(strict=True)
    if args.startup_timeout_seconds <= 0:
        fail("startup timeout must be a positive number of seconds")
    manifest, _ = load_manifest(args.manifest, root, verify_tree=True)
    if args.candidate not in ("baseline", "after") or args.task not in TASKS:
        fail("candidate or task is not in the fixed evaluation protocol")
    if not args.run_id or len(args.task_hash) != 64:
        fail("run id or task digest is invalid")
    if args.record.exists():
        fail("session record already exists")
    prior = None
    if args.retry_of is not None:
        if not args.retry_reason or not args.retry_reason.strip():
            fail("a retry requires a recorded infrastructure or protocol reason")
        prior_path = args.retry_of.resolve(strict=True)
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        if prior.get("status") not in {"failed", "interrupted"} or prior.get(
            "failure_class"
        ) not in {"infrastructure", "workspace_load", "protocol"}:
            fail(
                "only failed or interrupted infrastructure, workspace-load, or protocol attempts may be retried"
            )
        if prior.get("retry_run_id") or prior.get("attempt_no", 1) >= 2:
            fail("the one permitted retry has already been used")
        if (
            prior.get("candidate"),
            prior.get("task"),
            prior.get("task_sha256"),
            prior.get("manifest_sha256"),
        ) != (
            args.candidate,
            args.task,
            args.task_hash,
            manifest["manifest_sha256"],
        ):
            fail("retry candidate, task, and manifest must match the original attempt")
        if (
            prior.get("model_config") != args.model_config
            or prior.get("tool_config_sha256") != args.tool_config_sha256
        ):
            fail("retry model and tool configuration must match the original attempt")
    args.record.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "format": 1,
        "run_id": args.run_id,
        "candidate": args.candidate,
        "candidate_root": str(root),
        "manifest_sha256": manifest["manifest_sha256"],
        "task": args.task,
        "task_sha256": args.task_hash,
        "model_config": args.model_config,
        "attempt_no": (prior.get("attempt_no", 1) + 1) if prior else 1,
        "retry_of": prior.get("run_id") if prior else None,
        "retry_reason": args.retry_reason.strip() if prior else None,
        "retry_run_id": None,
        "external_help": [],
        "contamination": [],
        "tool_config_sha256": args.tool_config_sha256,
        "startup_timeout_seconds": args.startup_timeout_seconds,
        "started_monotonic": None,
        "events": [],
        "status": "started",
    }
    write_record(args.record, record)
    if prior is not None:
        prior["retry_run_id"] = args.run_id
        prior["retry_reason"] = args.retry_reason.strip()
        write_record(prior_path, prior)
    print(
        json.dumps(
            {"status": "started", "run_id": args.run_id, "root_guidance": "AGENTS.md"}
        )
    )


@serialized_record_update
def read_content(args):
    record = load_record(args.record)
    root = Path(record["candidate_root"]).resolve(strict=True)
    manifest_path = Path(args.manifest).resolve(strict=True)
    manifest, by_path = load_manifest(manifest_path, root, verify_tree=True)
    if manifest["manifest_sha256"] != record["manifest_sha256"]:
        fail("session candidate differs from its frozen manifest")
    key, raw = permitted_path(root, args.path, by_path)
    lines = raw.decode("utf-8").splitlines(keepends=True)
    heading_path = getattr(args, "heading_path", None)
    if heading_path is not None:
        if not key.casefold().endswith(".md"):
            fail("heading reads require a Markdown file")
        try:
            requested_path = (
                json.loads(heading_path)
                if isinstance(heading_path, str)
                else heading_path
            )
        except json.JSONDecodeError as exc:
            raise UsageError("heading path must be a JSON array of titles") from exc
        start, end = section_range(markdown_headings(raw), requested_path, len(lines))
    else:
        start, end = args.start, len(lines) if args.end is None else args.end
    if start < 1 or end < start or end > len(lines):
        fail("invalid line range")
    require_root_guidance(record, key, start, end, len(lines))
    selected = "".join(lines[start - 1 : end])
    event = {
        "kind": "read",
        "ranges": [{"path": key, "start": start, "end": end}],
        "content_bytes": len(selected.encode("utf-8")),
        "output_bytes": 0,
    }
    record["events"].append(event)
    event["unique_bytes_read"] = unique_byte_count([{**event, "root": str(root)}])
    reply = {
        "path": key,
        "start": start,
        "end": end,
        "content": selected,
        "content_bytes": event["content_bytes"],
        "unique_bytes_read": event["unique_bytes_read"],
    }
    printed = json.dumps(reply, ensure_ascii=False)
    event["output_bytes"] = len(printed.encode("utf-8"))
    write_record(args.record, record)
    print(printed)


@serialized_record_update
def list_headings(args):
    record = load_record(args.record)
    root = Path(record["candidate_root"]).resolve(strict=True)
    manifest, by_path = load_manifest(
        Path(args.manifest).resolve(strict=True), root, verify_tree=True
    )
    if manifest["manifest_sha256"] != record["manifest_sha256"]:
        fail("session candidate differs from its frozen manifest")
    require_root_guidance(record)
    key, raw = permitted_path(root, args.path, by_path)
    if not key.casefold().endswith(".md"):
        fail("heading listing requires a Markdown file")
    headings = markdown_headings(raw)
    ranges = [
        {"path": key, "start": item["line"], "end": item["end_line"]}
        for item in headings
    ]
    lines = raw.decode("utf-8").splitlines(keepends=True)
    content_bytes = sum(
        sum(
            len(line.encode("utf-8"))
            for line in lines[item["line"] - 1 : item["end_line"]]
        )
        for item in headings
    )
    event = {
        "kind": "headings",
        "ranges": ranges,
        "content_bytes": content_bytes,
        "output_bytes": 0,
    }
    record["events"].append(event)
    event["unique_bytes_read"] = unique_byte_count([{**event, "root": str(root)}])
    printed = json.dumps(
        {
            "path": key,
            "headings": headings,
            "content_bytes": content_bytes,
            "unique_bytes_read": event["unique_bytes_read"],
        },
        ensure_ascii=False,
    )
    event["output_bytes"] = len(printed.encode("utf-8"))
    write_record(args.record, record)
    print(printed)


@serialized_record_update
def search_content(args):
    if not args.query:
        fail("search query must not be empty")
    record = load_record(args.record)
    root = Path(record["candidate_root"]).resolve(strict=True)
    manifest, by_path = load_manifest(
        Path(args.manifest).resolve(strict=True), root, verify_tree=True
    )
    if manifest["manifest_sha256"] != record["manifest_sha256"]:
        fail("session candidate differs from its frozen manifest")
    require_root_guidance(record)
    matches = []
    ranges = []
    content_bytes = 0
    for name in sorted(by_path):
        if (
            forbidden_path(name)
            or not by_path[name]["readable_text"]
            or not fnmatch.fnmatchcase(name, args.glob)
        ):
            continue
        key, raw = permitted_path(root, name, by_path)
        for number, line in enumerate(raw.decode("utf-8").splitlines(keepends=True), 1):
            if args.query in line:
                matches.append(
                    {"path": key, "line": number, "content": line.rstrip("\r\n")}
                )
                ranges.append({"path": key, "start": number, "end": number})
                content_bytes += len(line.encode("utf-8"))
                if len(matches) > MAX_SEARCH_MATCHES:
                    fail(
                        f"search has more than {MAX_SEARCH_MATCHES} matches; narrow --glob"
                    )
    event = {
        "kind": "search",
        "query": args.query,
        "glob": args.glob,
        "ranges": ranges,
        "content_bytes": content_bytes,
        "output_bytes": 0,
    }
    record["events"].append(event)
    event["unique_bytes_read"] = unique_byte_count([{**event, "root": str(root)}])
    reply = {
        "matches": matches,
        "content_bytes": content_bytes,
        "unique_bytes_read": event["unique_bytes_read"],
    }
    printed = json.dumps(reply, ensure_ascii=False)
    event["output_bytes"] = len(printed.encode("utf-8"))
    write_record(args.record, record)
    print(printed)


@serialized_record_update
def submit(args):
    record = load_record(args.record)
    if not record["events"] or record["events"][0]["ranges"][0]["path"] != "AGENTS.md":
        fail("session must first read the complete AGENTS.md at the candidate root")
    try:
        answer = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        fail(f"answer is not valid JSON: {exc}")
    if (
        not isinstance(answer, dict)
        or set(answer) != set(ANSWER_FIELDS)
        or any(
            not isinstance(answer[key], str) or not answer[key].strip()
            for key in ANSWER_FIELDS
        )
    ):
        fail("answer must contain exactly six non-empty string fields")
    root = Path(record["candidate_root"])
    record["submitted_monotonic"] = time.monotonic()
    record["elapsed_seconds"] = round(
        record["submitted_monotonic"] - record["started_monotonic"], 3
    )
    record["status"] = (
        "submitted" if record["elapsed_seconds"] <= MAX_SESSION_SECONDS else "timeout"
    )
    record["answer"] = answer
    record["submission"] = {
        "status": record["status"],
        "elapsed_seconds": record["elapsed_seconds"],
        "monotonic": record["submitted_monotonic"],
    }
    record["content_bytes_read"] = sum(
        event["content_bytes"] for event in record["events"]
    )
    record["unique_bytes_read"] = unique_byte_count(
        [{**event, "root": str(root)} for event in record["events"]]
    )
    write_record(args.record, record)
    print(
        json.dumps(
            {
                "status": record["status"],
                "run_id": record["run_id"],
                "elapsed_seconds": record["elapsed_seconds"],
            }
        )
    )


@serialized_record_update
def close_failed_attempt(args):
    record = json.loads(args.record.read_text(encoding="utf-8"))
    if record.get("status") != "started":
        fail("only an open session can be marked failed, interrupted, or timed out")
    if not args.reason.strip():
        fail("a failure or interruption requires a reason")
    record["status"] = args.command
    record["failure_reason"] = args.reason.strip()
    record["failure_class"] = (
        "task_timeout" if args.command == "timeout" else args.failure_class
    )
    record["closed_monotonic"] = time.monotonic()
    write_record(args.record, record)
    print(json.dumps({"status": record["status"], "run_id": record["run_id"]}))


@serialized_record_update
def mark_session(args):
    record = json.loads(args.record.read_text(encoding="utf-8"))
    if record.get("status") != "started":
        fail("only an open session can record external help or contamination")
    if not args.details.strip():
        fail("audit detail is required")
    target = "external_help" if args.event == "external-help" else "contamination"
    record[target].append(
        {"details": args.details.strip(), "monotonic": time.monotonic()}
    )
    write_record(args.record, record)
    print(
        json.dumps({"run_id": record["run_id"], "event": args.event, "recorded": True})
    )


def mcp_tool_schemas():
    """Return the exact bounded MCP schemas used by the server and runner audit."""
    return [
        {
            "name": "read_candidate",
            "description": "Read a candidate-relative UTF-8 line range or one complete Markdown heading path. The first successful content call must read all of AGENTS.md at the candidate root.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start": {"type": "integer", "minimum": 1},
                    "end": {"type": "integer", "minimum": 1},
                    "heading_path": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_candidate_headings",
            "description": "List Markdown headings with their complete title hierarchy. Returned heading lines count as read content.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            },
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        {
            "name": "search_candidate",
            "description": "Search readable UTF-8 candidate files. Returned matching lines count as read content.",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "glob": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "submit_answer",
            "description": "Persist exactly six non-empty strings: entry, constraints, authorities, relevant_decisions, validation, unknowns. This checks structure only and does not score correctness.",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": False,
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "object",
                        "properties": {
                            key: {"type": "string", "minLength": 1}
                            for key in ANSWER_FIELDS
                        },
                        "required": list(ANSWER_FIELDS),
                        "additionalProperties": False,
                    }
                },
                "required": ["answer"],
                "additionalProperties": False,
            },
        },
        {
            "name": "report_session_event",
            "description": "Record external help or contamination for this session with a concise factual description.",
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": False,
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "event": {
                        "type": "string",
                        "enum": ["external-help", "contamination"],
                    },
                    "details": {"type": "string", "minLength": 1},
                },
                "required": ["event", "details"],
                "additionalProperties": False,
            },
        },
    ]


def mcp_server(args):
    """Expose only candidate read/search/submit and audit tools over MCP stdio."""
    tools = mcp_tool_schemas()

    def emit(value):
        sys.stdout.write(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        sys.stdout.flush()

    def log_tool_error(name, message):
        try:
            with record_lock(args.record):
                record = json.loads(args.record.read_text(encoding="utf-8"))
                record.setdefault("tool_errors", []).append(
                    {"tool": name, "message": message, "monotonic": time.monotonic()}
                )
                write_record(args.record, record)
        except (OSError, ValueError):
            pass

    for line in sys.stdin:
        request = {}
        try:
            request = json.loads(line)
            method = request.get("method")
            request_id = request.get("id")
            if method == "notifications/initialized":
                continue
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "disclosure-reading-collector",
                        "version": "1",
                    },
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": tools}
            elif method == "tools/call":
                params = request.get("params", {})
                name, values = params.get("name"), params.get("arguments", {})
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    if name == "read_candidate":
                        read_content(
                            argparse.Namespace(
                                manifest=args.manifest,
                                record=args.record,
                                path=values.get("path", ""),
                                start=values.get("start", 1),
                                end=values.get("end"),
                                heading_path=values.get("heading_path"),
                            )
                        )
                        payload = json.loads(output.getvalue())
                    elif name == "list_candidate_headings":
                        list_headings(
                            argparse.Namespace(
                                manifest=args.manifest,
                                record=args.record,
                                path=values.get("path", ""),
                            )
                        )
                        payload = json.loads(output.getvalue())
                    elif name == "search_candidate":
                        search_content(
                            argparse.Namespace(
                                manifest=args.manifest,
                                record=args.record,
                                query=values.get("query", ""),
                                glob=values.get("glob", "*.md"),
                            )
                        )
                        payload = json.loads(output.getvalue())
                    elif name == "submit_answer":
                        previous_stdin = sys.stdin
                        try:
                            sys.stdin = io.StringIO(json.dumps(values.get("answer")))
                            submit(argparse.Namespace(record=args.record))
                        finally:
                            sys.stdin = previous_stdin
                        payload = json.loads(output.getvalue())
                    elif name == "report_session_event":
                        mark_session(
                            argparse.Namespace(
                                record=args.record,
                                event=values.get("event"),
                                details=values.get("details", ""),
                            )
                        )
                        payload = json.loads(output.getvalue())
                    else:
                        raise UsageError("unknown collector tool")
                content = json.dumps(payload, ensure_ascii=False)
                try:
                    with record_lock(args.record):
                        record = json.loads(args.record.read_text(encoding="utf-8"))
                        if name in {
                            "read_candidate",
                            "list_candidate_headings",
                            "search_candidate",
                        } and record.get("events"):
                            record["events"][-1]["tool_output_bytes"] = len(
                                content.encode("utf-8")
                            )
                            write_record(args.record, record)
                except (OSError, ValueError):
                    pass
                result = {
                    "content": [{"type": "text", "text": content}],
                    "isError": False,
                }
            else:
                if request_id is None:
                    continue
                emit(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": "method not found"},
                    }
                )
                continue
            if request_id is not None:
                emit({"jsonrpc": "2.0", "id": request_id, "result": result})
        except (
            UsageError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            log_tool_error(request.get("params", {}).get("name", "unknown"), str(exc))
            emit(
                {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "content": [{"type": "text", "text": f"ERROR: {exc}"}],
                        "isError": True,
                    },
                }
            )


def parser():
    ap = argparse.ArgumentParser(
        description="Candidate-pinned read/search/submit collector for disclosure sessions.",
        epilog=(
            "Protocol: first call read for the complete AGENTS.md at the candidate root; then use read/search. "
            "All returned text is counted as UTF-8 content bytes. Submit exactly six non-empty strings: "
            "entry, constraints, authorities, relevant_decisions, validation, unknowns. "
            "Timing starts at the first successful content read and stops at submit. "
            "This collector validates structure only; it does not score answers."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = ap.add_subparsers(dest="command", required=True)
    item = commands.add_parser("manifest", help="freeze candidate file hashes")
    item.add_argument("--root", type=Path, required=True)
    item.add_argument("--out", type=Path, required=True)
    item = commands.add_parser("start", help="open one fresh candidate/task session")
    item.add_argument("--root", type=Path, required=True)
    item.add_argument("--manifest", type=Path, required=True)
    item.add_argument("--record", type=Path, required=True)
    item.add_argument("--run-id", required=True)
    item.add_argument("--candidate", choices=("baseline", "after"), required=True)
    item.add_argument("--task", choices=TASKS, required=True)
    item.add_argument("--task-hash", required=True)
    item.add_argument(
        "--model-config", required=True, help="actual model and reasoning setting"
    )
    item.add_argument("--tool-config-sha256", required=True)
    item.add_argument("--startup-timeout-seconds", type=float, default=60)
    item.add_argument(
        "--retry-of",
        type=Path,
        help="failed/interrupted attempt record; only one retry is allowed",
    )
    item.add_argument(
        "--retry-reason",
        default="",
        help="infrastructure/protocol failure that caused the retry",
    )
    item = commands.add_parser(
        "read", help="read a candidate-relative line range or Markdown heading"
    )
    item.add_argument("--manifest", type=Path, required=True)
    item.add_argument("--record", type=Path, required=True)
    item.add_argument("--path", required=True)
    item.add_argument("--start", type=int, default=1)
    item.add_argument("--end", type=int)
    item.add_argument(
        "--heading-path",
        help='JSON array of complete Markdown heading titles, e.g. ["Parent", "Child"]',
    )
    item = commands.add_parser(
        "headings", help="list complete Markdown heading hierarchies"
    )
    item.add_argument("--manifest", type=Path, required=True)
    item.add_argument("--record", type=Path, required=True)
    item.add_argument("--path", required=True)
    item = commands.add_parser("search", help="search readable candidate text")
    item.add_argument("--manifest", type=Path, required=True)
    item.add_argument("--record", type=Path, required=True)
    item.add_argument("--query", required=True)
    item.add_argument("--glob", default="*.md")
    item = commands.add_parser(
        "submit", help="persist a structurally valid six-field answer"
    )
    item.add_argument("--record", type=Path, required=True)
    for name in ("failed", "interrupted"):
        item = commands.add_parser(
            name, help=f"retain an original {name} attempt with its reason"
        )
        item.add_argument("--record", type=Path, required=True)
        item.add_argument("--reason", required=True)
        item.add_argument(
            "--failure-class",
            choices=(
                "infrastructure",
                "quota_exhausted",
                "workspace_load",
                "protocol",
                "task",
            ),
            required=True,
        )
    item = commands.add_parser(
        "timeout", help="retain a task timeout without allowing redraw"
    )
    item.add_argument("--record", type=Path, required=True)
    item.add_argument("--reason", required=True)
    item = commands.add_parser(
        "mark", help="audit external help or session contamination"
    )
    item.add_argument("--record", type=Path, required=True)
    item.add_argument(
        "--event", choices=("external-help", "contamination"), required=True
    )
    item.add_argument("--details", required=True)
    item = commands.add_parser("mcp", help="serve only reader tools over MCP stdio")
    item.add_argument("--manifest", type=Path, required=True)
    item.add_argument("--record", type=Path, required=True)
    commands.add_parser("self-test", help="check fixed collector invariants")
    return ap


def self_test():
    assert ANSWER_FIELDS == (
        "entry",
        "constraints",
        "authorities",
        "relevant_decisions",
        "validation",
        "unknowns",
    )
    assert len("café".encode("utf-8")) == 5
    print("PASS: six-field structural schema and UTF-8 accounting")


def main():
    args = parser().parse_args()
    handlers = {
        "manifest": lambda: build_manifest(args.root, args.out),
        "start": lambda: start_session(args),
        "read": lambda: read_content(args),
        "headings": lambda: list_headings(args),
        "search": lambda: search_content(args),
        "submit": lambda: submit(args),
        "failed": lambda: close_failed_attempt(args),
        "interrupted": lambda: close_failed_attempt(args),
        "timeout": lambda: close_failed_attempt(args),
        "mark": lambda: mark_session(args),
        "mcp": lambda: mcp_server(args),
        "self-test": self_test,
    }
    try:
        handlers[args.command]()
    except (
        UsageError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
