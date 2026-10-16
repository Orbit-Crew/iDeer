"""Behavioral contract for the Test Lane Shadow legacy-name aggregation jobs.

The shadow workflow preserves legacy required check names with tiny
aggregation jobs whose only input is the underlying job's result plus (for
lane-conditional ones) the lane selection. Their pass condition must
tolerate "skipped": a selected lane whose job did not run (an upstream
dependency failed) is gated by the PR Standard Gate as a missing required
result, so the legacy-name job stays green there and fails only on a real
failure or cancellation.
"""

import os
import subprocess
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[4] / ".github/workflows/test-lane-shadow.yml"

RESULT_OUTCOMES = [
    ("success", True),
    ("skipped", True),
    ("failure", False),
    ("cancelled", False),
]


def _legacy_check_steps() -> dict[str, str]:
    import yaml

    definition = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    steps: dict[str, str] = {}
    for job_name, job in definition["jobs"].items():
        for step in job.get("steps", []):
            if step.get("name") == "Preserve the legacy check name" and "run" in step:
                assert job_name not in steps, f"duplicate aggregation step in {job_name}"
                steps[job_name] = step["run"]
    return steps


def _run_step(script: str, selected: str, test_result: str) -> int:
    # GitHub Actions' default "shell: bash" is "bash --noprofile --norc
    # -eo pipefail"; reproduce the -eo flags or assertion failures inside
    # the step would not abort the script.
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        env={**os.environ, "SELECTED": selected, "TEST_RESULT": test_result},
        capture_output=True,
        text=True,
    ).returncode


def test_every_legacy_check_step_follows_the_skip_tolerant_contract():
    steps = _legacy_check_steps()
    assert set(steps) == {
        "backend-coverage",
        "backend-serial",
        "frontend-coverage",
        "lint-frontend",
        "agent-guidance",
    }


def test_legacy_check_steps_tolerate_skip_and_fail_on_real_outcomes():
    for job_name, script in _legacy_check_steps().items():
        for result, expected_pass in RESULT_OUTCOMES:
            exit_code = _run_step(script, "true", result)
            if expected_pass:
                assert exit_code == 0, f"{job_name} must pass when {result}"
            else:
                assert exit_code != 0, f"{job_name} must fail when {result}"


def test_unselected_legacy_check_steps_pass_when_not_run():
    for job_name, script in _legacy_check_steps().items():
        assert _run_step(script, "false", "skipped") == 0, f"{job_name} must pass when the lane was not selected"
