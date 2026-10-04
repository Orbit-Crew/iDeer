"""Generation guards for the fault-zeroing contract artifacts (ticket 07).

The contract module (``backend/app/agentplatform/fault_zeroing/contract.py``)
is the single source of the declarative Result Contract content.
``scripts/generate_fault_zeroing_contract_artifacts.py`` derives the two
sandbox-side artifacts from it:

- ``resources/skills/fault-zeroing/scripts/validate_fault_zeroing_outputs.py``
  — the stdlib-only offline validator with the contract embedded verbatim
  (the sandbox cannot import ``app.*``, so the embedded copy stays the
  established policy, ADR-0004);
- ``resources/skills/fault-zeroing/references/result_contract.md`` — the
  sandbox-readable citation target that workflow prompts and the SKILL/SOUL
  texts reference instead of restating the lists.

These tests pin that one command reproduces the committed artifacts byte for
byte and that a malformed contract source fails loudly instead of producing a
partial copy.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
GENERATOR = REPO_ROOT / "scripts" / "generate_fault_zeroing_contract_artifacts.py"
CONTRACT = REPO_ROOT / "backend" / "app" / "agentplatform" / "fault_zeroing" / "contract.py"
PACKAGED = REPO_ROOT / "resources" / "skills" / "fault-zeroing" / "scripts" / "validate_fault_zeroing_outputs.py"
REFERENCE = REPO_ROOT / "resources" / "skills" / "fault-zeroing" / "references" / "result_contract.md"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def _generate_into(tmp_path: Path, contract: Path = CONTRACT) -> tuple[Path, Path]:
    validator = tmp_path / "validate_fault_zeroing_outputs.py"
    reference = tmp_path / "result_contract.md"
    completed = _run("--contract", str(contract), "--validator-out", str(validator), "--reference-out", str(reference))
    assert completed.returncode == 0, completed.stderr
    return validator, reference


def test_one_command_reproduces_the_committed_artifacts(tmp_path: Path) -> None:
    """Regenerating from the contract module reproduces both committed
    artifacts byte for byte — the sandbox copy and the citation target are
    generated, never hand-maintained (一次规则改动一条命令重新同步)."""

    validator, reference = _generate_into(tmp_path)

    assert validator.read_bytes() == PACKAGED.read_bytes()
    assert reference.read_bytes() == REFERENCE.read_bytes()

    # The repo-side --check agrees (no drift between contract and artifacts).
    completed = _run("--check")
    assert completed.returncode == 0, completed.stderr


def test_generated_validator_compiles_and_embeds_the_contract_verbatim(tmp_path: Path) -> None:
    """The generated sandbox copy is runnable stdlib-only Python and carries
    the contract module body verbatim."""

    validator, _ = _generate_into(tmp_path)
    source = validator.read_text(encoding="utf-8")

    # Byte-stable across runs (no timestamps, no dict-order jitter).
    validator_again, _ = _generate_into(tmp_path / "again")
    assert validator_again.read_bytes() == validator.read_bytes()

    # It compiles standalone (a mid-file ``from __future__`` would break it).
    ast.parse(source)

    for third_party in ("import yaml", "import jsonschema", "from fastapi", "from pydantic"):
        assert third_party not in source

    # The embedded block is the contract module minus its module docstring,
    # byte-identical from the first import to the last helper.
    contract_source = CONTRACT.read_text(encoding="utf-8")
    docstring = ast.get_docstring(ast.parse(contract_source), clean=False)
    assert docstring  # the source must keep its module docstring
    module_body = contract_source.split(docstring, 1)[1].split('"""', 1)[1]
    assert module_body.strip("\n") in source


def test_generated_reference_lists_the_declarative_contract_content(tmp_path: Path) -> None:
    """The citation target names every declarative family section, so prompts
    and SKILL/SOUL texts can cite it instead of restating the lists (契约唯一
    归属).  The exhaustive item-level check lives in the committed-reference
    guard (test_regression_guards.py); byte identity with the committed file is
    pinned by test_one_command_reproduces_the_committed_artifacts."""

    _, reference = _generate_into(tmp_path)
    text = reference.read_text(encoding="utf-8")

    assert "生成" in text and "唯一来源" in text and "contract.py" in text
    for family in (
        "REQUIRED_OUTPUTS",
        "REQUIRED_REPORT_SECTIONS",
        "REQUIRED_COVERAGE",
        "REQUIRED_REPORT_KEY_PHRASES",
        "REQUIRED_STAGE_MARKERS",
        "REQUIRED_RESPONSIBILITY_PHRASES",
        "FORBIDDEN_RESPONSIBILITY_CLAIMS",
        "EVIDENCE_SIDE_DISCLOSURE",
    ):
        assert family in text, f"generated reference lost the {family} family"


def test_check_mode_detects_drift(tmp_path: Path) -> None:
    validator, reference = _generate_into(tmp_path)
    reference.write_text(reference.read_text(encoding="utf-8").replace("问题概述", "问题简介"), encoding="utf-8")

    completed = _run("--check", "--contract", str(CONTRACT), "--validator-out", str(validator), "--reference-out", str(reference))
    assert completed.returncode == 1
    assert "result_contract.md" in completed.stdout + completed.stderr


def test_malformed_contract_sources_fail_loudly(tmp_path: Path) -> None:
    """A source that does not compile or lost the contract surface fails
    before anything is written — no partial sandbox copy (fail-closed)."""

    # (a) source that does not compile
    broken = tmp_path / "broken_contract.py"
    broken.write_text("def broken(:\n", encoding="utf-8")
    completed = _run("--contract", str(broken), "--validator-out", str(tmp_path / "v.py"), "--reference-out", str(tmp_path / "r.md"))
    assert completed.returncode != 0
    assert "broken_contract.py" in completed.stderr

    # (b) source that compiles but lost a required constant
    incomplete = tmp_path / "incomplete_contract.py"
    incomplete.write_text('"""Incomplete contract stub."""\nCONTRACT_VERSION = "9.9.9"\n', encoding="utf-8")
    completed = _run("--contract", str(incomplete), "--validator-out", str(tmp_path / "v2.py"), "--reference-out", str(tmp_path / "r2.md"))
    assert completed.returncode != 0
    assert "REQUIRED_OUTPUTS" in completed.stderr

    # (c) source without its module docstring — the embedded-copy header
    # discipline requires it.
    bare = tmp_path / "bare_contract.py"
    bare.write_text("REQUIRED_OUTPUTS = ('x',)\n", encoding="utf-8")
    completed = _run("--contract", str(bare), "--validator-out", str(tmp_path / "v3.py"), "--reference-out", str(tmp_path / "r3.md"))
    assert completed.returncode != 0

    # No partial artifacts are left behind.
    for missing in ("v.py", "v2.py", "v3.py", "r.md", "r2.md", "r3.md"):
        assert not (tmp_path / missing).exists(), missing


@pytest.mark.parametrize("artifact", [PACKAGED, REFERENCE])
def test_committed_artifacts_carry_the_generation_banner(artifact: Path) -> None:
    """Both committed artifacts name the generator so nobody hand-edits them."""

    text = artifact.read_text(encoding="utf-8")
    assert "generate_fault_zeroing_contract_artifacts.py" in text
