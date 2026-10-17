"""Contributed routers need the caller's identity without importing app.*.

Every extension route is session-authenticated (contributed routers cannot
enter host-reserved or auth-exempt prefixes), but "logged in" and "admin" are
different questions and an extension must be able to ask the second one.
"""

from types import SimpleNamespace

import pytest
from deerflow_extension_api import (
    EXTENSION_PRINCIPAL_RESOLVER_KEY,
    ExtensionPrincipal,
    require_admin,
    resolve_principal,
)

ADMIN = ExtensionPrincipal(user_id="u1", is_admin=True, is_internal=False)
PLAIN = ExtensionPrincipal(user_id="u2", is_admin=False, is_internal=False)


def _request(principal):
    state = SimpleNamespace(**{EXTENSION_PRINCIPAL_RESOLVER_KEY: (lambda request: principal)})
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_resolve_returns_the_hosts_principal():
    assert resolve_principal(_request(ADMIN)) == ADMIN


def test_resolve_returns_none_when_the_host_installed_no_resolver():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    assert resolve_principal(request) is None


def test_resolve_returns_none_rather_than_raising_when_the_resolver_fails():
    def boom(request):
        raise RuntimeError("nope")

    state = SimpleNamespace(**{EXTENSION_PRINCIPAL_RESOLVER_KEY: boom})
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    assert resolve_principal(request) is None


def test_require_admin_accepts_an_admin():
    assert require_admin(_request(ADMIN)) == ADMIN


def test_require_admin_rejects_a_plain_user():
    with pytest.raises(PermissionError):
        require_admin(_request(PLAIN))


def test_require_admin_fails_closed_with_no_resolver():
    """An unanswerable authorization question must not resolve to 'allowed'."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(PermissionError):
        require_admin(request)


@pytest.fixture
def _stub_app_config(monkeypatch):
    """Keep ``create_app()`` independent of a real ``config.yaml``.

    The repo-root ``config.yaml`` is gitignored; a checkout that configures
    plugins there would otherwise make this test load them for real and leak
    a populated extension registry into the process-global singleton other
    tests read through (see ``tests/unit/extensions/test_extension_app_loading.py`` for the
    same pattern).
    """
    import app.gateway.app as app_module
    from deerflow.config.app_config import AppConfig
    from deerflow.config.sandbox_config import SandboxConfig
    from deerflow.extensions import reset_loaded_extensions, reset_runtime_diagnostics

    config = AppConfig(sandbox=SandboxConfig(use="test"))
    monkeypatch.setattr(app_module, "get_app_config", lambda: config)
    reset_loaded_extensions()
    reset_runtime_diagnostics()
    yield
    reset_runtime_diagnostics()
    reset_loaded_extensions()


def test_host_installs_a_resolver_on_app_state(_stub_app_config):
    from app.gateway.app import create_app

    app = create_app()
    assert callable(getattr(app.state, EXTENSION_PRINCIPAL_RESOLVER_KEY, None))


def _session_request(user_id, system_role):
    from app.gateway.auth_disabled import AUTH_SOURCE_SESSION

    return SimpleNamespace(
        state=SimpleNamespace(user=SimpleNamespace(id=user_id, system_role=system_role), auth_source=AUTH_SOURCE_SESSION),
    )


def test_the_installed_resolver_projects_the_users_ext_platform_role(_stub_app_config):
    """users_ext is the only authorization source: the projection must read
    the platform identity the auth middleware resolved onto the request, so
    ``roles`` carries the platform role and ``is_admin`` follows it."""
    from app.gateway.app import create_app
    from app.gateway.authz import _stash_rbac_identity

    app = create_app()
    resolver = getattr(app.state, EXTENSION_PRINCIPAL_RESOLVER_KEY)

    admin_request = _session_request("u1", system_role="user")
    _stash_rbac_identity(admin_request, user_id="u1", department_id=None, role="super_admin")
    admin_principal = resolver(admin_request)
    assert admin_principal.is_admin is True
    assert admin_principal.roles == ("super_admin",)

    plain_request = _session_request("u2", system_role="user")
    _stash_rbac_identity(plain_request, user_id="u2", department_id=None, role="user")
    plain_principal = resolver(plain_request)
    assert plain_principal.is_admin is False
    assert plain_principal.roles == ("user",)

    unresolved_request = _session_request("u3", system_role=None)
    unresolved_principal = resolver(unresolved_request)
    assert unresolved_principal.is_admin is False
    assert unresolved_principal.roles == ()


def test_legacy_system_role_cannot_elevate_the_extension_projection(_stub_app_config):
    """01-H2: a caller the platform downgraded (or never profiled) in
    users_ext must not be re-elevated because a stale legacy
    ``users.system_role`` row still says "admin". The projection never
    consults the legacy column."""
    from app.gateway.app import create_app
    from app.gateway.authz import _stash_rbac_identity

    app = create_app()
    resolver = getattr(app.state, EXTENSION_PRINCIPAL_RESOLVER_KEY)

    # Downgraded in users_ext while the legacy auth row still says "admin".
    downgraded_request = _session_request("u1", system_role="admin")
    _stash_rbac_identity(downgraded_request, user_id="u1", department_id=None, role="user")
    downgraded = resolver(downgraded_request)
    assert downgraded.is_admin is False
    assert downgraded.roles == ("user",)

    # No resolved platform identity at all: fail closed, whatever the
    # legacy field claims.
    unprofiled_request = _session_request("u2", system_role="admin")
    unprofiled = resolver(unprofiled_request)
    assert unprofiled.is_admin is False
    assert unprofiled.roles == ()


def test_the_installed_resolver_suppresses_admin_for_pat_callers(_stub_app_config):
    """P1 regression (#5041 review): an admin-owned PAT must not regain admin
    capability through the extension principal projection. Every admin signal
    — ``is_admin`` and the admin-bearing platform role — is suppressed for PAT
    callers, matching the documented guarantee that PAT credentials never
    carry admin capability."""
    from app.gateway.app import create_app
    from app.gateway.auth_disabled import AUTH_SOURCE_PAT
    from app.gateway.authz import _stash_rbac_identity

    app = create_app()
    resolver = getattr(app.state, EXTENSION_PRINCIPAL_RESOLVER_KEY)

    pat_request = SimpleNamespace(
        state=SimpleNamespace(user=SimpleNamespace(id="u1", system_role="admin"), auth_source=AUTH_SOURCE_PAT),
    )
    _stash_rbac_identity(pat_request, user_id="u1", department_id=None, role="super_admin")
    pat_principal = resolver(pat_request)
    assert pat_principal.is_admin is False
    assert "super_admin" not in pat_principal.roles

    # Control: the same platform admin over a session cookie still projects admin.
    session_request = _session_request("u1", system_role="admin")
    _stash_rbac_identity(session_request, user_id="u1", department_id=None, role="super_admin")
    session_principal = resolver(session_request)
    assert session_principal.is_admin is True
    assert session_principal.roles == ("super_admin",)

    # A non-admin PAT keeps its plain role: only admin signals are suppressed.
    plain_pat_request = SimpleNamespace(
        state=SimpleNamespace(user=SimpleNamespace(id="u2", system_role="user"), auth_source=AUTH_SOURCE_PAT),
    )
    _stash_rbac_identity(plain_pat_request, user_id="u2", department_id=None, role="user")
    assert resolver(plain_pat_request).roles == ("user",)


def test_the_installed_resolver_keeps_the_auth_disabled_admin_bypass(_stub_app_config):
    """The auth-disabled synthetic user is the documented local dev/E2E
    bypass (same contract as ``deps.is_admin_user``): it has no users_ext
    profile to resolve, and its fixed synthetic role keeps the extension
    admin gate open in that explicitly trusted mode."""
    from app.gateway.app import create_app
    from app.gateway.auth_disabled import AUTH_SOURCE_AUTH_DISABLED

    app = create_app()
    resolver = getattr(app.state, EXTENSION_PRINCIPAL_RESOLVER_KEY)

    disabled_request = SimpleNamespace(
        state=SimpleNamespace(user=SimpleNamespace(id="default", system_role="admin"), auth_source=AUTH_SOURCE_AUTH_DISABLED),
    )
    principal = resolver(disabled_request)
    assert principal.is_admin is True


def test_the_installed_resolver_projects_internal_callers_without_a_platform_role(_stub_app_config):
    """Internal callers project through the contract's ``is_internal`` signal;
    they carry no users_ext platform role and never resolve to admin."""
    from app.gateway.app import create_app
    from app.gateway.auth_disabled import AUTH_SOURCE_INTERNAL

    app = create_app()
    resolver = getattr(app.state, EXTENSION_PRINCIPAL_RESOLVER_KEY)

    internal_request = SimpleNamespace(
        state=SimpleNamespace(user=SimpleNamespace(id="default", system_role="internal"), auth_source=AUTH_SOURCE_INTERNAL),
    )
    principal = resolver(internal_request)
    assert principal.is_internal is True
    assert principal.is_admin is False
    assert principal.roles == ()
