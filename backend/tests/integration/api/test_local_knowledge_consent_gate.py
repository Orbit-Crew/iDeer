"""Web consent decisions cannot approve device-local knowledge retrieval (#114).

A retrieval that the owning Desktop's policy gated behind local confirmation
waits inside the Run (the gateway polls the broker task). The Web may observe
the wait, but the allow/deny decision itself belongs to the device user: a
remote consent call must be refused before it can act for the device, for
regular users and administrators alike.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agentplatform.rbac_models import UserModel
from app.gateway.app import register_exception_handlers
from app.gateway.authz import get_current_rbac_user
from app.gateway.routers import devices


@pytest.mark.parametrize("role", ["user", "super_admin"])
@pytest.mark.parametrize("operation", ["local.knowledge.search", "local.files.write"])
def test_remote_consent_cannot_approve_device_gated_operations(monkeypatch, role, operation):
    record = SimpleNamespace(device_id="owned-device", payload={"operation": operation})

    class Broker:
        def get_task(self, task_id):
            return record

        async def send_consent_decision(self, *args, **kwargs):
            raise AssertionError("remote approval must never be forwarded to the device broker")

    async def owner_check(action):
        return SimpleNamespace()

    monkeypatch.setattr(devices, "get_device_broker", lambda: Broker())
    monkeypatch.setattr(devices, "_run", owner_check)
    app = FastAPI()
    app.include_router(devices.router)
    register_exception_handlers(app)
    app.dependency_overrides[get_current_rbac_user] = lambda: UserModel(id="owner", username="owner@example.com", role=role)
    with TestClient(app) as client:
        response = client.post("/api/devices/tasks/knowledge-task/consent", json={"approved": True, "actor_id": "owner"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LOCAL_APPROVAL_REQUIRED"
