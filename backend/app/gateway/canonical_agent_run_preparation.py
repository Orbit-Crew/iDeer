"""Canonical Agent Run preparation.

This module is the single gateway seam for resolving an authorized Agent,
freezing its dependency closure, and preparing the frozen runtime view before
the Run record becomes visible to the worker.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, Request

from app.gateway.authz import _cached_rbac_identity
from app.gateway.local_knowledge import build_local_knowledge_specs


def _scope_restriction(context: dict[str, Any], key: str) -> set[str] | None:
    """Read an optional logical/provider KB restriction from run context."""

    value = context.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {item for item in value if isinstance(item, str) and item.strip()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return {item for item in value if isinstance(item, str) and item.strip()}
    return set()


class SelectedSkillOutsideClosure(Exception):
    """Diagnostic-only conflict for an Expert/Skill mismatch."""

    def __init__(
        self,
        *,
        agent: dict[str, str],
        requested_skill: str,
        available_skills: list[dict[str, str]],
    ) -> None:
        self.agent = agent
        self.requested_skill = requested_skill
        self.available_skills = available_skills


def build_frozen_knowledge_bindings(
    closure: list[Any],
    *,
    caller_user_id: str,
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    """Freeze KB → dataset bindings from the closure's resolved revisions.

    Provider-backed revisions keep their frozen provider dataset with the
    revision's own document allowlist. A device-local import revision (#113)
    binds to a ``local:<revision_id>`` dataset only when the run caller owns
    the KB and the manifest names exactly one importing device; anything else
    stays omitted, so an unauthorized or unrouteable KB remains invisible to
    the model instead of failing the Run.
    """

    from app.agentplatform.knowledge.revisions import is_local_import_revision
    from app.gateway.local_knowledge import local_dataset_token

    bindings: dict[str, str] = {}
    ready_document_ids: dict[str, list[str]] = {}
    retrieval_profiles: dict[str, dict[str, object]] = {}
    revision_metadata: dict[str, dict[str, object]] = {}
    for item in closure:
        revision = item.knowledge_revision
        if revision is None:
            continue
        resource = item.resource
        if is_local_import_revision(revision):
            if str(resource.owner_id) != str(caller_user_id):
                continue
            device_ids = sorted({
                str(entry["metadata"].get("device_id"))
                for entry in (revision.manifest_json or [])
                if isinstance(entry, dict) and isinstance(entry.get("metadata"), dict) and entry["metadata"].get("device_id")
            })
            if len(device_ids) != 1 or not device_ids[0]:
                continue
            documents = {
                str(entry["document_id"]): {
                    "logical_document_id": str(entry["document_id"]),
                    "display_name": str(entry.get("filename") or ""),
                    "content_hash": str(entry.get("content_hash") or ""),
                }
                for entry in (revision.manifest_json or [])
                if isinstance(entry, dict) and entry.get("document_id") and entry.get("filename") and entry.get("content_hash")
            }
            if not documents:
                continue
            dataset = local_dataset_token(revision.id)
            bindings[resource.id] = dataset
            ready_document_ids[dataset] = sorted(documents)
            revision_metadata[dataset] = {
                "knowledge_base_id": resource.id,
                "revision_id": revision.id,
                "revision_no": revision.revision_no,
                "manifest_hash": revision.manifest_hash,
                "configuration_source": "frozen_run_revision",
                "origin": "local_import",
                "device_id": device_ids[0],
                "documents": documents,
            }
            continue
        if not revision.provider_dataset_id:
            continue
        bindings[resource.id] = revision.provider_dataset_id
        ready_document_ids[revision.provider_dataset_id] = [str(provider_document_id) for provider_document_id in (revision.provider_doc_map_json or {}).values()]
        profiles = next(
            (entry.get("knowledge_profiles") for entry in (revision.manifest_json or []) if isinstance(entry, dict) and isinstance(entry.get("knowledge_profiles"), dict)),
            {},
        )
        retrieval = profiles.get("retrieval") if isinstance(profiles, dict) else None
        if isinstance(retrieval, dict):
            retrieval_profiles[revision.provider_dataset_id] = dict(retrieval)
        revision_metadata[revision.provider_dataset_id] = {
            "knowledge_base_id": resource.id,
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "manifest_hash": revision.manifest_hash,
            "configuration_source": "frozen_run_revision",
            "documents": {
                str(provider_document_id): {
                    "logical_document_id": str(document_id),
                    "display_name": next(
                        (entry.get("filename") for entry in (revision.manifest_json or []) if isinstance(entry, dict) and str(entry.get("document_id")) == str(document_id)),
                        None,
                    ),
                    "content_hash": next(
                        (entry.get("content_hash") for entry in (revision.manifest_json or []) if isinstance(entry, dict) and str(entry.get("document_id")) == str(document_id)),
                        None,
                    ),
                }
                for document_id, provider_document_id in (revision.provider_doc_map_json or {}).items()
            },
        }
    return bindings, ready_document_ids, retrieval_profiles, revision_metadata


async def prepare_canonical_agent_run(
    resource_id: str,
    request: Request,
    run_id: str,
    preferred_skill: str | None = None,
    preferred_skill_origin: str = "explicit",
    diagnostic_context: dict[str, Any] | None = None,
    thread_id: str | None = None,
) -> Any:
    """Prepare one canonical Agent Run from the authenticated user's view.

    ``preferred_skill_origin`` distinguishes the two selection entries #121
    must validate with the same rules: ``"explicit"`` (a request-context
    selection — the existing hard 409 on a closure miss) and ``"preference"``
    (a user trigger-preference match — the same closure validation, but a miss
    is audited and the Run proceeds WITHOUT the Skill, because an automatic
    trigger must never fail a Run nor activate beyond authority).
    """

    from agentplatform_extension.knowledge.scope import KnowledgeScope
    from sqlalchemy import select

    from app.agentplatform.knowledge.scope import (
        calculate_effective_knowledge_scope,
        deployment_allowed_datasets,
    )
    from app.agentplatform.rbac_models import UserModel
    from app.agentplatform.resource_runtime import (
        CanonicalResourceLoader,
        ResourceRuntimeError,
        ResourceStorage,
    )
    from app.agentplatform.resource_service import (
        ResourceActor,
        ResourceConflict,
        ResourceNotFound,
        ResourcePermissionDenied,
        ResourceService,
        VisibilityClosureError,
    )
    from app.agentplatform.resources.actors import actor_from_user, role_permissions
    from app.agentplatform.runtime_adapter import build_canonical_agent_factory
    from deerflow.config.app_config import get_app_config
    from deerflow.config.paths import get_paths
    from deerflow.persistence.engine import get_session_factory

    user_id = getattr(getattr(request.state, "user", None), "id", None)
    if user_id is None:
        raise HTTPException(401, "Authentication required")
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(503, "Resource persistence is unavailable")
    try:
        async with session_factory() as session:
            # T2: reuse the identity _authenticate already resolved instead of
            # issuing a duplicate UserModel SELECT on every first turn.
            cached = _cached_rbac_identity(request, str(user_id))
            if cached is not None:
                actor = ResourceActor(
                    user_id=cached["user_id"],
                    department_id=cached["department_id"],
                    role=cached["role"],
                    permissions=role_permissions(cached["role"]),
                    tool_groups=None,
                )
            else:
                user = (
                    await session.execute(
                        select(UserModel).where(
                            UserModel.id == str(user_id),
                            UserModel.disabled.is_not(True),
                        )
                    )
                ).scalar_one_or_none()
                if user is None:
                    raise ResourcePermissionDenied("Active RBAC user is required")
                actor = actor_from_user(user)
            service = ResourceService(session, actor)
            # T3: resolve the closure once — it serves the Skill check below
            # and the snapshot freeze, instead of walking the graph twice.
            closure = await service.resolve_dependency_closure(resource_id)
            selected_skill_id = None
            if preferred_skill:
                selected = next(
                    (item.resource for item in closure if item.resource.id == preferred_skill or item.resource.slug == preferred_skill),
                    None,
                )
                if selected is None or selected.type != "skill":
                    agent = next(item.resource for item in closure if item.resource.id == resource_id)
                    available_skills = [{"resource_id": item.resource.id, "slug": item.resource.slug} for item in closure if item.resource.type == "skill"]
                    if preferred_skill_origin == "preference":
                        # A preference is auto-trigger metadata: the same
                        # visibility/published/closure validation applies, but
                        # the outcome of a miss is "not activated" — the Run
                        # proceeds without it and the skip is audited. The user
                        # message text is never persisted.
                        from app.gateway.audit import record_audit

                        await record_audit(
                            str(user_id),
                            "skill_trigger_preference_skipped",
                            resource_type="skill",
                            resource_id=str(preferred_skill),
                            detail={
                                "agent": {"resource_id": agent.id, "slug": agent.slug},
                                "requested_skill": str(preferred_skill),
                                "reason": "skill_outside_agent_closure",
                                "run_attempt_id": run_id,
                                "thread_id": thread_id,
                            },
                        )
                        preferred_skill = None
                    else:
                        raise SelectedSkillOutsideClosure(
                            agent={"resource_id": agent.id, "slug": agent.slug},
                            requested_skill=str(preferred_skill),
                            available_skills=available_skills,
                        )
                else:
                    selected_skill_id = selected.id
            await service.create_run_snapshot(
                run_id,
                resource_id,
                selected_resource_id=selected_skill_id,
                closure=closure,
            )
            storage = ResourceStorage(get_paths().base_dir)
            loader = CanonicalResourceLoader(session, storage)
            definition = await loader.load_agent(run_id, resource_id)
            skill_definitions = await loader.load_agent_skill_definitions(run_id, resource_id, definition=definition)
            skills = [value.skill for value in skill_definitions]
            knowledge_resources = {item.resource.id: item.resource for item in closure if item.resource.type == "knowledge_base"}
            # LIVE/PINNED bindings come from the revision resolved into the
            # closure (frozen at enqueue), never from the mutable draft
            # dataset binding; the allowlist is the revision's own document
            # set. A KB without a published revision was already rejected by
            # closure resolution. Device-local import revisions (#113) bind
            # only for the owning caller with one importing device.
            bindings, ready_document_ids, retrieval_profiles, revision_metadata = build_frozen_knowledge_bindings(
                closure,
                caller_user_id=str(user_id),
            )
            run_context = diagnostic_context or {}
            try:
                tool_config = get_app_config().get_tool_config("knowledge_search")
            except Exception:
                # A deployment policy that cannot be read must deny retrieval;
                # treating it as absent would turn a configuration failure into
                # an authorization bypass.
                tool_config = None
            deployment_allowed = deployment_allowed_datasets(tool_config)
            # The scope is keyed by canonical KB UUIDs. Slugs are display
            # aliases and may collide across owners/departments.
            caller_allowed = set(knowledge_resources)
            knowledge_scope = calculate_effective_knowledge_scope(
                bindings,
                caller_allowed=caller_allowed,
                workflow_allowed=_scope_restriction(run_context, "knowledge_scope"),
                runtime_allowed=_scope_restriction(run_context, "runtime_knowledge_scope"),
                deployment_allowed=deployment_allowed,
            )
            knowledge_scope = {logical: dataset for logical, dataset in knowledge_scope.items() if ready_document_ids.get(dataset)}
            await asyncio.to_thread(
                storage.create_run_skill_view,
                run_id,
                [(value.resource_id, value.version, value.content_hash) for value in skill_definitions],
                aliases={value.resource_id: value.skill.name for value in skill_definitions},
            )
            if selected_skill_id is not None and preferred_skill_origin == "preference":
                # Evidence for the preference-triggered injection: the frozen
                # identity the Run actually carries (version/hash from the
                # snapshot). Read before the commit; recorded after it — the
                # audit writes on its own connection and must never contend
                # with this transaction's write lock.
                frozen = next(
                    (item for item in closure if item.resource.id == selected_skill_id),
                    None,
                )
                applied_audit = (
                    str(user_id),
                    {
                        "agent": {"resource_id": resource_id},
                        "origin": "preference",
                        "version": frozen.version.version if frozen is not None else None,
                        "content_hash": frozen.version.content_hash if frozen is not None else None,
                        "run_attempt_id": run_id,
                        "thread_id": thread_id,
                    },
                )
            else:
                applied_audit = None
            await session.commit()
        if applied_audit is not None:
            from app.gateway.audit import record_audit

            await record_audit(
                applied_audit[0],
                "skill_trigger_preference_applied",
                resource_type="skill",
                resource_id=selected_skill_id,
                detail=applied_audit[1],
            )
        local_authorization = None
        local_tool_executor = None
        local_context = run_context.get("local_authorization")
        local_device_id = run_context.get("local_device_id")
        local_tool_descriptors = run_context.get("local_tool_descriptors")
        if isinstance(local_context, dict) and local_device_id:
            from app.agentplatform.resources.service import ResourceAction
            from app.gateway.local_workspace_policy import agent_workspace_capabilities, platform_workspace_capabilities

            # Published Agent configuration and the authenticated actor are the
            # authority. Request dictionaries may only narrow these grants.
            workspace_root = run_context.get("local_workspace_root")
            if workspace_root:
                local_context["agent_capabilities"] = sorted(agent_workspace_capabilities(definition.config) & set(local_context.get("agent_capabilities", ())))
                local_context["caller_capabilities"] = sorted(platform_workspace_capabilities() & set(local_context.get("caller_capabilities", ()))) if ResourceAction.USE in actor.permissions else []
                local_context["platform_capabilities"] = sorted(platform_workspace_capabilities() & set(local_context.get("platform_capabilities", ())))
            local_tool_descriptors = dict(local_tool_descriptors or {})
            workspace_root = run_context.get("local_workspace_root")
            if workspace_root:
                for capability in platform_workspace_capabilities():
                    local_tool_descriptors[capability] = {"workspace_description": f" Selected logical directory: {workspace_root}."}
            from agentplatform_extension.local_runtime import (
                LocalAuthorization,
                LocalToolExecutor,
                RunAuthorizationSnapshot,
            )
            from agentplatform_extension.local_runtime.routing import (
                DeviceRoute,
                RunDeviceRouter,
            )

            factors = {
                key: frozenset(str(item) for item in local_context.get(key, ()))
                for key in (
                    "agent_capabilities",
                    "caller_capabilities",
                    "device_capabilities",
                    "local_policy_capabilities",
                    "workflow_capabilities",
                    "platform_capabilities",
                )
            }
            local_authorization = LocalAuthorization(
                **factors,
                device_online=bool(local_context.get("device_online", True)),
            )
            snapshot = RunAuthorizationSnapshot(
                run_id=run_id,
                thread_id=str(thread_id or "canonical"),
                device_id=str(local_device_id),
                policy_version=str(local_context.get("policy_version", "runtime-default")),
                authorization=local_authorization,
            )
            route = RunDeviceRouter(DeviceRoute(str(local_device_id)), local_authorization)

            async def send_local(device_id: str, capability: str, payload: dict[str, Any]) -> Any:
                from agentplatform_extension.evidence import current_tool_call_evidence

                from app.device_control.broker import TaskStatus, get_device_broker
                from app.gateway.local_workspace_policy import WORKSPACE_CAPABILITIES

                if capability in WORKSPACE_CAPABILITIES and not workspace_root:
                    from langchain_core.tools import ToolException

                    raise ToolException("CANONICAL_WORKSPACE_REQUIRED")
                broker = get_device_broker()
                connection = broker.connections.get(device_id) if workspace_root else None
                if workspace_root:
                    if connection is None or not connection.tasks_allowed or connection.owner_id != str(user_id) or capability not in connection.capabilities or capability not in platform_workspace_capabilities():
                        from langchain_core.tools import ToolException

                        raise ToolException("LOCAL_AUTHORIZATION_DENIED")
                    async with session_factory() as current_session:
                        current_user = (await current_session.execute(select(UserModel).where(UserModel.id == str(user_id), UserModel.disabled.is_not(True)))).scalar_one_or_none()
                        if current_user is None or ResourceAction.USE not in role_permissions(current_user.role):
                            from langchain_core.tools import ToolException

                            raise ToolException("LOCAL_AUTHORIZATION_DENIED")
                    if capability not in snapshot.effective:
                        from langchain_core.tools import ToolException

                        raise ToolException("LOCAL_AUTHORIZATION_DENIED")
                record = await broker.send_task(
                    device_id=device_id,
                    operation=capability,
                    path=payload.get("path", ""),
                    run_id=run_id,
                    tool_call_id=str(current_tool_call_evidence() or payload.get("tool_call_id") or ""),
                    expires_in=timedelta(seconds=305) if capability == "local.files.write" else timedelta(minutes=5),
                    payload_extra={
                        "arguments": {key: value for key, value in payload.items() if key not in {"run_id", "tool_call_id"}},
                        "operation": capability,
                        "thread_id": str(thread_id or "canonical"),
                    },
                    authorization_snapshot=snapshot.as_mapping(),
                )
                try:
                    while record.status in {
                        TaskStatus.CREATED,
                        TaskStatus.SENT,
                        TaskStatus.ACKED,
                        TaskStatus.CONSENT_REQUIRED,
                        TaskStatus.CANCEL_REQUESTED,
                        TaskStatus.PROGRESS,
                    }:
                        await asyncio.sleep(0.05)
                        record = broker.get_task(record.task_id)
                except asyncio.CancelledError:
                    await asyncio.shield(broker.cancel_task(record.task_id))
                    raise
                if record.receipt is not None:
                    from agentplatform_extension.evidence import (
                        record_local_execution_receipt,
                    )

                    record_local_execution_receipt(
                        record.receipt,
                        tool_call_id=record.tool_call_id or None,
                    )
                if record.status is not TaskStatus.COMPLETED:
                    from langchain_core.tools import ToolException

                    raise ToolException(record.error_code or "LOCAL_TASK_" + record.status.value.upper())
                return record.result

            local_tool_executor = LocalToolExecutor(local_authorization, route, send_local)

        # Issue 113: device-local KBs schedule retrieval to the one importing
        # device through the same broker discipline as local file tasks — the
        # payload carries frozen identity fields only, the device's unique
        # Runtime re-validates every document hash, and results outside the
        # frozen manifest are dropped before any receipt is built.
        # Issue 114: a failed local leg is a structured source failure instead
        # of a tool error — it must never impersonate "no material". Runs with
        # other authorized datasets proceed marked incomplete; local-only runs
        # pause. Scope, attribution, and receipts stay the frozen closure's.
        local_knowledge_search = None
        # knowledge_scope maps logical KB id → dataset token; the dispatch
        # specs are keyed by dataset token, so the membership check runs
        # against the bound datasets (a latent #113 filter bug fixed here —
        # checking the keys would silently drop every local dispatch).
        knowledge_specs = {
            dataset: spec
            for dataset, spec in build_local_knowledge_specs(revision_metadata).items()
            if dataset in set(knowledge_scope.values())
        }
        if knowledge_specs:
            from agentplatform_extension.knowledge.scope import is_local_dataset
            from langchain_core.tools import ToolException

            from app.agentplatform.resources.service import ResourceAction
            from app.device_control.broker import TaskStatus, get_device_broker
            from app.gateway.hybrid_knowledge import (
                local_retrieval_pause_result,
                local_source_unavailable_result,
                requires_local_material,
                source_attribution,
            )
            from app.gateway.local_knowledge import (
                LOCAL_KNOWLEDGE_OPERATION,
                search_task_payload,
                validate_local_search_result,
            )
            local_required = requires_local_material(knowledge_scope)

            def _source_failure(dataset_id: str, error_code: str) -> dict[str, Any]:
                attribution = source_attribution(dataset_id, revision_metadata.get(dataset_id) or {})
                if local_required and is_local_dataset(dataset_id):
                    return local_retrieval_pause_result(attribution, error_code)
                return local_source_unavailable_result(attribution, error_code)

            async def search_local_knowledge(query: str, dataset_id: str) -> Any:
                from agentplatform_extension.evidence import current_tool_call_evidence

                spec = knowledge_specs.get(dataset_id)
                if spec is None:
                    raise ToolException("KNOWLEDGE_ACCESS_DENIED")
                broker = get_device_broker()
                connection = broker.connections.get(spec["device_id"])
                if (
                    connection is None
                    or not connection.tasks_allowed
                    or connection.owner_id != str(user_id)
                    or LOCAL_KNOWLEDGE_OPERATION not in connection.capabilities
                ):
                    return _source_failure(dataset_id, "KNOWLEDGE_DEVICE_UNAVAILABLE")
                async with session_factory() as current_session:
                    current_user = (
                        await current_session.execute(select(UserModel).where(UserModel.id == str(user_id), UserModel.disabled.is_not(True)))
                    ).scalar_one_or_none()
                    if current_user is None or ResourceAction.USE not in role_permissions(current_user.role):
                        return _source_failure(dataset_id, "KNOWLEDGE_DEVICE_UNAVAILABLE")
                record = await broker.send_task(
                    device_id=spec["device_id"],
                    operation=LOCAL_KNOWLEDGE_OPERATION,
                    path="",
                    run_id=run_id,
                    tool_call_id=str(current_tool_call_evidence() or ""),
                    expires_in=timedelta(minutes=5),
                    payload_extra={
                        "arguments": search_task_payload(query, spec),
                        "operation": LOCAL_KNOWLEDGE_OPERATION,
                        "thread_id": str(thread_id or "canonical"),
                    },
                )
                try:
                    while record.status in {
                        TaskStatus.CREATED,
                        TaskStatus.SENT,
                        TaskStatus.ACKED,
                        TaskStatus.CONSENT_REQUIRED,
                        TaskStatus.CANCEL_REQUESTED,
                        TaskStatus.PROGRESS,
                    }:
                        await asyncio.sleep(0.05)
                        record = broker.get_task(record.task_id)
                except asyncio.CancelledError:
                    await asyncio.shield(broker.cancel_task(record.task_id))
                    raise
                if record.receipt is not None:
                    from agentplatform_extension.evidence import (
                        record_local_execution_receipt,
                    )

                    record_local_execution_receipt(
                        record.receipt,
                        tool_call_id=record.tool_call_id or None,
                    )
                if record.status is not TaskStatus.COMPLETED:
                    return _source_failure(dataset_id, str(record.error_code or "LOCAL_KNOWLEDGE_" + record.status.value.upper()))
                return validate_local_search_result(record.result, spec)

            local_knowledge_search = search_local_knowledge
        return build_canonical_agent_factory(
            definition,
            skills,
            runner_tool_groups=actor.tool_groups,
            knowledge_scope=KnowledgeScope.from_bindings(
                knowledge_scope,
                ready_document_ids={dataset: ready_document_ids[dataset] for dataset in knowledge_scope.values()},
                retrieval_profiles={dataset: retrieval_profiles[dataset] for dataset in knowledge_scope.values() if dataset in retrieval_profiles},
                revision_metadata={dataset: revision_metadata[dataset] for dataset in knowledge_scope.values() if dataset in revision_metadata},
            ),
            local_knowledge_search=local_knowledge_search,
            local_authorization=local_authorization,
            local_tool_executor=local_tool_executor,
            local_tool_descriptors=local_tool_descriptors if isinstance(local_tool_descriptors, dict) else None,
        )
    except ResourceNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ResourcePermissionDenied as exc:
        raise HTTPException(403, str(exc)) from exc
    except VisibilityClosureError as exc:
        raise HTTPException(
            409,
            detail={
                "code": "visibility_closure_violation",
                "message": str(exc),
                "violations": exc.violations,
            },
        ) from exc
    except SelectedSkillOutsideClosure as exc:
        from app.gateway.audit import record_audit

        await record_audit(
            str(user_id),
            "run_preparation_rejected",
            resource_type="agent",
            resource_id=resource_id,
            detail={
                "thread_id": thread_id,
                "run_attempt_id": run_id,
                "agent": exc.agent,
                "requested_skill": exc.requested_skill,
                "available_skills": exc.available_skills,
                "task_id": (diagnostic_context or {}).get("task_id"),
                "context_source": (diagnostic_context or {}).get("context_source", "request"),
                "reason": "skill_outside_agent_closure",
            },
        )
        raise HTTPException(
            409,
            detail={
                "code": "skill_outside_agent_closure",
                "message": "The selected Skill is not available to the current Expert.",
                "agent": exc.agent,
                "requested_skill": exc.requested_skill,
                "available_skills": exc.available_skills,
                "context_source": (diagnostic_context or {}).get("context_source", "request"),
            },
        ) from exc
    except (ResourceConflict, ResourceRuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc
