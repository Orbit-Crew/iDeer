"""01-M3: get_local_provider fails with its documented contract error.

The function previously kept a "fallback" that re-imported the same
``get_session_factory`` symbol and called it again — it could only return the
same None, and the duplicated import misled readers into thinking a second
session-factory source existed.
"""

from __future__ import annotations

import pytest


def test_get_local_provider_raises_contract_error_without_session_factory(monkeypatch):
    import deerflow.persistence.engine as engine
    from app.gateway import deps

    monkeypatch.setattr(deps, "_cached_repo", None)
    monkeypatch.setattr(deps, "_cached_local_provider", None)
    monkeypatch.setattr(engine, "get_session_factory", lambda: None)

    with pytest.raises(RuntimeError, match="init_engine_from_config"):
        deps.get_local_provider()
