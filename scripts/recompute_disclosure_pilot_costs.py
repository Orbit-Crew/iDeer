#!/usr/bin/env python3
"""Recompute non-scored pilot read intervals and byte costs from raw events."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from report_disclosure_costs import InputError, build_report

PILOT_CANDIDATES = {"baseline", "after"}
PILOT_TASKS = {
    "ui",
    "chat",
    "knowledge",
    "permissions",
    "tests",
    "runtime",
    "upstream",
    "history",
}


def recompute_pilot_costs(experiment_root: Path) -> dict[str, Any]:
    experiment_root = experiment_root.resolve(strict=True)
    freeze_root = experiment_root / "freeze-v2"
    try:
        freeze = json.loads((freeze_root / "freeze.json").read_text(encoding="utf-8"))
        role_map_path = freeze_root / "role-map.json"
        role_map_bytes = role_map_path.read_bytes()
        role_map = json.loads(role_map_bytes)
        queue_bytes = (freeze_root / "pilot-queue.json").read_bytes()
        queue = json.loads(queue_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError("frozen pilot inputs are missing or invalid") from exc

    if not isinstance(freeze, dict):
        raise InputError("pilot freeze must be a JSON object")
    if not isinstance(role_map, dict):
        raise InputError("role map must be a JSON object")
    role_map_shape = (
        role_map.get("format") == 1
        and isinstance(role_map.get("candidates"), dict)
        and isinstance(role_map.get("paths"), dict)
        and isinstance(role_map.get("sections"), list)
    )
    if not role_map_shape:
        raise InputError("pilot role map has an invalid structure")
    if (
        not isinstance(freeze.get("queue_sha256"), str)
        or hashlib.sha256(queue_bytes).hexdigest() != freeze["queue_sha256"]
    ):
        raise InputError("frozen pilot queue digest mismatch")
    if freeze.get("stage") != "non-scored":
        raise InputError("pilot cost recompute only accepts a non-scored freeze")
    if hashlib.sha256(role_map_bytes).hexdigest() != freeze.get("role_map_sha256"):
        raise InputError("frozen pilot role map digest mismatch")
    if not isinstance(queue, list) or not queue:
        raise InputError("frozen pilot queue must be a non-empty array")
    frozen_candidates = freeze.get("candidates")
    frozen_prompts = freeze.get("prompts")
    if not isinstance(frozen_candidates, dict):
        raise InputError("frozen candidate identities are missing")
    if not isinstance(frozen_prompts, dict):
        raise InputError("frozen task prompt identities are missing")
    experiment_root_resolved = experiment_root.resolve(strict=True)
    if not freeze_root.resolve(strict=True).is_relative_to(experiment_root_resolved):
        raise InputError("pilot freeze directory escapes experiment root")
    queue_keys: set[tuple[str, str]] = set()
    frozen_task_digests: dict[str, str] = {}
    for row in queue:
        if not isinstance(row, dict):
            raise InputError("frozen pilot queue contains an invalid row")
        candidate, task = row.get("candidate"), row.get("task")
        if candidate not in PILOT_CANDIDATES or task not in PILOT_TASKS:
            raise InputError("frozen pilot queue contains an unsafe candidate/task")
        queue_keys.add((candidate, task))
        manifest_path = freeze_root / "candidates" / f"{candidate}.manifest.json"
        prompt_path = freeze_root / "prompts" / f"{task}.txt"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            prompt_digest = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(
                f"frozen candidate manifest or task prompt is missing: {candidate}/{task}"
            ) from exc
        if not isinstance(manifest, dict):
            raise InputError(f"frozen candidate manifest is invalid: {candidate}")
        candidate_freeze = frozen_candidates.get(candidate)
        if not isinstance(candidate_freeze, dict):
            raise InputError(f"frozen candidate entry is invalid: {candidate}")
        frozen_digest = candidate_freeze.get("manifest_sha256")
        role_digest = role_map.get("candidates", {}).get(candidate)
        if (
            not isinstance(frozen_digest, str)
            or manifest.get("manifest_sha256") != frozen_digest
            or role_digest != frozen_digest
        ):
            raise InputError(f"frozen candidate identity mismatch: {candidate}")
        expected_prompt_digest = frozen_prompts.get(task)
        if (
            not isinstance(expected_prompt_digest, str)
            or prompt_digest != expected_prompt_digest
        ):
            raise InputError(f"frozen task prompt digest mismatch: {task}")
        frozen_task_digests[task] = prompt_digest

    pilots_root = freeze_root / "pilots"
    try:
        pilots_root = pilots_root.resolve(strict=True)
    except OSError as exc:
        raise InputError("frozen pilot records directory is missing") from exc
    if not pilots_root.is_relative_to(experiment_root_resolved):
        raise InputError("frozen pilot records directory escapes experiment root")
    if not pilots_root.is_dir():
        raise InputError("frozen pilot records directory is missing")
    attempts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for record_path in sorted(pilots_root.glob("*.json")):
        try:
            resolved_record_path = record_path.resolve(strict=True)
        except OSError as exc:
            raise InputError(f"invalid pilot record path: {record_path.name}") from exc
        if not resolved_record_path.is_relative_to(pilots_root):
            raise InputError(
                f"pilot record escapes records directory: {record_path.name}"
            )
        if record_path.name == "quota-exhausted.json" or record_path.name.endswith(
            ".config.json"
        ):
            continue
        try:
            record = json.loads(resolved_record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"invalid pilot record: {record_path.name}") from exc
        if not isinstance(record, dict):
            raise InputError(f"pilot record must be a JSON object: {record_path.name}")
        run_id = record.get("run_id")
        candidate, task = record.get("candidate"), record.get("task")
        if (
            not isinstance(run_id, str)
            or not run_id
            or Path(run_id).name != run_id
            or run_id in seen_ids
        ):
            raise InputError(f"invalid or duplicate pilot run id: {record_path.name}")
        if (candidate, task) not in queue_keys:
            raise InputError(f"pilot record is absent from the frozen queue: {run_id}")
        if record.get("task_sha256") != frozen_task_digests[task]:
            raise InputError(f"frozen task prompt digest mismatch for {run_id}")
        frozen_candidate = frozen_candidates[candidate]
        if record.get("manifest_sha256") != frozen_candidate.get("manifest_sha256"):
            raise InputError(f"candidate manifest digest mismatch for {run_id}")
        if record_path.stem != run_id:
            raise InputError(f"pilot record filename does not match run id: {run_id}")
        trace_path = pilots_root / f"{run_id}.jsonl"
        try:
            resolved_trace_path = trace_path.resolve(strict=True)
        except OSError as exc:
            raise InputError(f"pilot trace is missing for {run_id}") from exc
        if (
            not resolved_trace_path.is_relative_to(pilots_root)
            or not resolved_trace_path.is_file()
        ):
            raise InputError(f"pilot trace is missing for {run_id}")
        candidate_root = experiment_root / "candidates" / candidate
        try:
            candidate_root = candidate_root.resolve(strict=True)
        except OSError as exc:
            raise InputError(
                f"frozen candidate snapshot is missing for {run_id}"
            ) from exc
        if not candidate_root.is_relative_to(experiment_root_resolved):
            raise InputError(f"candidate snapshot escapes experiment root for {run_id}")
        if not candidate_root.is_dir():
            raise InputError(f"frozen candidate snapshot is missing for {run_id}")
        copied = dict(record)
        copied["candidate_root"] = str(candidate_root)
        attempts.append(copied)
        seen_ids.add(run_id)

    if not attempts:
        raise InputError("no raw pilot attempts are available")

    report = build_report({"role_map": role_map, "attempts": attempts})
    return {
        **report,
        "stage": "non-scored",
        "protocol_id": freeze.get("protocol_id"),
        "read_intervals_recomputed": True,
        "answer_scoring_performed": False,
        "scope": "all retained physical pilot attempts; interval unions and cost categories derive from raw ranges and frozen candidate snapshots",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = recompute_pilot_costs(args.experiment_root)
        if args.out.exists():
            raise InputError(f"pilot cost output already exists: {args.out}")
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
                    "read_intervals_recomputed": True,
                    "answer_scoring_performed": False,
                }
            )
        )
        return 0
    except (InputError, OSError, UnicodeError, TypeError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
