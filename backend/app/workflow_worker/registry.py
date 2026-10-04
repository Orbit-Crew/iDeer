"""Adapter registry construction for canonical workflow runs."""

from __future__ import annotations

import asyncio
from typing import Any


async def build_canonical_registry(run: Any, config: Any, session_factory: Any, storage: Any) -> Any:
    """Build adapters only from the Run's frozen UUID closure and runner policy."""

    from sqlalchemy import select

    from app.agentplatform.resource_models import Resource, RunResourceSnapshot
    from app.agentplatform.resource_runtime import CanonicalResourceLoader
    from app.agentplatform.workflow_runtime import (
        ActionAdapterRegistry,
        _CanonicalAgentAdapter,
        _ToolAdapter,
    )
    from deerflow.tools.tools import get_available_tools

    if session_factory is None:
        raise RuntimeError("canonical workflow run requires catalog persistence")
    raw_groups = run.runner_tool_groups
    allowed_groups = frozenset(raw_groups) if raw_groups is not None else None
    registry = ActionAdapterRegistry()
    for tool in get_available_tools(
        groups=sorted(allowed_groups) if allowed_groups is not None else None,
        app_config=config,
    ):
        registry.register("tool", tool.name, _ToolAdapter(tool, user_id=run.created_by))

    async with session_factory() as session:
        loader = CanonicalResourceLoader(session, storage)
        frozen_skill_versions: dict[str, tuple[int, str]] = {}
        frozen_skill_aliases: dict[str, str] = {}
        agent_rows = list(
            (
                await session.execute(
                    select(Resource.id, Resource.slug)
                    .join(
                        RunResourceSnapshot,
                        RunResourceSnapshot.resource_id == Resource.id,
                    )
                    .where(
                        RunResourceSnapshot.run_id == run.run_id,
                        Resource.type == "agent",
                    )
                    .order_by(Resource.id)
                )
            ).all()
        )
        for resource_id, resource_slug in agent_rows:
            definition = await loader.load_agent(run.run_id, resource_id)
            # Pass the already-loaded definition so the UUID-to-name skill
            # translation lands on the object the adapter keeps — not on a
            # discarded internal reload — and the load happens exactly once.
            skill_definitions = await loader.load_agent_skill_definitions(run.run_id, resource_id, definition=definition)
            skills = [value.skill for value in skill_definitions]
            for value in skill_definitions:
                frozen_skill_versions[value.resource_id] = (
                    value.version,
                    value.content_hash,
                )
                frozen_skill_aliases[value.resource_id] = value.skill.name
            adapter = _CanonicalAgentAdapter(
                definition,
                skills,
                run.created_by,
                allowed_tool_groups=allowed_groups,
            )
            # The version is already frozen by the run snapshot; the slug is
            # registered only as an alias to that same frozen adapter because
            # workflow definitions author agent actions by slug. The alias never
            # re-resolves a resource version at execution time.
            registry.register("agent", resource_id, adapter)
            if resource_slug and resource_slug != resource_id:
                registry.register("agent", resource_slug, adapter)
        await asyncio.to_thread(
            storage.create_run_skill_view,
            run.run_id,
            [(resource_id, version, content_hash) for resource_id, (version, content_hash) in sorted(frozen_skill_versions.items())],
            aliases=frozen_skill_aliases,
        )
    return registry
