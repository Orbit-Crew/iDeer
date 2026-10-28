"""Skill package preview/confirm import contracts over real persistence (#120).

The preview projects exactly what would be uploaded (body, scripts,
references, per-file and package SHA-256, and the private destination) and
persists nothing; the confirm step binds the preview hash to a private draft
owned by the importing account and never publishes by itself; publication
rides the existing draft/publish flow, a frozen Run keeps its exact version,
and a built-in skill refuses in-place edits.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit tables
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resource_models import Resource, ResourceDraft, ResourceVersion
from app.agentplatform.resources.service import ResourceAction, ResourceActor, ResourceNotFound, ResourceService
from app.gateway.routers import resources
from deerflow.persistence.base import Base

SKILL_MD = "---\nname: report-skill\ndescription: Build a weekly report\n---\n\n# Report skill\n\nUse the analyzer script and read the notes.\n"
SCRIPT = "print('analyze')\n"
REFERENCE = "# Frozen reference notes\n"


def _actor(user_id: str = "owner") -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id="dept-a",
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


def _user(user_id: str = "owner") -> UserModel:
    return UserModel(
        id=user_id,
        username=f"{user_id}@test.com",
        role=UserRole.USER,
        department_id="dept-a",
        disabled=False,
    )


def _canonical_hash(members: list[tuple[str, bytes]]) -> str:
    """The platform's own directory hash, recomputed from the frozen protocol."""
    digest = hashlib.sha256()
    for relative, data in sorted(members):
        encoded = relative.encode()
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(data)
    return digest.hexdigest()


def _skill_members() -> list[tuple[str, bytes]]:
    return [("SKILL.md", SKILL_MD.encode()), ("scripts/analyze.py", SCRIPT.encode()), ("references/notes.md", REFERENCE.encode())]


def _skill_zip() -> io.BytesIO:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, data in _skill_members():
            bundle.writestr(name, data)
    archive.seek(0)
    return archive


async def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, user: UserModel | None = None) -> async_sessionmaker:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'skill-import.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    current_user = user or _user()
    async with factory() as session:
        session.add(current_user)
        await session.commit()
    monkeypatch.setattr(resources, "_factory", lambda: factory)
    monkeypatch.setattr(resources, "get_paths", lambda: SimpleNamespace(base_dir=tmp_path))

    async def _audit(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(resources, "record_audit", _audit)
    return factory


@pytest.mark.asyncio
async def test_preview_reports_upload_scope_and_persists_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T120-01 (preview leg): the preview covers body/scripts/references and destination, and creates nothing."""
    factory = await _setup(tmp_path, monkeypatch)

    markdown = SKILL_MD.encode()
    preview = await resources.preview_skill_import(
        UploadFile(filename="report-skill.md", file=io.BytesIO(markdown)),
        "markdown",
        _user(),
    )
    assert preview["origin"] == "markdown"
    assert preview["name"] == "report-skill"
    assert preview["description"] == "Build a weekly report"
    assert preview["destination"] == {
        "resource_type": "skill",
        "visibility": "private",
        "owner_id": "owner",
    }
    assert [(item["path"], item["role"]) for item in preview["files"]] == [("SKILL.md", "body")]
    assert preview["files"][0]["sha256"] == hashlib.sha256(markdown).hexdigest()
    assert preview["files"][0]["bytes"] == len(markdown)
    # The package hash is the canonical directory identity, computed here from
    # the frozen protocol instead of being read back from the implementation.
    assert preview["package_hash"] == _canonical_hash([("SKILL.md", markdown)])
    assert "# Report skill" in preview["body"]
    assert preview["body_truncated"] is False

    zip_preview = await resources.preview_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "zip",
        _user(),
    )
    assert [(item["path"], item["role"]) for item in zip_preview["files"]] == [
        ("SKILL.md", "body"),
        ("references/notes.md", "reference"),
        ("scripts/analyze.py", "script"),
    ]
    assert zip_preview["files"][1]["sha256"] == hashlib.sha256(REFERENCE.encode()).hexdigest()
    assert zip_preview["files"][2]["bytes"] == len(SCRIPT)
    assert zip_preview["file_count"] == 3
    assert zip_preview["package_hash"] == _canonical_hash(_skill_members())
    # A directory package uploads as a ZIP and keeps the same canonical identity.
    directory_preview = await resources.preview_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "directory",
        _user(),
    )
    assert directory_preview["package_hash"] == zip_preview["package_hash"]

    async with factory() as session:
        assert (await session.execute(select(Resource))).scalars().all() == []
        assert (await session.execute(select(ResourceDraft))).scalars().all() == []
        assert (await session.execute(select(ResourceVersion))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("member", "content"),
    [
        ("../escape.txt", b"evil"),
        ("/absolute.txt", b"absolute"),
        ("sub/../../climb.txt", b"climb"),
        ("back\\slash.txt", b"evil"),
        ("scripts/run.sh", b"echo hi"),
    ],
)
async def test_preview_refuses_illegal_package_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    member: str,
    content: bytes,
) -> None:
    """T120-03 (import leg): traversal, absolute, and unscanned-executable members fail closed."""
    await _setup(tmp_path, monkeypatch)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("SKILL.md", SKILL_MD)
        bundle.writestr(member, content)
    archive.seek(0)
    with pytest.raises(HTTPException) as caught:
        await resources.preview_skill_import(
            UploadFile(filename="bad.zip", file=archive),
            "zip",
            _user(),
        )
    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_preview_refuses_symlink_and_broken_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _setup(tmp_path, monkeypatch)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("SKILL.md", SKILL_MD)
        info = zipfile.ZipInfo("scripts/link.py")
        info.external_attr = 0o120777 << 16  # S_IFLNK
        bundle.writestr(info, b"target")
    archive.seek(0)
    with pytest.raises(HTTPException) as caught:
        await resources.preview_skill_import(
            UploadFile(filename="link.zip", file=archive),
            "zip",
            _user(),
        )
    assert caught.value.status_code == 400
    with pytest.raises(HTTPException) as caught:
        await resources.preview_skill_import(
            UploadFile(filename="broken.zip", file=io.BytesIO(b"not a zip")),
            "zip",
            _user(),
        )
    assert caught.value.status_code == 400
    with pytest.raises(HTTPException) as caught:
        await resources.preview_skill_import(
            UploadFile(filename="odd.zip", file=_skill_zip()),
            "exe",
            _user(),
        )
    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_preview_refuses_markdown_without_frontmatter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _setup(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as caught:
        await resources.preview_skill_import(
            UploadFile(filename="plain.md", file=io.BytesIO(b"# no frontmatter\n")),
            "markdown",
            _user(),
        )
    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_confirm_creates_private_draft_without_publishing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T120-01 (confirm leg): the confirmed import lands as the owner's private draft and never publishes."""
    factory = await _setup(tmp_path, monkeypatch)
    audit_calls: list[tuple] = []

    async def _audit(actor_id, action, resource_type=None, resource_id=None, detail=None, **kwargs) -> None:
        audit_calls.append((actor_id, action, resource_type, resource_id, detail))

    monkeypatch.setattr(resources, "record_audit", _audit)
    preview = await resources.preview_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "zip",
        _user(),
    )
    payload = await resources.confirm_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "zip",
        preview["package_hash"],
        _user(),
    )
    assert payload["visibility"] == "private"
    assert payload["owner_id"] == "owner"
    assert payload["slug"] == "report-skill"
    assert payload["latest_version"] == 0
    assert payload["draft_revision"] == 1
    assert payload["can_modify"] is True
    assert payload["draft"]["revision"] == 1
    assert payload["draft"]["content_hash"] == preview["package_hash"]
    assert [(call[1], call[2]) for call in audit_calls] == [("skill_import_confirmed", "skill")]

    async with factory() as session:
        resource = (await session.execute(select(Resource))).scalar_one()
        assert resource.latest_version == 0
        assert resource.draft_revision == 1
        assert resource.system_owned is False
        draft = await session.get(ResourceDraft, resource.id)
        assert draft is not None and draft.revision == 1
        assert draft.content_hash == preview["package_hash"]
        assert (await session.execute(select(ResourceVersion))).scalars().all() == []
    draft_dir = tmp_path / "resources" / "skills" / payload["id"] / "draft" / "1"
    assert (draft_dir / "SKILL.md").is_file()
    assert (draft_dir / "scripts" / "analyze.py").is_file()
    assert (draft_dir / "references" / "notes.md").is_file()


@pytest.mark.asyncio
async def test_confirm_refuses_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T120-03 (hash leg): content that does not match the confirmed preview hash is refused."""
    factory = await _setup(tmp_path, monkeypatch)
    await resources.preview_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "zip",
        _user(),
    )
    drifted = io.BytesIO()
    with zipfile.ZipFile(drifted, "w") as bundle:
        bundle.writestr("SKILL.md", SKILL_MD.replace("weekly", "monthly"))
        bundle.writestr("scripts/analyze.py", SCRIPT)
        bundle.writestr("references/notes.md", REFERENCE)
    drifted.seek(0)
    with pytest.raises(HTTPException) as caught:
        await resources.confirm_skill_import(
            UploadFile(filename="report-skill.zip", file=drifted),
            "zip",
            "0" * 64,
            _user(),
        )
    assert caught.value.status_code == 400
    async with factory() as session:
        assert (await session.execute(select(Resource))).scalars().all() == []
        assert (await session.execute(select(ResourceDraft))).scalars().all() == []


@pytest.mark.asyncio
async def test_confirm_refuses_duplicate_slug_for_same_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _setup(tmp_path, monkeypatch)
    preview = await resources.preview_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "zip",
        _user(),
    )
    await resources.confirm_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "zip",
        preview["package_hash"],
        _user(),
    )
    with pytest.raises(HTTPException) as caught:
        await resources.confirm_skill_import(
            UploadFile(filename="report-skill.zip", file=_skill_zip()),
            "zip",
            preview["package_hash"],
            _user(),
        )
    assert caught.value.status_code == 409


@pytest.mark.asyncio
async def test_private_skill_is_invisible_to_other_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T120-03 (isolation leg): another account cannot resolve the private import."""
    await _setup(tmp_path, monkeypatch)
    preview = await resources.preview_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "zip",
        _user(),
    )
    payload = await resources.confirm_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "zip",
        preview["package_hash"],
        _user(),
    )
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'skill-import.db'}")
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            service = ResourceService(session, _actor("other"))
            with pytest.raises(ResourceNotFound):
                await service.get_visible(payload["id"])
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirmed_draft_publishes_through_existing_flow_and_keeps_run_frozen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T120-02/T120-04: publication reuses the draft/publish flow; a frozen Run keeps V1 while V2 lands."""
    factory = await _setup(tmp_path, monkeypatch)
    preview = await resources.preview_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "zip",
        _user(),
    )
    payload = await resources.confirm_skill_import(
        UploadFile(filename="report-skill.zip", file=_skill_zip()),
        "zip",
        preview["package_hash"],
        _user(),
    )
    resource_id = payload["id"]
    version_one = await resources.publish_resource(
        resource_id,
        resources.PublishRequest(expected_draft_revision=1, scan_result={"status": "clean"}),
        _user(),
    )
    assert version_one["version"] == 1
    assert version_one["content_hash"] == preview["package_hash"]

    # T120-04: the Run freezes its Skill version at snapshot time; the later
    # modification rides a new draft and lands as V2 without touching the run.
    async with factory() as session:
        service = ResourceService(session, _actor())
        snapshot = await service.create_run_snapshot("run-120", resource_id, selected_resource_id=resource_id)
        await session.commit()
    assert snapshot[0].version == 1
    assert snapshot[0].content_hash == preview["package_hash"]

    await resources.save_skill_draft(
        resource_id,
        resources.SkillDraftRequest(content=SKILL_MD.replace("weekly", "monthly"), expected_revision=1),
        _user(),
    )
    version_two = await resources.publish_resource(
        resource_id,
        resources.PublishRequest(expected_draft_revision=2, scan_result={"status": "clean"}),
        _user(),
    )
    assert version_two["version"] == 2

    async with factory() as session:
        service = ResourceService(session, _actor())
        frozen_one = await service.get_published_content(resource_id, version=1)
        latest = await service.get_published_content(resource_id)
        assert frozen_one.content_hash == preview["package_hash"]
        assert latest.version == 2 and latest.content_hash != preview["package_hash"]
        rows = (await session.execute(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id))).scalars().all()
        assert sorted(row.version for row in rows) == [1, 2]

    from app.agentplatform.resources.storage import ResourceStorage

    storage = ResourceStorage(tmp_path)
    view = storage.create_run_skill_view("run-120", [(resource_id, 1, preview["package_hash"])])
    assert (view / "custom" / resource_id / "SKILL.md").read_text(encoding="utf-8") == SKILL_MD
    # A tampered hash cannot masquerade as the frozen platform version.
    with pytest.raises(Exception):
        storage.create_run_skill_view("run-120-other", [(resource_id, 1, "f" * 64)])


@pytest.mark.asyncio
async def test_builtin_skill_is_read_only_and_changes_need_a_new_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T120-02 (built-in leg): a built-in (system_owned) skill refuses in-place edits.

    The platform is the only content/identity source: the bundled skill cannot
    be modified where it stands, and any change must ride a separate owned
    copy (fork-to-copy) that starts its own version line — the built-in bytes
    and version stay frozen.
    """
    factory = await _setup(tmp_path, monkeypatch)
    builtin_id = "33333333-3333-4333-8333-333333333333"
    builtin_key = f"skills/{builtin_id}/v1"
    builtin_dir = tmp_path / "resources" / builtin_key
    (builtin_dir / "scripts").mkdir(parents=True)
    (builtin_dir / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (builtin_dir / "scripts" / "analyze.py").write_text(SCRIPT, encoding="utf-8")
    async with factory() as session:
        session.add(
            Resource(
                id=builtin_id,
                type="skill",
                slug="builtin-report",
                display_name="builtin-report",
                owner_id="owner",
                visibility="private",
                latest_version=1,
                storage_kind="filesystem",
                storage_key=builtin_key,
                provenance="bundled",
                system_owned=True,
            )
        )
        session.add(
            ResourceVersion(
                id="44444444-4444-4444-8444-444444444444",
                resource_id=builtin_id,
                version=1,
                content_hash="a" * 64,
                storage_key=builtin_key,
                scan_result={"status": "clean"},
                created_by="owner",
            )
        )
        await session.commit()

    # The in-place edit of the built-in is refused before anything is staged.
    with pytest.raises(HTTPException) as caught:
        await resources.save_skill_draft(
            builtin_id,
            resources.SkillDraftRequest(content=SKILL_MD.replace("weekly", "monthly"), expected_revision=0),
            _user(),
        )
    assert caught.value.status_code == 403
    async with factory() as session:
        resource = await session.get(Resource, builtin_id)
        assert resource.latest_version == 1 and resource.draft_revision == 0
        assert (await session.execute(select(ResourceDraft))).scalars().all() == []
    assert (builtin_dir / "SKILL.md").read_text(encoding="utf-8") == SKILL_MD

    # Modification is a separate owned copy: fork-to-copy starts its own
    # version line (user provenance, not system-owned) and the built-in stays.
    copy_id = "55555555-5555-5555-8555-555555555555"
    copy_key = f"skills/{copy_id}/v1"
    shutil.copytree(builtin_dir, tmp_path / "resources" / copy_key)
    async with factory() as session:
        forked = await ResourceService(session, _actor()).fork(
            builtin_id,
            slug="builtin-report-copy",
            display_name="builtin-report-copy",
            copied_storage_key=copy_key,
            target_resource_id=copy_id,
        )
        await session.commit()
    assert forked.system_owned is False
    assert forked.latest_version == 1 and forked.draft_revision == 0
    async with factory() as session:
        original = await session.get(Resource, builtin_id)
        assert original.latest_version == 1 and original.draft_revision == 0
        versions = (await session.execute(select(ResourceVersion).where(ResourceVersion.resource_id.in_([builtin_id, copy_id])))).scalars().all()
        assert sorted((row.resource_id, row.version) for row in versions) == [
            (builtin_id, 1),
            (copy_id, 1),
        ]
