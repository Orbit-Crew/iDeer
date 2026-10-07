#!/usr/bin/env python3
"""Validate human anchor judgments and derive the disclosure acceptance report."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

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
ROUTINE_TASKS = frozenset(("ui", "chat", "knowledge", "permissions", "tests"))
ANSWER_FIELDS = (
    "entry",
    "constraints",
    "authorities",
    "relevant_decisions",
    "validation",
    "unknowns",
)
FAILED_STATUSES = frozenset(("timeout", "interrupted", "failed"))
TASK_ANCHORS: dict[str, tuple[tuple[str, str, str | None, str | None], ...]] = {
    "ui": (
        ("UI-01", "required", None, "major"),
        ("UI-02", "required", None, "major"),
        ("UI-03", "required", None, "major"),
        ("UI-04", "required", None, "minor"),
        ("UI-05", "required", None, "major"),
    ),
    "chat": (
        ("CHAT-01", "required", None, "major"),
        ("CHAT-02", "required", None, "major"),
        ("CHAT-03", "required", None, "critical"),
        (
            "CHAT-04",
            "conditional",
            "the task touches Run/Thread lifecycle, persistence, or event streaming",
            "critical",
        ),
        ("CHAT-05", "required", None, "minor"),
        ("CHAT-06", "required", None, "major"),
    ),
    "knowledge": (
        ("KB-01", "required", None, "critical"),
        ("KB-02", "required", None, "critical"),
        ("KB-03", "required", None, "critical"),
        ("KB-04", "required", None, "major"),
        ("KB-05", "required", None, "minor"),
        ("KB-06", "required", None, "major"),
    ),
    "permissions": (
        ("PERM-01", "required", None, "critical"),
        ("PERM-02", "required", None, "critical"),
        (
            "PERM-03",
            "conditional",
            "the task changes local/device execution",
            "critical",
        ),
        (
            "PERM-04",
            "conditional",
            "the task changes resource authorization or visibility",
            "critical",
        ),
        ("PERM-05", "required", None, "minor"),
        ("PERM-06", "required", None, "major"),
    ),
    "tests": (
        ("TEST-01", "required", None, "major"),
        ("TEST-02", "conditional", "the task adds or moves tests", "major"),
        ("TEST-03", "required", None, "major"),
        ("TEST-04", "required", None, "major"),
        ("TEST-05", "required", None, "minor"),
        ("TEST-06", "required", None, "major"),
        ("TEST-07", "conditional", "the selected lane is a combined lane", "minor"),
        ("TEST-08", "conditional", "the selected lane is smoke", "minor"),
        (
            "TEST-09",
            "conditional",
            "the selected lane requires optional credentials that are unavailable",
            "minor",
        ),
    ),
    "runtime": (
        ("RUN-01", "required", None, "critical"),
        ("RUN-02", "required", None, "critical"),
        (
            "RUN-03",
            "conditional",
            "the task changes offline capability switches or enterprise permission limits",
            "critical",
        ),
        ("RUN-04", "required", None, "major"),
        ("RUN-05", "required", None, "major"),
        ("RUN-06", "required", None, "minor"),
        ("RUN-07", "required", None, "major"),
    ),
    "upstream": (
        ("UP-01", "required", None, "major"),
        ("UP-02", "required", None, "critical"),
        ("UP-03", "required", None, "major"),
        ("UP-04", "required", None, "major"),
        ("UP-05", "required", None, "critical"),
        ("UP-06", "required", None, "major"),
        ("UP-07", "required", None, "major"),
    ),
    "history": (
        ("HIST-01", "required", None, "critical"),
        ("HIST-02", "required", None, "critical"),
        ("HIST-03", "required", None, "major"),
        ("HIST-04", "required", None, "major"),
        ("HIST-05", "optional", None, "minor"),
        ("HIST-06", "required", None, "major"),
    ),
}


class InputError(ValueError):
    """The provided scoring record violates the frozen input contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def _finite_nonnegative(value: Any, field: str) -> float:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{field} must be a number",
    )
    number = float(value)
    _require(
        math.isfinite(number) and number >= 0,
        f"{field} must be finite and non-negative",
    )
    return number


def _read_grade(
    grade: Any, task: str, known_reviewers: set[str], *, adjudicator: bool = False
) -> dict[str, Any]:
    _require(isinstance(grade, dict), "each review must be an object")
    reviewer = grade.get("reviewer")
    _require(isinstance(reviewer, str) and reviewer.strip(), "reviewer must be named")
    _require(
        reviewer not in known_reviewers, "reviewers must be independent and distinct"
    )
    known_reviewers.add(reviewer)
    anchor_rows = grade.get("anchors")
    _require(isinstance(anchor_rows, list), "review anchors must be a list")
    expected = {row[0]: row for row in TASK_ANCHORS[task]}
    decisions: dict[str, dict[str, Any]] = {}
    for row in anchor_rows:
        _require(isinstance(row, dict), "each anchor judgment must be an object")
        anchor_id = row.get("id")
        _require(
            anchor_id in expected and anchor_id not in decisions,
            f"unknown or duplicate anchor for {task}: {anchor_id}",
        )
        _require(
            row.get("decision") in ("met", "missed", "not_applicable"),
            f"invalid decision for {anchor_id}",
        )
        evidence = row.get("evidence")
        _require(
            isinstance(evidence, dict)
            and all(
                isinstance(evidence.get(key), str) and evidence[key].strip()
                for key in ("answer", "candidate")
            ),
            f"answer and candidate evidence are required for {anchor_id}",
        )
        _, category, _trigger, _severity = expected[anchor_id]
        triggered = row.get("triggered")
        if category == "conditional":
            _require(
                isinstance(triggered, bool),
                f"conditional anchor {anchor_id} needs an explicit trigger decision",
            )
            _require(
                (triggered and row["decision"] != "not_applicable")
                or (not triggered and row["decision"] == "not_applicable"),
                f"{anchor_id} decision conflicts with its trigger",
            )
        else:
            _require(
                "triggered" not in row,
                f"non-conditional anchor {anchor_id} cannot have a trigger",
            )
            _require(
                row["decision"] != "not_applicable",
                f"non-conditional anchor {anchor_id} cannot be not_applicable",
            )
        decisions[anchor_id] = {
            "decision": row["decision"],
            "triggered": triggered,
            "evidence": row["evidence"],
        }
    _require(
        set(decisions) == set(expected),
        f"review for {task} must judge every numbered anchor",
    )
    misuse = grade.get("historical_authority_misuse", False)
    _require(isinstance(misuse, bool), "historical_authority_misuse must be a boolean")
    misuse_evidence = grade.get("historical_misuse_evidence")
    if misuse:
        _require(
            isinstance(misuse_evidence, dict)
            and all(
                isinstance(misuse_evidence.get(key), str)
                and misuse_evidence[key].strip()
                for key in ("answer", "candidate")
            ),
            "historical misuse requires answer and candidate evidence",
        )
    else:
        _require(
            misuse_evidence is None,
            "historical misuse evidence requires a positive misuse judgment",
        )
    if adjudicator:
        _require(
            isinstance(grade.get("rationale"), str) and grade["rationale"].strip(),
            "adjudication requires a rationale",
        )
    return {
        "anchors": decisions,
        "historical_authority_misuse": misuse,
        "historical_misuse_evidence": misuse_evidence,
    }


def _review_disagrees(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["historical_authority_misuse"] != right[
        "historical_authority_misuse"
    ] or any(
        (left["anchors"][key]["decision"], left["anchors"][key]["triggered"])
        != (right["anchors"][key]["decision"], right["anchors"][key]["triggered"])
        for key in left["anchors"]
    )


def _validate_grade_quotes(grade: dict[str, Any], answer: dict[str, str]) -> None:
    answer_text = tuple(answer.values())
    for anchor in grade["anchors"].values():
        excerpt = anchor["evidence"]["answer"]
        _require(
            any(excerpt in field for field in answer_text),
            "answer evidence excerpt not found in the submitted answer",
        )
    misuse_evidence = grade["historical_misuse_evidence"]
    if misuse_evidence is not None:
        _require(
            any(misuse_evidence["answer"] in field for field in answer_text),
            "historical misuse answer evidence excerpt not found in the submitted answer",
        )


def _derive_record(record: Any) -> dict[str, Any]:
    _require(isinstance(record, dict), "each session record must be an object")
    task, candidate = record.get("task"), record.get("candidate")
    _require(
        task in TASK_ANCHORS and candidate in ("baseline", "after"),
        "unknown task or candidate",
    )
    _require(
        record.get("status") in {"submitted", *FAILED_STATUSES},
        "status must be submitted, timeout, interrupted, or failed",
    )
    answer = record.get("answer")
    if record["status"] == "submitted":
        _require(
            isinstance(answer, dict) and set(answer) == set(ANSWER_FIELDS),
            "submitted answer needs exactly six answer fields",
        )
        _require(
            all(
                isinstance(answer[field], str) and answer[field].strip()
                for field in ANSWER_FIELDS
            ),
            "all six answer fields must be non-empty strings",
        )
    elapsed = _finite_nonnegative(record.get("elapsed_seconds"), "elapsed_seconds")
    byte_count = _finite_nonnegative(
        record.get("unique_bytes_read"), "unique_bytes_read"
    )
    reviews = record.get("reviews")
    _require(
        isinstance(reviews, list)
        and (
            len(reviews) == 2
            or record["status"] in FAILED_STATUSES
            and len(reviews) == 0
        ),
        "each submitted answer needs two independent reviews; a failed sample may have none",
    )
    reviewers: set[str] = set()
    parsed = [_read_grade(review, task, reviewers) for review in reviews]
    if answer is not None:
        for grade in parsed:
            _validate_grade_quotes(grade, answer)
    disagrees = len(parsed) == 2 and _review_disagrees(parsed[0], parsed[1])
    adjudication = record.get("adjudication")
    _require(
        adjudication is None or disagrees,
        "adjudication is not allowed when the independent anchor reviews have no anchor disagreement",
    )
    if disagrees and adjudication is None:
        final = None
        unresolved = True
    elif adjudication is not None:
        final = _read_grade(adjudication, task, reviewers, adjudicator=True)
        if answer is not None:
            _validate_grade_quotes(final, answer)
        unresolved = False
    elif parsed:
        final = parsed[0]
        unresolved = False
    else:
        final = None
        unresolved = False

    critical_errors = historical_misuse = missed = 0
    correct = False
    if final is not None:
        correct = True
        for anchor_id, (anchor, category, _trigger, severity) in (
            (row[0], row) for row in TASK_ANCHORS[task]
        ):
            decision = final["anchors"][anchor_id]["decision"]
            triggered = final["anchors"][anchor_id]["triggered"]
            if decision == "missed":
                missed += 1
                critical_errors += severity == "critical"
                if category == "required" or category == "conditional" and triggered:
                    correct = False
        historical_misuse = int(final["historical_authority_misuse"])
    if record["status"] in FAILED_STATUSES:
        correct = False
    return {
        "run_id": record.get("run_id"),
        "candidate": candidate,
        "task": task,
        "status": record["status"],
        "elapsed_seconds": elapsed,
        "unique_bytes_read": byte_count,
        "correct": correct,
        "critical_errors": critical_errors,
        "historical_authority_misuse": historical_misuse,
        "missed_anchors": missed,
        "unresolved_disagreement": unresolved,
        "review_count": len(reviews),
        "answer": answer,
        "reviews": reviews,
        "adjudication": adjudication,
    }


def build_report(payload: Any) -> dict[str, Any]:
    _require(
        isinstance(payload, dict) and isinstance(payload.get("records"), list),
        "input must contain a records list",
    )
    derived = [_derive_record(record) for record in payload["records"]]
    required_pairs = {
        (task, candidate) for task in TASKS for candidate in ("baseline", "after")
    }
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    seen: set[str] = set()
    for row in derived:
        run_id = row["run_id"]
        _require(
            isinstance(run_id, str) and run_id.strip() and run_id not in seen,
            "run_id must be unique and non-empty",
        )
        seen.add(run_id)
        grouped.setdefault((row["task"], row["candidate"]), []).append(row)
    _require(
        set(grouped) == required_pairs
        and all(len(rows) == 2 for rows in grouped.values()),
        "expected exactly two baseline and two after records for all eight tasks (16 after denominator)",
    )

    after = [row for row in derived if row["candidate"] == "after"]
    routine_before = [
        row
        for row in derived
        if row["candidate"] == "baseline" and row["task"] in ROUTINE_TASKS
    ]
    routine_after = [row for row in after if row["task"] in ROUTINE_TASKS]
    before_bytes = statistics.median(row["unique_bytes_read"] for row in routine_before)
    after_bytes = statistics.median(row["unique_bytes_read"] for row in routine_after)
    reduction = (before_bytes - after_bytes) / before_bytes if before_bytes else -1.0
    routine_seconds = statistics.median(row["elapsed_seconds"] for row in routine_after)
    unresolved = sum(row["unresolved_disagreement"] for row in derived)
    incorrect_after = sum(not row["correct"] for row in after)
    critical_after = sum(row["critical_errors"] for row in after)
    historical_after = sum(row["historical_authority_misuse"] for row in after)
    per_task = {}
    for task in TASKS:
        baseline_rows, after_rows = (
            grouped[(task, "baseline")],
            grouped[(task, "after")],
        )
        baseline_median = statistics.median(
            row["unique_bytes_read"] for row in baseline_rows
        )
        after_median = statistics.median(row["unique_bytes_read"] for row in after_rows)
        per_task[task] = {
            "baseline_median_unique_bytes": baseline_median,
            "after_median_unique_bytes": after_median,
            "after_median_seconds": statistics.median(
                row["elapsed_seconds"] for row in after_rows
            ),
            "incorrect_after": sum(not row["correct"] for row in after_rows),
            "critical_errors_after": sum(row["critical_errors"] for row in after_rows),
            "historical_authority_misuse_after": sum(
                row["historical_authority_misuse"] for row in after_rows
            ),
        }
    return {
        "accepted": incorrect_after == 0
        and critical_after == 0
        and historical_after == 0
        and unresolved == 0
        and routine_seconds <= 300
        and reduction >= 0.30,
        "after_denominator": 16,
        "after_correct": 16 - incorrect_after,
        "incorrect_after": incorrect_after,
        "critical_errors_after": critical_after,
        "historical_authority_misuse_after": historical_after,
        "unresolved_disagreements": unresolved,
        "routine_median_seconds_after": routine_seconds,
        "routine_median_unique_bytes_baseline": before_bytes,
        "routine_median_unique_bytes_after": after_bytes,
        "routine_unique_byte_reduction": reduction,
        "per_task": per_task,
        "records": derived,
    }


def build_single_record_report(payload: Any) -> dict[str, Any]:
    _require(
        isinstance(payload, dict)
        and isinstance(payload.get("records"), list)
        and len(payload["records"]) == 1,
        "single-record mode requires exactly one record",
    )
    record = payload["records"][0]
    derived = _derive_record(record)
    derived["raw_grader_summary"] = record.get("raw_grader_summary")
    return {
        "mode": "single_record_calibration",
        "formal_acceptance": None,
        "record": derived,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--single-record",
        action="store_true",
        help="write one explicitly non-formal calibration audit, not a threshold result",
    )
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.records.read_text(encoding="utf-8"))
        report = (
            build_single_record_report(payload)
            if args.single_record
            else build_report(payload)
        )
        if "summary" in payload and payload["summary"] != {
            key: value for key, value in report.items() if key != "records"
        }:
            raise InputError("provided summary disagrees with item-level records")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        if args.single_record:
            print(
                json.dumps(
                    {
                        "mode": report["mode"],
                        "correct": report["record"]["correct"],
                        "formal_acceptance": None,
                    }
                )
            )
        else:
            print(
                json.dumps(
                    {
                        "accepted": report["accepted"],
                        "after_correct": report["after_correct"],
                        "after_denominator": 16,
                    }
                )
            )
        return 0
    except (
        InputError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        KeyError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
