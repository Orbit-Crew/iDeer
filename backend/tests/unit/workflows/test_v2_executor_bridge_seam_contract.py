"""Expand/contract contract tests for the workflow executor bridge seams (#64, 02-M6).

The bridge publishes two enterprise contracts — knowledge tool-scope
adaptation at tool assembly and workflow file-scope middlewares at subagent
agent assembly — on two tracks:

* ``legacy`` (expand default): import-time rewrites of
  ``deerflow.tools.get_available_tools`` and
  ``deerflow.subagents.executor.create_agent``;
* ``registry``: single-provider registration through the harness extension
  seams; upstream modules stay untouched.

These tests pin (a) the legacy install state, (b) the registry track's
process hygiene, (c) behavioral equivalence of both tracks on the shared
scenarios, and (d) the seam's executor-side middleware contract. The legacy
install-state probe flips together with the contract batch that removes the
rewrite.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from agentplatform_extension.knowledge.scope import KnowledgeScope

import deerflow.tools
import deerflow.tools.tools
from app.agentplatform.workflows.v2 import executor_bridge
from app.agentplatform.workflows.v2.executor_bridge import (
    WorkflowKnowledgeToolScopes,
    WorkflowMiddlewareSource,
    WorkflowSubagentConfig,
    WorkflowSubagentExecutor,
)
from deerflow.extensions import (
    reset_default_extension_seams,
    resolve_subagent_middlewares,
    resolve_tool_scopes,
    set_default_subagent_middlewares,
    set_default_tool_scopes,
)

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _run_probe(source: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run ``source`` in a fresh interpreter so import order cannot mask side effects."""
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=_BACKEND_DIR,
        timeout=180,
        env=full_env,
    )


# --- Track install state (probes) --------------------------------------------


def test_legacy_track_default_rewrites_upstream_bindings_at_import() -> None:
    """Expand-phase default: importing the bridge leaves the two import-time
    module rewrites in place. This probe flips to the stock-identity assertion
    in the contract batch that removes the rewrite."""
    probe = "\n".join(
        [
            "import deerflow.tools",
            "import deerflow.subagents.executor as executor_module",
            "import app.agentplatform.workflows.v2.executor_bridge",
            "assert getattr(deerflow.tools.get_available_tools, '_workflow_knowledge_scope_aware', False), 'tool loading rewrite missing'",
            "assert getattr(executor_module.create_agent, '_workflow_scope_aware', False), 'create_agent rewrite missing'",
        ]
    )
    result = _run_probe(probe)
    assert result.returncode == 0, result.stderr


def test_registry_track_leaves_upstream_bindings_unrewritten() -> None:
    """Registry track: the same import must leave upstream modules stock and
    publish both providers through the harness extension seams instead."""
    probe = "\n".join(
        [
            "import deerflow.tools, deerflow.tools.tools",
            "import deerflow.subagents.executor as executor_module",
            "from langchain.agents import create_agent as langchain_create_agent",
            "import app.agentplatform.workflows.v2.executor_bridge",
            "from deerflow.extensions import resolve_subagent_middlewares, resolve_tool_scopes",
            "assert deerflow.tools.get_available_tools is deerflow.tools.tools.get_available_tools, 'package binding rewritten'",
            "assert executor_module.create_agent is langchain_create_agent, 'executor binding rewritten'",
            "assert type(resolve_tool_scopes(None)).__name__ == 'WorkflowKnowledgeToolScopes', 'tool-scope provider missing'",
            "assert type(resolve_subagent_middlewares(None)).__name__ == 'WorkflowMiddlewareSource', 'middleware provider missing'",
        ]
    )
    result = _run_probe(probe, env={"IDEER_TOOL_SCOPE_SEAM": "registry", "IDEER_SUBAGENT_MIDDLEWARE_SEAM": "registry"})
    assert result.returncode == 0, result.stderr


# --- Tool-scope behavioral equivalence ---------------------------------------


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


def _scoped_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the real ``get_available_tools`` dependencies to load only a
    ``knowledge_search`` tool and one plain tool."""
    knowledge_tool = _FakeTool("knowledge_search")
    plain_tool = _FakeTool("write_file")
    config = MagicMock()
    tool_cfg = MagicMock()
    tool_cfg.name = "knowledge_search"
    tool_cfg.group = "test"
    tool_cfg.use = "tests.fake:knowledge_search"
    config.tools = [tool_cfg]
    config.models = []
    config.tool_search.enabled = False
    config.skill_evolution.enabled = False
    config.acp_agents = {}
    monkeypatch.setattr(deerflow.tools.tools, "get_app_config", lambda: config)
    monkeypatch.setattr(deerflow.tools.tools, "is_host_bash_allowed", lambda app_config: True)
    monkeypatch.setattr(deerflow.tools.tools, "resolve_variable", lambda use, base: knowledge_tool)
    monkeypatch.setattr(deerflow.tools.tools, "BUILTIN_TOOLS", [plain_tool])
    monkeypatch.setattr(deerflow.tools.tools, "SUBAGENT_TOOLS", [])
    monkeypatch.setattr(deerflow.tools.tools, "is_mcp_task_runtime_available", lambda: False)
    monkeypatch.setattr(deerflow.tools.tools, "is_subagent_batch_runtime_available", lambda: False)
    return None


def _names(tools: list) -> list[str]:
    return [tool.name for tool in tools]


_SCOPE = KnowledgeScope.from_bindings({"kb-allowed": "dataset-a"})
_SCENARIOS = [
    # (pending knowledge scope, subagent_enabled kwarg)
    (None, False),
    (None, True),
    (_SCOPE, False),  # native delegation: fail-closed empty scope
    (_SCOPE, True),  # workflow-context loading: narrowed scope
]


@pytest.fixture
def legacy_wrapper(monkeypatch: pytest.MonkeyPatch):
    """Isolate the legacy wrapper from the registry track.

    Saves the package binding as imported (the wrapper under the expand
    default), pins the package binding to the stock implementation so the
    registry leg never runs through the wrapper, and clears any process
    default providers. ``None`` once the legacy track is removed.
    """
    wrapper = deerflow.tools.get_available_tools
    is_wrapper = getattr(wrapper, "_workflow_knowledge_scope_aware", False)
    monkeypatch.setattr(deerflow.tools, "get_available_tools", deerflow.tools.tools.get_available_tools)
    reset_default_extension_seams()
    yield wrapper if is_wrapper else None
    reset_default_extension_seams()


@pytest.mark.parametrize(("scope", "subagent_enabled"), _SCENARIOS, ids=["no-scope-sub", "no-scope-lead", "scoped-sub", "scoped-lead"])
def test_registry_seam_matches_the_legacy_wrapper_behavior(monkeypatch: pytest.MonkeyPatch, legacy_wrapper, scope, subagent_enabled) -> None:
    """For every knowledge-scope scenario the registry-track seam (inside the
    stock ``tools.tools.get_available_tools``) and the legacy wrapper (the
    package binding, its captured original running with no provider) must
    produce equivalent results: same tool names and same adaptation matrix."""
    _scoped_loader(monkeypatch)

    token = executor_bridge._PENDING_KNOWLEDGE_SCOPE.set(scope)
    try:
        # Legacy track alone: wrapper over stock assembly (no provider registered).
        legacy_result = legacy_wrapper(subagent_enabled=subagent_enabled, include_mcp=False, include_upload_tool=False) if legacy_wrapper is not None else None
        # Registry track alone: the seam inside the stock implementation.
        set_default_tool_scopes(WorkflowKnowledgeToolScopes(), owner="test:seam_contract")
        registry_result = deerflow.tools.tools.get_available_tools(subagent_enabled=subagent_enabled, include_mcp=False, include_upload_tool=False)
    finally:
        executor_bridge._PENDING_KNOWLEDGE_SCOPE.reset(token)
        reset_default_extension_seams()

    # The fail-closed matrix pins the shared behavior (both tracks).
    if scope is None:
        assert _names(registry_result) == ["knowledge_search", "write_file"]
    elif subagent_enabled is False:
        assert _names(registry_result) == ["write_file"], "native delegation must fail closed"
    else:
        assert _names(registry_result) == ["knowledge_search", "write_file"]
        assert getattr(registry_result[0], "args_schema", None) is not None, "scoped loading must rebind the knowledge tool"
    assert registry_result[_names(registry_result).index("write_file")] is deerflow.tools.tools.BUILTIN_TOOLS[0]

    if legacy_result is not None:
        assert _names(legacy_result) == _names(registry_result), "tracks diverge on names"
        assert [getattr(t, "args_schema", None) is not None for t in legacy_result] == [getattr(t, "args_schema", None) is not None for t in registry_result], "tracks diverge on knowledge-tool adaptation"


def test_stock_behavior_without_provider(monkeypatch: pytest.MonkeyPatch, legacy_wrapper) -> None:
    """Without a registered provider the seam must be a pure passthrough even
    while a workflow scope is pending."""
    _scoped_loader(monkeypatch)
    token = executor_bridge._PENDING_KNOWLEDGE_SCOPE.set(_SCOPE)
    try:
        result = deerflow.tools.tools.get_available_tools(subagent_enabled=False, include_mcp=False, include_upload_tool=False)
    finally:
        executor_bridge._PENDING_KNOWLEDGE_SCOPE.reset(token)
    assert _names(result) == ["knowledge_search", "write_file"]


# --- Subagent middleware seam -------------------------------------------------


def test_middleware_source_passes_through_without_workflow_context() -> None:
    assert WorkflowMiddlewareSource().pending_middlewares() == []


def test_middleware_source_returns_the_pending_workflow_middlewares() -> None:
    sentinel = object()
    token = executor_bridge._PENDING_FILE_SCOPE.set([sentinel])
    try:
        assert WorkflowMiddlewareSource().pending_middlewares() == [sentinel]
    finally:
        executor_bridge._PENDING_FILE_SCOPE.reset(token)


# --- Bridge surface used by the adapters --------------------------------------


def test_bridge_surface_and_provider_resolution() -> None:
    """The workflow executor/config surface stays intact and the registry
    track serves both providers once registered."""
    assert WorkflowSubagentExecutor.__name__ == "WorkflowSubagentExecutor"
    config = WorkflowSubagentConfig(name="node", description="d", model="m", file_access={"read": ["/in"]}, knowledge_scope=None)
    assert config.file_access == {"read": ["/in"]}

    reset_default_extension_seams()
    set_default_tool_scopes(WorkflowKnowledgeToolScopes(), owner="test:seam_contract")
    set_default_subagent_middlewares(WorkflowMiddlewareSource(), owner="test:seam_contract")
    try:
        assert resolve_tool_scopes(None) is not None
        assert resolve_subagent_middlewares(None) is not None
    finally:
        reset_default_extension_seams()
