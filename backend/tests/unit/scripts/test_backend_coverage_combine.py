"""Regression contract for the scheduled backend-coverage combine step.

The ``backend-full`` and ``backend-serial`` jobs upload their coverage data
as artifacts that keep the repository-relative ``backend/`` prefix, and the
data files are named ``coverage-shard-*.dat`` / ``coverage-serial.dat``.
``coverage combine`` only auto-discovers files named ``<data_file>.*`` when
given a directory, so the combine step must consume the artifact-relative
files explicitly — a bare directory argument always ends in
"No data to combine" (observed on the scheduled lane since the evidence
artifacts were introduced, e.g. run 42360672273).
"""

from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[4]
    / ".github/workflows/backend-unit-tests.yml"
)


def _combine_steps() -> list[dict]:
    definition = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    steps = definition["jobs"]["backend-coverage"]["steps"]
    return [step for step in steps if step.get("name") == "Combine diagnostic coverage"]


def test_coverage_job_has_exactly_one_combine_step():
    assert len(_combine_steps()) == 1


def test_combine_consumes_artifact_relative_data_files():
    command = _combine_steps()[0]["run"]
    # The evidence artifacts preserve the repository layout, so the data
    # files land under ``.coverage-data/backend/`` with the shard/serial
    # names the upload paths declared.
    assert ".coverage-data/backend/coverage-" in command
    assert "coverage combine \"${data_files[@]}\"" in command
    # A bare directory argument can never match (coverage only auto-discovers
    # ``<data_file>.*`` names) and must not come back.
    assert "coverage combine .coverage-data\n" not in command


def test_combine_fails_loudly_when_no_data_files_arrived():
    command = _combine_steps()[0]["run"]
    # Empty artifact sets must abort with a diagnostic instead of silently
    # reporting zero coverage.
    assert "nullglob" in command
    assert "exit 1" in command
