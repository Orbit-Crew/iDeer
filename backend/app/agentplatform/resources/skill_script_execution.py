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
   and built-in identity do not exempt this approval);
6. the declared environment must be satisfiable in this sandbox: the OS, the
   interpreter, every parseable dependency, and every named tool are verified
   by one read-only probe — only after the grant matched, so an unauthorized
   caller never touches the sandbox — and anything the sandbox cannot confirm
   refuses as ``SKILL_ENVIRONMENT_UNAVAILABLE`` with zero script executions
   (#122 AC1, #170: a missing dependency is an explicit unavailability, never
   a silent downgrade).

The receipt binds the skill version, the package digest, the script digest,
and the authorization basis that approved it (AC3).
"""

from __future__ import annotations

import hashlib
import json
import re
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
PROBE_TIMEOUT_SECONDS = 30.0

#: Refusal categories; the API surface translates them one-to-one.
PACKAGE_CORRUPTED = "SKILL_PACKAGE_CORRUPTED"
ENVIRONMENT_UNDECLARED = "SKILL_ENVIRONMENT_UNDECLARED"
ENVIRONMENT_MISMATCH = "SKILL_ENVIRONMENT_MISMATCH"
ENVIRONMENT_UNAVAILABLE = "SKILL_ENVIRONMENT_UNAVAILABLE"
SCRIPT_NOT_FOUND = "SKILL_SCRIPT_NOT_FOUND"
EXECUTION_FAILED = "SKILL_SCRIPT_EXECUTION_FAILED"


class SkillScriptRefusal(RuntimeError):
    """One fixed-category refusal to execute; never carries local paths."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


def _truncate(output: str) -> str:
    return output if len(output) <= MAX_STDOUT_CHARS else output[:MAX_STDOUT_CHARS]


#: The requirement grammar the environment verification supports. It is
#: mirrored verbatim by the device runtime (frozen cross-repo contract): an
#: entry outside the grammar is a condition this leg cannot confirm and
#: refuses as unavailable — never a silent ignore (#170).
_REQUIREMENT_SPEC = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)"
    r"((?:\s*,)?\s*(?:>=|<=|==|!=|>|<|~=)\s*[0-9]+(?:\.[0-9]+)*)*$"
)
_INTERPRETER_NAME = re.compile(r"^python(?:3(?:\.\d+)?)?$", re.IGNORECASE)
_CONSTRAINT = re.compile(r"(>=|<=|==|!=|>|<|~=)\s*([0-9]+(?:\.[0-9]+)*)")
_BARE_COMMAND = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")

#: The one read-only probe the sandbox answers before any script runs: the
#: platform OS, the interpreter version, and the availability of every named
#: module and tool. Names travel as argv tokens, never as code.
_PROBE_CODE = "\n".join([
    "import json, platform, shutil, sys",
    "from importlib import metadata",
    "modules, binaries = {}, {}",
    "for token in sys.argv[1:]:",
    "    kind, _, name = token.partition(':')",
    "    if kind == 'module':",
    "        try:",
    "            modules[name] = metadata.version(name)",
    "        except Exception:",
    "            modules[name] = None",
    "    elif kind == 'binary':",
    "        binaries[name] = shutil.which(name) is not None",
    "print(json.dumps({'os': platform.system().lower(), 'python': list(sys.version_info[:3]),",
    "                  'modules': modules, 'binaries': binaries}))",
])


def _parse_requirement(entry: str) -> tuple[str, str] | None:
    """``name`` plus optional version constraints, or ``None`` when unsupported."""
    match = _REQUIREMENT_SPEC.match(entry.strip())
    if match is None:
        return None
    return match.group(1), match.group(2) or ""


def _constraints_satisfied(actual: tuple[int, ...], constraints: str) -> bool:
    for match in _CONSTRAINT.finditer(constraints):
        operator, raw = match.group(1), tuple(int(part) for part in match.group(2).split("."))
        target = raw + (0,) * max(0, len(actual) - len(raw))
        prefix = actual[:len(raw)]
        if operator == ">=" and not actual >= target:
            return False
        if operator == "<=" and not actual <= target:
            return False
        if operator == "==" and prefix != raw:
            return False
        if operator == "!=" and prefix == raw:
            return False
        if operator == ">" and not actual > target:
            return False
        if operator == "<" and not actual < target:
            return False
        if operator == "~=" and not (actual >= target and prefix == raw[:len(prefix)]):
            return False
    return True


def _probe_environment(sandbox, declaration: dict, timeout: float) -> dict[str, Any]:
    """Answer the declared facts with one sandbox round trip; any failure is
    an unconfirmable environment, never a downgrade (#170)."""
    module_names: list[str] = []
    binary_names: list[str] = []
    for entry in declaration.get("dependencies", []):
        parsed = _parse_requirement(str(entry))
        if parsed is None or _INTERPRETER_NAME.match(parsed[0]):
            continue  # answered by the probe's own interpreter fact
        module_names.append(parsed[0])
    for field in ("software", "tools"):
        for entry in declaration.get(field, []):
            name = str(entry).strip()
            if _BARE_COMMAND.match(name):
                binary_names.append(name)
    tokens = [f"module:{name}" for name in module_names] + [f"binary:{name}" for name in binary_names]
    command = "python3 -c " + shlex.quote(_PROBE_CODE)
    if tokens:
        command += " " + " ".join(shlex.quote(token) for token in tokens)
    try:
        raw = sandbox.execute_command(command, timeout=min(timeout or DEFAULT_TIMEOUT_SECONDS, PROBE_TIMEOUT_SECONDS))
        probe = json.loads(str(raw))
    except Exception:  # noqa: BLE001 - an unreadable probe refuses, never guesses
        raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE) from None
    if not isinstance(probe, dict) or not isinstance(probe.get("os"), str) \
            or not isinstance(probe.get("python"), list) \
            or not isinstance(probe.get("modules"), dict) or not isinstance(probe.get("binaries"), dict):
        raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE)
    return probe


def verify_declared_environment(declaration: dict, probe: dict[str, Any]) -> None:
    """Refuse every declared condition this sandbox cannot confirm (AC1).

    ``data`` requirements have no provisioning contract yet, so a declared
    data need is an explicit unavailability rather than an ignored claim.
    """
    if declaration.get("os") and not skill_environment.os_matches(declaration["os"], str(probe.get("os", ""))):
        raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE)
    try:
        interpreter = tuple(int(part) for part in list(probe.get("python", []))[:3])
    except (TypeError, ValueError):
        raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE) from None
    if len(interpreter) < 2:
        raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE)
    modules, binaries = probe.get("modules"), probe.get("binaries")
    for entry in declaration.get("dependencies", []):
        parsed = _parse_requirement(str(entry))
        if parsed is None:
            raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE)
        name, constraints = parsed
        if _INTERPRETER_NAME.match(name):
            actual = interpreter
        else:
            installed = modules.get(name)
            if not isinstance(installed, str):
                raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE)
            try:
                actual = tuple(int(part) for part in installed.split(".")[:3])
            except ValueError:
                raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE) from None
        if not _constraints_satisfied(actual, constraints):
            raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE)
    for field in ("software", "tools"):
        for entry in declaration.get(field, []):
            name = str(entry).strip()
            if not _BARE_COMMAND.match(name) or binaries.get(name) is not True:
                raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE)
    if declaration.get("data"):
        raise SkillScriptRefusal(ENVIRONMENT_UNAVAILABLE)


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

    # The environment probe only ever runs for an authorized caller, after
    # the exact content/scope binding matched (#170): a refusal here leaves
    # the script execution count at zero.
    if any(declaration.get(field) for field in skill_environment.DECLARATION_FIELDS):
        verify_declared_environment(declaration, _probe_environment(sandbox, declaration, timeout))

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
