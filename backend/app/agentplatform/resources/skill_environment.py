"""Per-Skill execution environment declaration (#122).

AC1: every Skill that ships executable scripts declares the environment it
needs — data, OS, dependencies, software, and tooling requirements — as a
bounded ``execution-environment`` block in the SKILL.md front-matter. The
declaration is evaluated per Skill at draft/import time; it is never copied
from another location and never grants permission by itself.

The declaration travels inside the frozen version bytes, so a Run view or a
confirmed package carries the exact requirements its scripts were authorized
against. The canonical fingerprint below is the scope identity the
content-bound script authorization (#122 AC2) binds to, and the device-side
runtime mirrors the same parsing rules verbatim (frozen cross-repo contract;
the device file keeps a copy of this header).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

import yaml

from app.agentplatform.resources.skill_types import SKILL_MD_FILE

EXECUTION_ENVIRONMENT_KEY = "execution-environment"

#: The one execution target a Skill declares. A script runs only where it was
#: declared: a ``user_device`` Skill never downgrades to a Server execution
#: and vice versa (AC1: no cross-environment fallback).
SCRIPT_TARGETS = ("server", "user_device")

#: The declared need dimensions (AC1: data/OS/dependencies/software/tools).
DECLARATION_FIELDS = ("os", "dependencies", "software", "tools", "data")

MAX_DECLARATION_ENTRIES = 16
MAX_ENTRY_CHARS = 128

_SCRIPTS_DIR = "scripts"
_OS_PLATFORMS = ("windows", "linux", "darwin")


class SkillEnvironmentError(ValueError):
    """A fixed-category declaration rejection; messages never carry paths."""


def _refuse(message: str) -> SkillEnvironmentError:
    return SkillEnvironmentError(message)


def _parse_entries(raw: object, field: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_DECLARATION_ENTRIES:
        raise _refuse(f"execution-environment.{field} must be a list of at most {MAX_DECLARATION_ENTRIES} entries")
    entries: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise _refuse(f"execution-environment.{field} must contain only strings")
        value = " ".join(item.split())
        if not value or len(value) > MAX_ENTRY_CHARS:
            raise _refuse(f"execution-environment.{field} entries must be 1-{MAX_ENTRY_CHARS} characters")
        entries.append(value)
    return entries


def parse_execution_environment(raw: object) -> dict | None:
    """Validate and normalize one ``execution-environment`` front-matter value.

    Returns ``None`` when the Skill declares nothing. Raises
    :class:`SkillEnvironmentError` for any malformed declaration: an unknown
    key, a missing or unknown ``target``, or an out-of-bounds entry list.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _refuse("execution-environment must be a mapping with a target")
    unknown = set(raw) - {"target", *DECLARATION_FIELDS}
    if unknown:
        raise _refuse(
            "Unexpected key(s) in execution-environment: "
            + ", ".join(sorted(str(key) for key in unknown))
        )
    target = raw.get("target")
    if not isinstance(target, str) or target not in SCRIPT_TARGETS:
        raise _refuse("execution-environment.target must be one of: " + ", ".join(SCRIPT_TARGETS))
    declaration: dict = {"target": target}
    for field in DECLARATION_FIELDS:
        entries = _parse_entries(raw.get(field), field)
        if field == "os":
            entries = sorted({entry.lower() for entry in entries})
        declaration[field] = entries
    return declaration


def requirements_fingerprint(declaration: dict | None) -> str:
    """The canonical scope identity of one declaration (empty means no scripts).

    Every declared dimension is in the fingerprint, so a dependency, tool, or
    data-requirement change is a scope change that requires re-authorization,
    while prose-only SKILL.md edits leave it — and the grant that binds to it
    — untouched (AC2).
    """
    normalized = declaration or {}
    payload: dict = {"target": None}
    payload.update({field: [] for field in DECLARATION_FIELDS})
    payload.update({key: normalized[key] for key in payload if key in normalized})
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _frontmatter(skill_md: Path) -> dict:
    try:
        content = skill_md.read_text(encoding="utf-8")
    except (UnicodeError, OSError) as exc:
        raise _refuse("Skill declaration unreadable") from exc
    match = re.match(r"\A---\s*\n(.*?)\n---", content, re.DOTALL)
    if match is None:
        return {}
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def declaration_from_directory(skill_dir: Path) -> dict | None:
    """The declaration of one laid-out Skill directory, validated again."""
    frontmatter = _frontmatter(skill_dir / SKILL_MD_FILE)
    return parse_execution_environment(frontmatter.get(EXECUTION_ENVIRONMENT_KEY))


def skill_has_scripts(skill_dir: Path) -> bool:
    """Whether the package carries executable script members under ``scripts/``."""
    scripts = skill_dir / _SCRIPTS_DIR
    if not scripts.is_dir():
        return False
    return any(path.is_file() for path in scripts.rglob("*"))


def normalize_script_path(raw: object) -> str:
    """The one bounded ``scripts/``-relative POSIX path an execution may name."""
    if not isinstance(raw, str) or not raw or len(raw) > 512 or "\x00" in raw:
        raise _refuse("script path must be a relative scripts/ path")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise _refuse("script path must be a relative scripts/ path")
    if relative.as_posix() != raw or "\\" in raw:
        raise _refuse("script path must be a relative scripts/ path")
    if len(relative.parts) < 2 or relative.parts[0] != _SCRIPTS_DIR:
        raise _refuse("script path must stay under scripts/")
    return relative.as_posix()


def os_matches(declared_os: list[str], current_system: str) -> bool:
    """Whether the current platform satisfies the declared ``os`` list.

    An empty declaration constrains nothing; otherwise the current platform
    name must be one of the declared entries (case-insensitive prefix match,
    so ``Windows 11`` declares ``windows``). A mismatch is an explicit
    unavailability — never a downgrade to another environment (AC1).
    """
    if not declared_os:
        return True
    current = str(current_system or "").lower()
    return any(
        current.startswith(entry.lower())
        for entry in declared_os
        if any(entry.lower().startswith(platform) for platform in _OS_PLATFORMS)
    )


# --- content-bound grant matching (pure protocol, shared by both legs) ------

#: Fixed decision categories; only these cross the API boundary.
APPROVAL_REQUIRED = "SCRIPT_APPROVAL_REQUIRED"
REAUTHORIZATION_REQUIRED = "SCRIPT_REAUTHORIZATION_REQUIRED"
AUTHORIZATION_REVOKED = "SCRIPT_AUTHORIZATION_REVOKED"
GRANTED = "granted"


def script_sha256(data: bytes) -> str:
    """The content identity one authorization binds to."""
    return hashlib.sha256(data).hexdigest()


def evaluate_grant(
    row: object | None,
    *,
    script_digest: str,
    requirements_hash: str,
) -> str:
    """Match one stored grant against the requested content and scope.

    ``row`` is a grant projection (mapping or model). Absent maps to
    :data:`APPROVAL_REQUIRED`, a content or scope difference to
    :data:`REAUTHORIZATION_REQUIRED`, a revoked row to
    :data:`AUTHORIZATION_REVOKED`, and an exact match to :data:`GRANTED`.
    The skill version is deliberately not part of the match: a republished
    version with unchanged script bytes and declaration stays authorized
    (AC2: only a description change must not re-ask).
    """

    def field(name: str) -> object:
        if isinstance(row, dict):
            return row.get(name)
        return getattr(row, name, None)

    if row is None:
        return APPROVAL_REQUIRED
    if field("revoked_at") is not None:
        return AUTHORIZATION_REVOKED
    if field("script_sha256") != script_digest or field("requirements_hash") != requirements_hash:
        return REAUTHORIZATION_REQUIRED
    return GRANTED
