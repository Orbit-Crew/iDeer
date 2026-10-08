"""Validate and dispatch a frozen v2 disclosure reading queue."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

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


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_frozen_queue(queue: dict[str, object]) -> list[dict[str, object]]:
    """Verify the queue digest, seed-derived sequence, and fixed 32-slot balance."""
    claimed = queue.get("queue_sha256")
    unsigned = {key: value for key, value in queue.items() if key != "queue_sha256"}
    if not isinstance(claimed, str) or canonical_sha256(unsigned) != claimed:
        raise ValueError("frozen queue SHA-256 mismatch")
    if queue.get("protocol_id") != "disclosure-reading-v2":
        raise ValueError("unexpected formal reading protocol")
    if queue.get("max_parallel") != 3:
        raise ValueError("frozen formal queue must allow at most three readers")
    seed = queue.get("seed")
    if not isinstance(seed, str) or not seed:
        raise ValueError("frozen queue seed is missing")

    pairs = [(task, replicate) for task in TASKS for replicate in (1, 2)]
    random.Random(seed).shuffle(pairs)
    expected = []
    for task, replicate in pairs:
        candidates = ("baseline", "after") if replicate == 1 else ("after", "baseline")
        for candidate in candidates:
            expected.append((candidate, task, replicate))

    slots = queue.get("slots")
    if not isinstance(slots, list) or len(slots) != 32:
        raise ValueError("formal queue must contain exactly 32 slots")
    actual = []
    for number, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict) or slot.get("slot") != number:
            raise ValueError("formal queue slots must be sequential from 1 to 32")
        actual.append((slot.get("candidate"), slot.get("task"), slot.get("replicate")))
        if slot.get("stage") != "formal" or slot.get("freeze") != "freeze-v2":
            raise ValueError(f"slot {number} does not use the frozen formal inputs")
    if actual != expected:
        raise ValueError("formal queue order does not match its frozen seed")
    for candidate in ("baseline", "after"):
        if sum(row[0] == candidate for row in actual) != 16:
            raise ValueError(f"formal queue must contain 16 {candidate} slots")
    for task in TASKS:
        for candidate in ("baseline", "after"):
            if sum(row[:2] == (candidate, task) for row in actual) != 2:
                raise ValueError(f"formal queue must contain two {candidate}/{task} slots")
    return slots


def validate_frozen_inputs(
    queue: dict[str, object], frozen: dict[str, object]
) -> None:
    """Bind the queue seed to the separately frozen input manifest."""
    inputs = frozen.get("freeze_inputs")
    if not isinstance(inputs, dict):
        raise ValueError("frozen input manifest is missing freeze_inputs")
    inputs_digest = canonical_sha256(inputs)
    if frozen.get("freeze_inputs_canonical_sha256") != inputs_digest:
        raise ValueError("frozen input manifest canonical SHA-256 mismatch")
    expected_seed = hashlib.sha256(
        b"disclosure-reading-v2-formal-queue\0"
        + json.dumps(
            inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    if queue.get("seed") != expected_seed:
        raise ValueError("formal queue seed does not match frozen inputs")


def classify_attempt(record_path: Path, quota_marker: Path) -> dict[str, object]:
    """Prefer a persisted result; use the global quota marker only if absent."""
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        result = {
            "status": record.get("status", "failed"),
            "failure_class": record.get("failure_class"),
            "record": str(record_path),
        }
        if record_path.with_suffix(".jsonl").is_file():
            result["trace"] = str(record_path.with_suffix(".jsonl"))
        config = record_path.with_name(record_path.stem + ".config.json")
        if config.is_file():
            result["config"] = str(config)
        return result
    if quota_marker.is_file():
        marker = json.loads(quota_marker.read_text(encoding="utf-8"))
        return {
            "status": "failed",
            "failure_class": "quota_exhausted",
            "blocked_by_run_id": marker.get("run_id"),
        }
    return {"status": "failed", "failure_class": "protocol"}


def dispatch_queue(
    slots: Iterable[dict[str, object]],
    launch: Callable[[dict[str, object]], dict[str, object]],
    *,
    max_parallel: int = 3,
) -> dict[str, object]:
    """Dispatch in queue order, draining started tasks after quota exhaustion."""
    if max_parallel < 1 or max_parallel > 3:
        raise ValueError("max_parallel must be between one and three")
    pending = list(slots)
    started: list[int] = []
    completed: dict[int, dict[str, object]] = {}
    active = {}
    stopped = False
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        while pending or active:
            while pending and len(active) < max_parallel and not stopped:
                slot = pending.pop(0)
                number = int(slot["slot"])
                started.append(number)
                active[pool.submit(launch, slot)] = number
            if not active:
                break
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            results = []
            for future in sorted(done, key=lambda item: active[item]):
                number = active.pop(future)
                try:
                    result = dict(future.result())
                except Exception as error:
                    result = {
                        "status": "failed",
                        "failure_class": "infrastructure",
                        "error": f"{type(error).__name__}: {error}",
                    }
                result["slot"] = number
                completed[number] = result
                results.append(result)
            if any(item.get("failure_class") == "quota_exhausted" for item in results):
                stopped = True
    return {
        "dispatch_stopped": stopped,
        "stop_reason": "quota_exhausted" if stopped else None,
        "started_slots": started,
        "pending_slots": pending,
        "results": [completed[number] for number in sorted(completed)],
    }
