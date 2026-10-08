import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts.disclosure_formal_queue import (  # noqa: E402
    classify_attempt,
    dispatch_queue,
    validate_frozen_inputs,
    validate_frozen_queue,
)


def test_submitted_record_wins_over_global_quota_marker(tmp_path):
    record = tmp_path / "slot-25.json"
    record.write_text(json.dumps({"status": "submitted", "failure_class": None}))
    marker = tmp_path / "quota-exhausted.json"
    marker.write_text(json.dumps({"run_id": "later-slot-26"}))

    assert classify_attempt(record, marker) == {
        "status": "submitted",
        "failure_class": None,
        "record": str(record),
    }


def test_missing_record_uses_quota_marker_as_failure(tmp_path):
    marker = tmp_path / "quota-exhausted.json"
    marker.write_text(json.dumps({"run_id": "slot-26"}))

    assert classify_attempt(tmp_path / "missing.json", marker) == {
        "status": "failed",
        "failure_class": "quota_exhausted",
        "blocked_by_run_id": "slot-26",
    }


def test_queue_dispatch_stops_new_work_after_quota_and_keeps_order():
    slots = [{"slot": number} for number in range(1, 7)]
    started = []

    def launch(slot):
        started.append(slot["slot"])
        if slot["slot"] == 2:
            return {"status": "failed", "failure_class": "quota_exhausted"}
        return {"status": "submitted", "failure_class": None}

    result = dispatch_queue(slots, launch, max_parallel=1)

    assert started == [1, 2]
    assert result["started_slots"] == [1, 2]
    assert result["pending_slots"] == slots[2:]
    assert result["dispatch_stopped"] is True


def test_frozen_queue_checks_hash_order_and_balance():
    queue_path = ROOT / "dev-log/disclosure-dual-track/ticket07-formal/formal-queue.json"
    with open(queue_path, encoding="utf-8") as source:
        queue = json.load(source)

    slots = validate_frozen_queue(queue)
    with (ROOT / "dev-log/disclosure-dual-track/ticket07-formal/freeze-inputs.json").open(encoding="utf-8") as source:
        frozen = json.load(source)
    validate_frozen_inputs(queue, frozen)

    assert len(slots) == 32
    assert [slot["slot"] for slot in slots] == list(range(1, 33))
    assert sum(slot["candidate"] == "baseline" for slot in slots) == 16
    assert sum(slot["candidate"] == "after" for slot in slots) == 16


def test_frozen_queue_rejects_tampering():
    with pytest.raises(ValueError, match="SHA"):
        validate_frozen_queue({"slots": [], "queue_sha256": "bad"})


def test_frozen_queue_rejects_seed_from_different_inputs():
    queue_path = ROOT / "dev-log/disclosure-dual-track/ticket07-formal/formal-queue.json"
    frozen_path = ROOT / "dev-log/disclosure-dual-track/ticket07-formal/freeze-inputs.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    frozen["freeze_inputs"]["tool_config_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="canonical SHA"):
        validate_frozen_inputs(queue, frozen)
