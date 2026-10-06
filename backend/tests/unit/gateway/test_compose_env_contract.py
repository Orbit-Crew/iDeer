"""Contract: compose environment exports must be consumable by the backend.

Generalizes the D1 incident: the compose files exported ``IDEER_CHANNELS_*``
while the backend resolved ``DEER_FLOW_CHANNELS_*`` and ``compat_env`` carried
no alias for the pair, so the exported values were silently dropped. This test
parses ``docker/docker-compose.yaml`` and ``docker/docker-compose.intranet.yaml``,
collects the ``IDEER_*``/``DEER_FLOW_*`` names exported to every service, and
asserts each name has a backend consumption path, meaning one of:

(a) the name is read natively somewhere in ``backend/app`` or the vendored
    ``backend/packages`` runtime (substring scan over the source, deliberately
    robust to how the read is spelled; ``compat_env.py`` itself is excluded —
    it is the alias table of route (b), not a native reader), or
(b) the name is a key in ``app.gateway.compat_env._LEGACY_ENV_ALIASES``, or
(c) the name is in ``_INTENTIONALLY_DEPLOY_SIDE_ONLY`` below with a
    justification (exports that no backend code is supposed to read).

Any newly exported compose variable that registers none of these turns this
test red: register a consumption path (a native read in ``backend/app`` or an
``_LEGACY_ENV_ALIASES`` entry mapping the legacy ``IDEER_*`` name to the
``DEER_FLOW_*`` name the runtime reads) instead of parking it in the allow-list.
"""

from pathlib import Path

import yaml

from app.gateway.compat_env import _LEGACY_ENV_ALIASES

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKEND_APP_DIR = _REPO_ROOT / "backend" / "app"
_BACKEND_PACKAGES_DIR = _REPO_ROOT / "backend" / "packages"
_COMPAT_ENV_PATH = (_BACKEND_APP_DIR / "gateway" / "compat_env.py").resolve()
_COMPOSE_FILES = (
    _REPO_ROOT / "docker" / "docker-compose.yaml",
    _REPO_ROOT / "docker" / "docker-compose.intranet.yaml",
)

# Compose exports that intentionally have no backend/app consumption path.
# Every entry needs a justification; a variable the backend is *supposed* to
# read must be registered instead (native read or ``_LEGACY_ENV_ALIASES``),
# never parked here.
_INTENTIONALLY_DEPLOY_SIDE_ONLY: dict[str, str] = {
    # Read by the Next.js server (frontend/src/core/auth/gateway-config.ts and
    # the frontend app/api route handlers) to reach the gateway; exported on
    # the frontend service only, never consumed by backend/app.
    "IDEER_INTERNAL_GATEWAY_BASE_URL": ("consumed by the frontend server (frontend/src/core/auth/gateway-config.ts, frontend/src/app/api/**), not by backend/app"),
    # Deprecated since v2.1.0: the managed /mnt/skills projection replaced the
    # host skills-path translation (see CHANGELOG v2.1.0). No runtime consumer;
    # the compose files still export the names for older deploy tooling.
    "IDEER_HOST_SKILLS_PATH": ("deprecated since v2.1.0 (managed /mnt/skills projection replaced the host skills-path translation); kept in compose for older deploy tooling"),
    "DEER_FLOW_HOST_SKILLS_PATH": ("deprecated since v2.1.0 (managed /mnt/skills projection replaced the host skills-path translation); kept in compose for older deploy tooling"),
}


def _compose_env_names(path: Path) -> set[str]:
    """Collect the IDEER_*/DEER_FLOW_* names a compose file exports to its services.

    ``environment:`` accepts both mapping and list (``- NAME=value``) form, and
    values carry ``${VAR:-default}`` interpolation; only the NAME before ``=``
    matters here.
    """
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = (doc or {}).get("services") or {}
    names: set[str] = set()
    for service in services.values():
        environment = (service or {}).get("environment") or {}
        if isinstance(environment, dict):
            entries = [f"{key}={value}" for key, value in environment.items()]
        else:
            entries = [str(entry) for entry in environment]
        for entry in entries:
            name = entry.split("=", 1)[0].strip()
            if name.startswith(("IDEER_", "DEER_FLOW_")):
                names.add(name)
    return names


def _backend_consumption_source() -> str:
    """Source that may natively read an env var, as one string for a substring scan.

    Covers ``backend/app`` plus the vendored ``backend/packages`` runtime (the
    ``deerflow.*`` readers of the ``DEER_FLOW_*`` names). ``compat_env.py`` is
    excluded on purpose: it is the alias table itself (route (b) below), so its
    entries — even commented-out ones — must never count as native reads.
    """
    paths = sorted((*_BACKEND_APP_DIR.rglob("*.py"), *_BACKEND_PACKAGES_DIR.rglob("*.py")))
    return "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in paths if path.resolve() != _COMPAT_ENV_PATH)


def test_both_compose_files_yield_product_env_inventories():
    """Parse sanity: a broken YAML or name filter must fail loudly, not fake a pass."""
    inventories = {path.name: _compose_env_names(path) for path in _COMPOSE_FILES}
    for filename, names in inventories.items():
        assert names, f"{filename} yielded no IDEER_*/DEER_FLOW_* environment names; compose parsing or the export filter is broken"
    # The D1 incident pair must stay visible to the inventory this contract judges.
    assert {"IDEER_CHANNELS_LANGGRAPH_URL", "IDEER_CHANNELS_GATEWAY_URL"} <= inventories["docker-compose.yaml"]


def test_compose_env_exports_have_backend_consumption_path():
    """Every compose-exported IDEER_*/DEER_FLOW_* var reaches the backend env layer."""
    inventory: set[str] = set()
    for path in _COMPOSE_FILES:
        inventory |= _compose_env_names(path)

    source = _backend_consumption_source()
    unconsumed = sorted(name for name in inventory if not (name in _LEGACY_ENV_ALIASES or name in _INTENTIONALLY_DEPLOY_SIDE_ONLY or name in source))

    assert not unconsumed, (
        "Compose exports IDEER_*/DEER_FLOW_* variables that no backend consumption path "
        "covers: neither read natively in backend/app nor aliased in "
        "backend/app/gateway/compat_env.py::_LEGACY_ENV_ALIASES. Silently dropped values: "
        f"{unconsumed}. Register a consumption path (a native read in backend/app, or an "
        "_LEGACY_ENV_ALIASES entry mapping the legacy IDEER_* name to the DEER_FLOW_* name "
        "the runtime reads); only if the export is intentionally deploy-side only, document "
        "it with a justification in _INTENTIONALLY_DEPLOY_SIDE_ONLY in this test module."
    )
