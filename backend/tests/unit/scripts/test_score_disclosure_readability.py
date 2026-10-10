"""Public CLI regression tests for the disclosure scoring contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "score_disclosure_readability.py"
TASKS = ("ui", "chat", "knowledge", "permissions", "tests", "runtime", "upstream", "history")


ANCHORS = {
    "ui": ["UI-01", "UI-02", "UI-03", "UI-04", "UI-05"],
    "chat": ["CHAT-01", "CHAT-02", "CHAT-03", "CHAT-04", "CHAT-05", "CHAT-06"],
    "knowledge": ["KB-01", "KB-02", "KB-03", "KB-04", "KB-05", "KB-06"],
    "permissions": ["PERM-01", "PERM-02", "PERM-03", "PERM-04", "PERM-05", "PERM-06"],
    "tests": ["TEST-01", "TEST-02", "TEST-03", "TEST-04", "TEST-05", "TEST-06", "TEST-07", "TEST-08", "TEST-09"],
    "runtime": ["RUN-01", "RUN-02", "RUN-03", "RUN-04", "RUN-05", "RUN-06", "RUN-07"],
    "upstream": ["UP-01", "UP-02", "UP-03", "UP-04", "UP-05", "UP-06", "UP-07"],
    "history": ["HIST-01", "HIST-02", "HIST-03", "HIST-04", "HIST-05", "HIST-06"],
}
CONDITIONALS = {
    "CHAT-04",
    "PERM-03",
    "PERM-04",
    "RUN-03",
    "TEST-02",
    "TEST-07",
    "TEST-08",
    "TEST-09",
}


def _grade(reviewer: str, task: str) -> dict:
    return {
        "reviewer": reviewer,
        "anchors": [
            {
                "id": anchor,
                "decision": "not_applicable" if anchor in CONDITIONALS else "met",
                "evidence": {
                    "answer": "answer entry",
                    "candidate": f"candidate evidence for {anchor}",
                },
                **({"triggered": False} if anchor in CONDITIONALS else {}),
            }
            for anchor in ANCHORS[task]
        ],
    }


def _records() -> list[dict]:
    records = []
    for task in TASKS:
        for candidate in ("baseline", "after"):
            for run in (1, 2):
                records.append(
                    {
                        "run_id": f"{candidate}-{task}-{run}",
                        "candidate": candidate,
                        "task": task,
                        "status": "submitted",
                        "elapsed_seconds": 100,
                        "unique_bytes_read": 100 if candidate == "baseline" else 70,
                        "answer": {field: f"answer {field}" for field in ("entry", "constraints", "authorities", "relevant_decisions", "validation", "unknowns")},
                        "reviews": [_grade("reviewer-a", task), _grade("reviewer-b", task)],
                    }
                )
    return records


def _invoke(tmp_path: Path, payload: dict, *, single_record: bool = False) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "records.json"
    output = tmp_path / "report.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--records", str(source), "--out", str(output), *(["--single-record"] if single_record else [])],
        capture_output=True,
        text=True,
        check=False,
    )


def _runtime_demo_record() -> dict:
    answer = {
        "entry": "Inspect runtime manager for cancellation behavior.",
        "constraints": "Prefer Extension and preserve runtime contracts.",
        "authorities": "Root runtime guidance applies.",
        "relevant_decisions": "Use applicable lifecycle decisions.",
        "validation": "Run focused checks and both compatibility modes.",
        "unknowns": "Inspect current tests for the precise transition.",
    }
    anchors = ["RUN-01", "RUN-02", "RUN-03", "RUN-04", "RUN-05", "RUN-06", "RUN-07"]

    def review(reviewer: str) -> dict:
        return {
            "reviewer": reviewer,
            "anchors": [
                {
                    "id": anchor,
                    "decision": "not_applicable" if anchor == "RUN-03" else "met",
                    **({"triggered": False} if anchor == "RUN-03" else {}),
                    "evidence": {
                        "answer": "preserve runtime contracts" if anchor == "RUN-02" else "Inspect runtime manager",
                        "candidate": f"Evidence for {anchor} in candidate guidance.",
                    },
                }
                for anchor in anchors
            ],
        }

    return {
        "run_id": "cal-runtime-demo",
        "candidate": "after",
        "task": "runtime",
        "status": "submitted",
        "elapsed_seconds": 120,
        "unique_bytes_read": 1000,
        "answer": answer,
        "reviews": [review("grader-a"), review("grader-b")],
    }


def test_cli_rejects_summary_that_disagrees_with_item_records(tmp_path: Path) -> None:
    payload = {"records": _records(), "summary": {"accepted": True, "after_correct": 15}}

    result = _invoke(tmp_path, payload)

    assert result.returncode == 2
    assert "summary" in result.stderr.lower()
    assert "disagree" in result.stderr.lower()


def test_cli_single_record_report_derives_item_result_and_is_non_formal(tmp_path: Path) -> None:
    record = _runtime_demo_record()
    record["raw_grader_summary"] = {"reviewer": "grader-b", "correct": False}

    result = _invoke(tmp_path, {"records": [record]}, single_record=True)

    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "single_record_calibration"
    assert report["formal_acceptance"] is None
    assert report["record"]["correct"] is True
    assert report["record"]["critical_errors"] == 0


def test_cli_single_record_rejects_inconsistent_supplied_summary(tmp_path: Path) -> None:
    record = _runtime_demo_record()
    result = _invoke(tmp_path, {"records": [record], "summary": {"correct": False}}, single_record=True)

    assert result.returncode == 2
    assert "summary" in result.stderr.lower()


def test_cli_uses_rubric_severity_for_runtime_and_upstream_anchors(tmp_path: Path) -> None:
    records = _records()
    for task, anchor_id in (("runtime", "RUN-05"), ("upstream", "UP-04")):
        sample = next(row for row in records if row["run_id"] == f"after-{task}-1")
        for review in sample["reviews"]:
            anchor = next(item for item in review["anchors"] if item["id"] == anchor_id)
            anchor.update(
                decision="missed",
                evidence={
                    "answer": sample["answer"]["entry"],
                    "candidate": f"Candidate evidence for {anchor_id}.",
                },
            )

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    for task, anchor_id in (("runtime", "RUN-05"), ("upstream", "UP-04")):
        scored = next(row for row in report["records"] if row["run_id"] == f"after-{task}-1")
        assert scored["correct"] is False
        assert scored["missed_anchors"] == 1
        assert scored["critical_errors"] == 0, anchor_id


def test_cli_rejects_answer_evidence_not_quoted_from_the_submitted_answer(tmp_path: Path) -> None:
    records = _records()
    review = next(row for row in records if row["run_id"] == "after-ui-1")["reviews"][0]
    review["anchors"][0]["evidence"]["answer"] = "invented excerpt outside the answer"

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 2
    assert "answer evidence" in result.stderr.lower()
    assert "not found" in result.stderr.lower()


def test_cli_uses_exact_thirty_percent_and_three_hundred_second_boundaries(tmp_path: Path) -> None:
    records = _records()
    for record in records:
        if record["task"] in {"ui", "chat", "knowledge", "permissions", "tests"}:
            record["elapsed_seconds"] = 290 + 20 * (record["run_id"].endswith("-2"))
            if record["candidate"] == "baseline":
                record["unique_bytes_read"] = 90 + 20 * record["run_id"].endswith("-2")
            else:
                record["unique_bytes_read"] = 63 + 14 * record["run_id"].endswith("-2")
        elif record["candidate"] == "after":
            record["unique_bytes_read"] = 900_000

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["accepted"] is True
    assert report["after_denominator"] == 16
    assert report["routine_median_seconds_after"] == 300
    assert report["routine_median_unique_bytes_baseline"] == 100
    assert report["routine_median_unique_bytes_after"] == 70
    assert report["routine_unique_byte_reduction"] == 0.3


def test_cli_rejects_missing_formal_sample_instead_of_changing_denominator(tmp_path: Path) -> None:
    records = _records()
    records = [row for row in records if row["run_id"] != "after-history-2"]

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 2
    assert "16 after denominator" in result.stderr


def test_cli_keeps_timeout_in_after_denominator_and_fails_acceptance(tmp_path: Path) -> None:
    records = _records()
    failed = next(row for row in records if row["run_id"] == "after-chat-1")
    failed.update(status="timeout", elapsed_seconds=301, unique_bytes_read=1_000_000, reviews=[])

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["accepted"] is False
    assert report["after_denominator"] == 16
    assert report["after_correct"] == 15
    scored_sample = next(row for row in report["records"] if row["run_id"] == "after-chat-1")
    assert scored_sample["status"] == "timeout"
    assert report["per_task"]["chat"]["after_median_unique_bytes"] == 500_035
    assert report["per_task"]["chat"]["after_median_seconds"] == 200.5


def test_cli_keeps_interrupted_after_sample_in_denominator(tmp_path: Path) -> None:
    records = _records()
    failed = next(row for row in records if row["run_id"] == "after-history-2")
    failed.update(status="interrupted", reviews=[])

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["after_denominator"] == 16
    assert report["after_correct"] == 15
    assert report["records"][-1]["status"] == "interrupted"


def test_cli_reports_even_median_for_combined_routine_tasks(tmp_path: Path) -> None:
    records = _records()
    values = iter((10, 20, 30, 40, 50, 60, 70, 80, 90, 100))
    for record in records:
        if record["candidate"] == "after" and record["task"] in {"ui", "chat", "knowledge", "permissions", "tests"}:
            record["unique_bytes_read"] = next(values)

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["routine_median_unique_bytes_after"] == 55


def test_cli_requires_third_party_adjudication_for_anchor_disagreement(tmp_path: Path) -> None:
    records = _records()
    sample = next(row for row in records if row["run_id"] == "after-ui-1")
    sample["reviews"][1]["anchors"][0]["decision"] = "missed"

    unresolved_result = _invoke(tmp_path, {"records": records})
    assert unresolved_result.returncode == 0, unresolved_result.stderr
    unresolved = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert unresolved["accepted"] is False
    assert unresolved["unresolved_disagreements"] == 1

    sample["adjudication"] = _grade("reviewer-c", "ui") | {"rationale": "The applicable UI route is present in the candidate and the answer names it."}
    resolved_result = _invoke(tmp_path, {"records": records})
    assert resolved_result.returncode == 0, resolved_result.stderr
    resolved = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert resolved["unresolved_disagreements"] == 0
    resolved_sample = next(row for row in resolved["records"] if row["run_id"] == "after-ui-1")
    assert resolved_sample["correct"] is True


def test_cli_rejects_adjudication_when_independent_anchor_reviews_agree(tmp_path: Path) -> None:
    records = _records()
    sample = next(row for row in records if row["run_id"] == "after-ui-1")
    overriding = _grade("reviewer-c", "ui") | {"rationale": "An adjudicator cannot override unanimous anchor judgments."}
    for anchor in overriding["anchors"]:
        anchor["decision"] = "missed"
    sample["adjudication"] = overriding

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 2
    assert "no anchor disagreement" in result.stderr.lower()


def test_cli_requires_conditional_anchor_when_its_trigger_is_true(tmp_path: Path) -> None:
    records = _records()
    sample = next(row for row in records if row["run_id"] == "after-chat-1")
    sample["answer"]["constraints"] = "The proposed change modifies stream delivery."
    for review in sample["reviews"]:
        anchor = next(item for item in review["anchors"] if item["id"] == "CHAT-04")
        anchor.update(
            decision="missed",
            triggered=True,
            evidence={"answer": "The proposed change modifies stream delivery", "candidate": "the prompt says streaming event delivery changes"},
        )

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["incorrect_after"] == 1
    scored_sample = next(row for row in report["records"] if row["run_id"] == "after-chat-1")
    assert scored_sample["correct"] is False


def test_cli_treats_untriggered_domain_conditions_as_not_applicable(tmp_path: Path) -> None:
    result = _invoke(tmp_path, {"records": _records()})

    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["accepted"] is True


def test_cli_does_not_infer_historical_misuse_from_an_omitted_history_anchor(tmp_path: Path) -> None:
    records = _records()
    sample = next(row for row in records if row["run_id"] == "after-history-1")
    for review in sample["reviews"]:
        review["anchors"][0]["decision"] = "missed"

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    scored_sample = next(row for row in report["records"] if row["run_id"] == "after-history-1")
    assert scored_sample["correct"] is False
    assert scored_sample["historical_authority_misuse"] == 0


def test_cli_counts_explicit_historical_misuse_separately_in_any_task(tmp_path: Path) -> None:
    records = _records()
    sample = next(row for row in records if row["run_id"] == "after-ui-1")
    sample["answer"]["constraints"] = "The answer treats an archived report as current validation."
    for review in sample["reviews"]:
        review["historical_authority_misuse"] = True
        review["historical_misuse_evidence"] = {
            "answer": "The answer treats an archived report as current validation.",
            "candidate": "the candidate labels that report historical",
        }

    result = _invoke(tmp_path, {"records": records})

    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["historical_authority_misuse_after"] == 1
    assert report["accepted"] is False
