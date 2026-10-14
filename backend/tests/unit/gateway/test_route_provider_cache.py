"""01-L3: the route provider cache keys on the config signature alone.

The previous ``id(config)`` fast path could mis-hit when a new config object
reused a freed object's memory address. The signature-keyed single-entry
cache treats a miss as a redundant provider build — directionally safe.
"""

import app.gateway.authz as authz
from app.gateway.authz import _get_cached_route_provider
from deerflow.config.authorization_config import AuthorizationConfig


def test_signature_keyed_cache_is_the_only_fast_path(monkeypatch):
    calls: list[int] = []

    def fake_resolve(config):
        calls.append(1)
        return object()

    monkeypatch.setattr("app.gateway.authz.resolve_authorization_provider", fake_resolve)
    monkeypatch.setattr(authz, "_route_provider_cache", {})
    monkeypatch.setattr(authz, "_route_provider_config_sig", None)

    config = AuthorizationConfig()
    first = _get_cached_route_provider(config)
    second = _get_cached_route_provider(config)
    assert first is second
    assert len(calls) == 1

    changed = AuthorizationConfig(enabled=not config.enabled)
    third = _get_cached_route_provider(changed)
    assert third is not first
    assert len(calls) == 2
    assert authz._route_provider_config_sig is not None
    assert authz._route_provider_cache
