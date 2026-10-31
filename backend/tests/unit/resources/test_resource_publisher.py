"""Filesystem and database publication consistency contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from zipfile import ZipFile

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit_logs
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.models import KnowledgeBase, KnowledgeRevision
from app.agentplatform.resource_models import Resource, ResourceDraft, ResourceVersion
from app.agentplatform.resources.publisher import ResourcePublisher
from app.agentplatform.resources.service import (
    ResourceAction,
    ResourceActor,
    ResourceConflict,
    ResourceService,
)
from app.agentplatform.resources.storage import ResourceStorage
from deerflow.persistence.base import Base


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'publisher.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _actor(user_id: str = "owner") -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id="dept-a",
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    (source / "config.yaml").write_text("name: example\n")
    return source


def _skill_source(tmp_path: Path) -> Path:
    source = tmp_path / "skill-source"
    source.mkdir(exist_ok=True)
    (source / "SKILL.md").write_text("---\nname: helper-skill\n---\n\nHelper skill body.\n")
    return source


async def _create_resource(factory: async_sessionmaker[AsyncSession]) -> str:
    async with factory() as session:
        resource = await ResourceService(session, _actor()).create_resource(
            resource_type="agent",
            slug="example",
            display_name="Example",
            storage_kind="filesystem",
        )
        await session.commit()
        return resource.id


@pytest.mark.asyncio
async def test_publish_commits_only_after_version_directory_exists_and_removes_draft(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    resource_id = await _create_resource(session_factory)
    storage = ResourceStorage(tmp_path)
    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        draft = await publisher.save_filesystem_draft(
            resource_id,
            source_dir=_source(tmp_path),
            expected_revision=0,
        )
        version = await publisher.publish_filesystem(
            resource_id,
            expected_draft_revision=draft.revision,
            scan_result={"status": "clean"},
        )

    async with session_factory() as verification:
        resource = await verification.get(Resource, resource_id)
        persisted = (await verification.execute(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id))).scalar_one()
        assert resource is not None and resource.latest_version == 1
        assert persisted.storage_key == version.storage_key
        assert (storage.resources_root / persisted.storage_key).is_dir()
        assert await verification.get(ResourceDraft, resource_id) is None
        assert not (storage.resources_root / f"agents/{resource_id}/draft/1").exists()


@pytest.mark.asyncio
async def test_archive_draft_is_validated_and_stored_in_canonical_draft_directory(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    resource_id = await _create_resource(session_factory)
    archive = tmp_path / "agent.zip"
    with ZipFile(archive, "w") as value:
        value.writestr("config.yaml", "name: archived-agent\n")

    storage = ResourceStorage(tmp_path)
    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        draft = await publisher.save_archive_draft(
            resource_id,
            archive_path=archive,
            expected_revision=0,
        )

    assert draft.revision == 1
    assert (storage.resources_root / draft.storage_key / "config.yaml").read_text() == "name: archived-agent\n"


@pytest.mark.asyncio
async def test_publisher_fork_copies_files_before_committing_independent_private_v1(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    resource_id = await _create_resource(session_factory)
    storage = ResourceStorage(tmp_path)
    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        draft = await publisher.save_filesystem_draft(resource_id, source_dir=_source(tmp_path), expected_revision=0)
        await publisher.publish_filesystem(resource_id, expected_draft_revision=draft.revision, scan_result={})
        resource = await session.get(Resource, resource_id)
        assert resource is not None
        resource.visibility = "public"
        await session.commit()

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor("fork-owner")), storage)
        forked = await publisher.fork(
            resource_id,
            slug="forked-example",
            display_name="Forked Example",
        )

    assert forked.owner_id == "fork-owner"
    assert forked.visibility == "private"
    assert (storage.resources_root / f"agents/{forked.id}/versions/1/config.yaml").is_file()


@pytest.mark.asyncio
async def test_database_commit_failure_leaves_reconcilable_unreferenced_version_and_preserves_draft(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_id = await _create_resource(session_factory)
    storage = ResourceStorage(tmp_path)
    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        draft = await publisher.save_filesystem_draft(
            resource_id,
            source_dir=_source(tmp_path),
            expected_revision=0,
        )

        async def fail_commit() -> None:
            raise RuntimeError("injected commit failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="injected commit failure"):
            await publisher.publish_filesystem(
                resource_id,
                expected_draft_revision=draft.revision,
                scan_result={"status": "clean"},
            )

    async with session_factory() as verification:
        resource = await verification.get(Resource, resource_id)
        persisted_draft = await verification.get(ResourceDraft, resource_id)
        versions = list((await verification.execute(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id))).scalars())
        assert resource is not None and resource.latest_version == 0
        assert persisted_draft is not None
        assert versions == []
        report = storage.reconcile({}, expected_drafts={persisted_draft.storage_key: persisted_draft.content_hash})
        assert report.unreferenced_versions == [f"agents/{resource_id}/versions/1"]
        assert report.missing_drafts == []


@pytest.mark.asyncio
async def test_workflow_database_publication_is_immutable_and_hashes_canonical_json(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async with session_factory() as session:
        resource = await ResourceService(session, _actor()).create_resource(
            resource_type="workflow",
            slug="flow",
            display_name="Flow",
            storage_kind="database",
        )
        await session.commit()
        resource_id = resource.id

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), ResourceStorage(tmp_path))
        content = {
            "schema_version": 2,
            "name": "flow",
            "entrypoint": "start",
            "nodes": [{"id": "start", "type": "action", "action": {"kind": "tool", "name": "noop"}}],
            "edges": [],
        }
        draft = await publisher.save_database_draft(
            resource_id,
            content=content,
            expected_revision=0,
        )
        version = await publisher.publish_database(
            resource_id,
            expected_draft_revision=draft.revision,
            scan_result={"status": "valid"},
        )

    assert version.storage_key == f"workflows/{resource_id}/versions/1"
    assert version.content == content
    assert len(version.content_hash) == 64
    async with session_factory() as verification:
        persisted = (await verification.execute(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id))).scalar_one()
        assert persisted.content == version.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        {"dataset_id": "raw-dataset-id"},
        {"ragflow_dataset": "raw-dataset-id"},
        {"retrieval_profile": {"provider_dataset_uuid": "raw-dataset-id"}},
        {"provider": {"access_token": "provider-secret"}},
    ],
)
async def test_knowledge_database_draft_rejects_provider_identity_and_credentials(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    content: dict,
) -> None:
    async with session_factory() as session:
        resource = await ResourceService(session, _actor()).create_resource(
            resource_type="knowledge_base",
            slug="protected-kb",
            display_name="Protected Knowledge Base",
            storage_kind="database",
        )
        await session.commit()
        resource_id = resource.id

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), ResourceStorage(tmp_path))
        with pytest.raises(ValueError, match="cannot contain provider credentials or dataset IDs"):
            await publisher.save_database_draft(
                resource_id,
                content=content,
                expected_revision=0,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_type", ["agent", "workflow"])
async def test_rollback_copies_old_content_into_a_new_version(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    resource_type: str,
) -> None:
    storage = ResourceStorage(tmp_path)
    async with session_factory() as session:
        resource = await ResourceService(session, _actor()).create_resource(
            resource_type=resource_type,
            slug=f"rollback-{resource_type}",
            display_name="Rollback",
            storage_kind="database" if resource_type == "workflow" else "filesystem",
        )
        await session.commit()
        resource_id = resource.id

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        if resource_type == "workflow":
            content = {
                "schema_version": 2,
                "name": "rollback-workflow",
                "entrypoint": "start",
                "nodes": [{"id": "start", "type": "action", "action": {"kind": "tool", "name": "noop"}}],
                "edges": [],
            }
            draft = await publisher.save_database_draft(resource_id, content=content, expected_revision=0)
            first = await publisher.publish_database(resource_id, expected_draft_revision=draft.revision, scan_result={})
            rolled_back = await publisher.rollback_database(resource_id, source_version=1)
        else:
            draft = await publisher.save_filesystem_draft(resource_id, source_dir=_source(tmp_path), expected_revision=0)
            first = await publisher.publish_filesystem(resource_id, expected_draft_revision=draft.revision, scan_result={})
            rolled_back = await publisher.rollback_filesystem(resource_id, source_version=1)

    assert (first.version, rolled_back.version) == (1, 2)
    assert rolled_back.storage_key != first.storage_key
    assert rolled_back.content_hash == first.content_hash
    assert (rolled_back.source_resource_id, rolled_back.source_version) == (resource_id, 1)
    if resource_type == "agent":
        assert (storage.resources_root / rolled_back.storage_key).is_dir()
    else:
        assert rolled_back.content == first.content


@pytest.mark.asyncio
async def test_invalid_workflow_contract_cannot_be_published(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async with session_factory() as session:
        resource = await ResourceService(session, _actor()).create_resource(
            resource_type="workflow",
            slug="invalid-flow",
            display_name="Invalid Flow",
            storage_kind="database",
        )
        await session.commit()
        resource_id = resource.id

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), ResourceStorage(tmp_path))
        draft = await publisher.save_database_draft(
            resource_id,
            content={"schema_version": 2, "nodes": []},
            expected_revision=0,
        )
        with pytest.raises(ValueError, match="name|entrypoint|nodes"):
            await publisher.publish_database(
                resource_id,
                expected_draft_revision=draft.revision,
                scan_result={},
            )

    async with session_factory() as verification:
        resource = await verification.get(Resource, resource_id)
        assert resource is not None and resource.latest_version == 0


@pytest.mark.asyncio
async def test_agent_with_plaintext_credentials_cannot_be_published(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    resource_id = await _create_resource(session_factory)
    source = _source(tmp_path)
    (source / "config.yaml").write_text("name: example\npassword: plaintext\n")
    storage = ResourceStorage(tmp_path)
    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        draft = await publisher.save_filesystem_draft(resource_id, source_dir=source, expected_revision=0)
        with pytest.raises(Exception, match="credential"):
            await publisher.publish_filesystem(
                resource_id,
                expected_draft_revision=draft.revision,
                scan_result={"status": "clean"},
            )

    async with session_factory() as verification:
        resource = await verification.get(Resource, resource_id)
        assert resource is not None and resource.latest_version == 0
        assert not (storage.resources_root / f"agents/{resource_id}/versions/1").exists()


@pytest.mark.asyncio
async def test_dependency_conflict_publishes_nothing_and_same_draft_retries_clean(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    resource_id = await _create_resource(session_factory)
    async with session_factory() as session:
        dependency = await ResourceService(session, _actor()).create_resource(
            resource_type="skill",
            slug="helper-skill",
            display_name="Helper Skill",
            storage_kind="filesystem",
        )
        await ResourceService(session, _actor()).replace_dependencies(resource_id, [dependency.id])
        await session.commit()
        dependency_id = dependency.id

    storage = ResourceStorage(tmp_path)
    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        draft = await publisher.save_filesystem_draft(resource_id, source_dir=_source(tmp_path), expected_revision=0)
        with pytest.raises(ResourceConflict, match="Required resource dependencies are not published"):
            await publisher.publish_filesystem(
                resource_id,
                expected_draft_revision=draft.revision,
                scan_result={"status": "clean"},
            )

    async with session_factory() as verification:
        resource = await verification.get(Resource, resource_id)
        versions = list((await verification.execute(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id))).scalars())
        assert resource is not None and resource.latest_version == 0
        assert versions == []
        assert await verification.get(ResourceDraft, resource_id) is not None
        assert not (storage.resources_root / f"agents/{resource_id}/versions/1").exists()
        assert (storage.resources_root / f"agents/{resource_id}/draft/1").is_dir()

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        skill_draft = await publisher.save_filesystem_draft(dependency_id, source_dir=_skill_source(tmp_path), expected_revision=0)
        await publisher.publish_filesystem(dependency_id, expected_draft_revision=skill_draft.revision, scan_result={"status": "clean"})

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        version = await publisher.publish_filesystem(
            resource_id,
            expected_draft_revision=draft.revision,
            scan_result={"status": "clean"},
        )

    assert version.version == 1
    async with session_factory() as verification:
        resource = await verification.get(Resource, resource_id)
        assert resource is not None and resource.latest_version == 1
        assert (storage.resources_root / version.storage_key).is_dir()


@pytest.mark.asyncio
async def test_dependency_conflict_after_publish_discards_the_unreferenced_directory(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_id = await _create_resource(session_factory)
    storage = ResourceStorage(tmp_path)

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        draft = await publisher.save_filesystem_draft(resource_id, source_dir=_source(tmp_path), expected_revision=0)

        checks = {"count": 0}

        async def dependency_deactivates_midflight(source: object) -> None:
            checks["count"] += 1
            if checks["count"] == 1:
                return
            raise ResourceConflict("Required resource dependencies are not published: helper-skill")

        monkeypatch.setattr(publisher.service, "assert_required_dependencies_ready", dependency_deactivates_midflight)
        with pytest.raises(ResourceConflict, match="Required resource dependencies are not published"):
            await publisher.publish_filesystem(
                resource_id,
                expected_draft_revision=draft.revision,
                scan_result={"status": "clean"},
            )

    async with session_factory() as verification:
        resource = await verification.get(Resource, resource_id)
        versions = list((await verification.execute(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id))).scalars())
        assert resource is not None and resource.latest_version == 0
        assert versions == []
        assert await verification.get(ResourceDraft, resource_id) is not None
        assert not (storage.resources_root / f"agents/{resource_id}/versions/1").exists()
        assert (storage.resources_root / f"agents/{resource_id}/draft/1").is_dir()


@pytest.mark.asyncio
async def test_database_dependency_conflict_keeps_draft_and_retries_same_revision(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async with session_factory() as session:
        workflow = await ResourceService(session, _actor()).create_resource(
            resource_type="workflow",
            slug="dependent-flow",
            display_name="Dependent Flow",
            storage_kind="database",
        )
        dependency = await ResourceService(session, _actor()).create_resource(
            resource_type="skill",
            slug="helper-skill-db",
            display_name="Helper Skill DB",
            storage_kind="filesystem",
        )
        await ResourceService(session, _actor()).replace_dependencies(workflow.id, [dependency.id])
        await session.commit()
        workflow_id, dependency_id = workflow.id, dependency.id

    content = {
        "schema_version": 2,
        "name": "dependent-flow",
        "entrypoint": "start",
        "nodes": [{"id": "start", "type": "action", "action": {"kind": "tool", "name": "noop"}}],
        "edges": [],
    }
    storage = ResourceStorage(tmp_path)
    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        draft = await publisher.save_database_draft(workflow_id, content=content, expected_revision=0)
        with pytest.raises(ResourceConflict, match="Required resource dependencies are not published"):
            await publisher.publish_database(
                workflow_id,
                expected_draft_revision=draft.revision,
                scan_result={"status": "valid"},
            )

    async with session_factory() as verification:
        resource = await verification.get(Resource, workflow_id)
        versions = list((await verification.execute(select(ResourceVersion).where(ResourceVersion.resource_id == workflow_id))).scalars())
        assert resource is not None and resource.latest_version == 0
        assert versions == []
        persisted = await verification.get(ResourceDraft, workflow_id)
        assert persisted is not None and persisted.revision == 1

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        skill_draft = await publisher.save_filesystem_draft(dependency_id, source_dir=_skill_source(tmp_path), expected_revision=0)
        await publisher.publish_filesystem(dependency_id, expected_draft_revision=skill_draft.revision, scan_result={"status": "clean"})

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        version = await publisher.publish_database(
            workflow_id,
            expected_draft_revision=1,
            scan_result={"status": "valid"},
        )

    assert version.version == 1
    async with session_factory() as verification:
        resource = await verification.get(Resource, workflow_id)
        assert resource is not None and resource.latest_version == 1


@pytest.mark.asyncio
async def test_knowledge_dependency_activation_unlocks_same_draft_retry(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    resource_id = await _create_resource(session_factory)
    async with session_factory() as session:
        knowledge_base = await ResourceService(session, _actor()).create_resource(
            resource_type="knowledge_base",
            slug="docs-kb",
            display_name="Docs KB",
            storage_kind="database",
        )
        await ResourceService(session, _actor()).replace_dependencies(resource_id, [knowledge_base.id])
        await session.commit()
        knowledge_base_id = knowledge_base.id

    storage = ResourceStorage(tmp_path)
    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        draft = await publisher.save_filesystem_draft(resource_id, source_dir=_source(tmp_path), expected_revision=0)
        with pytest.raises(ResourceConflict, match="Required resource dependencies are not published: docs-kb"):
            await publisher.publish_filesystem(
                resource_id,
                expected_draft_revision=draft.revision,
                scan_result={"status": "clean"},
            )

    async with session_factory() as verification:
        resource = await verification.get(Resource, resource_id)
        versions = list((await verification.execute(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id))).scalars())
        assert resource is not None and resource.latest_version == 0
        assert versions == []
        assert await verification.get(ResourceDraft, resource_id) is not None
        assert not (storage.resources_root / f"agents/{resource_id}/versions/1").exists()
        assert (storage.resources_root / f"agents/{resource_id}/draft/1").is_dir()

    async with session_factory() as session:
        revision = KnowledgeRevision(
            id="docs-kb-revision-1",
            knowledge_base_id=knowledge_base_id,
            revision_no=1,
            status="published",
            manifest_hash="a" * 64,
            manifest_json=[],
            provider_doc_map_json={},
            document_count=1,
            provider_dataset_id="docs-dataset-1",
            publish_attempt=1,
            created_by="owner",
        )
        session.add(revision)
        binding = await session.get(KnowledgeBase, knowledge_base_id)
        assert binding is not None
        binding.active_revision_id = revision.id
        await session.commit()

    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        version = await publisher.publish_filesystem(
            resource_id,
            expected_draft_revision=draft.revision,
            scan_result={"status": "clean"},
        )

    assert version.version == 1
    async with session_factory() as verification:
        resource = await verification.get(Resource, resource_id)
        assert resource is not None and resource.latest_version == 1
        assert (storage.resources_root / version.storage_key).is_dir()


@pytest.mark.asyncio
async def test_bundled_workflow_database_flow_draft_publish_and_rollback_succeed(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async with session_factory() as session:
        resource = await ResourceService(session, _actor()).create_resource(
            resource_type="workflow",
            slug="bundled-flow",
            display_name="Bundled Flow",
            storage_kind="database",
        )
        resource.provenance = "bundled"
        await session.commit()
        resource_id = resource.id

    storage = ResourceStorage(tmp_path)
    async with session_factory() as session:
        publisher = ResourcePublisher(ResourceService(session, _actor()), storage)
        content = {
            "schema_version": 2,
            "name": "bundled-flow",
            "entrypoint": "start",
            "nodes": [{"id": "start", "type": "action", "action": {"kind": "tool", "name": "noop"}}],
            "edges": [],
        }
        draft = await publisher.save_database_draft(resource_id, content=content, expected_revision=0)
        first = await publisher.publish_database(
            resource_id,
            expected_draft_revision=draft.revision,
            scan_result={"status": "valid"},
        )
        rolled_back = await publisher.rollback_database(resource_id, source_version=1)

    assert (first.version, rolled_back.version) == (1, 2)
    async with session_factory() as verification:
        resource = await verification.get(Resource, resource_id)
        assert resource is not None and resource.provenance == "bundled"
        assert resource.latest_version == 2
