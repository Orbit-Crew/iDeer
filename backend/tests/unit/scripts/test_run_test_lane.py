import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RUNNER = ROOT / "scripts" / "run-test-lane.sh"


def _evidence_failure_python(tmp_path: Path, *, fail_lane_command: bool = False) -> Path:
    wrapper = tmp_path / "python-with-evidence-failure"
    wrapper_lines = [
        "#!/usr/bin/python3",
        "import os, sys",
        "if '--complete' in sys.argv:",
        "    print('injected evidence completion failure', file=sys.stderr)",
        "    raise SystemExit(23)",
    ]
    if fail_lane_command:
        wrapper_lines.extend(
            [
                "if any(arg.endswith('scripts/check_test_contracts.py') for arg in sys.argv):",
                "    print('injected test command failure', file=sys.stderr)",
                "    raise SystemExit(7)",
            ]
        )
    wrapper_lines.append(f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])")
    wrapper.write_text("\n".join(wrapper_lines) + "\n", encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


def _run_lane(
    tmp_path: Path,
    lane: str,
    *,
    python: Path | None = None,
    credentials: bool = True,
) -> tuple[subprocess.CompletedProcess[str], Path, str]:
    artifacts = tmp_path / "artifacts"
    summary = tmp_path / "summary.md"
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("OPENAI_BASE_URL", None)
    if credentials:
        env["OPENAI_API_KEY"] = "test-key-is-never-used"
    env.update(
        {
            "GITHUB_STEP_SUMMARY": str(summary),
            "TEST_LANE_ARTIFACT_DIR": str(artifacts),
            "TEST_LANE_SKIP_PREFLIGHT": "1",
        }
    )
    if python is not None:
        env["PYTHON"] = str(python)

    result = subprocess.run(
        ["bash", str(RUNNER), lane],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    lane_artifacts = next(artifacts.glob(f"{lane}-*"))
    lane_heading = f"## Test lane: `{lane}`"
    return result, lane_artifacts, summary.read_text(encoding="utf-8").rsplit(lane_heading, 1)[-1]


def _assert_timing_consistent(output: str, artifacts: Path, summary: str, *, evidence_complete: bool) -> None:
    duration_match = re.search(r"TEST_LANE_DURATION lane=[^ ]+ seconds=(\d+) status=\d+", output)
    metadata_match = re.search(r"^seconds=(\d+)$", (artifacts / "run.meta").read_text(), re.M)
    summary_match = re.search(r"Test execution: (\d+)s", summary)
    assert duration_match and metadata_match and summary_match
    seconds = duration_match.group(1)
    assert metadata_match.group(1) == seconds
    assert summary_match.group(1) == seconds
    if evidence_complete:
        evidence = json.loads((artifacts / "lane-evidence.json").read_text(encoding="utf-8"))
        assert evidence["duration_seconds"] == int(seconds)


def _assert_failure_tail(output: str, lane: str, lane_artifacts: Path, *, status: int) -> None:
    """Ticket 06 output contract on failure paths.

    The duration line still reports the lane's final status, and when the
    artifact directory was created the runner prints the artifact pointer
    AFTER it, so failing stdout ends with TEST_LANE_ARTIFACT, not with the
    status itself.
    """
    assert re.search(rf"^TEST_LANE_DURATION lane={lane} seconds=\d+ status={status}$", output, re.M)
    assert output.rstrip().endswith(f"TEST_LANE_ARTIFACT lane={lane} dir={lane_artifacts}")


def _assert_status_consistent(
    output: str,
    artifacts: Path,
    summary: str,
    *,
    expected_status: int,
    expected_outcome: str,
    evidence_complete: bool,
) -> None:
    duration_match = re.search(r"TEST_LANE_DURATION lane=[^ ]+ seconds=\d+ status=(\d+)", output)
    metadata_match = re.search(r"^status=(\d+)$", (artifacts / "run.meta").read_text(encoding="utf-8"), re.M)
    assert duration_match and int(duration_match.group(1)) == expected_status
    assert metadata_match and int(metadata_match.group(1)) == expected_status
    assert f"Exit status: {expected_status}" in summary
    assert f"Outcome: {expected_outcome}" in summary
    if evidence_complete:
        evidence = json.loads((artifacts / "lane-evidence.json").read_text(encoding="utf-8"))
        assert evidence["status"] == expected_status
        assert evidence["outcome"] == expected_outcome


def test_missing_stagehand_credentials_are_recorded_as_unexecuted(tmp_path: Path) -> None:
    result, artifacts, summary = _run_lane(tmp_path, "frontend-stagehand", credentials=False)

    evidence = json.loads((artifacts / "lane-evidence.json").read_text(encoding="utf-8"))
    metadata = (artifacts / "run.meta").read_text(encoding="utf-8")
    assert result.returncode == 0
    assert "status=unexecuted reason=missing_stagehand_credentials" in result.stdout
    assert "TEST_LANE_DURATION lane=frontend-stagehand seconds=" in result.stdout
    assert result.stdout.count("status=0") == 1
    assert "Outcome: unexecuted" in summary
    assert "status=0" in metadata
    assert evidence["outcome"] == "unexecuted"
    assert evidence["status"] == 0
    _assert_timing_consistent(result.stdout, artifacts, summary, evidence_complete=True)
    _assert_status_consistent(
        result.stdout,
        artifacts,
        summary,
        expected_status=0,
        expected_outcome="unexecuted",
        evidence_complete=True,
    )


def test_evidence_failure_fails_successful_lane_and_leaves_incomplete_evidence(
    tmp_path: Path,
) -> None:
    wrapper = _evidence_failure_python(tmp_path)
    result, artifacts, summary = _run_lane(tmp_path, "test-contracts", python=wrapper)

    evidence = json.loads((artifacts / "lane-evidence.json").read_text(encoding="utf-8"))
    metadata = (artifacts / "run.meta").read_text(encoding="utf-8")
    assert result.returncode == 1
    assert "TEST_LANE_EVIDENCE_ERROR lane=test-contracts status=23" in result.stdout
    _assert_failure_tail(result.stdout, "test-contracts", artifacts, status=1)
    assert "status=1" in metadata
    assert "Exit status: 1" in summary
    assert "Outcome: failed" in summary
    assert not {"finished_at", "status", "outcome", "duration_seconds"} & evidence.keys()
    _assert_timing_consistent(result.stdout, artifacts, summary, evidence_complete=False)
    _assert_status_consistent(
        result.stdout,
        artifacts,
        summary,
        expected_status=1,
        expected_outcome="failed",
        evidence_complete=False,
    )


def test_test_failure_is_preserved_when_evidence_completion_also_fails(
    tmp_path: Path,
) -> None:
    wrapper = _evidence_failure_python(tmp_path, fail_lane_command=True)
    result, artifacts, summary = _run_lane(tmp_path, "test-contracts", python=wrapper)

    evidence = json.loads((artifacts / "lane-evidence.json").read_text(encoding="utf-8"))
    metadata = (artifacts / "run.meta").read_text(encoding="utf-8")
    assert result.returncode == 7
    assert "TEST_LANE_EVIDENCE_ERROR lane=test-contracts status=23" in result.stdout
    _assert_failure_tail(result.stdout, "test-contracts", artifacts, status=7)
    assert "status=7" in metadata
    assert "Exit status: 7" in summary
    assert "Outcome: failed" in summary
    assert not {"finished_at", "status", "outcome", "duration_seconds"} & evidence.keys()
    _assert_timing_consistent(result.stdout, artifacts, summary, evidence_complete=False)
    _assert_status_consistent(
        result.stdout,
        artifacts,
        summary,
        expected_status=7,
        expected_outcome="failed",
        evidence_complete=False,
    )


def test_successful_lane_records_passed_result_consistently(tmp_path: Path) -> None:
    result, artifacts, summary = _run_lane(tmp_path, "test-contracts")

    evidence = json.loads((artifacts / "lane-evidence.json").read_text(encoding="utf-8"))
    metadata = (artifacts / "run.meta").read_text(encoding="utf-8")
    assert result.returncode == 0
    assert result.stdout.rstrip().endswith("status=0")
    assert "status=0" in metadata
    assert "Exit status: 0" in summary
    assert "Outcome: passed" in summary
    assert evidence["outcome"] == "passed"
    assert evidence["status"] == 0
    _assert_timing_consistent(result.stdout, artifacts, summary, evidence_complete=True)
    _assert_status_consistent(
        result.stdout,
        artifacts,
        summary,
        expected_status=0,
        expected_outcome="passed",
        evidence_complete=True,
    )
