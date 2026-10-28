"""Skill trigger preferences: user-isolated configuration and Server-side matching (#121).

Expected constants come from the frozen protocol documented in
``app.gateway.skill_trigger`` and from the pre-existing run-selection rules at
the #120 tip — one preferred Skill per Run snapshot (``selection_role`` CHECK),
the closure's visibility/published/cycle validation, the explicit selection's
hard ``skill_outside_agent_closure`` failure — never from implementation
output.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit tables
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
import deerflow.persistence.models  # noqa: F401 - register harness tables
from app.agentplatform.audit_model import AuditLog
from app.agentplatform.rbac_models import UserModel
from app.agentplatform.resource_models import Resource, ResourceDependency, ResourceVersion, RunResourceSnapshot
from app.agentplatform.resources.publisher import ResourcePublisher
from app.agentplatform.resources.runtime import ResourceStorage
from app.agentplatform.resources.service import ResourceAction, ResourceActor, ResourcePermissionDenied, ResourceService
from app.gateway.canonical_agent_run_preparation import prepare_canonical_agent_run
from app.gateway.routers import resources
from app.gateway.skill_trigger import (
    KEYWORD_MAX_CHARS,
    MAX_APPLICABLE_AGENTS,
    MAX_KEYWORDS,
    MAX_TRIGGERED_SKILLS_PER_RUN,
    PREFERENCE_MESSAGE_LIMIT,
    PRIORITY_MAX,
    PRIORITY_MIN,
    SkillTriggerPreferenceRepository,
    keyword_hit,
    message_text_from_input,
    preference_matches,
    select_preference,
    validate_preference_document,
)
from deerflow.persistence.base import Base

SKILL_MD = "---\nname: report-skill\ndescription: Build a weekly report\n---\n\n# Report skill\n"


def _actor(user_id: str) -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id="dept-a",
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


async def _engine_factory(tmp_path: Path, name: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


def _preference(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "skill_resource_id": "skill-1",
        "enabled": True,
        "keywords": ["report"],
        "always_inject": False,
        "applicable_agent_ids": [],
        "priority": 0,
    }
    fields.update(overrides)
    return fields


# --- Matching semantics: the documented rules ----------------------------


def test_matching_semantics_bind_documented_rules() -> None:
    """Enabled gate, agent applicability, empty-keyword always-inject, keyword hits."""
    preference = _preference()
    # A keyword hit matches.
    assert preference_matches(preference, agent_id="agent-1", message_text="please build the weekly report")
    # A non-match never injects (no false trigger).
    assert not preference_matches(preference, agent_id="agent-1", message_text="hello world")
    # Disabled preferences never match.
    assert not preference_matches(_preference(enabled=False), agent_id="agent-1", message_text="report")
    # Applicable-agent allowlist: empty means every Agent; otherwise membership is required.
    assert not preference_matches(_preference(applicable_agent_ids=["agent-1"]), agent_id="agent-2", message_text="report")
    assert preference_matches(_preference(applicable_agent_ids=["agent-1"]), agent_id="agent-1", message_text="report")
    # Empty keywords always inject — even with no message text at all.
    assert preference_matches(_preference(keywords=[]), agent_id="agent-1", message_text="")
    # always_inject matches regardless of keywords.
    assert preference_matches(_preference(always_inject=True), agent_id="agent-1", message_text="anything")
    # NFKC casefold discipline: full-width letters hit their ASCII keyword.
    assert keyword_hit(["report"], "ＲＥＰＯＲＴ please")
    assert not keyword_hit(["report"], "")


def test_selection_returns_the_single_highest_priority_match() -> None:
    """Priority wins; ties break on the smaller skill id; at most ONE match."""
    assert MAX_TRIGGERED_SKILLS_PER_RUN == 1
    low = _preference(skill_resource_id="skill-low", priority=1)
    high = _preference(skill_resource_id="skill-high", priority=10)
    tie_a = _preference(skill_resource_id="skill-b", priority=5)
    tie_b = _preference(skill_resource_id="skill-a", priority=5)
    assert select_preference([low, high], agent_id="a", message_text="report")["skill_resource_id"] == "skill-high"
    assert select_preference([tie_b, tie_a], agent_id="a", message_text="report")["skill_resource_id"] == "skill-a"
    chosen = select_preference([low, high, tie_a, tie_b], agent_id="a", message_text="report")
    assert chosen is not None and chosen["skill_resource_id"] == "skill-high"
    # No match at all → nothing is injected.
    assert select_preference([_preference(enabled=False)], agent_id="a", message_text="report") is None
    assert select_preference([], agent_id="a", message_text="report") is None


def test_message_text_extraction_bounded_to_this_run_request() -> None:
    """Only this request's user messages participate, bounded by the fixed limit."""
    run_input = {
        "messages": [
            {"type": "ai", "content": "earlier answer ignore me report"},
            {"type": "human", "content": "please build the weekly report"},
            {"type": "human", "content": [{"type": "text", "text": "second turn"}]},
        ]
    }
    text = message_text_from_input(run_input)
    assert "weekly report" in text
    assert "second turn" in text
    assert "earlier answer" not in text
    assert message_text_from_input(None) == ""
    assert message_text_from_input({"messages": "nope"}) == ""
    huge = "x" * (PREFERENCE_MESSAGE_LIMIT + 5000)
    assert len(message_text_from_input({"messages": [{"type": "human", "content": huge}]})) == PREFERENCE_MESSAGE_LIMIT


def test_preference_document_bounds_are_fixed_protocol_constants() -> None:
    assert MAX_KEYWORDS == 16
    assert KEYWORD_MAX_CHARS == 64
    assert MAX_APPLICABLE_AGENTS == 32
    assert (PRIORITY_MIN, PRIORITY_MAX) == (-1000, 1000)
    keywords, agents, priority = validate_preference_document(
        keywords=["  Report "], applicable_agent_ids=[str(uuid.uuid4())], priority=7
    )
    assert keywords == ["Report"] and priority == 7 and len(agents) == 1
    with pytest.raises(ValueError):
        validate_preference_document(keywords=["ok"] * (MAX_KEYWORDS + 1), applicable_agent_ids=[], priority=0)
    with pytest.raises(ValueError):
        validate_preference_document(keywords=["x" * (KEYWORD_MAX_CHARS + 1)], applicable_agent_ids=[], priority=0)
    with pytest.raises(ValueError):
        validate_preference_document(keywords=[""], applicable_agent_ids=[], priority=0)
    with pytest.raises(ValueError):
        validate_preference_document(keywords=["same", "SAME"], applicable_agent_ids=[], priority=0)
    with pytest.raises(ValueError):
        validate_preference_document(keywords=[], applicable_agent_ids=["not-a-uuid"], priority=0)
    with pytest.raises(ValueError):
        validate_preference_document(keywords=[], applicable_agent_ids=[str(uuid.uuid4())] * (MAX_APPLICABLE_AGENTS + 1), priority=0)
    for bad_priority in (PRIORITY_MAX + 1, PRIORITY_MIN - 1, "5", True, 1.5):
        with pytest.raises(ValueError):
            validate_preference_document(keywords=[], applicable_agent_ids=[], priority=bad_priority)


# --- CRUD contract: user isolation, owner-gated writes -------------------


async def _catalog_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[async_sessionmaker, str]:
    """One public published Skill owned by 'owner'; accounts 'runner' and 'runner-b'."""
    factory = await _engine_factory(tmp_path, "skill-prefs.db")
    async with factory() as session:
        session.add_all(
            [
                UserModel(id="owner", username="owner@test.com", role="user", department_id=None, disabled=False),
                UserModel(id="runner", username="runner@test.com", role="user", department_id=None, disabled=False),
                UserModel(id="runner-b", username="runner-b@test.com", role="user", department_id=None, disabled=False),
            ]
        )
        await session.commit()
        service = ResourceService(session, _actor("owner"))
        skill = await service.create_resource(resource_type="skill", slug="report-skill", display_name="Report skill", storage_kind="filesystem")
        await session.commit()
        publisher = ResourcePublisher(service, ResourceStorage(tmp_path))
        source = tmp_path / "skill-source"
        source.mkdir()
        (source / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        draft = await publisher.save_filesystem_draft(skill.id, source_dir=source, expected_revision=0)
        await publisher.publish_filesystem(skill.id, expected_draft_revision=draft.revision, scan_result={})
        skill.visibility = "public"
        await session.commit()
        skill_id = skill.id
    monkeypatch.setattr(resources, "_factory", lambda: factory)
    monkeypatch.setattr(resources, "get_paths", lambda: SimpleNamespace(base_dir=tmp_path))

    async def _audit(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(resources, "record_audit", _audit)
    return factory, skill_id


def _runner() -> UserModel:
    return UserModel(id="runner", username="runner@test.com", role="user", department_id=None, disabled=False)


async def _second_public_skill(tmp_path: Path, factory: async_sessionmaker) -> str:
    """One more published public Skill owned by 'owner' (for cap scenarios)."""
    async with factory() as session:
        service = ResourceService(session, _actor("owner"))
        skill = await service.create_resource(resource_type="skill", slug="second-skill", display_name="Second skill", storage_kind="filesystem")
        await session.commit()
        publisher = ResourcePublisher(service, ResourceStorage(tmp_path))
        source = tmp_path / "second-skill-source"
        source.mkdir()
        (source / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        draft = await publisher.save_filesystem_draft(skill.id, source_dir=source, expected_revision=0)
        await publisher.publish_filesystem(skill.id, expected_draft_revision=draft.revision, scan_result={})
        skill.visibility = "public"
        await session.commit()
        return skill.id


@pytest.mark.asyncio
async def test_put_creates_updates_and_lists_only_the_caller_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T121-01/T121-03 (config legs): upsert works and rows are user-isolated."""
    factory, skill_id = await _catalog_world(tmp_path, monkeypatch)
    body = resources.SkillTriggerPreferenceUpsert(keywords=["weekly report"], priority=5)
    await resources.put_skill_trigger_preference(skill_id, body, _runner())

    own = await resources.list_skill_trigger_preferences(_runner())
    assert own["total"] == 1
    row = own["items"][0]
    assert row["skill_resource_id"] == skill_id
    assert row["enabled"] is True
    assert row["keywords"] == ["weekly report"]
    assert row["always_inject"] is False
    assert row["applicable_agent_ids"] == []
    assert row["priority"] == 5
    assert row["skill"]["slug"] == "report-skill"
    assert row["skill"]["available"] is True
    # User isolation: another account sees none of this.
    other = await resources.list_skill_trigger_preferences(UserModel(id="runner-b", username="runner-b@test.com", role="user", department_id=None, disabled=False))
    assert other == {"items": [], "total": 0}

    # Upsert replaces the fields; the account still holds exactly one row.
    await resources.put_skill_trigger_preference(
        skill_id,
        resources.SkillTriggerPreferenceUpsert(enabled=False, always_inject=True, priority=-3),
        _runner(),
    )
    updated = await resources.list_skill_trigger_preferences(_runner())
    assert updated["total"] == 1
    assert updated["items"][0]["enabled"] is False
    assert updated["items"][0]["always_inject"] is True
    assert updated["items"][0]["keywords"] == []
    assert updated["items"][0]["priority"] == -3

    repository = SkillTriggerPreferenceRepository(factory)
    assert await repository.get("runner", skill_id) is not None
    await repository.delete("runner", skill_id)
    assert await resources.list_skill_trigger_preferences(_runner()) == {"items": [], "total": 0}
    # Delete is idempotent, including for rows the caller never had.
    await resources.delete_skill_trigger_preference(skill_id, _runner())
    await resources.delete_skill_trigger_preference(skill_id, UserModel(id="runner-b", username="runner-b@test.com", role="user", department_id=None, disabled=False))


@pytest.mark.asyncio
async def test_put_validates_visibility_type_and_unavailable_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T121-02 (configuration leg): invisible or non-Skill targets are refused."""
    factory, skill_id = await _catalog_world(tmp_path, monkeypatch)
    async with factory() as session:
        service = ResourceService(session, _actor("owner"))
        private_skill = await service.create_resource(resource_type="skill", slug="private-skill", display_name="Private", storage_kind="filesystem")
        await session.commit()
        source = tmp_path / "private-source"
        source.mkdir()
        (source / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        publisher = ResourcePublisher(service, ResourceStorage(tmp_path))
        draft = await publisher.save_filesystem_draft(private_skill.id, source_dir=source, expected_revision=0)
        await publisher.publish_filesystem(private_skill.id, expected_draft_revision=draft.revision, scan_result={})
        agent = await service.create_resource(resource_type="agent", slug="plain-agent", display_name="Agent", storage_kind="filesystem")
        await session.commit()
        agent.visibility = "public"
        await session.commit()
        private_id, agent_id = private_skill.id, agent.id

    # Another account's private Skill is invisible: configuring it must not even
    # disclose that it exists (404, not 403).
    with pytest.raises(HTTPException) as invisible:
        await resources.put_skill_trigger_preference(private_id, resources.SkillTriggerPreferenceUpsert(), _runner())
    assert invisible.value.status_code == 404
    with pytest.raises(HTTPException) as missing:
        await resources.put_skill_trigger_preference(str(uuid.uuid4()), resources.SkillTriggerPreferenceUpsert(), _runner())
    assert missing.value.status_code == 404
    # A non-Skill resource cannot carry a trigger preference.
    with pytest.raises(HTTPException) as wrong_type:
        await resources.put_skill_trigger_preference(agent_id, resources.SkillTriggerPreferenceUpsert(), _runner())
    assert wrong_type.value.status_code == 409


@pytest.mark.asyncio
async def test_model_rejects_out_of_bounds_documents_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        resources.SkillTriggerPreferenceUpsert(keywords=["x"] * (MAX_KEYWORDS + 1))
    with pytest.raises(ValidationError):
        resources.SkillTriggerPreferenceUpsert(keywords=["y" * 65])
    with pytest.raises(ValidationError):
        resources.SkillTriggerPreferenceUpsert(applicable_agent_ids=["nope"])
    with pytest.raises(ValidationError):
        resources.SkillTriggerPreferenceUpsert(priority=PRIORITY_MAX + 1)
    with pytest.raises(ValidationError):
        resources.SkillTriggerPreferenceUpsert(extra_field="nope")  # type: ignore[call-arg]
    factory, skill_id = await _catalog_world(tmp_path, monkeypatch)
    repository = SkillTriggerPreferenceRepository(factory)
    assert await repository.count("runner") == 0


@pytest.mark.asyncio
async def test_per_user_preference_cap_and_availability_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agentplatform.resource_models import SkillTriggerPreferenceRow
    from app.gateway.skill_trigger import MAX_PREFERENCES_PER_USER

    factory, skill_id = await _catalog_world(tmp_path, monkeypatch)
    repository = SkillTriggerPreferenceRepository(factory)
    # The caller's own row exists first: updates stay allowed at the cap.
    await resources.put_skill_trigger_preference(skill_id, resources.SkillTriggerPreferenceUpsert(), _runner())
    # Fill the rest of the cap (FK enforcement is off in these unit stores,
    # matching the projection-only nature of the bound).
    rows = [
        {
            "user_id": "runner",
            "skill_resource_id": str(uuid.uuid4()),
            "enabled": True,
            "keywords": [],
            "always_inject": False,
            "applicable_agent_ids": [],
            "priority": 0,
        }
        for _ in range(MAX_PREFERENCES_PER_USER - 1)
    ]
    async with factory() as session:
        session.add_all(SkillTriggerPreferenceRow(**row) for row in rows)
        await session.commit()
    assert await repository.count("runner") == MAX_PREFERENCES_PER_USER
    new_skill = await _second_public_skill(tmp_path, factory)
    with pytest.raises(HTTPException) as capped:
        await resources.put_skill_trigger_preference(new_skill, resources.SkillTriggerPreferenceUpsert(), _runner())
    assert capped.value.status_code == 409
    # Updating an existing row stays allowed at the cap.
    await resources.put_skill_trigger_preference(skill_id, resources.SkillTriggerPreferenceUpsert(priority=1), _runner())
    assert await repository.count("runner") == MAX_PREFERENCES_PER_USER

    # A suspended Skill reports available=False in the projection.
    async with factory() as session:
        resource = await session.get(Resource, skill_id)
        resource.lifecycle_status = "suspended"
        await session.commit()
    listed = await resources.list_skill_trigger_preferences(_runner())
    row = next(item for item in listed["items"] if item["skill_resource_id"] == skill_id)
    assert row["skill"]["available"] is False
    assert row["skill"]["slug"] == "report-skill"


@pytest.mark.asyncio
async def test_preference_grants_no_content_or_script_rights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T121-03: a preference never confers edit rights on the Skill's content."""
    factory, skill_id = await _catalog_world(tmp_path, monkeypatch)
    await resources.put_skill_trigger_preference(skill_id, resources.SkillTriggerPreferenceUpsert(), _runner())
    async with factory() as session:
        service = ResourceService(session, _actor("runner"))
        resource = await service.resolve_for_use(skill_id)
        with pytest.raises(ResourcePermissionDenied):
            service.assert_modify(resource)
    with pytest.raises(HTTPException) as denied:
        await resources.save_skill_draft(
            skill_id,
            resources.SkillDraftRequest(content=SKILL_MD.replace("weekly", "monthly"), expected_revision=1),
            _runner(),
        )
    assert denied.value.status_code == 403
    # The preference projection carries identity facts only — never content.
    listed = await resources.list_skill_trigger_preferences(_runner())
    serialized = str(listed)
    assert "# Report skill" not in serialized
    assert "scripts/analyze.py" not in serialized


# --- Run preparation: the frozen-selection seam --------------------------


async def _run_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[async_sessionmaker, str, str]:
    """Published public Agent + published public Skill joined by one dependency edge."""
    factory = await _engine_factory(tmp_path, "skill-trigger-run.db")
    async with factory() as session:
        session.add_all(
            [
                UserModel(id="owner", username="owner@test.com", role="user", department_id=None, disabled=False),
                UserModel(id="runner", username="runner@test.com", role="user", department_id=None, disabled=False),
            ]
        )
        await session.commit()
        service = ResourceService(session, _actor("owner"))
        skill = await service.create_resource(resource_type="skill", slug="report-skill", display_name="Report skill", storage_kind="filesystem")
        await session.commit()
        publisher = ResourcePublisher(service, ResourceStorage(tmp_path))
        skill_source = tmp_path / "skill-source"
        skill_source.mkdir()
        (skill_source / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        skill_draft = await publisher.save_filesystem_draft(skill.id, source_dir=skill_source, expected_revision=0)
        await publisher.publish_filesystem(skill.id, expected_draft_revision=skill_draft.revision, scan_result={})
        agent = await service.create_resource(resource_type="agent", slug="canonical-agent", display_name="Canonical Agent", storage_kind="filesystem")
        await session.commit()
        agent_source = tmp_path / "agent-source"
        agent_source.mkdir()
        (agent_source / "config.yaml").write_text("name: canonical-agent\n", encoding="utf-8")
        (agent_source / "SOUL.md").write_text("frozen soul\n", encoding="utf-8")
        agent_draft = await publisher.save_filesystem_draft(agent.id, source_dir=agent_source, expected_revision=0)
        await publisher.publish_filesystem(agent.id, expected_draft_revision=agent_draft.revision, scan_result={})
        session.add(ResourceDependency(id=str(uuid.uuid4()), source_resource_id=agent.id, target_resource_id=skill.id))
        skill.visibility = "public"
        agent.visibility = "public"
        await session.commit()
        return factory, agent.id, skill.id


def _runner_request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id="runner")))


def _monkeypatch_run_stack(monkeypatch: pytest.MonkeyPatch, factory: async_sessionmaker, tmp_path: Path) -> None:
    monkeypatch.setattr("deerflow.persistence.engine.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.gateway.audit.get_session_factory", lambda: factory)
    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))


@pytest.mark.asyncio
async def test_explicit_selection_keeps_the_hard_closure_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, agent_id, _skill_id = await _run_world(tmp_path, monkeypatch)
    _monkeypatch_run_stack(monkeypatch, factory, tmp_path)
    with pytest.raises(HTTPException) as rejected:
        await prepare_canonical_agent_run(agent_id, _runner_request(), str(uuid.uuid4()), preferred_skill="not-in-closure")
    assert rejected.value.status_code == 409
    assert rejected.value.detail["code"] == "skill_outside_agent_closure"
    async with factory() as session:
        audit = (await session.execute(select(AuditLog).where(AuditLog.action == "run_preparation_rejected"))).scalar_one()
        assert audit.detail is not None and "skill_outside_agent_closure" in audit.detail


@pytest.mark.asyncio
async def test_preference_origin_selects_closure_skill_and_audits_frozen_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, agent_id, skill_id = await _run_world(tmp_path, monkeypatch)
    _monkeypatch_run_stack(monkeypatch, factory, tmp_path)
    run_id = str(uuid.uuid4())
    factory_callable = await prepare_canonical_agent_run(
        agent_id,
        _runner_request(),
        run_id,
        preferred_skill=skill_id,
        preferred_skill_origin="preference",
    )
    assert callable(factory_callable)
    async with factory() as session:
        snapshots = list((await session.execute(select(RunResourceSnapshot).where(RunResourceSnapshot.run_id == run_id))).scalars())
        by_role = {item.resource_id: item.selection_role for item in snapshots}
        assert by_role[agent_id] == "root"
        assert by_role[skill_id] == "preferred"
        version = (await session.execute(select(ResourceVersion).where(ResourceVersion.resource_id == skill_id))).scalar_one()
        applied = (await session.execute(select(AuditLog).where(AuditLog.action == "skill_trigger_preference_applied"))).scalar_one()
        assert applied.detail is not None
        applied_detail = json.loads(applied.detail)
        assert applied_detail["origin"] == "preference"
        assert applied_detail["version"] == 1
        assert applied_detail["content_hash"] == version.content_hash


@pytest.mark.asyncio
async def test_preference_origin_skips_skill_outside_closure_without_failing_the_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T121-02 (trigger leg): a Skill outside THIS Agent's closure is skipped, never activated."""
    factory, agent_id, _skill_id = await _run_world(tmp_path, monkeypatch)
    _monkeypatch_run_stack(monkeypatch, factory, tmp_path)
    # A published Skill that is visible to the caller but is NOT a dependency
    # of this Agent — the realistic stale-preference shape.
    outside_id = await _second_public_skill(tmp_path, factory)
    run_id = str(uuid.uuid4())
    factory_callable = await prepare_canonical_agent_run(
        agent_id,
        _runner_request(),
        run_id,
        preferred_skill=outside_id,
        preferred_skill_origin="preference",
    )
    assert callable(factory_callable)
    async with factory() as session:
        snapshots = list((await session.execute(select(RunResourceSnapshot).where(RunResourceSnapshot.run_id == run_id))).scalars())
        # The frozen closure is there, but no snapshot carries the preference's
        # Skill and nothing is marked preferred.
        assert {item.resource_id for item in snapshots} != set()
        assert all(item.resource_id != outside_id for item in snapshots)
        assert all(item.selection_role != "preferred" for item in snapshots)
        skipped = (await session.execute(select(AuditLog).where(AuditLog.action == "skill_trigger_preference_skipped"))).scalar_one()
        assert skipped.detail is not None
        skipped_detail = json.loads(skipped.detail)
        assert skipped_detail["reason"] == "skill_outside_agent_closure"
        assert skipped_detail["requested_skill"] == outside_id
        assert (await session.execute(select(AuditLog).where(AuditLog.action == "run_preparation_rejected"))).scalars().all() == []


@pytest.mark.asyncio
async def test_run_still_refuses_when_a_required_closure_dependency_becomes_invisible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T121-02: the pre-existing dependency-visibility rule is untouched by preferences.

    When a Skill that the Agent's closure REQUIRES becomes invisible to the
    caller, the closure walk refuses the Run (404) — a preference never
    rescues it and nothing is activated.
    """
    factory, agent_id, skill_id = await _run_world(tmp_path, monkeypatch)
    _monkeypatch_run_stack(monkeypatch, factory, tmp_path)
    async with factory() as session:
        skill = await session.get(Resource, skill_id)
        skill.visibility = "private"
        await session.commit()
    run_id = str(uuid.uuid4())
    with pytest.raises(HTTPException) as refused:
        await prepare_canonical_agent_run(
            agent_id,
            _runner_request(),
            run_id,
            preferred_skill=skill_id,
            preferred_skill_origin="preference",
        )
    assert refused.value.status_code == 404
    async with factory() as session:
        snapshots = list((await session.execute(select(RunResourceSnapshot).where(RunResourceSnapshot.run_id == run_id))).scalars())
        assert snapshots == []
        applied = (await session.execute(select(AuditLog).where(AuditLog.action == "skill_trigger_preference_applied"))).scalars().all()
        assert applied == []


@pytest.mark.asyncio
async def test_unpublished_dependency_cannot_be_activated_by_any_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T121-02: an unpublished Skill dependency is refused by the existing closure rule."""
    factory, agent_id, _skill_id = await _run_world(tmp_path, monkeypatch)
    _monkeypatch_run_stack(monkeypatch, factory, tmp_path)
    async with factory() as session:
        service = ResourceService(session, _actor("owner"))
        draft_skill = await service.create_resource(resource_type="skill", slug="draft-skill", display_name="Draft", storage_kind="filesystem")
        await session.commit()
        session.add(ResourceDependency(id=str(uuid.uuid4()), source_resource_id=agent_id, target_resource_id=draft_skill.id))
        draft_skill.visibility = "public"
        await session.commit()
        draft_id = draft_skill.id
    # Even a preference naming the unpublished Skill cannot help: the closure
    # walk itself refuses the Run (409 "no published version").
    with pytest.raises(HTTPException) as refused:
        await prepare_canonical_agent_run(
            agent_id,
            _runner_request(),
            str(uuid.uuid4()),
            preferred_skill=draft_id,
            preferred_skill_origin="preference",
        )
    assert refused.value.status_code == 409
    with pytest.raises(HTTPException) as explicit:
        await prepare_canonical_agent_run(agent_id, _runner_request(), str(uuid.uuid4()), preferred_skill=draft_id)
    assert explicit.value.status_code == 409


@pytest.mark.asyncio
async def test_new_versions_and_preference_changes_never_drift_a_frozen_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T121-04: the in-flight Run keeps V1; a new Run resolves V2 under the new state."""
    factory, agent_id, skill_id = await _run_world(tmp_path, monkeypatch)
    _monkeypatch_run_stack(monkeypatch, factory, tmp_path)
    repository = SkillTriggerPreferenceRepository(factory)
    frozen_run = str(uuid.uuid4())
    await prepare_canonical_agent_run(agent_id, _runner_request(), frozen_run, preferred_skill=skill_id, preferred_skill_origin="preference")

    # The world moves: the preference is rewritten and a V2 is published.
    await repository.upsert("runner", skill_id, enabled=False, keywords=[], always_inject=False, applicable_agent_ids=[], priority=99)
    async with factory() as session:
        service = ResourceService(session, _actor("owner"))
        publisher = ResourcePublisher(service, ResourceStorage(tmp_path))
        source = tmp_path / "skill-source-2"
        source.mkdir()
        (source / "SKILL.md").write_text(SKILL_MD.replace("weekly", "monthly"), encoding="utf-8")
        draft = await publisher.save_filesystem_draft(skill_id, source_dir=source, expected_revision=1)
        await publisher.publish_filesystem(skill_id, expected_draft_revision=draft.revision, scan_result={})

    async with factory() as session:
        frozen_snapshots = {
            item.resource_id: (item.version, item.content_hash)
            for item in (await session.execute(select(RunResourceSnapshot).where(RunResourceSnapshot.run_id == frozen_run))).scalars()
        }
        first_version = (await session.execute(select(ResourceVersion).where(ResourceVersion.resource_id == skill_id).order_by(ResourceVersion.version))).scalars().all()
        assert [row.version for row in first_version] == [1, 2]
    # The frozen run still carries V1 exactly as enqueued.
    assert frozen_snapshots[skill_id][0] == 1

    # A new Run under the disabled preference carries no preferred Skill, and
    # an explicit selection of the same Skill freezes V2.
    new_run = str(uuid.uuid4())
    await prepare_canonical_agent_run(agent_id, _runner_request(), new_run)
    async with factory() as session:
        new_snapshots = {item.resource_id: item.selection_role for item in (await session.execute(select(RunResourceSnapshot).where(RunResourceSnapshot.run_id == new_run))).scalars()}
        assert new_snapshots.get(skill_id) == "resolved"
        explicit_run = str(uuid.uuid4())
        await prepare_canonical_agent_run(agent_id, _runner_request(), explicit_run, preferred_skill=skill_id)
        explicit_snapshots = {
            item.resource_id: item.version
            for item in (await session.execute(select(RunResourceSnapshot).where(RunResourceSnapshot.run_id == explicit_run))).scalars()
        }
        assert explicit_snapshots[skill_id] == 2


# --- prepare_run integration: matching happens Server-side, once ---------


def _run_body(agent_id: str, message: str = "please build the weekly report", context: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        assistant_id=agent_id,
        input={"messages": [{"type": "human", "content": message}]},
        context=context or {},
        metadata=None,
    )


def _authed_request(user_id: str = "runner") -> MagicMock:
    request = MagicMock()
    request.state.user = SimpleNamespace(id=user_id)
    return request


@pytest.mark.asyncio
async def test_prepare_run_applies_the_preference_match_without_explicit_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, agent_id, skill_id = await _run_world(tmp_path, monkeypatch)
    _monkeypatch_run_stack(monkeypatch, factory, tmp_path)
    await SkillTriggerPreferenceRepository(factory).upsert(
        "runner",
        skill_id,
        enabled=True,
        keywords=["weekly report"],
        always_inject=False,
        applicable_agent_ids=[],
        priority=1,
    )
    from app.gateway import run_preparation as prep

    prepared_factory = MagicMock()
    mock_prepare = AsyncMock(return_value=prepared_factory)
    with (
        patch.object(prep, "_prepare_canonical_agent_run", new=mock_prepare),
        patch.object(prep, "_canonical_selection_metadata", new=AsyncMock(return_value={})),
    ):
        prepared = await prep.prepare_run(_run_body(agent_id), "thread-1", _authed_request())
    mock_prepare.assert_awaited_once()
    kwargs = mock_prepare.await_args.kwargs
    assert kwargs["preferred_skill"] == skill_id
    assert kwargs["preferred_skill_origin"] == "preference"
    assert prepared.body_context["skill_resource_id"] == skill_id

    # A non-matching message triggers nothing — no false injection.
    mock_prepare = AsyncMock(return_value=prepared_factory)
    with (
        patch.object(prep, "_prepare_canonical_agent_run", new=mock_prepare),
        patch.object(prep, "_canonical_selection_metadata", new=AsyncMock(return_value={})),
    ):
        await prep.prepare_run(_run_body(agent_id, message="hello world"), "thread-2", _authed_request())
    kwargs = mock_prepare.await_args.kwargs
    assert "preferred_skill" not in kwargs


@pytest.mark.asyncio
async def test_prepare_run_explicit_selection_wins_and_store_failure_degrades(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, agent_id, skill_id = await _run_world(tmp_path, monkeypatch)
    _monkeypatch_run_stack(monkeypatch, factory, tmp_path)
    await SkillTriggerPreferenceRepository(factory).upsert(
        "runner",
        skill_id,
        enabled=True,
        keywords=[],
        always_inject=False,
        applicable_agent_ids=[],
        priority=1,
    )
    from app.gateway import run_preparation as prep

    # The explicit request-context selection bypasses preference matching.
    mock_prepare = AsyncMock(return_value=MagicMock())
    with (
        patch.object(prep, "_prepare_canonical_agent_run", new=mock_prepare),
        patch.object(prep, "_canonical_selection_metadata", new=AsyncMock(return_value={})),
    ):
        await prep.prepare_run(_run_body(agent_id, context={"skill_resource_id": "requested"}), "thread-3", _authed_request())
    kwargs = mock_prepare.await_args.kwargs
    assert kwargs["preferred_skill"] == "requested"
    assert kwargs["preferred_skill_origin"] == "explicit"

    # A preference store hiccup degrades to "no trigger", never a Run failure.
    monkeypatch.setattr("deerflow.persistence.engine.get_session_factory", lambda: None)
    mock_prepare = AsyncMock(return_value=MagicMock())
    with (
        patch.object(prep, "_prepare_canonical_agent_run", new=mock_prepare),
        patch.object(prep, "_canonical_selection_metadata", new=AsyncMock(return_value={})),
    ):
        await prep.prepare_run(_run_body(agent_id), "thread-4", _authed_request())
    kwargs = mock_prepare.await_args.kwargs
    assert "preferred_skill" not in kwargs
