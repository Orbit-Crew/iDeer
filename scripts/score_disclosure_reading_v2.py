#!/usr/bin/env python3
"""Aggregate independent answer reviews under disclosure-reading-v2 rules."""

from __future__ import annotations

from collections import Counter
from typing import Any

DECISIONS = frozenset({"met", "missed", "not_applicable", "unresolved"})
CATEGORIES = frozenset({"required", "conditional", "auxiliary"})

# Canonical IDs are projections of the frozen v2 protocol's task rows, not new
# requirements. Grader-specific labels are normalized through the alias table.
V2_ANCHORS: dict[str, list[dict[str, str]]] = {
    "ui": [
        {"id": "UI-01", "category": "required"},
        {"id": "UI-02", "category": "required"},
        {"id": "UI-03", "category": "required"},
        {"id": "UI-C1", "category": "conditional"},
        {"id": "UI-C2", "category": "conditional"},
        {"id": "UI-AUX", "category": "auxiliary"},
    ],
    "chat": [
        {"id": "CHAT-SDK-01", "category": "required"},
        {"id": "CHAT-SDK-02", "category": "required"},
        {"id": "CHAT-SDK-03", "category": "required"},
        {"id": "CHAT-C1", "category": "conditional"},
        {"id": "CHAT-AUX", "category": "auxiliary"},
    ],
    "knowledge": [
        {"id": "KB-01", "category": "required"},
        {"id": "KB-02", "category": "required"},
        {"id": "KB-03", "category": "required"},
        {"id": "KB-04", "category": "required"},
        {"id": "KB-C1", "category": "conditional"},
        {"id": "KB-AUX", "category": "auxiliary"},
    ],
    "permissions": [
        {"id": "PERM-01", "category": "required"},
        {"id": "PERM-02", "category": "required"},
        {"id": "PERM-03", "category": "required"},
        {"id": "PERM-C1", "category": "conditional"},
        {"id": "PERM-C2", "category": "conditional"},
        {"id": "PERM-C3", "category": "conditional"},
        {"id": "PERM-AUX", "category": "auxiliary"},
    ],
    "tests": [
        {"id": "TEST-01", "category": "required"},
        {"id": "TEST-02", "category": "required"},
        {"id": "TEST-03", "category": "required"},
        {"id": "TEST-04", "category": "required"},
        {"id": "TEST-05", "category": "required"},
        {"id": "TEST-C1", "category": "conditional"},
        {"id": "TEST-AUX", "category": "auxiliary"},
    ],
    "runtime": [
        {"id": "RUN-01", "category": "required"},
        {"id": "RUN-02", "category": "required"},
        {"id": "RUN-03", "category": "required"},
        {"id": "RUN-04", "category": "required"},
        {"id": "RUN-C1", "category": "conditional"},
        {"id": "RUN-C2", "category": "conditional"},
        {"id": "RUN-AUX", "category": "auxiliary"},
    ],
    "upstream": [
        {"id": "UP-01", "category": "required"},
        {"id": "UP-02", "category": "required"},
        {"id": "UP-03", "category": "required"},
        {"id": "UP-C1", "category": "conditional"},
        {"id": "UP-AUX", "category": "auxiliary"},
    ],
    "history": [
        {"id": "HIST-01", "category": "required"},
        {"id": "HIST-02", "category": "required"},
        {"id": "HIST-03", "category": "required"},
        {"id": "HIST-C1", "category": "conditional"},
        {"id": "HIST-AUX", "category": "auxiliary"},
    ],
}

V2_ANCHOR_ALIASES: dict[str, dict[str, str | tuple[str, ...]]] = {
    "ui": {
        "UI-V2-01": "UI-01",
        "UI-ENTRY": "UI-01",
        "UI-V2-02": "UI-02",
        "UI-BEHAVIOR": "UI-02",
        "UI-V2-03": "UI-03",
        "UI-VALIDATION": "UI-03",
        "UI-V2-C1": "UI-C1",
        "UI-GENERATED": "UI-C1",
        "UI-V2-C2": "UI-C2",
        "UI-CLIENT": "UI-C2",
        "ui-entry": "UI-01",
        "ui-behavior": "UI-02",
        "ui-validation": "UI-03",
        "ui-generated-ui": "UI-C1",
        "ui-client-interaction": "UI-C2",
        "ui-conventions": "UI-AUX",
    },
    "chat": {
        "CHAT-SDK-V2-01": "CHAT-SDK-01",
        "CHAT-OWNER": "CHAT-SDK-01",
        "CHAT-01": "CHAT-SDK-01",
        "CHAT-SDK-V2-02": "CHAT-SDK-02",
        "CHAT-IDENTITY": "CHAT-SDK-02",
        "CHAT-02": "CHAT-SDK-02",
        "CHAT-SDK-V2-03": "CHAT-SDK-03",
        "CHAT-REGRESSION": "CHAT-SDK-03",
        "CHAT-03": "CHAT-SDK-03",
        "CHAT-SDK-C1": "CHAT-C1",
        "CHAT-CROSS-SOURCE": "CHAT-C1",
        "CHAT-04": "CHAT-C1",
        "chat-assembly-owner": "CHAT-SDK-01",
        "chat-identity-merge": "CHAT-SDK-02",
        "chat-chunk-regression": "CHAT-SDK-03",
        "chat-cross-source-boundary": "CHAT-C1",
        "chat-display-boundary": "CHAT-AUX",
    },
    "knowledge": {
        "KB-V2-01": "KB-01",
        "KB-01": "KB-01",
        "KB-V2-02": "KB-02",
        "KB-02": "KB-02",
        "KB-V2-03": "KB-03",
        "KB-03": "KB-03",
        "KB-V2-04": "KB-04",
        "KB-04": "KB-04",
        "KB-V2-C1": "KB-C1",
        "KB-06": "KB-C1",
        "knowledge-list-seam": "KB-01",
        "knowledge-visibility-page": "KB-02",
        "knowledge-canonical-response": "KB-03",
        "knowledge-provider-boundary": "KB-03",
        "knowledge-pagination-test": "KB-04",
        "knowledge-lifecycle": "KB-C1",
        "knowledge-identity-aux": "KB-AUX",
    },
    "permissions": {
        "PERM-V2-01": "PERM-01",
        "PERM-01": "PERM-01",
        "permissions-distinction": "PERM-01",
        "PERM-V2-02": "PERM-02",
        "PERM-02": "PERM-02",
        "permissions-seams": "PERM-02",
        "PERM-V2-03": "PERM-03",
        "PERM-03": "PERM-03",
        "permissions-boundaries-tests": "PERM-03",
        "PERM-V2-C1": "PERM-C1",
        "PERM-C3": "PERM-C1",
        "permissions-approval-flow": "PERM-C1",
        "PERM-V2-C2": "PERM-C2",
        "PERM-C2": "PERM-C2",
        "permissions-kb-provider": "PERM-C2",
        "PERM-V2-C3": "PERM-C3",
        "PERM-C1": "PERM-C3",
        "permissions-local-execution": "PERM-C3",
        "permissions-aux": "PERM-AUX",
        "permissions-visibility-vs-operations": "PERM-01",
        "permissions-rules-and-seams": "PERM-02",
        "permissions-allowed-denied-test": "PERM-03",
        "permissions-approval-lifecycle": "PERM-C1",
        "permissions-admin-boundary": "PERM-AUX",
    },
    "tests": {
        "TEST-V2-01": "TEST-01",
        "TEST-LAYER": "TEST-01",
        "TEST-01": "TEST-01",
        "tests-layer": "TEST-01",
        "TEST-V2-02": "TEST-02",
        "TEST-MIGRATION": "TEST-02",
        "TEST-02": "TEST-02",
        "tests-migration": "TEST-02",
        "TEST-MOVE-LEDGER": "TEST-02",
        "TEST-V2-03": "TEST-03",
        "TEST-PRESERVE": "TEST-03",
        "TEST-03": "TEST-03",
        "tests-preservation": "TEST-03",
        "TEST-V2-04": "TEST-04",
        "TEST-FOCUSED": "TEST-04",
        "TEST-04": "TEST-04",
        "tests-focus-inventory": "TEST-04",
        "TEST-V2-05": "TEST-05",
        "TEST-INVENTORY": "TEST-05",
        "TEST-05": "TEST-05",
        "tests-inventory": "TEST-05",
        "TEST-V2-C1": "TEST-C1",
        "TEST-LANE-CONTRACT": "TEST-C1",
        "tests-lane-contract": "TEST-C1",
        "tests-move-ledger": "TEST-02",
        "tests-runner-allocation": "TEST-AUX",
        "tests-migration-procedure": "TEST-02",
        "tests-preserve-cases": "TEST-03",
        "tests-focused-and-inventory": ("TEST-04", "TEST-05"),
    },
    "runtime": {
        "RUN-V2-01": "RUN-01",
        "RUN-01": "RUN-01",
        "RUN-V2-02": "RUN-02",
        "RUN-02": "RUN-02",
        "RUN-V2-03": "RUN-03",
        "RUN-03": "RUN-03",
        "RUN-V2-04": "RUN-04",
        "RUN-04": "RUN-04",
        "RUN-V2-C1": "RUN-C1",
        "RUN-C1": "RUN-C1",
        "RUN-V2-C2": "RUN-C2",
        "RUN-C2": "RUN-C2",
        "RUN-AUX": "RUN-AUX",
        "runtime-cancel-recovery-owner": "RUN-01",
        "runtime-effect-and-lifecycle": ("RUN-02", "RUN-03"),
        "runtime-recovery-test": "RUN-04",
        "runtime-harness-patch": "RUN-C1",
        "runtime-state-aux": "RUN-AUX",
    },
    "upstream": {
        "UP-V2-01": "UP-01",
        "UP-01": "UP-01",
        "upstream-lock": "UP-01",
        "UP-V2-02": "UP-02",
        "UP-02": "UP-02",
        "upstream-conflicts": "UP-02",
        "UP-V2-03": "UP-03",
        "UP-03": "UP-03",
        "upstream-statuses": "UP-03",
        "UP-V2-C1": "UP-C1",
        "UP-C1": "UP-C1",
        "upstream-patch-registration": "UP-C1",
        "upstream-branch-policy": "UP-AUX",
        "upstream-effective-lock": "UP-01",
        "upstream-conflict-resolution": "UP-02",
        "upstream-separated-status": "UP-03",
        "upstream-harness-patch": "UP-C1",
        "upstream-mirror-policy": "UP-AUX",
    },
    "history": {
        "HISTORY-V2-01": "HIST-01",
        "HIST-01": "HIST-01",
        "HISTORY-V2-02": "HIST-02",
        "HIST-02": "HIST-02",
        "HISTORY-V2-03": "HIST-03",
        "HIST-03": "HIST-03",
        "HISTORY-V2-04": "HIST-AUX",
        "HIST-04": "HIST-AUX",
        "HIST-05": "HIST-C1",
        "history-not-current-proof": "HIST-01",
        "history-current-status-path": "HIST-02",
        "history-unknowns": "HIST-03",
        "history-numeric-provenance": "HIST-C1",
        "history-route-aux": "HIST-AUX",
    },
}


def _validate_queue(queue: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    if not isinstance(queue, list) or len(queue) != 32:
        raise ValueError("queue must contain exactly 32 slots")
    by_slot: dict[int, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for row in queue:
        slot = row.get("slot")
        candidate = row.get("candidate")
        if (
            not isinstance(slot, int)
            or slot in by_slot
            or candidate not in {"baseline", "after"}
        ):
            raise ValueError("queue slots must be unique and identify a candidate")
        by_slot[slot] = row
        counts[candidate] += 1
    if set(by_slot) != set(range(1, 33)) or counts != Counter(
        {"baseline": 16, "after": 16}
    ):
        raise ValueError("queue must have 16 baseline and 16 after slots")
    return by_slot


def _validate_specs(
    anchor_specs: dict[str, list[dict[str, str]]],
) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    for task, rows in anchor_specs.items():
        anchors: dict[str, str] = {}
        for row in rows:
            anchor_id = row.get("id")
            category = row.get("category")
            if not anchor_id or anchor_id in anchors or category not in CATEGORIES:
                raise ValueError(f"invalid or duplicate anchor definition for {task}")
            anchors[anchor_id] = category
        normalized[task] = anchors
    return normalized


def normalize_review(task: str, review: dict[str, Any]) -> dict[str, Any]:
    """Project grader-specific v2 numbering and evidence fields to canonical IDs."""
    specs = _validate_specs(V2_ANCHORS)
    if task not in specs or not isinstance(review.get("anchors"), list):
        raise ValueError(f"slot review for {task!r} has no per-anchor evidence")
    aliases = V2_ANCHOR_ALIASES[task]
    rows_by_id: dict[str, dict[str, Any]] = {}
    for row in review["anchors"]:
        source_id = row.get("id")
        alias = aliases.get(source_id)
        if alias is None and isinstance(source_id, str):
            folded = {key.casefold(): value for key, value in aliases.items()}
            alias = folded.get(source_id.casefold())
        target_ids = (
            (source_id,)
            if source_id in specs[task]
            else (alias if isinstance(alias, tuple) else (alias,))
        )
        if not target_ids or any(
            anchor_id not in specs[task] for anchor_id in target_ids
        ):
            raise ValueError(
                f"unknown or duplicate grader anchor for {task}: {source_id}"
            )
        evidence = row.get("evidence", {})
        excerpt = row.get("excerpt") or evidence.get("answer") or ""
        candidate_path = row.get("candidate_path") or evidence.get("candidate") or ""
        for anchor_id in target_ids:
            category = specs[task][anchor_id]
            trigger = row.get("trigger", row.get("triggered"))
            normalized = {
                "id": anchor_id,
                "category": category,
                "decision": row.get("decision"),
                "excerpt": excerpt,
                "candidate_path": candidate_path,
            }
            if category == "conditional":
                normalized["trigger"] = (
                    trigger if trigger in (True, False, "unknown") else "unknown"
                )
            previous = rows_by_id.get(anchor_id)
            if previous is None:
                rows_by_id[anchor_id] = normalized
                continue
            prior_trigger = previous.get("trigger")
            if previous["decision"] != normalized[
                "decision"
            ] or prior_trigger != normalized.get("trigger"):
                previous["decision"] = "unresolved"
                if category == "conditional":
                    previous["trigger"] = "unknown"
            previous["excerpt"] = " / ".join(
                value for value in (previous["excerpt"], excerpt) if value
            )
            previous["candidate_path"] = " ; ".join(
                value
                for value in (previous["candidate_path"], candidate_path)
                if value and value not in previous["candidate_path"]
            )
    rows = list(rows_by_id.values())
    return {
        "reviewer": review.get("reviewer"),
        "anchors": rows,
        "critical_error": review.get(
            "critical_error", review.get("critical_errors", False)
        ),
        "historical_authority_misuse": review.get(
            "historical_authority_misuse", review.get("history_misuse", False)
        ),
    }


def _review_map(
    review: dict[str, Any], expected: dict[str, str]
) -> tuple[str, dict[str, dict[str, Any]]]:
    reviewer = review.get("reviewer")
    rows = review.get("anchors")
    if (
        not isinstance(reviewer, str)
        or not reviewer.strip()
        or not isinstance(rows, list)
    ):
        raise ValueError("each independent review needs a reviewer and anchor list")
    judgments: dict[str, dict[str, Any]] = {}
    for row in rows:
        anchor_id = row.get("id")
        if anchor_id not in expected or anchor_id in judgments:
            raise ValueError(f"unknown or duplicate v2 anchor: {anchor_id}")
        if (
            row.get("category") != expected[anchor_id]
            or row.get("decision") not in DECISIONS
        ):
            raise ValueError(f"invalid v2 judgment for {anchor_id}")
        judgments[anchor_id] = row
    if set(judgments) != set(expected):
        raise ValueError("each reviewer must judge every frozen v2 anchor")
    return reviewer, judgments


def _effective_judgment(
    anchor_id: str,
    category: str,
    first: dict[str, Any],
    second: dict[str, Any],
    adjudication: dict[str, Any] | None,
) -> tuple[str, str | None]:
    first_decision, second_decision = first["decision"], second["decision"]
    first_trigger, second_trigger = first.get("trigger"), second.get("trigger")
    disagrees = first_decision != second_decision or first_trigger != second_trigger
    if disagrees:
        if adjudication is None:
            return "unresolved", "disagreement"
        matches = [
            row for row in adjudication.get("anchors", []) if row.get("id") == anchor_id
        ]
        if len(matches) != 1:
            return "unresolved", "disagreement"
        judgment = matches[0]
        if judgment.get("decision") not in DECISIONS:
            raise ValueError(f"invalid adjudication for {anchor_id}")
        decision, trigger = judgment["decision"], judgment.get("trigger")
    else:
        decision, trigger = first_decision, first_trigger

    if category == "conditional":
        if trigger is False:
            if decision == "not_applicable":
                return "not_applicable", None
            return "unresolved", "false_trigger_mismatch"
        if trigger is True:
            if decision in {"met", "missed"}:
                return decision, None
            return "unresolved", "triggered_conditional_unresolved"
        return "unresolved", "unknown_trigger"
    if category == "auxiliary":
        if trigger is not None:
            raise ValueError(f"auxiliary anchor {anchor_id} cannot have a trigger")
        return decision, None
    if trigger is not None:
        raise ValueError(f"non-conditional anchor {anchor_id} cannot have a trigger")
    if decision == "not_applicable":
        return "unresolved", "required_anchor_marked_not_applicable"
    return decision, None


def score_reviews(
    queue: list[dict[str, Any]],
    records: list[dict[str, Any]],
    anchor_specs: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    """Score valid submitted records while retaining the frozen 16-answer denominators."""
    queue_by_slot = _validate_queue(queue)
    specs = _validate_specs(anchor_specs)
    records_by_slot: dict[int, dict[str, Any]] = {}
    for record in records:
        slot = record.get("slot")
        if slot not in queue_by_slot or slot in records_by_slot:
            raise ValueError(f"unknown or duplicate result slot: {slot}")
        records_by_slot[slot] = record

    candidate_stats = {
        name: {
            "denominator": 16,
            "scored": 0,
            "correct": 0,
            "incorrect": 0,
            "unresolved": 0,
            "correct_rate": 0.0,
        }
        for name in ("baseline", "after")
    }
    task_results: list[dict[str, Any]] = []
    unresolved_disagreements = unresolved_conditionals = auxiliary_misses = 0
    critical_errors = historical_misuse = 0
    missing_or_invalid: list[int] = []

    for slot in range(1, 33):
        queued = queue_by_slot[slot]
        record = records_by_slot.get(slot)
        if (
            record is None
            or record.get("status") != "submitted"
            or record.get("tool_valid") is not True
        ):
            missing_or_invalid.append(slot)
            continue
        task, candidate = queued.get("task"), queued["candidate"]
        if task not in specs:
            raise ValueError(f"missing frozen v2 anchors for task {task}")
        reviews = record.get("reviews")
        if not isinstance(reviews, list) or len(reviews) != 2:
            raise ValueError(f"slot {slot} requires two independent reviews")
        reviewer_names: set[str] = set()
        mapped = []
        for review in reviews:
            reviewer, judgments = _review_map(review, specs[task])
            if reviewer in reviewer_names:
                raise ValueError(f"slot {slot} reviewers must be distinct")
            reviewer_names.add(reviewer)
            mapped.append(judgments)
        adjudication = record.get("adjudication")
        if adjudication is not None:
            reviewer = adjudication.get("reviewer")
            if not reviewer or reviewer in reviewer_names:
                raise ValueError(f"slot {slot} adjudicator must be independent")

        effective: dict[str, str] = {}
        for anchor_id, category in specs[task].items():
            decision, issue = _effective_judgment(
                anchor_id,
                category,
                mapped[0][anchor_id],
                mapped[1][anchor_id],
                adjudication,
            )
            effective[anchor_id] = decision
            unresolved_disagreements += issue == "disagreement"
            unresolved_conditionals += issue in {
                "unknown_trigger",
                "false_trigger_mismatch",
                "triggered_conditional_unresolved",
                "required_anchor_marked_not_applicable",
            }
            auxiliary_misses += category == "auxiliary" and decision == "missed"

        gate_decisions = [
            effective[anchor_id]
            for anchor_id, category in specs[task].items()
            if category == "required"
            or (category == "conditional" and effective[anchor_id] != "not_applicable")
        ]
        correct: bool | None = (
            False
            if "missed" in gate_decisions
            else None
            if "unresolved" in gate_decisions
            else True
        )
        critical_errors += record.get("critical_error") is True
        historical_misuse += record.get("historical_authority_misuse") is True
        candidate_stats[candidate]["scored"] += 1
        if correct is True:
            candidate_stats[candidate]["correct"] += 1
        elif correct is False:
            candidate_stats[candidate]["incorrect"] += 1
        else:
            candidate_stats[candidate]["unresolved"] += 1
        task_results.append(
            {
                "slot": slot,
                "task": task,
                "candidate": candidate,
                "correct": correct,
                "anchors": effective,
                "reviews": reviews,
                "adjudication": adjudication,
            }
        )

    for stats in candidate_stats.values():
        stats["correct_rate"] = stats["correct"] / stats["denominator"]
    unresolved = bool(unresolved_disagreements or unresolved_conditionals)
    complete = not missing_or_invalid and not unresolved
    after_all_correct = (
        candidate_stats["after"]["correct"] == candidate_stats["after"]["denominator"]
    )
    status = (
        "incomplete"
        if not complete
        else "pass"
        if after_all_correct and not critical_errors and not historical_misuse
        else "fail"
    )
    return {
        "protocol": "disclosure-reading-v2",
        "status": status,
        "candidates": candidate_stats,
        "tasks": task_results,
        "missing_or_invalid_slots": missing_or_invalid,
        "unresolved_disagreements": int(unresolved_disagreements),
        "unresolved_conditionals": int(unresolved_conditionals),
        "auxiliary_misses": int(auxiliary_misses),
        "critical_errors": int(critical_errors),
        "historical_authority_misuse": int(historical_misuse),
    }
