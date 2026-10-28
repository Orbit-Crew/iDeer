"""Server-leg Skill script execution behind the content-bound grant (#122).

The representative SERVER execution path: one script of one frozen published
Skill version runs through the platform's own sandbox command surface
(``Sandbox.execute_command``) — the same isolation every server-orchestrated
execution uses, never a bare subprocess on the host. Before a single byte
runs, the gate re-derives every fact from the frozen bytes:

1. the version directory must still hash to its published content hash
   (a tampered/corrupted package refuses as ``SKILL_PACKAGE_CORRUPTED``);
2. the version must declare an execution environment
   (``SKILL_ENVIRONMENT_UNDECLARED`` otherwise) — the declaration is never
   inferred from a legacy location (AC1);
3. the declared target must be this leg's target — a ``user_device`` Skill
   refuses Server execution and never downgrades (``SKILL_ENVIRONMENT_MISMATCH``);
4. the script must be a ``scripts/`` member of the frozen version;
5. the caller's own content-bound grant must match the exact script bytes and
   the declared requirements fingerprint (AC2/AC3: directory grants, sharing,
   and built-in identity do not exempt this approval).

The receipt binds the skill version, the package digest, the script digest,
and the authorization basis that approved it (AC3).
"""

from __future__ import annotations

import hashlib
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agentplatform.resources import skill_environment
from app.agentplatform.resources.skill_environment import (
    APPROVAL_REQUIRED,
    AUTHORIZATION_REVOKED,
    REAUTHORIZATION_REQUIRED,
    evaluate_grant,
    script_sha256,
)

MAX_STDOUT_CHARS = 20_000
DEFAULT_TIMEOUT_SECONDS = 120.0

#: Refusal categories; the API surface translates them one-to-one.
PACKAGE_CORRUPTED = "SKILL_PACKAGE_CORRUPTED"
ENVIRONMENT_UNDECLARED = "SKILL_ENVIRONMENT_UNDECLARED"
ENVIRONMENT_MISMATCH = "SKILL_ENVIRONMENT_MISMATCH"
SCRIPT_NOT_FOUND = "SKILL_SCRIPT_NOT_FOUND"
EXECUTION_FAILED = "SKILL_SCRIPT_EXECUTION_FAILED"


class SkillScriptRefusal(RuntimeError):
    """One fixed-category refusal to execute; never carries local paths."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


def _truncate(output: str) -> str:
    return output if len(output) <= MAX_STDOUT_CHARS else output[:MAX_STDOUT_CHARS]


def execute_server_skill_script(
    storage,
    sandbox,
    grant,
    *,
    version_dir: Path,
    script_path: str,
    skill_resource_id: str,
    slug: str,
    skill_version: int,
    expected_content_hash: str,
    execution_target: str = "server",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Gate and run one frozen Skill script; returns the bound receipt.

    ``grant`` is the caller's stored authorization row (or ``None``);
    ``sandbox`` exposes the platform's ``execute_command``. Every refusal
    raises :class:`SkillScriptRefusal` with a fixed category before any
    effect.
    """
    try:
        inspected = storage.inspect_directory("skill", version_dir)
    except (OSError, ValueError) as exc:
        raise SkillScriptRefusal(PACKAGE_CORRUPTED) from exc
    if inspected.content_hash != expected_content_hash:
        raise SkillScriptRefusal(PACKAGE_CORRUPTED)

    try:
        declaration = skill_environment.declaration_from_directory(version_dir)
    except skill_environment.SkillEnvironmentError as exc:
        raise SkillScriptRefusal(ENVIRONMENT_UNDECLARED) from exc
    if declaration is None:
        raise SkillScriptRefusal(ENVIRONMENT_UNDECLARED)
    if declaration["target"] != execution_target:
        raise SkillScriptRefusal(ENVIRONMENT_MISMATCH)
    requirements_hash = skill_environment.requirements_fingerprint(declaration)

    try:
        relative = skill_environment.normalize_script_path(script_path)
    except skill_environment.SkillEnvironmentError as exc:
        raise SkillScriptRefusal(SCRIPT_NOT_FOUND) from exc
    script_file = version_dir / relative
    try:
        if not script_file.is_file() or script_file.is_symlink():
            raise SkillScriptRefusal(SCRIPT_NOT_FOUND)
        data = script_file.read_bytes()
    except OSError as exc:
        raise SkillScriptRefusal(SCRIPT_NOT_FOUND) from exc
    digest = script_sha256(data)

    decision = evaluate_grant(grant, script_digest=digest, requirements_hash=requirements_hash)
    if decision == APPROVAL_REQUIRED:
        raise SkillScriptRefusal(APPROVAL_REQUIRED)
    if decision == REAUTHORIZATION_REQUIRED:
        raise SkillScriptRefusal(REAUTHORIZATION_REQUIRED)
    if decision == AUTHORIZATION_REVOKED:
        raise SkillScriptRefusal(AUTHORIZATION_REVOKED)
    basis = f"skill_script_authorization:{grant['authorization_id']}"

    command = f"python3 {shlex.quote(str(script_file))}"
    try:
        output = sandbox.execute_command(command, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - the sandbox failure category is fixed
        raise SkillScriptRefusal("SKILL_SCRIPT_EXECUTION_FAILED") from exc

    executed_at = datetime.now(UTC).isoformat()
    return {
        "skill_resource_id": skill_resource_id,
        "slug": slug,
        "skill_version": int(skill_version),
        "package_hash": inspected.content_hash,
        "script_path": relative,
        "script_sha256": digest,
        "requirements_hash": requirements_hash,
        "execution_target": execution_target,
        "authorization_basis": basis,
        "status": "completed",
        "command": command,
        "stdout": _truncate(str(output)),
        "stdout_sha256": hashlib.sha256(str(output).encode()).hexdigest(),
        "executed_at": executed_at,
    }
