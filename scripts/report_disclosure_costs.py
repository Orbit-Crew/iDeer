#!/usr/bin/env python3
"""Recompute layered disclosure costs from immutable physical attempt records."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from disclosure_reading_collector import (
    canonical_json,
    candidate_files,
    digest,
    forbidden_path,
    markdown_headings,
    permitted_path,
    section_range,
    UsageError,
)

CATEGORIES = (
    "root_guidance",
    "descendant_guidance",
    "route",
    "current_documentation",
    "historical_material",
    "source_test_config",
    "other",
)


class InputError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def finite_nonnegative(value: Any, field: str) -> float:
    require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{field} must be a number",
    )
    try:
        number = float(value)
    except OverflowError as exc:
        raise InputError(f"{field} must be finite and non-negative") from exc
    require(
        math.isfinite(number) and number >= 0,
        f"{field} must be finite and non-negative",
    )
    return number


def _role_for_line(
    path: str,
    line: int,
    path_roles: dict[str, str],
    section_ranges: list[dict[str, Any]],
) -> str:
    matches = [
        section
        for section in section_ranges
        if section["path"] == path and section["start"] <= line <= section["end"]
    ]
    if matches:
        most_specific_depth = max(len(section["heading_path"]) for section in matches)
        matches = [
            section
            for section in matches
            if len(section["heading_path"]) == most_specific_depth
        ]
        roles = {section["role"] for section in matches}
        require(
            len(roles) == 1, f"overlapping section roles conflict for {path}:{line}"
        )
        return next(iter(roles))
    return path_roles.get(path, "other")


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    categories = {
        name: sum(row["categories"][name] for row in rows) for name in CATEGORIES
    }
    return {
        "count": len(rows),
        "content_bytes_returned": sum(row["content_bytes_returned"] for row in rows),
        "unique_bytes_read": sum(row["unique_bytes_read"] for row in rows),
        "repeated_return_bytes": sum(row["repeated_return_bytes"] for row in rows),
        "submission_elapsed_seconds": sum(
            row["submission_elapsed_seconds"] or 0 for row in rows
        ),
        "submission_elapsed_missing": sum(
            row["submission_elapsed_seconds"] is None for row in rows
        ),
        "failure_close_seconds": sum(row["failure_close_seconds"] or 0 for row in rows),
        "failure_close_missing": sum(
            row["failure_close_seconds"] is None
            for row in rows
            if row["status"] in {"failed", "interrupted", "timeout"}
        ),
        "categories": categories,
    }


def build_report(payload: Any) -> dict[str, Any]:
    require(isinstance(payload, dict), "input must be an object")
    role_map, attempts = payload.get("role_map"), payload.get("attempts")
    require(
        isinstance(role_map, dict) and role_map.get("format") == 1,
        "role_map format 1 is required",
    )
    require(
        isinstance(attempts, list) and attempts, "attempts must be a non-empty list"
    )
    expected_candidates = role_map.get("candidates")
    path_roles = role_map.get("paths")
    sections = role_map.get("sections")
    require(
        isinstance(expected_candidates, dict)
        and isinstance(path_roles, dict)
        and isinstance(sections, list),
        "role_map needs candidates, paths, and sections",
    )
    for role in path_roles.values():
        require(role in CATEGORIES, f"unknown path role: {role}")

    parsed_sections = []
    for section in sections:
        require(isinstance(section, dict), "each section role must be an object")
        path, heading_path, role = (
            section.get("path"),
            section.get("heading_path"),
            section.get("role"),
        )
        require(
            isinstance(path, str)
            and path.casefold().endswith(".md")
            and isinstance(heading_path, list),
            "section role needs a Markdown path and heading_path",
        )
        require(role in CATEGORIES, f"unknown section role: {role}")
        for previous in parsed_sections:
            require(
                not (
                    previous["path"] == path
                    and previous["heading_path"] == heading_path
                ),
                "duplicate section role mapping",
            )
        parsed_sections.append(
            {"path": path, "heading_path": heading_path, "role": role}
        )

    ids: dict[str, dict[str, Any]] = {}
    for record in attempts:
        require(isinstance(record, dict), "each attempt must be an object")
        run_id = record.get("run_id")
        require(
            isinstance(run_id, str) and run_id.strip() and run_id not in ids,
            "run_id must be unique and non-empty",
        )
        ids[run_id] = record

    derived = []
    for record in attempts:
        run_id, candidate = record["run_id"], record.get("candidate")
        expected_sha = expected_candidates.get(candidate)
        require(
            isinstance(expected_sha, str) and len(expected_sha) == 64,
            f"role map has no frozen manifest digest for {candidate}",
        )
        require(
            record.get("manifest_sha256") == expected_sha,
            f"candidate manifest digest drift for {run_id}",
        )
        status = record.get("status")
        require(
            status in {"started", "submitted", "timeout", "interrupted", "failed"},
            f"invalid attempt status for {run_id}",
        )
        root = Path(record.get("candidate_root", ""))
        require(root.is_dir(), f"candidate root is unavailable for {run_id}")
        rows = candidate_files(root.resolve(strict=True))
        by_path = {row["path"]: row for row in rows}
        excluded = [
            {"path": row["path"], "sha256": row["sha256"], "reason": row["exclusion"]}
            for row in rows
            if row["exclusion"]
        ]
        manifest_body = {
            "format": 2,
            "root_name": root.name,
            "files": rows,
            "exclusions": excluded,
        }
        manifest_body["exclusion_sha256"] = digest(canonical_json(excluded))
        require(
            digest(canonical_json(manifest_body)) == expected_sha,
            f"candidate snapshot drift for {run_id}",
        )
        events = record.get("events", [])
        require(isinstance(events, list), f"events must be a list for {run_id}")

        resolved_sections = []
        for spec in parsed_sections:
            try:
                section_key, source_bytes = permitted_path(root, spec["path"], by_path)
            except (UsageError, OSError) as exc:
                raise InputError(f"invalid section source: {spec['path']}") from exc
            lines = source_bytes.decode("utf-8").splitlines(keepends=True)
            try:
                start, end = section_range(
                    markdown_headings(source_bytes),
                    spec["heading_path"],
                    len(lines),
                )
            except UsageError as exc:
                raise InputError(f"invalid section role: {exc}") from exc
            resolved_sections.append(
                {**spec, "path": section_key, "start": start, "end": end}
            )

        seen_lines: dict[str, set[int]] = {}
        categories = {name: 0 for name in CATEGORIES}
        returned = 0
        for event in events:
            require(
                isinstance(event, dict) and isinstance(event.get("ranges"), list),
                f"invalid event ranges for {run_id}",
            )
            event_bytes = 0
            for selected in event["ranges"]:
                require(isinstance(selected, dict), f"invalid event range for {run_id}")
                path, start, end = (
                    selected.get("path"),
                    selected.get("start"),
                    selected.get("end"),
                )
                require(
                    isinstance(path, str)
                    and isinstance(start, int)
                    and not isinstance(start, bool)
                    and isinstance(end, int)
                    and not isinstance(end, bool)
                    and 1 <= start <= end,
                    f"invalid event range for {run_id}",
                )
                rel = PurePosixPath(path)
                require(
                    not rel.is_absolute()
                    and not any(part in ("", ".", "..") for part in rel.parts)
                    and not forbidden_path(path),
                    f"forbidden event path: {path}",
                )
                source = root.joinpath(*rel.parts)
                require(
                    source.resolve(strict=True).is_relative_to(
                        root.resolve(strict=True)
                    ),
                    f"event path escapes candidate: {path}",
                )
                require(source.is_file(), f"event source is missing: {path}")
                lines = source.read_bytes().decode("utf-8").splitlines(keepends=True)
                require(
                    end <= len(lines), f"event range exceeds candidate file: {path}"
                )
                seen = seen_lines.setdefault(path, set())
                for number in range(start, end + 1):
                    size = len(lines[number - 1].encode("utf-8"))
                    event_bytes += size
                    if number not in seen:
                        categories[
                            _role_for_line(path, number, path_roles, resolved_sections)
                        ] += size
                        seen.add(number)
            declared = finite_nonnegative(
                event.get("content_bytes"), "event.content_bytes"
            )
            require(
                declared == event_bytes, f"event content byte count drift for {run_id}"
            )
            returned += event_bytes
        unique = sum(categories.values())
        require(
            unique <= returned, f"unique read bytes exceed returned bytes for {run_id}"
        )
        submitted = record.get("submitted_monotonic") is not None
        elapsed = (
            finite_nonnegative(record.get("elapsed_seconds"), "elapsed_seconds")
            if submitted
            else None
        )
        close_elapsed = None
        if status in {"failed", "interrupted", "timeout"}:
            started, closed = (
                record.get("started_monotonic"),
                record.get("closed_monotonic"),
            )
            if started is not None and closed is not None:
                close_elapsed = round(
                    finite_nonnegative(closed - started, "failure_close_seconds"), 3
                )
        derived.append(
            {
                "run_id": run_id,
                "logical_id": record.get("retry_of") or run_id,
                "retry_of": record.get("retry_of"),
                "candidate": candidate,
                "task": record.get("task"),
                "status": status,
                "submission_elapsed_seconds": elapsed,
                "failure_close_seconds": close_elapsed,
                "content_bytes_returned": returned,
                "unique_bytes_read": unique,
                "repeated_return_bytes": returned - unique,
                "categories": categories,
            }
        )

    retry_children: dict[str, list[str]] = {}
    for parent_id, original in ids.items():
        linked_child = original.get("retry_run_id")
        if linked_child is not None:
            require(
                isinstance(linked_child, str)
                and linked_child in ids
                and ids[linked_child].get("retry_of") == parent_id,
                f"retry child is missing or has mismatched parent for {parent_id}",
            )
    for row in derived:
        parent = row["retry_of"]
        if parent is not None:
            require(parent in ids, f"retry parent not found for {row['run_id']}")
            original = ids[parent]
            current = ids[row["run_id"]]
            retry_children.setdefault(parent, []).append(row["run_id"])
            require(
                original.get("status") in {"failed", "interrupted"}
                and original.get("failure_class")
                in {"infrastructure", "workspace_load", "protocol"},
                f"retry parent is not eligible for {row['run_id']}",
            )
            require(
                original.get("retry_run_id") == row["run_id"]
                and isinstance(current.get("retry_reason"), str)
                and current["retry_reason"].strip(),
                f"retry linkage evidence is incomplete for {row['run_id']}",
            )
            identity_fields = (
                "candidate",
                "task",
                "task_sha256",
                "manifest_sha256",
                "model_config",
                "tool_config_sha256",
            )
            require(
                all(
                    isinstance(original.get(field), str)
                    and original[field].strip()
                    and original.get(field) == current.get(field)
                    for field in identity_fields
                ),
                f"retry identity mismatch for {row['run_id']}",
            )
            require(
                isinstance(original.get("attempt_no"), int)
                and not isinstance(original.get("attempt_no"), bool)
                and original["attempt_no"] == 1
                and isinstance(current.get("attempt_no"), int)
                and not isinstance(current.get("attempt_no"), bool)
                and current["attempt_no"] == 2,
                f"retry attempt count is invalid for {row['run_id']}",
            )
    require(
        all(len(children) == 1 for children in retry_children.values()),
        "each attempt may have only one linked retry",
    )

    root_by_attempt: dict[str, str] = {}
    for row in derived:
        cursor = row["run_id"]
        chain: set[str] = set()
        while ids[cursor].get("retry_of") is not None:
            require(cursor not in chain, "retry links contain a cycle")
            chain.add(cursor)
            cursor = ids[cursor]["retry_of"]
            require(cursor in ids, f"retry parent not found: {cursor}")
        root_by_attempt[row["run_id"]] = cursor
    leaves = {root: [] for root in root_by_attempt.values()}
    for row in derived:
        leaves[root_by_attempt[row["run_id"]]].append(row)
    final_rows = []
    for logical_id, chain in leaves.items():
        parent_ids = {row["retry_of"] for row in chain if row["retry_of"]}
        terminal = [row for row in chain if row["run_id"] not in parent_ids]
        require(
            len(terminal) == 1,
            f"logical attempt {logical_id} must have exactly one final attempt",
        )
        final_rows.extend(terminal)
    return {
        "format": 1,
        "attempts": derived,
        "final_logical_attempts": _aggregate(final_rows),
        "all_physical_attempts": _aggregate(derived),
        "unknown_role_paths": sorted(
            {
                selected["path"]
                for row in attempts
                for event in row.get("events", [])
                for selected in event.get("ranges", [])
                if selected["path"] not in path_roles
                and not any(
                    section["path"] == selected["path"] for section in parsed_sections
                )
            }
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.records.read_text(encoding="utf-8"))
        report = build_report(payload)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "physical_attempts": report["all_physical_attempts"]["count"],
                    "logical_attempts": report["final_logical_attempts"]["count"],
                }
            )
        )
        return 0
    except (
        InputError,
        UsageError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        KeyError,
        ValueError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
