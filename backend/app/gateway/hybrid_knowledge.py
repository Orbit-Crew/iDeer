"""Hybrid device/server knowledge retrieval semantics (#114).

Web and Desktop drive one Server authorization chain: a canonical Run's
Effective Knowledge Scope may hold provider datasets and device-local
datasets side by side. Every authorized result names its KB/revision source
and its engine, and the two engines' raw scores are never put on one scale —
there is no server-side cross-engine merge or ranking, only per-source
results with attribution. A failed local leg is a structured source failure
instead of a tool error, so it can never impersonate "no material": runs
with other authorized sources proceed marked incomplete, and runs whose
authorized material is local-only pause instead of answering.
"""

from __future__ import annotations

from typing import Any

from agentplatform_extension.knowledge.scope import is_local_dataset

# Engine labels carried by every receipt, model-facing chunk, and source
# failure. Scores are comparable only inside one engine; no component may
# rank a provider similarity against a device text match.
ENGINE_LOCAL_DEVICE = "local_device"
ENGINE_SERVER_PROVIDER = "server_provider"

# Receipt result_status values for a failed local leg. Both are distinct
# from "empty_hit" so a retrieval failure can never read as "no material".
RESULT_SOURCE_UNAVAILABLE = "source_unavailable"
RESULT_STATUS_PAUSED_LOCAL_REQUIRED = "paused_local_required"


def source_engine(dataset_id: str) -> str:
    """The engine that serves one authorized dataset binding."""

    return ENGINE_LOCAL_DEVICE if is_local_dataset(str(dataset_id)) else ENGINE_SERVER_PROVIDER


def source_attribution(dataset_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Project the frozen KB/revision identity plus the serving engine.

    The projection comes from the frozen run revision metadata only — never
    from request data — so hybrid attribution cannot widen or re-point a
    frozen scope.
    """

    metadata = metadata if isinstance(metadata, dict) else {}
    return {
        "knowledge_base_id": metadata.get("knowledge_base_id"),
        "revision_id": metadata.get("revision_id"),
        "revision_no": metadata.get("revision_no"),
        "manifest_hash": metadata.get("manifest_hash"),
        "origin": str(metadata.get("origin") or "provider"),
        "engine": source_engine(dataset_id),
    }


def requires_local_material(knowledge_scope: dict[str, str] | None) -> bool:
    """True when every authorized dataset is device-local.

    A run in this state must depend on local material: if that leg fails
    there is no authorized fallback, so retrieval pauses instead of
    answering from nothing.
    """

    scope = knowledge_scope or {}
    return bool(scope) and all(is_local_dataset(str(dataset)) for dataset in scope.values())


def local_source_unavailable_result(attribution: dict[str, Any], error_code: str) -> dict[str, Any]:
    """Structured partial failure: other authorized sources remain usable.

    The marker flows through the retrieval-receipt pipeline, which records
    ``source_unavailable`` and projects the incompleteness statement to the
    model. ``chunks`` stays empty — nothing is fabricated to fill the gap.
    """

    return {
        "chunks": [],
        "missing": [],
        "truncated": False,
        "incomplete": True,
        "source_failure": {**_bounded(attribution), "error_code": str(error_code or "LOCAL_SOURCE_UNAVAILABLE")},
    }


def local_retrieval_pause_result(attribution: dict[str, Any], error_code: str) -> dict[str, Any]:
    """Structured pause: this run's authorized material is local-only.

    The model is directed to end the turn reporting a paused retrieval — it
    must not answer from unrelated material and must not claim that no
    material exists.
    """

    return {
        "chunks": [],
        "missing": [],
        "truncated": False,
        "incomplete": True,
        "pause": {"reason": "local_knowledge_required", "error_code": str(error_code or "LOCAL_SOURCE_UNAVAILABLE")},
        "source_failure": {**_bounded(attribution), "error_code": str(error_code or "LOCAL_SOURCE_UNAVAILABLE")},
    }


def _bounded(attribution: dict[str, Any]) -> dict[str, Any]:
    return {key: attribution.get(key) for key in ("knowledge_base_id", "revision_id", "revision_no", "manifest_hash", "origin", "engine")}


async def knowledge_scope_view(session: Any, actor: Any, resource_id: str) -> dict[str, Any]:
    """Project the caller-authorized KB sources behind one Agent (#114).

    The Web selection surface reads this view so it can offer exactly what a
    Run would bind for this caller — server provider KBs and the caller's
    own device KBs (with live availability) alike. Authorization and freeze
    are the Run's own: the closure resolution and frozen bindings are shared
    verbatim, so the view cannot reveal or offer anything the Run would not
    search. Selection rides ``runtime_knowledge_scope`` and can only narrow.
    """

    from app.agentplatform.resource_service import ResourceNotFound
    from app.agentplatform.resources.service import ResourceService
    from app.device_control.broker import get_device_broker
    from app.gateway.canonical_agent_run_preparation import build_frozen_knowledge_bindings

    closure = await ResourceService(session, actor).resolve_dependency_closure(resource_id)
    agent = next((item.resource for item in closure if item.resource.id == resource_id and item.resource.type == "agent"), None)
    if agent is None:
        raise ResourceNotFound(f"Agent {resource_id} was not found")
    bindings, _ready, _profiles, revision_metadata = build_frozen_knowledge_bindings(closure, caller_user_id=str(actor.user_id))
    broker = get_device_broker()

    sources: list[dict[str, Any]] = []
    for item in closure:
        kb = item.resource
        if kb.type != "knowledge_base":
            continue
        dataset = bindings.get(kb.id)
        if not dataset:
            # Not bound for this caller: unauthorized, unanchored, or
            # unrouteable — it stays invisible instead of failing the view.
            continue
        metadata = revision_metadata.get(dataset) if isinstance(revision_metadata, dict) else {}
        source: dict[str, Any] = {
            "resource_id": kb.id,
            "slug": kb.slug,
            "display_name": kb.display_name,
            "origin": str((metadata or {}).get("origin") or "provider"),
            "dataset": dataset,
            "revision_id": getattr(item.knowledge_revision, "id", None),
            "revision_no": getattr(item.knowledge_revision, "revision_no", None),
            "manifest_hash": getattr(item.knowledge_revision, "manifest_hash", None),
        }
        if source["origin"] == "local_import":
            device_id = str((metadata or {}).get("device_id") or "")
            connection = broker.connections.get(device_id) if device_id else None
            source["device_id"] = device_id
            source["device_online"] = bool(connection is not None and getattr(connection, "tasks_allowed", False))
        sources.append(source)
    sources.sort(key=lambda entry: str(entry["resource_id"]))
    return {"agent_id": resource_id, "sources": sources, "selection": "narrow_only"}
