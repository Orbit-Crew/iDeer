"""Contract: the production compose gateway healthcheck must survive its base image.

The gateway runtime image (backend/Dockerfile final stage, ``python:3.12-slim-bookworm``)
ships neither curl nor wget, so a healthcheck that shells out to curl can never
succeed: ``docker compose up --wait`` never sees the gateway healthy and nginx's
``service_healthy`` dependency stays blocked. Upstream probes with python urllib
from the same position (deer-flow #4806, later repointed at ``/health/ready`` by
#5166); the local compose regressed to ``curl`` when the healthcheck was re-added
in 819607837. The probed path must also be one the gateway app actually
registers — probing an unregistered route returns 404 forever with the same
stuck-unhealthy outcome.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
_COMPOSE_PATH = _REPO_ROOT / "docker" / "docker-compose.yaml"
_GATEWAY_APP_PATH = _REPO_ROOT / "backend" / "app" / "gateway" / "app.py"


def _gateway_healthcheck() -> dict:
    doc = yaml.safe_load(_COMPOSE_PATH.read_text(encoding="utf-8"))
    gateway = (doc or {}).get("services", {}).get("gateway")
    assert gateway, "docker/docker-compose.yaml must define a gateway service"
    healthcheck = gateway.get("healthcheck")
    assert healthcheck, "gateway service must define a healthcheck (nginx depends_on gateway: service_healthy)"
    return healthcheck


def test_production_gateway_healthcheck_probes_with_python_urllib() -> None:
    """The healthcheck command must be the python urllib form, never curl/wget."""
    command = _gateway_healthcheck()["test"]
    assert command[:3] == ["CMD", "python", "-c"], f"gateway healthcheck must run python directly as ['CMD', 'python', '-c', <script>]; the base image has no curl/wget, got {command!r}"
    script = command[3]
    assert "import urllib.request" in script, f"healthcheck script must use urllib.request, got {script!r}"
    assert "urllib.request.urlopen(" in script, f"healthcheck script must probe via urllib.request.urlopen, got {script!r}"
    assert "curl" not in script and "wget" not in script, f"healthcheck script must not shell out to curl/wget, got {script!r}"


def test_production_gateway_healthcheck_targets_a_registered_route() -> None:
    """The probed path must be a GET route the gateway app actually registers."""
    command = _gateway_healthcheck()["test"]
    script = command[-1]
    match = re.search(r"urllib\.request\.urlopen\('http://127\.0\.0\.1:8001([^']*)'", script)
    assert match, f"healthcheck must probe the in-container gateway on http://127.0.0.1:8001/…, got {script!r}"
    path = match.group(1)

    app_source = _GATEWAY_APP_PATH.read_text(encoding="utf-8")
    registered = set(re.findall(r'@app\.get\("(/[^"]*)"', app_source))
    assert path in registered, f"gateway healthcheck probes {path!r} but app.gateway.app only registers {sorted(registered)}; a probe against an unregistered route returns 404 and the container can never become healthy"
