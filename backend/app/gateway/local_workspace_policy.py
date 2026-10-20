"""Deployment and frozen Agent limits for Desktop read-only workspaces."""
from __future__ import annotations

import os
from typing import Any

READ_CAPABILITIES = frozenset({'local.files.list', 'local.files.read', 'local.files.search'})


def platform_read_capabilities() -> frozenset[str]:
    """The host may narrow the read-only default; client context cannot widen it."""
    configured = os.environ.get('IDEER_LOCAL_READ_CAPABILITIES')
    if configured is None:
        return READ_CAPABILITIES
    return READ_CAPABILITIES & frozenset(value.strip() for value in configured.split(','))


def agent_read_capabilities(config: Any) -> frozenset[str]:
    groups = getattr(config, 'tool_groups', None)
    if groups is None or 'local.files' in groups:
        return READ_CAPABILITIES
    return READ_CAPABILITIES & frozenset(groups)
