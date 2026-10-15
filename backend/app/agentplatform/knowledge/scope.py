"""Control-plane calculation of the knowledge scope for a frozen Run."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def deployment_allowed_datasets(tool_config: Any | None) -> Iterable[str] | None:
    """Resolve the deployment layer's dataset veto from the tool config.

    An unconfigured ``knowledge_search`` tool denies: a run carrying KB
    bindings must not silently shed the deployment veto just because the
    deployment never declared a retrieval tool.  A configured tool without a
    ``datasets`` attribute imposes no deployment restriction — the allowlist
    is an optional operator control (see ``config.example.yaml``).
    """

    if tool_config is None:
        return ()
    return getattr(tool_config, "datasets", None)


def calculate_effective_knowledge_scope(
    resource_bindings: Mapping[str, str | None],
    *,
    caller_allowed: Iterable[str] | None = None,
    workflow_allowed: Iterable[str] | None = None,
    runtime_allowed: Iterable[str] | None = None,
    deployment_allowed: Iterable[str] | None = None,
) -> dict[str, str]:
    """Return logical KB → provider dataset bindings after all vetoes.

    ``None`` means that a layer has no additional restriction.  Empty sets
    remain empty: an empty allowlist is an intentional deny, not "all".
    Unbound KBs are omitted because they cannot be searched safely.
    """

    scope = {logical: dataset for logical, dataset in resource_bindings.items() if dataset}
    for restriction in (caller_allowed, workflow_allowed, runtime_allowed, deployment_allowed):
        if restriction is not None:
            allowed = set(restriction)
            scope = {logical: dataset for logical, dataset in scope.items() if logical in allowed or dataset in allowed}
    return dict(sorted(scope.items()))
