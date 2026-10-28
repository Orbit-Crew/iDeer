"""Skill execution environment declaration and content-bound script grants (#122).

Covers the four #122 contracts on the Server leg:

- T122-01 (declaration + execution leg): a per-Skill ``execution-environment``
  block is validated at the draft/import surface and a representative SERVER
  skill executes through the platform sandbox contract with a fixed output;
- T122-02 (default-off leg): execution without a grant refuses with
  ``SCRIPT_APPROVAL_REQUIRED`` and never touches the sandbox; a user_device
  declaration refuses Server execution (no cross-environment downgrade);
- T122-03 (content binding leg): changed script bytes or a changed declared
  scope require re-authorization, while a prose-only version bump with
  unchanged script bytes and declaration keeps the grant and does not re-ask;
- T122-04 (identity leg): grants are owner-scoped and device-bound; a
  revoked grant refuses; a corrupted (hash-drifted) package refuses even
  with a valid grant; the receipt binds version, digests, and the exact
  authorization basis.
"""

from __future__ import annotations

import hashlib
import shlex
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit tables
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resource_models import Resource, ResourceVersion
from app.agentplatform.resources import skill_environment, skill_package, skill_script_execution
from app.agentplatform.resources.skill_validation import _validate_skill_frontmatter
from app.agentplatform.resources.storage import ResourceStorage
from app.gateway.routers import resources
from app.gateway.skill_script import (
    APPROVAL_REQUIRED,
    AUTHORIZATION_REVOKED,
    GRANTED,
    REAUTHORIZATION_REQUIRED,
    SkillScriptAuthorizationRepository,
    evaluate_grant,
    script_sha256,
)
from deerflow.persistence.base import Base

EXPECTED_OUTPUT = "weekly-report-fixed-ok\n"

SKILL_MD = (
    "---\nname: report-skill\ndescription: Build a weekly report\n"
    "execution-environment:\n"
    "  target: server\n"
    "  os: ['linux']\n"
    "  dependencies: ['python3']\n"
    "  tools: ['python3']\n"
    "---\n\n"
    "# Report skill\n\nRun the analyzer script.\n"
)
DEVICE_SKILL_MD = SKILL_MD.replace("target: server", "target: user_device")
SCRIPT_TEXT = "print('weekly-report-fixed-ok')\n"


def _user(user_id: str = "owner") -> UserModel:
    return UserModel(
        id=user_id,
        username=f"{user_id}@test.com",
        role=UserRole.USER,
        department_id="dept-a",
        disabled=False,
    )


async def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> async_sessionmaker:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'skill-script.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(_user("owner"))
        session.add(_user("other"))
        await session.commit()
    monkeypatch.setattr(resources, "_factory", lambda: factory)
    monkeypatch.setattr(resources, "get_paths", lambda: SimpleNamespace(base_dir=tmp_path))

    async def _audit(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(resources, "record_audit", _audit)
    return factory


def _canonical_hash(members: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for relative, data in sorted(members):
        encoded = relative.encode()
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(data)
    return digest.hexdigest()


async def _publish_skill(
    factory: async_sessionmaker,
    tmp_path: Path,
    *,
    body: str = SKILL_MD,
    script: str = SCRIPT_TEXT,
    slug: str = "report-skill",
    owner_id: str = "owner",
    visibility: str = "private",
    resource_id: str = "11111111-1111-4111-8111-111111111111",
) -> dict:
    """One published frozen Skill version laid out under the storage root."""
    members = [("SKILL.md", body.encode()), ("scripts/analyze.py", script.encode())]
    storage = ResourceStorage(tmp_path)
    version_dir = storage.resources_root / "skills" / resource_id / "versions" / "1"
    version_dir.mkdir(parents=True, exist_ok=True)
    for relative, data in members:
        target = version_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    content_hash = storage.inspect_directory("skill", version_dir).content_hash
    assert content_hash == _canonical_hash(members)
    async with factory() as session:
        session.add(
            Resource(
                id=resource_id,
                type="skill",
                slug=slug,
                display_name=slug,
                owner_id=owner_id,
                visibility=visibility,
                latest_version=1,
                storage_kind="filesystem",
                storage_key=f"skills/{resource_id}",
            )
        )
        session.add(
            ResourceVersion(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{resource_id}-v1")),
                resource_id=resource_id,
                version=1,
                content_hash=content_hash,
                storage_key=f"skills/{resource_id}/versions/1",
                created_by=owner_id,
            )
        )
        await session.commit()
    return {
        "resource_id": resource_id,
        "version": 1,
        "content_hash": content_hash,
        "version_dir": version_dir,
        "script_sha256": script_sha256(script.encode()),
        "requirements_hash": skill_environment.requirements_fingerprint(
            skill_environment.declaration_from_directory(version_dir)
        ),
    }


class FakeSandbox:
    """Records commands without running anything."""

    def __init__(self, output: str = EXPECTED_OUTPUT) -> None:
        self.calls: list[tuple[str, float | None]] = []
        self.output = output

    def execute_command(self, command: str, env=None, timeout=None) -> str:
        self.calls.append((command, timeout))
        return self.output


class RealPythonSandbox:
    """Runs the frozen script with the platform's interpreter contract."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute_command(self, command: str, env=None, timeout=None) -> str:
        self.calls.append(command)
        completed = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603
        return completed.stdout if completed.returncode == 0 else completed.stderr


def _grant_for(repository: SkillScriptAuthorizationRepository, skill: dict, user_id: str = "owner", **overrides):
    payload = dict(
        execution_target="server",
        device_id="",
        slug="report-skill",
        skill_version=1,
        skill_content_hash=skill["content_hash"],
        script_path="scripts/analyze.py",
        script_digest=skill["script_sha256"],
        requirements_hash=skill["requirements_hash"],
    )
    payload.update(overrides)
    return repository.grant(user_id, skill["resource_id"], **payload)


# --- declaration contract ---------------------------------------------------

def test_declaration_parses_and_normalizes() -> None:
    declaration = skill_environment.parse_execution_environment(
        {"target": "server", "os": ["Windows 11"], "dependencies": ["python3"], "tools": [], "data": ["quarterly CSV"]}
    )
    assert declaration == {
        "target": "server",
        "os": ["windows 11"],
        "dependencies": ["python3"],
        "software": [],
        "tools": [],
        "data": ["quarterly CSV"],
    }
    assert skill_environment.parse_execution_environment(None) is None


def test_declaration_refuses_malformed_shapes() -> None:
    with pytest.raises(skill_environment.SkillEnvironmentError):
        skill_environment.parse_execution_environment({"os": ["linux"]})
    with pytest.raises(skill_environment.SkillEnvironmentError):
        skill_environment.parse_execution_environment({"target": "anywhere"})
    with pytest.raises(skill_environment.SkillEnvironmentError):
        skill_environment.parse_execution_environment({"target": "server", "permissions": ["write"]})
    with pytest.raises(skill_environment.SkillEnvironmentError):
        skill_environment.parse_execution_environment({"target": "server", "os": ["x" * 200]})
    with pytest.raises(skill_environment.SkillEnvironmentError):
        skill_environment.parse_execution_environment({"target": "server", "tools": [f"tool{n}" for n in range(20)]})
    with pytest.raises(skill_environment.SkillEnvironmentError):
        skill_environment.parse_execution_environment(["server"])


def test_requirements_fingerprint_binds_scope_not_prose() -> None:
    base = skill_environment.parse_execution_environment({"target": "server", "dependencies": ["python3"]})
    same = skill_environment.parse_execution_environment({"target": "server", "dependencies": ["python3"]})
    changed = skill_environment.parse_execution_environment({"target": "server", "dependencies": ["python3.12"]})
    device = skill_environment.parse_execution_environment({"target": "user_device", "dependencies": ["python3"]})
    assert skill_environment.requirements_fingerprint(base) == skill_environment.requirements_fingerprint(same)
    assert skill_environment.requirements_fingerprint(base) != skill_environment.requirements_fingerprint(changed)
    assert skill_environment.requirements_fingerprint(base) != skill_environment.requirements_fingerprint(device)


def test_os_matches_declares_platform_not_downgrade() -> None:
    assert skill_environment.os_matches([], "Windows")
    assert skill_environment.os_matches(["windows"], "Windows-11")
    assert not skill_environment.os_matches(["linux"], "Windows")
    assert not skill_environment.os_matches(["linux"], "")


def test_normalize_script_path_stays_under_scripts() -> None:
    assert skill_environment.normalize_script_path("scripts/analyze.py") == "scripts/analyze.py"
    for bad in ("analyze.py", "../escape.py", "scripts/../escape.py", "/absolute.py", "scripts/a\\b.py", ""):
        with pytest.raises(skill_environment.SkillEnvironmentError):
            skill_environment.normalize_script_path(bad)


def test_frontmatter_validation_accepts_and_rejects_declaration(tmp_path: Path) -> None:
    """T122-01 (declaration leg): the draft/import surface validates the block."""
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    valid, message, name = _validate_skill_frontmatter(skill_dir)
    assert valid and name == "report-skill", message

    (skill_dir / "SKILL.md").write_text(SKILL_MD.replace("  os: ['linux']", "  os: 'linux'"), encoding="utf-8")
    valid, message, _ = _validate_skill_frontmatter(skill_dir)
    assert not valid and "execution-environment.os" in message


def test_preview_projects_declared_environment(tmp_path: Path) -> None:
    package = tmp_path / "package"
    (package / "scripts").mkdir(parents=True)
    (package / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (package / "scripts" / "analyze.py").write_text(SCRIPT_TEXT, encoding="utf-8")
    preview = skill_package.build_preview(package, origin="directory", storage=ResourceStorage(tmp_path))
    declaration = preview["execution_environment"]
    assert declaration is not None and declaration["target"] == "server"
    assert preview["requirements_hash"] == skill_environment.requirements_fingerprint(declaration)


# --- authorization protocol -------------------------------------------------

@pytest.mark.asyncio
async def test_grant_matches_exact_content_and_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    factory = await _setup(tmp_path, monkeypatch)
    repository = SkillScriptAuthorizationRepository(lambda: factory)
    grant = await repository.grant(
        "owner", "resource-1", execution_target="server", device_id="", slug="report-skill",
        skill_version=1, skill_content_hash="a" * 64, script_path="scripts/analyze.py",
        script_digest="b" * 64, requirements_hash="c" * 64,
    )
    row = await repository.active("owner", "resource-1", execution_target="server", device_id="", script_path="scripts/analyze.py")
    assert row is not None and row["authorization_id"] == grant["authorization_id"]
    assert evaluate_grant(row, script_digest="b" * 64, requirements_hash="c" * 64) == GRANTED
    assert evaluate_grant(None, script_digest="b" * 64, requirements_hash="c" * 64) == APPROVAL_REQUIRED
    assert evaluate_grant(row, script_digest="d" * 64, requirements_hash="c" * 64) == REAUTHORIZATION_REQUIRED
    assert evaluate_grant(row, script_digest="b" * 64, requirements_hash="d" * 64) == REAUTHORIZATION_REQUIRED
    assert await repository.revoke("owner", grant["authorization_id"]) is True
    row = await repository.active("owner", "resource-1", execution_target="server", device_id="", script_path="scripts/analyze.py")
    assert evaluate_grant(row, script_digest="b" * 64, requirements_hash="c" * 64) == AUTHORIZATION_REVOKED


@pytest.mark.asyncio
async def test_regrant_after_content_change_replaces_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    factory = await _setup(tmp_path, monkeypatch)
    repository = SkillScriptAuthorizationRepository(lambda: factory)
    first = await repository.grant(
        "owner", "resource-1", execution_target="server", device_id="", slug="s", skill_version=1,
        skill_content_hash="a" * 64, script_path="scripts/a.py", script_digest="b" * 64, requirements_hash="c" * 64,
    )
    second = await repository.grant(
        "owner", "resource-1", execution_target="server", device_id="", slug="s", skill_version=2,
        skill_content_hash="e" * 64, script_path="scripts/a.py", script_digest="d" * 64, requirements_hash="c" * 64,
    )
    assert first["authorization_id"] != second["authorization_id"]
    rows = await repository.list("owner", "resource-1")
    assert len(rows) == 1 and rows[0]["script_sha256"] == "d" * 64
    assert (
        await repository.active("owner", "resource-1", execution_target="server", device_id="", script_path="scripts/a.py")
    )["authorization_id"] == second["authorization_id"]


@pytest.mark.asyncio
async def test_grants_do_not_cross_accounts_or_devices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T122-04 (identity leg): another account or device never inherits a grant."""
    factory = await _setup(tmp_path, monkeypatch)
    repository = SkillScriptAuthorizationRepository(lambda: factory)
    await _grant_for(repository, {"resource_id": "resource-1", "content_hash": "a" * 64, "script_sha256": "b" * 64, "requirements_hash": "c" * 64})
    assert await repository.active("other", "resource-1", execution_target="server", device_id="", script_path="scripts/analyze.py") is None
    assert await repository.active("owner", "resource-1", execution_target="server", device_id="device-2", script_path="scripts/analyze.py") is None
    assert await repository.active("owner", "resource-1", execution_target="user_device", device_id="", script_path="scripts/analyze.py") is None


# --- executor gate ----------------------------------------------------------

@pytest.mark.asyncio
async def test_executor_runs_representative_skill_and_binds_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T122-01 (execution leg): the declared skill executes with the fixed output and a bound receipt."""
    factory = await _setup(tmp_path, monkeypatch)
    skill = await _publish_skill(factory, tmp_path)
    repository = SkillScriptAuthorizationRepository(lambda: factory)
    grant = await _grant_for(repository, skill)
    sandbox = RealPythonSandbox()
    receipt = skill_script_execution.execute_server_skill_script(
        ResourceStorage(tmp_path),
        sandbox,
        await repository.active("owner", skill["resource_id"], execution_target="server", device_id="", script_path="scripts/analyze.py"),
        version_dir=skill["version_dir"],
        script_path="scripts/analyze.py",
        skill_resource_id=skill["resource_id"],
        slug="report-skill",
        skill_version=1,
        expected_content_hash=skill["content_hash"],
    )
    assert sandbox.calls and "scripts/analyze.py" in sandbox.calls[0]
    assert receipt["status"] == "completed"
    assert receipt["skill_version"] == 1
    assert receipt["package_hash"] == skill["content_hash"]
    assert receipt["script_sha256"] == skill["script_sha256"]
    assert receipt["requirements_hash"] == skill["requirements_hash"]
    assert receipt["authorization_basis"] == f"skill_script_authorization:{grant['authorization_id']}"
    assert EXPECTED_OUTPUT in receipt["stdout"]


@pytest.mark.asyncio
async def test_executor_default_off_without_grant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T122-02 (default-off leg): no grant means nothing runs."""
    factory = await _setup(tmp_path, monkeypatch)
    skill = await _publish_skill(factory, tmp_path)
    sandbox = FakeSandbox()
    with pytest.raises(skill_script_execution.SkillScriptRefusal) as caught:
        skill_script_execution.execute_server_skill_script(
            ResourceStorage(tmp_path), sandbox, None,
            version_dir=skill["version_dir"], script_path="scripts/analyze.py",
            skill_resource_id=skill["resource_id"], slug="report-skill", skill_version=1,
            expected_content_hash=skill["content_hash"],
        )
    assert caught.value.category == APPROVAL_REQUIRED
    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_executor_refuses_cross_environment_and_corruption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC1/AC4: undeclared and device-declared skills never run on the Server; drift refuses."""
    factory = await _setup(tmp_path, monkeypatch)
    grant_row = {"authorization_id": "grant"}
    no_decl_header = SKILL_MD.split("execution-environment")[0] + "---\n\n# no declaration\n"
    undeclared = await _publish_skill(factory, tmp_path, body=no_decl_header, slug="undeclared",
                                      resource_id="22222222-2222-4222-8222-222222222222")
    with pytest.raises(skill_script_execution.SkillScriptRefusal) as caught:
        skill_script_execution.execute_server_skill_script(
            ResourceStorage(tmp_path), FakeSandbox(), grant_row,
            version_dir=undeclared["version_dir"], script_path="scripts/analyze.py",
            skill_resource_id=undeclared["resource_id"], slug="undeclared", skill_version=1,
            expected_content_hash=undeclared["content_hash"],
        )
    assert caught.value.category == skill_script_execution.ENVIRONMENT_UNDECLARED

    device = await _publish_skill(factory, tmp_path, body=DEVICE_SKILL_MD, slug="device-skill",
                                  resource_id="33333333-3333-4333-8333-333333333333")
    with pytest.raises(skill_script_execution.SkillScriptRefusal) as caught:
        skill_script_execution.execute_server_skill_script(
            ResourceStorage(tmp_path), FakeSandbox(), grant_row,
            version_dir=device["version_dir"], script_path="scripts/analyze.py",
            skill_resource_id=device["resource_id"], slug="device-skill", skill_version=1,
            expected_content_hash=device["content_hash"],
        )
    assert caught.value.category == skill_script_execution.ENVIRONMENT_MISMATCH

    skill = await _publish_skill(factory, tmp_path)
    with pytest.raises(skill_script_execution.SkillScriptRefusal) as caught:
        skill_script_execution.execute_server_skill_script(
            ResourceStorage(tmp_path), FakeSandbox(), grant_row,
            version_dir=skill["version_dir"], script_path="SKILL.md",
            skill_resource_id=skill["resource_id"], slug="report-skill", skill_version=1,
            expected_content_hash=skill["content_hash"],
        )
    assert caught.value.category == skill_script_execution.SCRIPT_NOT_FOUND

    (skill["version_dir"] / "scripts" / "analyze.py").write_text("print('tampered')\n", encoding="utf-8")
    with pytest.raises(skill_script_execution.SkillScriptRefusal) as caught:
        skill_script_execution.execute_server_skill_script(
            ResourceStorage(tmp_path), FakeSandbox(), grant_row,
            version_dir=skill["version_dir"], script_path="scripts/analyze.py",
            skill_resource_id=skill["resource_id"], slug="report-skill", skill_version=1,
            expected_content_hash=skill["content_hash"],
        )
    assert caught.value.category == skill_script_execution.PACKAGE_CORRUPTED


@pytest.mark.asyncio
async def test_executor_reauthorizes_on_content_or_scope_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T122-03: changed bytes or scope refuse; a prose-only version bump keeps the grant."""
    factory = await _setup(tmp_path, monkeypatch)
    skill = await _publish_skill(factory, tmp_path)
    repository = SkillScriptAuthorizationRepository(lambda: factory)
    await _grant_for(repository, skill)
    row = await repository.active("owner", skill["resource_id"], execution_target="server", device_id="", script_path="scripts/analyze.py")

    # Changed script content under the same path: the old grant no longer matches.
    changed = await _publish_skill(factory, tmp_path, script="print('changed-output')\n", slug="changed-skill",
                                   resource_id="44444444-4444-4444-8444-444444444444")
    sandbox = FakeSandbox()
    with pytest.raises(skill_script_execution.SkillScriptRefusal) as caught:
        skill_script_execution.execute_server_skill_script(
            ResourceStorage(tmp_path), sandbox, row,
            version_dir=changed["version_dir"], script_path="scripts/analyze.py",
            skill_resource_id=changed["resource_id"], slug="changed-skill", skill_version=1,
            expected_content_hash=changed["content_hash"],
        )
    assert caught.value.category == REAUTHORIZATION_REQUIRED
    assert sandbox.calls == []

    # A changed declared scope (dependency change) also refuses.
    changed_scope = await _publish_skill(
        factory, tmp_path,
        body=SKILL_MD.replace("dependencies: ['python3']", "dependencies: ['python3.12']"),
        slug="changed-scope", resource_id="55555555-5555-4555-8555-555555555555",
    )
    assert changed_scope["requirements_hash"] != skill["requirements_hash"]
    assert changed_scope["script_sha256"] == skill["script_sha256"]
    with pytest.raises(skill_script_execution.SkillScriptRefusal) as caught:
        skill_script_execution.execute_server_skill_script(
            ResourceStorage(tmp_path), FakeSandbox(), row,
            version_dir=changed_scope["version_dir"], script_path="scripts/analyze.py",
            skill_resource_id=changed_scope["resource_id"], slug="changed-scope", skill_version=1,
            expected_content_hash=changed_scope["content_hash"],
        )
    assert caught.value.category == REAUTHORIZATION_REQUIRED

    # Prose-only version bump: new content hash, same script bytes and declaration.
    prose = SKILL_MD.replace("Run the analyzer script.", "Run the analyzer script carefully.")
    evolved = await _publish_skill(factory, tmp_path, body=prose, slug="report-skill-2",
                                   resource_id="66666666-6666-4666-8666-666666666666")
    assert evolved["script_sha256"] == skill["script_sha256"]
    assert evolved["requirements_hash"] == skill["requirements_hash"]
    assert evolved["content_hash"] != skill["content_hash"]
    receipt = skill_script_execution.execute_server_skill_script(
        ResourceStorage(tmp_path), RealPythonSandbox(), row,
        version_dir=evolved["version_dir"], script_path="scripts/analyze.py",
        skill_resource_id=evolved["resource_id"], slug="report-skill-2", skill_version=1,
        expected_content_hash=evolved["content_hash"],
    )
    assert EXPECTED_OUTPUT in receipt["stdout"]


# --- router surface ---------------------------------------------------------

@pytest.mark.asyncio
async def test_authorize_execute_revoke_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T122-02/03/04 over the API: authorize, execute, remember, revoke, refuse."""
    factory = await _setup(tmp_path, monkeypatch)
    skill = await _publish_skill(factory, tmp_path)
    sandbox = RealPythonSandbox()
    monkeypatch.setattr(resources, "_skill_script_sandbox", lambda user_id: sandbox)

    with pytest.raises(HTTPException) as caught:
        await resources.authorize_skill_script(
            skill["resource_id"],
            resources.SkillScriptAuthorizeRequest(version=1, script_path="scripts/analyze.py", expected_script_sha256="0" * 64),
            _user(),
        )
    assert caught.value.status_code == 400

    # Default off: executing before any grant refuses and never runs.
    with pytest.raises(HTTPException) as caught:
        await resources.execute_skill_script(
            skill["resource_id"],
            resources.SkillScriptExecuteRequest(version=1, script_path="scripts/analyze.py"),
            _user(),
        )
    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == APPROVAL_REQUIRED
    assert sandbox.calls == []

    grant = await resources.authorize_skill_script(
        skill["resource_id"],
        resources.SkillScriptAuthorizeRequest(version=1, script_path="scripts/analyze.py", expected_script_sha256=skill["script_sha256"]),
        _user(),
    )
    assert grant["execution_target"] == "server"
    receipt = await resources.execute_skill_script(
        skill["resource_id"],
        resources.SkillScriptExecuteRequest(version=1, script_path="scripts/analyze.py"),
        _user(),
    )
    assert EXPECTED_OUTPUT in receipt["stdout"]
    assert receipt["authorization_basis"] == f"skill_script_authorization:{grant['authorization_id']}"
    assert receipt["script_sha256"] == skill["script_sha256"]
    assert receipt["package_hash"] == skill["content_hash"]
    calls_after_first = len(sandbox.calls)

    # Remembered: the second execution does not ask again and runs directly.
    again = await resources.execute_skill_script(
        skill["resource_id"],
        resources.SkillScriptExecuteRequest(version=1, script_path="scripts/analyze.py"),
        _user(),
    )
    assert again["authorization_basis"] == receipt["authorization_basis"]
    assert len(sandbox.calls) == calls_after_first + 1

    listed = await resources.list_skill_script_authorizations(skill["resource_id"], _user())
    assert [row["authorization_id"] for row in listed["authorizations"]] == [grant["authorization_id"]]

    assert await resources.revoke_skill_script_authorization(skill["resource_id"], grant["authorization_id"], _user()) == {"revoked": True}
    with pytest.raises(HTTPException) as caught:
        await resources.execute_skill_script(
            skill["resource_id"],
            resources.SkillScriptExecuteRequest(version=1, script_path="scripts/analyze.py"),
            _user(),
        )
    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == AUTHORIZATION_REVOKED
    assert len(sandbox.calls) == calls_after_first + 1  # the revoked request never ran


@pytest.mark.asyncio
async def test_device_declared_skill_refuses_server_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1: a user_device skill's approvals live on the device, not the Server."""
    factory = await _setup(tmp_path, monkeypatch)
    skill = await _publish_skill(factory, tmp_path, body=DEVICE_SKILL_MD)
    with pytest.raises(HTTPException) as caught:
        await resources.authorize_skill_script(
            skill["resource_id"],
            resources.SkillScriptAuthorizeRequest(version=1, script_path="scripts/analyze.py", expected_script_sha256=skill["script_sha256"]),
            _user(),
        )
    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_other_account_needs_its_own_grant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T122-04: sharing visibility never substitutes for the caller's own grant."""
    factory = await _setup(tmp_path, monkeypatch)
    skill = await _publish_skill(factory, tmp_path, visibility="public")
    monkeypatch.setattr(resources, "_skill_script_sandbox", lambda user_id: FakeSandbox())
    await resources.authorize_skill_script(
        skill["resource_id"],
        resources.SkillScriptAuthorizeRequest(version=1, script_path="scripts/analyze.py", expected_script_sha256=skill["script_sha256"]),
        _user("owner"),
    )
    with pytest.raises(HTTPException) as caught:
        await resources.execute_skill_script(
            skill["resource_id"],
            resources.SkillScriptExecuteRequest(version=1, script_path="scripts/analyze.py"),
            _user("other"),
        )
    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == APPROVAL_REQUIRED
