from __future__ import annotations

import hashlib
import importlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
legacy_recompute = importlib.import_module("scripts.recompute_disclosure_legacy_costs")
RecomputeError = legacy_recompute.RecomputeError
_raw_path = legacy_recompute._raw_path
role_for_path = legacy_recompute.role_for_path
load_trusted_audit = legacy_recompute.load_trusted_audit
validate_slot_identity = legacy_recompute.validate_slot_identity
validate_slots = legacy_recompute.validate_slots

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "disclosure_evidence_archive.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def make_inputs(tmp_path: Path) -> tuple[Path, Path]:
    legacy = tmp_path / "legacy"
    experiment = tmp_path / "experiment"
    legacy.mkdir()
    experiment.mkdir()
    (legacy / "raw.jsonl").write_text('{"event":"read"}\n', encoding="utf-8")
    (experiment / "answer.json").write_text('{"status":"failed"}\n', encoding="utf-8")
    return legacy, experiment


def pack(tmp_path: Path, legacy: Path, experiment: Path) -> Path:
    archive = tmp_path / "evidence.tar.gz"
    result = run(
        "pack",
        "--legacy-root",
        str(legacy),
        "--experiment-root",
        str(experiment),
        "--out",
        str(archive),
    )
    assert result.returncode == 0, result.stderr
    return archive


def test_archive_restores_and_verifies_all_files_in_clean_directory(tmp_path: Path) -> None:
    legacy, experiment = make_inputs(tmp_path)
    archive = pack(tmp_path, legacy, experiment)
    restore = tmp_path / "clean-restore"

    result = run("verify", "--archive", str(archive), "--restore-to", str(restore))

    assert result.returncode == 0, result.stderr
    assert (restore / "legacy/raw.jsonl").read_text(encoding="utf-8") == '{"event":"read"}\n'
    assert (restore / "experiment/answer.json").read_text(encoding="utf-8") == '{"status":"failed"}\n'
    assert '"verified_files": 2' in result.stdout


def test_archive_verification_fails_closed_on_tampered_content(tmp_path: Path) -> None:
    legacy, experiment = make_inputs(tmp_path)
    archive = pack(tmp_path, legacy, experiment)
    tampered = tmp_path / "tampered.tar.gz"
    with tarfile.open(archive, "r:gz") as source, tarfile.open(tampered, "w:gz") as target:
        for member in source.getmembers():
            data = source.extractfile(member).read() if member.isfile() else None
            if member.name == "legacy/raw.jsonl":
                data = b"tampered\n"
            if data is None:
                target.addfile(member)
            else:
                member.size = len(data)
                target.addfile(member, io.BytesIO(data))

    result = run(
        "verify",
        "--archive",
        str(tampered),
        "--restore-to",
        str(tmp_path / "tampered-restore"),
    )

    assert result.returncode != 0
    assert "digest mismatch" in result.stderr
    assert not (tmp_path / "tampered-restore").exists()


def test_archive_verification_fails_closed_when_a_manifested_file_is_missing(tmp_path: Path) -> None:
    legacy, experiment = make_inputs(tmp_path)
    archive = pack(tmp_path, legacy, experiment)
    missing = tmp_path / "missing.tar.gz"
    with tarfile.open(archive, "r:gz") as source, tarfile.open(missing, "w:gz") as target:
        for member in source.getmembers():
            if member.name == "experiment/answer.json":
                continue
            data = source.extractfile(member).read() if member.isfile() else None
            if data is None:
                target.addfile(member)
            else:
                target.addfile(member, io.BytesIO(data))

    result = run(
        "verify",
        "--archive",
        str(missing),
        "--restore-to",
        str(tmp_path / "missing-restore"),
    )

    assert result.returncode != 0
    assert "archive file set differs from manifest" in result.stderr
    assert not (tmp_path / "missing-restore").exists()


def test_pilot_recompute_retains_failed_slot_and_unstarted_queue_order(tmp_path: Path) -> None:
    experiment = tmp_path / "experiment"
    (experiment / "candidates").mkdir(parents=True)
    (experiment / "prompts").mkdir()
    (experiment / "pilots").mkdir()
    (experiment / "candidates/after.manifest.json").write_text(json.dumps({"manifest_sha256": "a" * 64}), encoding="utf-8")
    (experiment / "freeze.json").write_text(
        json.dumps(
            {
                "stage": "non-scored",
                "model": {"alias": "gpt-6.1-sol", "reasoning": "medium"},
            }
        ),
        encoding="utf-8",
    )
    prompt = "Frozen task prompt\n"
    (experiment / "prompts/ui.txt").write_text(prompt, encoding="utf-8")
    (experiment / "prompts/chat.txt").write_text("Second prompt\n", encoding="utf-8")
    (experiment / "pilot-queue.json").write_text(
        json.dumps(
            [
                {"slot": 1, "candidate": "after", "task": "ui"},
                {"slot": 2, "candidate": "after", "task": "chat"},
            ]
        ),
        encoding="utf-8",
    )
    run_id = "after-ui-attempt-1"
    record = {
        "run_id": run_id,
        "candidate": "after",
        "task": "ui",
        "manifest_sha256": "a" * 64,
        "task_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "status": "failed",
        "failure_class": "protocol",
        "attempt_no": 1,
        "retry_of": None,
        "tool_config_sha256": "b" * 64,
        "events": [],
    }
    (experiment / f"pilots/{run_id}.json").write_text(json.dumps(record), encoding="utf-8")
    (experiment / f"pilots/{run_id}.jsonl").write_text('{"type":"error"}\n', encoding="utf-8")
    (experiment / f"pilots/{run_id}.config.json").write_text(
        json.dumps(
            {
                "config": {
                    "model": "gpt-6.1-sol",
                    "reasoning": "medium",
                    "stage": "non-scored",
                },
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "manifest_sha256": "a" * 64,
                "tool_config_sha256": "b" * 64,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "pilot-summary.json"

    result = run(
        "recompute-pilots",
        "--experiment-root",
        str(experiment),
        "--out",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["status"] == "incomplete"
    assert summary["attempt_count"] == 1
    assert summary["terminal_failures"] == 1
    assert summary["unstarted_queue_slots"] == [2]
    assert summary["read_intervals_recomputed"] is False
    assert "pilot interval/cost report" in summary["read_intervals_scope"]


def test_pilot_recompute_fails_closed_when_trace_is_missing(tmp_path: Path) -> None:
    experiment = tmp_path / "experiment"
    (experiment / "candidates").mkdir(parents=True)
    (experiment / "prompts").mkdir()
    (experiment / "pilots").mkdir()
    prompt = "Frozen task prompt\n"
    (experiment / "prompts/ui.txt").write_text(prompt, encoding="utf-8")
    (experiment / "candidates/after.manifest.json").write_text(json.dumps({"manifest_sha256": "a" * 64}), encoding="utf-8")
    (experiment / "freeze.json").write_text(
        json.dumps(
            {
                "stage": "non-scored",
                "model": {"alias": "gpt-6.1-sol", "reasoning": "medium"},
            }
        ),
        encoding="utf-8",
    )
    (experiment / "pilot-queue.json").write_text(
        json.dumps([{"slot": 1, "candidate": "after", "task": "ui"}]),
        encoding="utf-8",
    )
    run_id = "after-ui-attempt-1"
    (experiment / f"pilots/{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "candidate": "after",
                "task": "ui",
                "manifest_sha256": "a" * 64,
                "task_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "status": "failed",
                "failure_class": "protocol",
                "attempt_no": 1,
                "retry_of": None,
                "tool_config_sha256": "b" * 64,
                "events": [],
            }
        ),
        encoding="utf-8",
    )
    (experiment / f"pilots/{run_id}.config.json").write_text(
        json.dumps(
            {
                "config": {
                    "model": "gpt-6.1-sol",
                    "reasoning": "medium",
                    "stage": "non-scored",
                },
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "manifest_sha256": "a" * 64,
                "tool_config_sha256": "b" * 64,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "pilot-summary.json"

    result = run(
        "recompute-pilots",
        "--experiment-root",
        str(experiment),
        "--out",
        str(output),
    )

    assert result.returncode != 0
    assert "trace is missing" in result.stderr
    assert not output.exists()


def test_pilot_recompute_rejects_path_traversal_in_queue_identity(tmp_path: Path) -> None:
    experiment = tmp_path / "experiment"
    (experiment / "candidates").mkdir(parents=True)
    (experiment / "prompts").mkdir()
    (experiment / "pilots").mkdir()
    (experiment / "freeze.json").write_text(
        json.dumps(
            {
                "stage": "non-scored",
                "model": {"alias": "gpt-6.1-sol", "reasoning": "medium"},
            }
        ),
        encoding="utf-8",
    )
    (experiment / "escape.manifest.json").write_text(json.dumps({"manifest_sha256": "e" * 64}), encoding="utf-8")
    (experiment / "candidates/after.manifest.json").write_text(json.dumps({"manifest_sha256": "a" * 64}), encoding="utf-8")
    (experiment / "escape.txt").write_text("outside prompt\n", encoding="utf-8")
    (experiment / "prompts/ui.txt").write_text("inside prompt\n", encoding="utf-8")
    (experiment / "pilot-queue.json").write_text(
        json.dumps(
            [
                {"slot": 1, "candidate": "../escape", "task": "ui"},
                {"slot": 2, "candidate": "after", "task": "../escape"},
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "pilot-summary.json"

    result = run(
        "recompute-pilots",
        "--experiment-root",
        str(experiment),
        "--out",
        str(output),
    )

    assert result.returncode != 0
    assert "unsafe queue candidate/task" in result.stderr
    assert not output.exists()


def test_legacy_recompute_classifies_and_rejects_paths_outside_evidence_root(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()

    assert role_for_path("AGENTS.md") == "root_guidance"
    assert role_for_path("frontend/src/app.tsx") == "source_test_config"
    assert role_for_path("docs/decisions/0001.md") == "historical_material"
    try:
        _raw_path(legacy, "dev-log/disclosure-readability-recovery/../outside.json")
    except RecomputeError as exc:
        assert "unsafe historical raw path" in str(exc)
    else:
        raise AssertionError("path traversal was accepted")


def test_legacy_recompute_binds_audit_digest_and_terminal_slot_identity(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps({"slots": []}), encoding="utf-8")
    try:
        load_trusted_audit(audit_path)
    except RecomputeError as exc:
        assert "audit digest mismatch" in str(exc)
    else:
        raise AssertionError("untrusted audit was accepted")

    slots = [{"slot": number} for number in range(1, 33)]
    validate_slots(slots)
    slots[1]["slot"] = 1
    try:
        validate_slots(slots)
    except RecomputeError as exc:
        assert "slot identities must be unique" in str(exc)
    else:
        raise AssertionError("duplicate slot identities were accepted")

    slot = {"slot": 1, "run_id": "run-1", "candidate": "after", "task": "ui", "status": "submitted"}
    record = dict(slot)
    record["task"] = "chat"
    try:
        validate_slot_identity(slot, record)
    except RecomputeError as exc:
        assert "identity/status mismatch" in str(exc)
    else:
        raise AssertionError("record from another task was accepted")
