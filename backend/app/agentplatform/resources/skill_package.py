"""Skill package preview and confirmed-import identity (#120).

Three user-facing package shapes share one canonical Skill identity: a single
Markdown file (wrapped as ``SKILL.md``), a ZIP archive, and a directory (the
device uploads it as a ZIP). The preview is a bounded, read-only projection of
exactly what would be uploaded — body, scripts, references, per-file SHA-256
and the canonical package hash — and the confirm step binds that hash to the
private draft it creates, so drifted bytes can never impersonate the confirmed
preview. Illegal package content (path traversal, absolute members, symlinks,
unscanned executables, oversized entries) is refused deterministically and
nothing is ever executed here: the package only ever becomes catalog content
served to Server-orchestrated Runs.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path, PurePosixPath

import yaml

from app.agentplatform.resources import skill_environment
from app.agentplatform.resources.skill_types import SKILL_MD_FILE
from app.agentplatform.resources.skill_validation import _validate_skill_frontmatter
from app.agentplatform.resources.storage import ResourceStorage, StorageValidationError

SKILL_PACKAGE_ORIGINS = frozenset({"markdown", "zip", "directory"})
PREVIEW_BODY_LIMIT = 20_000
PREVIEW_FILE_LIMIT = 200


class SkillPackageError(StorageValidationError):
    """A fixed-category package rejection; messages never carry local paths."""


def classify_role(relative: PurePosixPath) -> str:
    """One package member's upload-scope role: body, script, reference, or attachment."""
    posix = relative.as_posix()
    if posix == SKILL_MD_FILE:
        return "body"
    if len(relative.parts) > 1 and relative.parts[0] == "scripts":
        return "script"
    if len(relative.parts) > 1 and relative.parts[0] == "references":
        return "reference"
    return "attachment"


def materialize(origin: str, upload: Path, destination: Path, storage: ResourceStorage) -> None:
    """Lay the uploaded package out as a Skill directory without executing anything."""
    if origin not in SKILL_PACKAGE_ORIGINS:
        raise SkillPackageError(f"Unsupported Skill package origin: {origin}")
    if origin == "markdown":
        try:
            text = upload.read_text(encoding="utf-8")
        except (UnicodeError, OSError) as exc:
            raise SkillPackageError("Skill markdown must be UTF-8 text") from exc
        destination.mkdir(parents=True, exist_ok=True)
        (destination / SKILL_MD_FILE).write_text(text, encoding="utf-8")
        return
    _extract_archive(upload, destination, storage)


def _extract_archive(archive_path: Path, destination: Path, storage: ResourceStorage) -> None:
    """Safe extraction with the canonical member rules, before any resource identity exists."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            if len(members) > storage.limits.max_files:
                raise StorageValidationError("Archive file count exceeds limit")
            total_size = 0
            for item in members:
                relative = storage._validate_archive_member(item)
                if item.file_size > storage.limits.max_file_bytes:
                    raise StorageValidationError(f"Archive member exceeds size limit: {relative.as_posix()}")
                total_size += item.file_size
                if total_size > storage.limits.max_total_bytes:
                    raise StorageValidationError("Archive expanded size exceeds limit")
                target = destination.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                target.chmod(0o644)
    except zipfile.BadZipFile as exc:
        raise StorageValidationError("Skill package is not a valid ZIP file") from exc


def _frontmatter(skill_md: Path) -> dict:
    content = skill_md.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---", content, re.DOTALL)
    if match is None:
        return {}
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_preview(source: Path, *, origin: str, storage: ResourceStorage) -> dict:
    """The bounded read-only projection of one Skill package; nothing persists.

    ``inspect_directory`` applies the canonical content bar (``SKILL.md``
    present, no symlinks, no unscanned executables, size and count limits) and
    ``_validate_skill_frontmatter`` applies the enterprise front-matter rules;
    the package hash is the same canonical directory hash that drafts and
    versions carry, so the preview identity and the platform identity coincide.
    """
    if origin not in SKILL_PACKAGE_ORIGINS:
        raise SkillPackageError(f"Unsupported Skill package origin: {origin}")
    inspected = storage.inspect_directory("skill", source)
    valid, message, name = _validate_skill_frontmatter(source)
    if not valid:
        raise SkillPackageError(f"Skill package rejected: {message}")
    metadata = _frontmatter(source / SKILL_MD_FILE)
    description = metadata.get("description")
    files: list[dict[str, object]] = []
    for path in sorted(
        (value for value in source.rglob("*") if value.is_file()),
        key=lambda value: value.relative_to(source).as_posix(),
    ):
        relative = path.relative_to(source)
        data = path.read_bytes()
        files.append(
            {
                "path": relative.as_posix(),
                "role": classify_role(relative),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    body = (source / SKILL_MD_FILE).read_text(encoding="utf-8")
    assert name is not None  # A valid front-matter always carries its name.
    # Issue 122: the preview projects the declared execution environment so a
    # confirming user sees exactly which target/needs the scripts declare.
    try:
        declaration = skill_environment.parse_execution_environment(metadata.get(skill_environment.EXECUTION_ENVIRONMENT_KEY))
    except skill_environment.SkillEnvironmentError:
        declaration = None  # Already refused by the front-matter validation above.
    return {
        "execution_environment": declaration,
        "requirements_hash": skill_environment.requirements_fingerprint(declaration),
        "origin": origin,
        "name": name,
        "description": description.strip() if isinstance(description, str) else "",
        "body": body[:PREVIEW_BODY_LIMIT],
        "body_truncated": len(body) > PREVIEW_BODY_LIMIT,
        "files": files[:PREVIEW_FILE_LIMIT],
        "file_count": inspected.file_count,
        "total_bytes": inspected.total_bytes,
        "package_hash": inspected.content_hash,
    }
