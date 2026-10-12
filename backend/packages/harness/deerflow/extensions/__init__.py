"""DeerFlow's extension mechanism (host side).

The public contracts live in the separate `deerflow-extension-api` package;
this module implements loading, registration, middleware injection and the
hook-site plumbing.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from deerflow.extensions.loader import (
    Diagnostic,
    ExtensionLoadError,
    ExtensionSpec,
    load_extensions,
)
from deerflow.extensions.registry import EMPTY_EXTENSIONS, ExtensionRegistry, LoadedExtensions

#: Runtime-context key carrying the run's immutable extension snapshot.
#:
#: The graph-build binding below is a ContextVar scoped to synchronous agent
#: construction, so it is long gone by the time a tool delegates work. Runtime
#: context is how the run reaches that later code. The double-underscore prefix
#: marks it as host-internal: the Gateway strips caller-supplied ``__`` keys,
#: and this snapshot is never part of the public extension contract.
EXTENSION_SNAPSHOT_CONTEXT_KEY = "__deerflow_extension_snapshot"

_loaded: LoadedExtensions = EMPTY_EXTENSIONS
_agent_build_extensions: ContextVar[LoadedExtensions | None] = ContextVar(
    "deerflow_agent_build_extensions",
    default=None,
)


def get_loaded_extensions() -> LoadedExtensions:
    """Return the process-wide loaded extensions.

    Mirrors the existing `get_app_config()` convention so call sites can take
    an explicit override parameter and fall back to this.
    """
    return _loaded


def get_agent_build_extensions() -> LoadedExtensions:
    """Return the run-bound snapshot while an agent graph is being built."""
    return _agent_build_extensions.get() or get_loaded_extensions()


@contextmanager
def bind_agent_build_extensions(loaded: LoadedExtensions) -> Iterator[None]:
    """Bind one immutable extension snapshot to synchronous graph assembly."""
    token = _agent_build_extensions.set(loaded)
    try:
        yield
    finally:
        _agent_build_extensions.reset(token)


def resolve_run_extensions(context: Any | None) -> LoadedExtensions | None:
    """Return the run's extension snapshot from *context*, or ``None``.

    Runtime context is caller-mergeable, so the value is type-checked rather
    than trusted. ``None`` means "this caller installed no snapshot" (embedded
    client, standalone LangGraph Server) and leaves consumers on their existing
    ``get_loaded_extensions()`` fallback.
    """
    if not isinstance(context, Mapping):
        return None
    snapshot = context.get(EXTENSION_SNAPSHOT_CONTEXT_KEY)
    return snapshot if isinstance(snapshot, LoadedExtensions) else None


def resolve_runtime_evidence_hooks(extensions: LoadedExtensions | None) -> Any | None:
    """Return the run's optional evidence hook provider.

    Runtime evidence hooks are a single-provider registration (a duplicate
    registration is refused by the registry), so a loaded set carries at most
    one entry. ``None`` means the caller has no run snapshot
    (``resolve_run_extensions`` contract) and falls back to the process
    default loaded set, mirroring the executor and run worker; only a loaded
    set without registered hooks falls through to the optional process-global
    default.
    """
    if extensions is None:
        extensions = get_loaded_extensions()
    if extensions.runtime_evidence_hooks:
        return extensions.runtime_evidence_hooks[-1][1]
    from deerflow_extension_api import get_runtime_evidence_hooks

    return get_runtime_evidence_hooks()


# --- Host seam providers (02-M6 registry contract) ---------------------------
#
# Three single-provider seams let the enterprise composition publish behavior
# that upstream call sites consult (tool-scope adaptation, subagent assembly
# middlewares, builtin tool overrides). Resolution mirrors
# ``resolve_runtime_evidence_hooks``: an explicit extensions argument (or the
# process default loaded set when ``None``) wins when it carries a registered
# provider; otherwise resolution falls through to the process default
# registered by the host composition below. The process default exists
# because these seams are composition-level contracts, not plugin-optional
# contributions: a host that installs the enterprise layer at gateway
# composition must keep the seams active even when no plugin spec is loaded
# (``load_extensions`` never runs there).


def _resolve_single_seam(extensions: LoadedExtensions | None, bucket: str, default: Any) -> Any | None:
    if extensions is None:
        extensions = get_loaded_extensions()
    entries = getattr(extensions, bucket)
    if entries:
        return entries[-1][1]
    return default


def resolve_tool_scopes(extensions: LoadedExtensions | None) -> Any | None:
    """Return the host's tool-scope adapter, or ``None`` for stock behavior."""
    return _resolve_single_seam(extensions, "tool_scopes", _default_tool_scopes[0])


def resolve_subagent_middlewares(extensions: LoadedExtensions | None) -> Any | None:
    """Return the host's subagent middleware source, or ``None``."""
    return _resolve_single_seam(extensions, "subagent_middlewares", _default_subagent_middlewares[0])


def resolve_builtin_tool_overrides(extensions: LoadedExtensions | None) -> Any | None:
    """Return the host's builtin tool overrides, or ``None``."""
    return _resolve_single_seam(extensions, "builtin_tool_overrides", _default_builtin_tool_overrides[0])


def _register_default_seam(bucket: list[Any], label: str, owner: str, provider: Any) -> None:
    """Install a process-default seam provider (single registration).

    Same single-provider semantics as the registry bucket: a second, different
    provider is refused with both owners named. Re-registering the identical
    object is a no-op so module re-imports (test reloads) stay harmless.
    """
    current = bucket[0]
    if current is provider:
        return
    if current is not None:
        raise ValueError(f"{label} are a single-provider registration: '{bucket[1]}' already registered them, refusing the registration from '{owner}'")
    bucket[:] = (provider, owner)


def set_default_tool_scopes(adapter: Any, *, owner: str = "host:tool_scopes") -> None:
    """Register the process-default tool-scope adapter (gateway composition)."""
    _register_default_seam(_default_tool_scopes, "tool scopes", owner, adapter)


def set_default_subagent_middlewares(source: Any, *, owner: str = "host:subagent_middlewares") -> None:
    """Register the process-default subagent middleware source."""
    _register_default_seam(_default_subagent_middlewares, "subagent middlewares", owner, source)


def set_default_builtin_tool_overrides(overrides: Any, *, owner: str = "host:builtin_tools") -> None:
    """Register the process-default builtin tool overrides."""
    _register_default_seam(_default_builtin_tool_overrides, "builtin tool overrides", owner, overrides)


def reset_default_extension_seams() -> None:
    """Clear the process-default seam providers. Test hygiene only."""
    _default_tool_scopes[:] = (None, None)
    _default_subagent_middlewares[:] = (None, None)
    _default_builtin_tool_overrides[:] = (None, None)


_default_tool_scopes: list[Any] = [None, None]
_default_subagent_middlewares: list[Any] = [None, None]
_default_builtin_tool_overrides: list[Any] = [None, None]


def set_loaded_extensions(loaded: LoadedExtensions) -> None:
    global _loaded
    _loaded = loaded


def reset_loaded_extensions() -> None:
    """Reset to a FRESH empty set. Used by tests to prevent singleton leaks.

    Builds a new instance rather than reusing EMPTY_EXTENSIONS: that singleton
    owns a mutable ExtensionData app_store, so resetting to it would carry any
    write made while "empty" across every later reset and across the process.
    """
    global _loaded
    _loaded = ExtensionRegistry().build()


_runtime_diagnostics: list[Diagnostic] = []
_runtime_diagnostics_lock = threading.RLock()
_MAX_RUNTIME_DIAGNOSTICS = 1000


def _trim_runtime_diagnostics() -> None:
    overflow = len(_runtime_diagnostics) - _MAX_RUNTIME_DIAGNOSTICS
    if overflow > 0:
        del _runtime_diagnostics[:overflow]


def initialize_runtime_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    """Install and return the live diagnostic list for the current host."""
    with _runtime_diagnostics_lock:
        _runtime_diagnostics.clear()
        _runtime_diagnostics.extend(diagnostics)
        _trim_runtime_diagnostics()
        return _runtime_diagnostics


def record_runtime_diagnostic(diagnostic: Diagnostic) -> None:
    """Collect one diagnostic in the canonical process sink."""
    with _runtime_diagnostics_lock:
        _runtime_diagnostics.append(diagnostic)
        _trim_runtime_diagnostics()


def record_runtime_diagnostics(diagnostics: list[Diagnostic]) -> None:
    """Collect a diagnostic batch in the canonical process sink."""
    with _runtime_diagnostics_lock:
        _runtime_diagnostics.extend(diagnostics)
        _trim_runtime_diagnostics()


def get_runtime_diagnostics() -> list[Diagnostic]:
    with _runtime_diagnostics_lock:
        return list(_runtime_diagnostics)


def reset_runtime_diagnostics() -> None:
    with _runtime_diagnostics_lock:
        _runtime_diagnostics.clear()


__all__ = [
    "EMPTY_EXTENSIONS",
    "EXTENSION_SNAPSHOT_CONTEXT_KEY",
    "Diagnostic",
    "ExtensionLoadError",
    "ExtensionRegistry",
    "ExtensionSpec",
    "LoadedExtensions",
    "bind_agent_build_extensions",
    "get_agent_build_extensions",
    "get_loaded_extensions",
    "get_runtime_diagnostics",
    "initialize_runtime_diagnostics",
    "load_extensions",
    "record_runtime_diagnostic",
    "record_runtime_diagnostics",
    "reset_default_extension_seams",
    "reset_loaded_extensions",
    "reset_runtime_diagnostics",
    "resolve_builtin_tool_overrides",
    "resolve_run_extensions",
    "resolve_runtime_evidence_hooks",
    "resolve_subagent_middlewares",
    "resolve_tool_scopes",
    "set_default_builtin_tool_overrides",
    "set_default_subagent_middlewares",
    "set_default_tool_scopes",
    "set_loaded_extensions",
]
