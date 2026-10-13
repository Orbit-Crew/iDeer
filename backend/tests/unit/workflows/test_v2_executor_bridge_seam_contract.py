"""Contract tests for the workflow executor bridge seams (#64, 02-M6).

The bridge publishes two enterprise contracts — knowledge tool-scope
adaptation at tool assembly and workflow file-scope middlewares at subagent
agent assembly — as single-provider registrations through the harness
extension seams (contract batches 1-2 removed both import-time module
rewrites; upstream modules stay stock).

These tests pin (a) the registry-only install state for both seams, (b) the
scoped behavior matrix the seams must uphold, and (c) the seam's
executor-side middleware contract.
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


def test_tool_scope_track_is_registry_only_at_import() -> None:
    """Contract batch 1 (tool loading): importing the bridge must leave the
    ``deerflow.tools`` package binding stock and serve the knowledge tool-scope
    contract through the harness extension seam instead. Was the expand-phase
    legacy probe asserting the rewrite was present; flipped with the batch that
    removed ``_install_scope_aware_tool_loading``."""
    probe = "\n".join(
        [
            "import deerflow.tools, deerflow.tools.tools",
            "import app.agentplatform.workflows.v2.executor_bridge",
            "from deerflow.extensions import resolve_tool_scopes",
            "assert deerflow.tools.get_available_tools is deerflow.tools.tools.get_available_tools, 'package binding rewritten'",
            "assert type(resolve_tool_scopes(None)).__name__ == 'WorkflowKnowledgeToolScopes', 'tool-scope provider missing'",
        ]
    )
    result = _run_probe(probe)
    assert result.returncode == 0, result.stderr


def test_middleware_track_is_registry_only_at_import() -> None:
    """Contract batch 2 (middleware seam): importing the bridge must leave the
    executor module's ``create_agent`` binding stock and serve the middleware
    contract through the harness extension seam instead. Was the expand-phase
    legacy probe asserting the rewrite was present; flipped with the batch
    that removed ``_install_scope_aware_create_agent``."""
    probe = "\n".join(
        [
            "import deerflow.subagents.executor as executor_module",
            "from langchain.agents import create_agent as langchain_create_agent",
            "import app.agentplatform.workflows.v2.executor_bridge",
            "from deerflow.extensions import resolve_subagent_middlewares, resolve_tool_scopes",
            "assert executor_module.create_agent is langchain_create_agent, 'executor binding rewritten'",
            "assert type(resolve_subagent_middlewares(None)).__name__ == 'WorkflowMiddlewareSource', 'middleware provider missing'",
            "assert type(resolve_tool_scopes(None)).__name__ == 'WorkflowKnowledgeToolScopes', 'tool-scope provider missing'",
        ]
    )
    result = _run_probe(probe)
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
def stock_seam_state(monkeypatch: pytest.MonkeyPatch):
    """Isolate the stock tool assembly from the bridge's registrations.

    Importing the bridge (contract batches 1-2) registers the process-default
    tool-scope and middleware providers. Pin the package binding to the stock
    implementation (belt-and-braces against any test-process rewrite) and
    clear the process default providers for the duration of the test.
    """
    monkeypatch.setattr(deerflow.tools, "get_available_tools", deerflow.tools.tools.get_available_tools)
    reset_default_extension_seams()
    yield
    reset_default_extension_seams()


@pytest.mark.parametrize(("scope", "subagent_enabled"), _SCENARIOS, ids=["no-scope-sub", "no-scope-lead", "scoped-sub", "scoped-lead"])
def test_registry_seam_scoping_matrix(monkeypatch: pytest.MonkeyPatch, stock_seam_state, scope, subagent_enabled) -> None:
    """The registry-track seam (inside the stock
    ``tools.tools.get_available_tools``) must uphold the fail-closed scoping
    matrix the expand-phase equivalence test pinned against the removed legacy
    wrapper: same tool names, same adaptation decisions per scenario."""
    _scoped_loader(monkeypatch)

    token = executor_bridge._PENDING_KNOWLEDGE_SCOPE.set(scope)
    try:
        set_default_tool_scopes(WorkflowKnowledgeToolScopes(), owner="test:seam_contract")
        registry_result = deerflow.tools.tools.get_available_tools(subagent_enabled=subagent_enabled, include_mcp=False, include_upload_tool=False)
    finally:
        executor_bridge._PENDING_KNOWLEDGE_SCOPE.reset(token)
        reset_default_extension_seams()

    # The fail-closed matrix pins the shared behavior (both historical tracks).
    if scope is None:
        assert _names(registry_result) == ["knowledge_search", "write_file"]
    elif subagent_enabled is False:
        assert _names(registry_result) == ["write_file"], "native delegation must fail closed"
    else:
        assert _names(registry_result) == ["knowledge_search", "write_file"]
        assert getattr(registry_result[0], "args_schema", None) is not None, "scoped loading must rebind the knowledge tool"
    assert registry_result[_names(registry_result).index("write_file")] is deerflow.tools.tools.BUILTIN_TOOLS[0]


def test_stock_behavior_without_provider(monkeypatch: pytest.MonkeyPatch, stock_seam_state) -> None:
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
