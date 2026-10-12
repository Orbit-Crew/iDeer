"""Device control-plane credential gate exercised through the REAL gateway.

Regression for 01-H1: the device endpoints were only ever exercised on a bare
``FastAPI()`` app, so the global AuthMiddleware/CSRFMiddleware gates were never
in the loop. Under ``create_app()`` every device request was rejected with
403/401 before reaching the route's own device-credential checks, while the
bare-app tests stayed green.

Gate contract proven here:

- bootstrap (``register`` / ``register/complete``): one-time credentials in
  the body (pairing code, claim token) enforced by ``DeviceControlService``;
  a rejected credential is a 401.
- session (``heartbeat`` / ``disconnect``): the ``X-Device-Session`` token is
  enforced by the route (missing header → 401) and the service (unknown or
  disconnected token → 401).
- the browser-session gates stay fail-closed for every other device route
  (owner bootstrap, listing, revocation).
- the device WS channel authenticates on its own and still works behind the
  full middleware stack.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[4] / "local-runtime"))

from app.device_control.broker import get_device_broker
from app.device_control.protocol import MessageType, TaskEnvelope, public_key_text, sign_envelope

DEVICE_KEY = "ssh-ed25519 AAAA-real-gateway-gate-key"


def _error_message(response) -> str:
    """The real gateway stringifies non-whitelisted dict details into
    ``error.message``; the device control codes stay greppable there."""
    return str(response.json().get("error", {}).get("message", ""))


# Minimal config that satisfies AppConfig validation (mirrors the real-server
# e2e fixture); the device gate tests never instantiate a model.
_MINIMAL_CONFIG_YAML = """\
log_level: info
models:
  - name: fake-test-model
    display_name: Fake Test Model
    use: langchain_openai:ChatOpenAI
    model: gpt-4o-mini
    api_key: $OPENAI_API_KEY
    base_url: $OPENAI_API_BASE
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
agents_api:
  enabled: true
database:
  backend: sqlite
"""


@pytest.fixture
def gateway_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build the real ``create_app()`` inside an isolated DEER_FLOW_HOME."""
    monkeypatch.delenv("DEER_FLOW_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("DEER_FLOW_HOME", str(tmp_path / "ideer-home"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-key-not-used-by-device-gate-tests")
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.invalid")
    (tmp_path / "ideer-home").mkdir()
    staged_config = tmp_path / "config.yaml"
    staged_config.write_text(_MINIMAL_CONFIG_YAML, encoding="utf-8")
    monkeypatch.setenv("DEER_FLOW_CONFIG_PATH", str(staged_config))

    from deerflow.config import app_config as app_config_module
    from deerflow.config import paths as paths_module
    from deerflow.persistence import engine as engine_module

    for module, attr in (
        (app_config_module, "_app_config"),
        (app_config_module, "_app_config_path"),
        (app_config_module, "_app_config_mtime"),
        (paths_module, "_paths_singleton"),
        (engine_module, "_engine"),
        (engine_module, "_session_factory"),
    ):
        monkeypatch.setattr(module, attr, None, raising=False)

    # The local auth provider caches its user repository together with the
    # first engine's session factory; without this reset a second real-app
    # test in the same process would look users up in the previous test's
    # disposed database.
    from app.gateway import deps as gateway_deps

    monkeypatch.setattr(gateway_deps, "_cached_local_provider", None)
    monkeypatch.setattr(gateway_deps, "_cached_repo", None)

    # Pin the sqlite file into tmp_path: the default sqlite_dir is CWD-relative
    # and would share one database across every test in the session.
    cfg = app_config_module.get_app_config()
    cfg.database.sqlite_dir = str(tmp_path / "ideer-home" / "db")

    from app.gateway.app import create_app

    return create_app()


def _register_owner(owner_client: TestClient) -> dict:
    registered = owner_client.post(
        "/api/v1/auth/register",
        json={"email": "device-owner@example.com", "password": "very-strong-password-123"},
    )
    assert registered.status_code == 201, registered.text
    csrf_token = owner_client.cookies.get("csrf_token")
    assert csrf_token, "register must set the CSRF double-submit cookie"
    return {"X-CSRF-Token": csrf_token}


@pytest.mark.no_auto_user
def test_device_credential_gate_under_real_middleware(gateway_app) -> None:
    """No-credential → 401 on every device endpoint; valid device credentials pass."""
    broker = get_device_broker()
    broker.connections.clear()
    broker.tasks.clear()
    device_key = Ed25519PrivateKey.generate()

    with TestClient(gateway_app) as owner_client:
        owner_headers = _register_owner(owner_client)

        # --- owner bootstrap: create pairing, then confirm after registration
        pairing = owner_client.post("/api/devices/pairing", headers=owner_headers)
        assert pairing.status_code == 200, pairing.text
        challenge = pairing.json()

        # --- device client: no cookies, no session — exactly the tray/CLI caller
        device_client = TestClient(gateway_app)

        registered = device_client.post(
            "/api/devices/register",
            json={
                "pairing_code": challenge["code"],
                "name": "Gate laptop",
                "public_key": public_key_text(device_key.public_key()),
                "protocol_version": "1",
                "runtime_version": "0.1.0",
                "capabilities": ["echo"],
            },
        )
        assert registered.status_code == 200, registered.text
        registration = registered.json()
        device_id = registration["device"]["id"]
        assert registration["claim_token"]
        assert registration["server_public_key"]

        rejected_register = device_client.post(
            "/api/devices/register",
            json={
                "pairing_code": "0123456789abcdef",
                "name": "Gate laptop",
                "public_key": public_key_text(device_key.public_key()),
                "protocol_version": "1",
                "runtime_version": "0.1.0",
                "capabilities": ["echo"],
            },
        )
        assert rejected_register.status_code == 401, rejected_register.text
        assert "PAIRING_INVALID" in _error_message(rejected_register)

        confirmed = owner_client.post(
            f"/api/devices/pairing/{challenge['pairing_id']}/confirm",
            json={"code": challenge["code"]},
            headers=owner_headers,
        )
        assert confirmed.status_code == 200, confirmed.text

        wrong_claim = device_client.post(
            "/api/devices/register/complete",
            json={
                "device_id": device_id,
                "public_key": public_key_text(device_key.public_key()),
                "claim_token": "wrong-claim-token-value",
            },
        )
        assert wrong_claim.status_code == 401, wrong_claim.text
        assert "PAIRING_CLAIM_INVALID" in _error_message(wrong_claim)

        completed = device_client.post(
            "/api/devices/register/complete",
            json={
                "device_id": device_id,
                "public_key": public_key_text(device_key.public_key()),
                "claim_token": registration["claim_token"],
            },
        )
        assert completed.status_code == 200, completed.text
        session_token = completed.json()["session_token"]

        missing_session = device_client.post(f"/api/devices/{device_id}/heartbeat", json={})
        assert missing_session.status_code == 401, missing_session.text
        assert "DEVICE_SESSION_INVALID" in _error_message(missing_session)

        missing_disconnect = device_client.post(f"/api/devices/{device_id}/disconnect")
        assert missing_disconnect.status_code == 401, missing_disconnect.text

        online = device_client.post(
            f"/api/devices/{device_id}/heartbeat",
            headers={"X-Device-Session": session_token},
            json={},
        )
        assert online.status_code == 200, online.text
        assert online.json()["status"] == "online"

        offline = device_client.post(
            f"/api/devices/{device_id}/disconnect",
            headers={"X-Device-Session": session_token},
        )
        assert offline.status_code == 200, offline.text
        assert offline.json()["status"] == "offline"

        stale_session = device_client.post(
            f"/api/devices/{device_id}/heartbeat",
            headers={"X-Device-Session": session_token},
            json={},
        )
        assert stale_session.status_code == 401, stale_session.text
        assert "DEVICE_SESSION_INVALID" in _error_message(stale_session)

        # --- fail-closed control: user-side device routes keep the session gate
        anonymous_list = device_client.get("/api/devices")
        assert anonymous_list.status_code == 401, anonymous_list.text
        owner_list = owner_client.get("/api/devices")
        assert owner_list.status_code == 200, owner_list.text


@pytest.mark.no_auto_user
def test_device_endpoints_reject_missing_credentials_with_401(gateway_app) -> None:
    """The CSRF gate must not mask the auth failure: missing device credentials → 401."""
    with TestClient(gateway_app):
        device_client = TestClient(gateway_app)

        register_response = device_client.post(
            "/api/devices/register",
            json={
                "pairing_code": "0123456789abcdef",
                "name": "Anonymous laptop",
                "public_key": DEVICE_KEY,
                "protocol_version": "1",
                "runtime_version": "0.1.0",
                "capabilities": ["echo"],
            },
        )
        assert register_response.status_code == 401, register_response.text
        assert "PAIRING_INVALID" in _error_message(register_response)

        complete_response = device_client.post(
            "/api/devices/register/complete",
            json={
                "device_id": "does-not-exist",
                "public_key": DEVICE_KEY,
                "claim_token": "0123456789abcdef0123456789abcdef",
            },
        )
        assert complete_response.status_code == 401, complete_response.text
        assert "PAIRING_CLAIM_INVALID" in _error_message(complete_response)

        heartbeat_response = device_client.post("/api/devices/does-not-exist/heartbeat", json={})
        assert heartbeat_response.status_code == 401, heartbeat_response.text
        assert "DEVICE_SESSION_INVALID" in _error_message(heartbeat_response)

        disconnect_response = device_client.post("/api/devices/does-not-exist/disconnect")
        assert disconnect_response.status_code == 401, disconnect_response.text
        assert "DEVICE_SESSION_INVALID" in _error_message(disconnect_response)


@pytest.mark.no_auto_user
def test_device_websocket_channel_unregressed_under_real_middleware(gateway_app) -> None:
    """A signed device HELLO still opens the WS channel behind the full stack."""
    broker = get_device_broker()
    broker.connections.clear()
    broker.tasks.clear()
    device_key = Ed25519PrivateKey.generate()

    with TestClient(gateway_app) as owner_client:
        owner_headers = _register_owner(owner_client)
        pairing = owner_client.post("/api/devices/pairing", headers=owner_headers)
        assert pairing.status_code == 200, pairing.text
        challenge = pairing.json()

        device_client = TestClient(gateway_app)
        registered = device_client.post(
            "/api/devices/register",
            json={
                "pairing_code": challenge["code"],
                "name": "WS laptop",
                "public_key": public_key_text(device_key.public_key()),
                "protocol_version": "1",
                "runtime_version": "0.1.0",
                "capabilities": ["echo"],
            },
        )
        assert registered.status_code == 200, registered.text
        registration = registered.json()
        device_id = registration["device"]["id"]

        confirmed = owner_client.post(
            f"/api/devices/pairing/{challenge['pairing_id']}/confirm",
            json={"code": challenge["code"]},
            headers=owner_headers,
        )
        assert confirmed.status_code == 200, confirmed.text

        completed = device_client.post(
            "/api/devices/register/complete",
            json={
                "device_id": device_id,
                "public_key": public_key_text(device_key.public_key()),
                "claim_token": registration["claim_token"],
            },
        )
        assert completed.status_code == 200, completed.text
        session_id = completed.json()["session_id"]
        session_token = completed.json()["session_token"]

        with device_client.websocket_connect("/api/devices/ws") as websocket:
            hello = sign_envelope(
                private_key=device_key,
                message_type=MessageType.HELLO,
                device_id=device_id,
                session_id=session_id,
                payload={
                    "session_token": session_token,
                    "public_key": public_key_text(device_key.public_key()),
                    "protocol_version": "1",
                    "runtime_version": "0.1.0",
                    "capabilities": ["echo"],
                },
            )
            websocket.send_text(hello.model_dump_json(by_alias=True))
            server_hello = TaskEnvelope.model_validate_json(websocket.receive_text())
            assert server_hello.type == MessageType.HELLO
            assert device_id in broker.connections
