"""Contract tests for the canonical ``setup_agent`` seam (#64, 02-M6).

The gateway composition publishes the canonical (resource-catalog)
``setup_agent`` as a ``BuiltinToolOverrides`` provider through the harness
extension seam (contract batch removed the legacy module-attribute rewrites);
upstream modules stay stock. These tests pin the install state, the override
resolution contract, and the canonical tool behavior.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.agentplatform.agent_bootstrap as agent_bootstrap
from deerflow.extensions import (
    reset_default_extension_seams,
    resolve_builtin_tool_overrides,
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


def test_gateway_import_leaves_the_builtin_stock_and_registers_the_override() -> None:
    """Contract batch (builtin seam): importing the gateway must leave the
    stock builtin in place on both upstream module attributes — no
    ``get_session_factory`` attribute leaks onto the tool module — and publish
    the canonical tool through the extension seam instead. Was the
    expand-phase legacy probe asserting the rewrites were present; flipped
    with the batch that removed the attribute rewrites."""
    probe = "\n".join(
        [
            "import app.gateway.services",
            "import deerflow.tools.builtins as builtins_module",
            "import deerflow.tools.builtins.setup_agent_tool as tool_module",
            "import app.agentplatform.agent_bootstrap as agent_bootstrap",
            "from deerflow.extensions import resolve_builtin_tool_overrides",
            "assert builtins_module.setup_agent is tool_module.setup_agent, 'builtins re-export rewritten'",
            "assert not getattr(tool_module.setup_agent, '__module__', '').startswith('app.'), 'tool module attribute rewritten'",
            "assert not hasattr(tool_module, 'get_session_factory'), 'attribute leaked onto the upstream module'",
            "provider = resolve_builtin_tool_overrides(None)",
            "assert provider is not None, 'builtin tool override provider missing'",
            "assert provider.resolve_builtin_tool('setup_agent', None) is agent_bootstrap.setup_agent, 'override must resolve the canonical tool'",
            "stock = tool_module.setup_agent",
            "assert provider.resolve_builtin_tool('setup_agent', stock) is agent_bootstrap.setup_agent",
            "assert provider.resolve_builtin_tool('update_agent', stock) is stock, 'unmanaged builtins keep the host default'",
        ]
    )
    result = _run_probe(probe)
    assert result.returncode == 0, result.stderr


# --- install() contract -------------------------------------------------------


def test_install_registers_once_and_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_bootstrap, "_installed", False)
    reset_default_extension_seams()
    try:
        agent_bootstrap.install()
        first = resolve_builtin_tool_overrides(None)
        assert isinstance(first, agent_bootstrap.CanonicalBuiltinToolOverrides)

        agent_bootstrap.install()  # idempotent: no second registration, same provider
        assert resolve_builtin_tool_overrides(None) is first
    finally:
        reset_default_extension_seams()


# --- Canonical tool behavior --------------------------------------------------


class _DummyRuntime(SimpleNamespace):
    context: dict
    tool_call_id: str


def _paths_mock(tmp_path: Path) -> MagicMock:
    paths = MagicMock()
    paths.base_dir = tmp_path
    return paths


def test_canonical_tool_rejects_empty_soul_without_writing(tmp_path: Path) -> None:
    runtime = _DummyRuntime(context={"agent_name": "canonical-agent", "user_id": "user-1"}, tool_call_id="call-1")

    with patch("deerflow.tools.builtins.setup_agent_tool.get_paths", return_value=_paths_mock(tmp_path)):
        result = agent_bootstrap.setup_agent.func(soul="   ", description="d", runtime=runtime)

    messages = result.update["messages"]
    assert len(messages) == 1
    assert messages[0].content.startswith("Error: soul content is empty")
    assert "created_agent_name" not in result.update


def test_canonical_tool_writes_default_agent_soul_file(tmp_path: Path) -> None:
    """Default agent (no agent_name): the SOUL stays file-based at the global
    base dir — identical contract to the stock tool, through the canonical one."""
    runtime = _DummyRuntime(context={"user_id": "user-1"}, tool_call_id="call-2")

    with patch("deerflow.tools.builtins.setup_agent_tool.get_paths", return_value=_paths_mock(tmp_path)):
        result = agent_bootstrap.setup_agent.func(soul="# Default SOUL", description="d", runtime=runtime)

    assert (tmp_path / "SOUL.md").read_text(encoding="utf-8") == "# Default SOUL"
    assert result.update["messages"][0].content == "Agent 'None' created successfully!"


def test_canonical_tool_falls_back_to_the_agent_store_without_a_session_factory(tmp_path: Path) -> None:
    """No catalog session available (standalone graphs / first boot): the
    canonical upsert falls back to the per-user agent store seam."""
    runtime = _DummyRuntime(context={"agent_name": "fallback-agent", "user_id": "user-9"}, tool_call_id="call-3")
    store = MagicMock()
    store.get.side_effect = FileNotFoundError
    with (
        patch.object(agent_bootstrap, "get_session_factory", return_value=None),
        patch("deerflow.tools.builtins.setup_agent_tool.get_paths", return_value=_paths_mock(tmp_path)),
        patch("deerflow.tools.builtins.setup_agent_tool.get_agent_store", return_value=store),
    ):
        result = agent_bootstrap.setup_agent.func(soul="# Fallback SOUL", description="d", runtime=runtime)

    assert result.update["created_agent_name"] == "fallback-agent"
    store.update.assert_called_once()
    assert store.update.call_args.args[0] == "fallback-agent"
    assert store.update.call_args.args[2] == "# Fallback SOUL"
