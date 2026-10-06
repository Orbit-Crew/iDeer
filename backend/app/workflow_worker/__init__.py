"""Process entrypoint package for the single durable workflow worker.

The former single-file module is now a same-named package: execution and the
operator resume protocol live in ``run_session`` (``execute`` / ``resume``),
adapter registry construction in ``registry``, and the durable queue loop in
``entrypoint``. Every name the old module exported stays importable from this
package root, so external imports are unchanged.
"""

from __future__ import annotations

# Canonical runs key their sandboxes on a run-scoped identity; teach the
# runtime's local provider to mount the run's frozen read-only skill view.
from app.agentplatform.resources.canonical_sandbox import (
    install_run_skill_view_resolver as _install_run_skill_view_resolver,
)

# Alias legacy IDEER_* deployment env names before any config resolution.
# The alias runs at import time inside compat_env, so importing it here first
# is sufficient (see app/gateway/app.py for the same pattern).
from app.gateway.compat_env import apply_legacy_env_aliases as _apply_legacy_env_aliases  # noqa: F401
from deerflow.config import get_app_config

from .entrypoint import main, run_worker
from .registry import build_canonical_registry
from .run_session import (
    _workflow_run_evidence_context,
    execute,
    execute_workflow_task,
    load_workflow_definition_for_run,
    resume,
)

_install_run_skill_view_resolver()

__all__ = [
    "_workflow_run_evidence_context",
    "build_canonical_registry",
    "execute",
    "execute_workflow_task",
    "get_app_config",
    "load_workflow_definition_for_run",
    "main",
    "resume",
    "run_worker",
]
