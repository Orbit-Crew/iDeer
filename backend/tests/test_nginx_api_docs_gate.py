"""Contract: the published nginx entry 404s the OpenAPI surface by default (08-M10).

``docker/nginx/nginx.conf`` proxied ``/docs``, ``/redoc`` and ``/openapi.json``
straight to the gateway, so the public entry served the full OpenAPI structure
to anyone who could reach port 2026. The template now gates all three
locations on ``$api_docs_enabled`` — a map over ``$NGINX_EXPOSE_API_DOCS``,
rendered at container start by the nginx service command (``envsubst`` with a
restricted variable list so the runtime proxies' ``$gateway_upstream`` etc.
stay untouched). Prod and intranet default to ``false``; the dev stack
defaults to ``true`` for local debugging.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_TEMPLATE = REPO_ROOT / "docker" / "nginx" / "nginx.conf"

COMPOSE_DEFAULTS = {
    "prod": (REPO_ROOT / "docker" / "docker-compose.yaml", "false"),
    "dev": (REPO_ROOT / "docker" / "docker-compose-dev.yaml", "true"),
    "intranet": (REPO_ROOT / "docker" / "docker-compose.intranet.yaml", "false"),
}

GATED_LOCATIONS = ("/docs", "/redoc", "/openapi.json")


def test_nginx_template_gates_every_openapi_surface_location() -> None:
    """Each docs location must 404 unless the rendered gate enables it."""
    config = NGINX_TEMPLATE.read_text(encoding="utf-8")

    assert 'map "$NGINX_EXPOSE_API_DOCS" $api_docs_enabled' in config, "nginx.conf must define the api docs gate as a map over the container-rendered NGINX_EXPOSE_API_DOCS value (08-M10)"
    for location in GATED_LOCATIONS:
        block = _location_block(config, location)
        assert "if ($api_docs_enabled = 0)" in block, f"{location} must return 404 while the rendered NGINX_EXPOSE_API_DOCS is not 'true' (08-M10); the location exposes the full OpenAPI structure"
        assert "return 404;" in block


def test_compose_files_render_the_gate_with_a_restricted_envsubst() -> None:
    """The nginx service command must render the gate without touching runtime variables.

    ``envsubst`` without a variable list would blank every ``$gateway_upstream``/
    ``$http_host``/``$remote_addr`` expression in the template, so the command
    must pass exactly ``$NGINX_EXPOSE_API_DOCS`` (compose-escaped as ``$$``).
    """
    for variant, (path, _) in COMPOSE_DEFAULTS.items():
        compose = yaml.safe_load(path.read_text(encoding="utf-8"))
        nginx = compose["services"]["nginx"]
        command = _nginx_command_text(nginx)
        # the file stores the compose-escaped form ($$ -> $ after compose interpolation)
        assert "envsubst '$$NGINX_EXPOSE_API_DOCS'" in command, (
            f"{variant} nginx command must render the template with envsubst restricted to $NGINX_EXPOSE_API_DOCS (compose-escaped as $$); a bare envsubst would substitute the runtime nginx variables too"
        )
        assert "cp /etc/nginx/nginx.conf.template /etc/nginx/nginx.conf" not in command, (
            f"{variant} must render via envsubst instead of copying the unrendered template; nginx would fail to start on the unknown $NGINX_EXPOSE_API_DOCS variable"
        )


def test_compose_files_default_the_gate_closed_for_prod_and_open_for_dev() -> None:
    for variant, (path, expected_default) in COMPOSE_DEFAULTS.items():
        compose = yaml.safe_load(path.read_text(encoding="utf-8"))
        environment = compose["services"]["nginx"].get("environment") or {}
        if isinstance(environment, list):
            environment = dict(entry.split("=", 1) for entry in environment)
        declared = environment.get("NGINX_EXPOSE_API_DOCS")
        assert declared == f"${{NGINX_EXPOSE_API_DOCS:-{expected_default}}}", f"{variant} nginx must default NGINX_EXPOSE_API_DOCS to {expected_default}; got {declared!r}"


def test_every_container_nginx_stack_carries_the_ipv6_fallback() -> None:
    """08-L8: prod/intranet nginx commands need the dev stack's no-IPv6 sed fallback.

    Without it, nginx on an IPv6-disabled kernel fails to bind [::]:2026 and
    the container restart-loops; only docker-compose-dev.yaml had the guard.
    """
    for name in ("docker-compose.yaml", "docker-compose-dev.yaml", "docker-compose.intranet.yaml"):
        compose = yaml.safe_load((REPO_ROOT / "docker" / name).read_text(encoding="utf-8"))
        command = _nginx_command_text(compose["services"]["nginx"])
        assert "/proc/net/if_inet6" in command, f"{name} nginx command must keep the IPv6-disabled-host fallback that strips the 'listen [::]:2026' line (08-L8)"
        assert "\\[::\\]:2026" in command, f"{name} must reference the exact [::]:2026 listen pattern"


def test_rendered_template_resolves_the_gate_for_both_settings() -> None:
    """Substituting the rendered value must produce a concrete map for 'false' and 'true'."""
    config = NGINX_TEMPLATE.read_text(encoding="utf-8")
    for rendered, expected in (("false", 'map "false" $api_docs_enabled'), ("true", 'map "true" $api_docs_enabled')):
        rendered_config = config.replace("$NGINX_EXPOSE_API_DOCS", rendered)
        assert expected in rendered_config, f"after rendering NGINX_EXPOSE_API_DOCS={rendered}, the gate map must read {expected!r}"
    # every other runtime variable stays in place for nginx to resolve at runtime
    rendered = config.replace("$NGINX_EXPOSE_API_DOCS", "false")
    assert "$gateway_upstream" in rendered
    assert "$http_host" in rendered


def _location_block(config: str, location: str) -> str:
    marker = f"location {location} {{"
    start = config.index(marker)
    end = config.index("\n        }", start)
    return config[start:end]


def _nginx_command_text(nginx_service: dict) -> str:
    command = nginx_service.get("command")
    if isinstance(command, str):
        return command
    if isinstance(command, list):
        return "\n".join(str(part) for part in command)
    raise AssertionError(f"unexpected nginx command shape: {command!r}")
