import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REPORT = ROOT / "scripts" / "report_disclosure_costs.py"


def invoke(tmp_path, payload):
    source = tmp_path / "attempts.json"
    output = tmp_path / "costs.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(REPORT), "--records", str(source), "--out", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    return result, output


def test_cost_report_separates_roles_attempts_and_missing_submission_time(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AGENTS.md").write_text("# Root\nGuide.\n", encoding="utf-8")
    (candidate / "docs.md").write_text("# Current\n\n可见。\n\n## History\nOld.\n", encoding="utf-8")
    expected_sha = "a" * 64
    payload = {
        "role_map": {
            "format": 1,
            "candidates": {"after": expected_sha},
            "paths": {"AGENTS.md": "root_guidance", "docs.md": "current_documentation"},
            "sections": [{"path": "docs.md", "heading_path": ["Current", "History"], "role": "historical_material"}],
        },
        "attempts": [
            {
                "run_id": "first",
                "candidate": "after",
                "task": "history",
                "status": "failed",
                "manifest_sha256": expected_sha,
                "candidate_root": str(candidate),
                "started_monotonic": 10.0,
                "closed_monotonic": 13.5,
                "events": [
                    {"kind": "read", "ranges": [{"path": "AGENTS.md", "start": 1, "end": 2}], "content_bytes": 15},
                    {"kind": "read", "ranges": [{"path": "docs.md", "start": 1, "end": 3}], "content_bytes": len("# Current\n\n可见。\n".encode())},
                    {"kind": "read", "ranges": [{"path": "docs.md", "start": 3, "end": 5}], "content_bytes": len("可见。\n\n## History\n".encode())},
                ],
            },
            {
                "run_id": "retry",
                "retry_of": "first",
                "candidate": "after",
                "task": "history",
                "status": "submitted",
                "manifest_sha256": expected_sha,
                "candidate_root": str(candidate),
                "started_monotonic": 20.0,
                "submitted_monotonic": 22.0,
                "elapsed_seconds": 2.0,
                "events": [{"kind": "read", "ranges": [{"path": "docs.md", "start": 4, "end": 5}], "content_bytes": len(b"## History\nOld.\n")}],
            },
        ],
    }

    result, output = invoke(tmp_path, payload)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["all_physical_attempts"]["count"] == 2
    assert report["final_logical_attempts"]["count"] == 1
    first, retry = report["attempts"]
    assert first["submission_elapsed_seconds"] is None
    assert first["failure_close_seconds"] == 3.5
    assert first["unique_bytes_read"] < first["content_bytes_returned"]
    assert first["categories"]["root_guidance"] == 15
    assert first["categories"]["historical_material"] > 0
    assert first["repeated_return_bytes"] > 0
    assert retry["submission_elapsed_seconds"] == 2.0
    assert retry["failure_close_seconds"] is None


def test_cost_report_fails_closed_on_candidate_digest_drift(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
    payload = {
        "role_map": {"format": 1, "candidates": {"after": "a" * 64}, "paths": {}, "sections": []},
        "attempts": [
            {
                "run_id": "drift",
                "candidate": "after",
                "task": "history",
                "status": "failed",
                "manifest_sha256": "b" * 64,
                "candidate_root": str(candidate),
                "events": [],
            }
        ],
    }
    result, _ = invoke(tmp_path, payload)
    assert result.returncode == 2
    assert "manifest" in result.stderr.lower()
