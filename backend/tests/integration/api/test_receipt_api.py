"""Issue101 signed receipt API, real device authorization and durable query."""

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.agentplatform.rbac_models import UserModel
from app.device_control.broker import get_device_broker
from app.device_control.protocol import MessageType, TaskEnvelope, public_key_text, sign_envelope
from app.device_control.receipt_archive import receipt_digest
from app.gateway.authz import get_current_rbac_user
from app.gateway.routers import devices
from tests.integration.api.test_devices_router import device_factory  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.usefixtures("device_factory")
async def test_receipt_replay_api_is_idempotent_owner_scoped_and_revocation_checked(monkeypatch):
    app = FastAPI()
    app.include_router(devices.router)
    owner = UserModel(id="owner", username="owner@example.com", role="user")
    app.dependency_overrides[get_current_rbac_user] = lambda: owner
    broker = get_device_broker()
    broker.connections.clear()
    broker.tasks.clear()
    key = Ed25519PrivateKey.generate()
    public = public_key_text(key.public_key())
    with TestClient(app) as client:
        pairing = client.post("/api/devices/pairing").json()
        registered = client.post("/api/devices/register", json={"pairing_code": pairing["code"], "name": "Receipt fixture", "public_key": public, "protocol_version": "1", "runtime_version": "0.1.0", "capabilities": ["echo"]}).json()
        device = registered["device"]["id"]
        assert client.post(f"/api/devices/pairing/{pairing['pairing_id']}/confirm", json={"code": pairing["code"]}).status_code == 200
        session = client.post("/api/devices/register/complete", json={"device_id": device, "public_key": public, "claim_token": registered["claim_token"]}).json()

        def hello():
            return sign_envelope(
                private_key=key,
                message_type=MessageType.HELLO,
                device_id=device,
                session_id=session["session_id"],
                payload={"session_token": session["session_token"], "public_key": public, "protocol_version": "1", "runtime_version": "0.1.0", "capabilities": ["echo"]},
            ).model_dump_json(by_alias=True)

        with client.websocket_connect("/api/devices/ws") as socket:
            socket.send_text(hello())
            server_hello = TaskEnvelope.model_validate_json(socket.receive_text())
            assert server_hello.payload["receipt_replay"] == 1
            task_id = client.post(f"/api/devices/{device}/tasks/echo", json={"run_id": "terminal-run", "tool_call_id": "call-101", "value": "fixed101"}).json()["task_id"]
            task = TaskEnvelope.model_validate_json(socket.receive_text())
            original = client.get(f"/api/devices/receipts/{task_id}").json()
            receipt = {"task_id": task_id, "run_id": "terminal-run", "capability": "echo", "request_hash": task.payload_hash, "payload_hash": task.payload_hash, "status": "completed", "policy_decision": "allow"}
            upload = {"receipt_id": "receipt-api-101", "binding": original["binding"], "task": original["task"], "receipt": receipt}
            upload["receipt_hash"] = receipt_digest(upload)
            acknowledgments = []
            for _ in range(2):
                socket.send_text(sign_envelope(private_key=key, message_type=MessageType.RECEIPT_UPLOAD, device_id=device, session_id=session["session_id"], task_id=task_id, payload=upload).model_dump_json(by_alias=True))
                acknowledgment = TaskEnvelope.model_validate_json(socket.receive_text())
                acknowledgment.verify(public_key=broker.server_private_key.public_key(), expected_device_id=device, expected_session_id=session["session_id"])
                assert acknowledgment.type == MessageType.RECEIPT_ACK
                acknowledgments.append(acknowledgment.payload)
            assert acknowledgments[0] == acknowledgments[1]
            broker.tasks.clear()
            persisted = client.get(f"/api/devices/receipts/{task_id}").json()
            assert persisted["evidence"]["tool_call_id"] == "call-101"
            app.dependency_overrides[get_current_rbac_user] = lambda: UserModel(id="other", username="other@example.com", role="user")
            assert client.get(f"/api/devices/receipts/{task_id}").status_code == 404
            app.dependency_overrides[get_current_rbac_user] = lambda: owner

            async def leave_existing_socket_open(*args, **kwargs):
                pass

            monkeypatch.setattr(broker, "invalidate", leave_existing_socket_open)
            assert client.post(f"/api/devices/{device}/revoke").status_code == 200
            socket.send_text(sign_envelope(private_key=key, message_type=MessageType.RECEIPT_UPLOAD, device_id=device, session_id=session["session_id"], task_id=task_id, payload=upload).model_dump_json(by_alias=True))
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_text()
            assert closed.value.code == 4003
        with client.websocket_connect("/api/devices/ws") as socket:
            socket.send_text(hello())
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_text()
            assert closed.value.code == 4003
