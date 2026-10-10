import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REPORT = ROOT / "scripts" / "report_disclosure_costs.py"
COLLECTOR = ROOT / "scripts" / "disclosure_reading_collector.py"


def manifest_sha(tmp_path, candidate):
    target = tmp_path / "manifest.json"
    result = subprocess.run([sys.executable, str(COLLECTOR), "manifest", "--root", str(candidate), "--out", str(target)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(target.read_text(encoding="utf-8"))["manifest_sha256"]


def invoke(tmp_path, payload):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "attempts.json"
    output = tmp_path / "costs.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run([sys.executable, str(REPORT), "--records", str(source), "--out", str(output)], text=True, capture_output=True, check=False)
    return result, output


def test_cost_report_separates_roles_attempts_and_missing_submission_time(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AGENTS.md").write_text("# Root\nGuide.\n", encoding="utf-8")
    (candidate / "docs.md").write_text("# Current\n\n可见。\n\n## History\nOld.\n", encoding="utf-8")
    (candidate / "source.py").write_text('print("x")\n', encoding="utf-8")
    (candidate / "misc.txt").write_text("unknown role\n", encoding="utf-8")
    expected_sha = manifest_sha(tmp_path, candidate)
    payload = {
        "role_map": {
            "format": 1,
            "candidates": {"after": expected_sha},
            "paths": {
                "AGENTS.md": "root_guidance",
                "docs.md": "current_documentation",
                "source.py": "source_test_config",
            },
            "sections": [
                {"path": "docs.md", "heading_path": ["Current"], "role": "current_documentation"},
                {"path": "docs.md", "heading_path": ["Current", "History"], "role": "historical_material"},
            ],
        },
        "attempts": [
            {
                "run_id": "first",
                "candidate": "after",
                "task": "history",
                "status": "failed",
                "failure_class": "infrastructure",
                "manifest_sha256": expected_sha,
                "task_sha256": "t" * 64,
                "model_config": "gpt-6.1-sol; reasoning=medium",
                "tool_config_sha256": "c" * 64,
                "attempt_no": 1,
                "retry_run_id": "retry",
                "candidate_root": str(candidate),
                "started_monotonic": 10.0,
                "closed_monotonic": 13.5,
                "events": [
                    {"kind": "read", "ranges": [{"path": "AGENTS.md", "start": 1, "end": 2}], "content_bytes": len(b"# Root\nGuide.\n")},
                    {"kind": "read", "ranges": [{"path": "docs.md", "start": 1, "end": 3}], "content_bytes": len("# Current\n\n可见。\n".encode())},
                    {"kind": "read", "ranges": [{"path": "docs.md", "start": 3, "end": 5}], "content_bytes": len("可见。\n\n## History\n".encode())},
                    {"kind": "read", "ranges": [{"path": "source.py", "start": 1, "end": 1}], "content_bytes": len(b'print("x")\n')},
                    {"kind": "read", "ranges": [{"path": "misc.txt", "start": 1, "end": 1}], "content_bytes": len(b"unknown role\n")},
                ],
            },
            {
                "run_id": "retry",
                "retry_of": "first",
                "retry_reason": "collector transport interruption",
                "candidate": "after",
                "task": "history",
                "status": "submitted",
                "manifest_sha256": expected_sha,
                "task_sha256": "t" * 64,
                "model_config": "gpt-6.1-sol; reasoning=medium",
                "tool_config_sha256": "c" * 64,
                "attempt_no": 2,
                "candidate_root": str(candidate),
                "started_monotonic": 20.0,
                "submitted_monotonic": 22.0,
                "elapsed_seconds": 2.0,
                "events": [{"kind": "read", "ranges": [{"path": "docs.md", "start": 5, "end": 6}], "content_bytes": len(b"## History\nOld.\n")}],
            },
            {
                "run_id": "early-failure",
                "candidate": "after",
                "task": "ui",
                "status": "failed",
                "manifest_sha256": expected_sha,
                "candidate_root": str(candidate),
                "events": [],
            },
        ],
    }
    result, output = invoke(tmp_path, payload)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["all_physical_attempts"]["count"] == 3
    assert report["final_logical_attempts"]["count"] == 2
    first, retry, early = report["attempts"]
    assert first["submission_elapsed_seconds"] is None
    assert first["failure_close_seconds"] == 3.5
    assert first["unique_bytes_read"] < first["content_bytes_returned"]
    assert first["categories"]["root_guidance"] == len(b"# Root\nGuide.\n")
    assert first["categories"]["current_documentation"] > 0
    assert first["categories"]["historical_material"] > 0
    assert first["categories"]["source_test_config"] == len(b'print("x")\n')
    assert first["categories"]["other"] == len(b"unknown role\n")
    assert report["unknown_role_paths"] == ["misc.txt"]
    assert first["repeated_return_bytes"] > 0
    assert retry["submission_elapsed_seconds"] == 2.0
    assert retry["failure_close_seconds"] is None
    assert early["failure_close_seconds"] is None

    payload["role_map"]["sections"].reverse()
    reversed_result, reversed_output = invoke(tmp_path / "reversed", payload)
    assert reversed_result.returncode == 0, reversed_result.stderr
    reversed_report = json.loads(reversed_output.read_text(encoding="utf-8"))
    assert reversed_report["attempts"][0]["categories"] == first["categories"]

    drifted_retry = json.loads(json.dumps(payload))
    drifted_retry["attempts"][1]["model_config"] = "gpt-other; reasoning=low"
    drift_result, _ = invoke(tmp_path / "retry-drift", drifted_retry)
    assert drift_result.returncode == 2
    assert "retry identity mismatch" in drift_result.stderr.lower()

    quota_retry = json.loads(json.dumps(payload))
    quota_retry["attempts"][0]["failure_class"] = "quota_exhausted"
    quota_result, _ = invoke(tmp_path / "quota-retry", quota_retry)
    assert quota_result.returncode == 2
    assert "not eligible" in quota_result.stderr.lower()


def test_cost_report_fails_closed_on_candidate_digest_drift(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
    expected_sha = manifest_sha(tmp_path, candidate)
    (candidate / "AGENTS.md").write_text("# Changed\n", encoding="utf-8")
    payload = {
        "role_map": {"format": 1, "candidates": {"after": expected_sha}, "paths": {}, "sections": []},
        "attempts": [{"run_id": "drift", "candidate": "after", "task": "history", "status": "failed", "manifest_sha256": expected_sha, "candidate_root": str(candidate), "events": []}],
    }
    result, _ = invoke(tmp_path, payload)
    assert result.returncode == 2
    assert "snapshot drift" in result.stderr.lower()


def test_cost_report_rejects_malformed_event_ranges_without_traceback(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
    expected_sha = manifest_sha(tmp_path, candidate)
    payload = {
        "role_map": {"format": 1, "candidates": {"after": expected_sha}, "paths": {}, "sections": []},
        "attempts": [
            {
                "run_id": "malformed",
                "candidate": "after",
                "task": "history",
                "status": "failed",
                "manifest_sha256": expected_sha,
                "candidate_root": str(candidate),
                "events": [{"content_bytes": 1, "ranges": ["not-an-object"]}],
            }
        ],
    }

    result, _ = invoke(tmp_path, payload)
    assert result.returncode == 2
    assert "invalid event range" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()


def test_cost_report_rejects_missing_section_role_without_traceback(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
    (candidate / "guide.md").write_text("# Current\nBody.\n", encoding="utf-8")
    expected_sha = manifest_sha(tmp_path, candidate)
    payload = {
        "role_map": {
            "format": 1,
            "candidates": {"after": expected_sha},
            "paths": {},
            "sections": [{"path": "guide.md", "heading_path": ["Missing"], "role": "route"}],
        },
        "attempts": [
            {
                "run_id": "missing-section",
                "candidate": "after",
                "task": "history",
                "status": "failed",
                "manifest_sha256": expected_sha,
                "candidate_root": str(candidate),
                "events": [],
            }
        ],
    }
    result, _ = invoke(tmp_path, payload)
    assert result.returncode == 2
    assert "heading path not found" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()


def test_cost_report_rejects_section_roles_outside_candidate_root(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    expected_sha = manifest_sha(tmp_path, candidate)
    payload = {
        "role_map": {
            "format": 1,
            "candidates": {"after": expected_sha},
            "paths": {},
            "sections": [{"path": "../outside.md", "heading_path": ["Outside"], "role": "route"}],
        },
        "attempts": [
            {
                "run_id": "outside-section",
                "candidate": "after",
                "task": "history",
                "status": "failed",
                "manifest_sha256": expected_sha,
                "candidate_root": str(candidate),
                "events": [],
            }
        ],
    }
    result, _ = invoke(tmp_path, payload)
    assert result.returncode == 2
    assert "invalid section source" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()


def test_cost_report_rejects_unrepresentable_numeric_cost_without_traceback(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
    expected_sha = manifest_sha(tmp_path, candidate)
    payload = {
        "role_map": {"format": 1, "candidates": {"after": expected_sha}, "paths": {}, "sections": []},
        "attempts": [
            {
                "run_id": "huge-cost",
                "candidate": "after",
                "task": "history",
                "status": "failed",
                "manifest_sha256": expected_sha,
                "candidate_root": str(candidate),
                "events": [{"content_bytes": 10**400, "ranges": []}],
            }
        ],
    }
    result, _ = invoke(tmp_path, payload)
    assert result.returncode == 2
    assert "finite and non-negative" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()


def test_cost_report_closes_on_candidate_symlink_escape_without_traceback(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    (candidate / "outside.md").symlink_to(outside)
    payload = {
        "role_map": {"format": 1, "candidates": {"after": "a" * 64}, "paths": {}, "sections": []},
        "attempts": [
            {
                "run_id": "symlink-escape",
                "candidate": "after",
                "task": "history",
                "status": "failed",
                "manifest_sha256": "a" * 64,
                "candidate_root": str(candidate),
                "events": [],
            }
        ],
    }
    result, _ = invoke(tmp_path, payload)
    assert result.returncode == 2
    assert "symlink outside" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()


def test_cost_report_rejects_missing_attempt_linked_by_parent(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
    expected_sha = manifest_sha(tmp_path, candidate)
    payload = {
        "role_map": {"format": 1, "candidates": {"after": expected_sha}, "paths": {}, "sections": []},
        "attempts": [
            {
                "run_id": "parent",
                "candidate": "after",
                "task": "history",
                "status": "failed",
                "failure_class": "infrastructure",
                "retry_run_id": "missing-child",
                "manifest_sha256": expected_sha,
                "candidate_root": str(candidate),
                "events": [],
            }
        ],
    }
    result, _ = invoke(tmp_path, payload)
    assert result.returncode == 2
    assert "retry child" in result.stderr.lower()
