"""Tests for the legacy env alias layer (``app.gateway.compat_env``).

The enterprise deploy surface (``docker/docker-compose*.yaml``) exports the
pre-convergence ``IDEER_*`` variable names while the converged runtime reads
``DEER_FLOW_*``. These tests pin the alias contract, including the channels
service URLs that the docker stack passes to the gateway container.
"""

import os

import pytest

from app.gateway.compat_env import _LEGACY_ENV_ALIASES, apply_legacy_env_aliases

_ALIASED_KEYS = (
    "IDEER_CHANNELS_LANGGRAPH_URL",
    "IDEER_CHANNELS_GATEWAY_URL",
    "DEER_FLOW_CHANNELS_LANGGRAPH_URL",
    "DEER_FLOW_CHANNELS_GATEWAY_URL",
)


@pytest.fixture(autouse=True)
def _channels_env_cleanup():
    """apply_legacy_env_aliases() writes the real os.environ; keep tests isolated."""
    yield
    for key in _ALIASED_KEYS:
        os.environ.pop(key, None)


def test_channels_env_vars_are_aliased(monkeypatch):
    """Compose exports IDEER_CHANNELS_*; the runtime must see DEER_FLOW_CHANNELS_*.

    Regression for the docker stack: docker-compose.yaml passes
    IDEER_CHANNELS_LANGGRAPH_URL / IDEER_CHANNELS_GATEWAY_URL into the gateway
    container, and ChannelService resolves its URLs from the DEER_FLOW_CHANNELS_*
    equivalents. Before the channels aliases existed the compose values were
    silently dropped and the service fell back to the localhost defaults.
    """
    from app.channels.service import ChannelService

    monkeypatch.setenv("IDEER_CHANNELS_LANGGRAPH_URL", "http://gateway:8001/api")
    monkeypatch.setenv("IDEER_CHANNELS_GATEWAY_URL", "http://gateway:8001")
    monkeypatch.delenv("DEER_FLOW_CHANNELS_LANGGRAPH_URL", raising=False)
    monkeypatch.delenv("DEER_FLOW_CHANNELS_GATEWAY_URL", raising=False)

    applied = apply_legacy_env_aliases()

    assert applied["IDEER_CHANNELS_LANGGRAPH_URL"] == "DEER_FLOW_CHANNELS_LANGGRAPH_URL"
    assert applied["IDEER_CHANNELS_GATEWAY_URL"] == "DEER_FLOW_CHANNELS_GATEWAY_URL"
    assert os.environ["DEER_FLOW_CHANNELS_LANGGRAPH_URL"] == "http://gateway:8001/api"
    assert os.environ["DEER_FLOW_CHANNELS_GATEWAY_URL"] == "http://gateway:8001"

    service = ChannelService(channels_config={})
    assert service.manager._langgraph_url == "http://gateway:8001/api"
    assert service.manager._gateway_url == "http://gateway:8001"


def test_explicit_modern_channels_value_wins(monkeypatch):
    """Aliases never override an explicit new-style value."""
    monkeypatch.setenv("IDEER_CHANNELS_LANGGRAPH_URL", "http://legacy:8001/api")
    monkeypatch.setenv("DEER_FLOW_CHANNELS_LANGGRAPH_URL", "http://modern:8001/api")

    applied = apply_legacy_env_aliases()

    assert "IDEER_CHANNELS_LANGGRAPH_URL" not in applied
    assert os.environ["DEER_FLOW_CHANNELS_LANGGRAPH_URL"] == "http://modern:8001/api"


def test_alias_table_covers_channels_pairs():
    from app.channels.service import _CHANNELS_GATEWAY_URL_ENV, _CHANNELS_LANGGRAPH_URL_ENV

    assert _LEGACY_ENV_ALIASES["IDEER_CHANNELS_LANGGRAPH_URL"] == _CHANNELS_LANGGRAPH_URL_ENV
    assert _LEGACY_ENV_ALIASES["IDEER_CHANNELS_GATEWAY_URL"] == _CHANNELS_GATEWAY_URL_ENV
