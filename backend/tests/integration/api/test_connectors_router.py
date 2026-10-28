"""Canonical Connector identity (#123).

A connector installed on the user's own device gets a platform-canonical
identity row, but the runnable binding — command line, environment, secrets,
entry path — never leaves the device: the registration body has a fixed key
allowlist and every credential-shaped key is rejected outright. The identity
is owner-scoped by construction: no visibility field, no share or publish
endpoint exists, so another account cannot see, list, or run another user's
connector (invisible is 404, not 403), and a second device of the same owner
learns at most the identity — never a runnable configuration.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agentplatform.rbac_models import UserModel
from app.gateway.authz import get_current_rbac_user
from app.gateway.routers import connectors
from deerflow.persistence.base import Base


@pytest_asyncio.fixture
async def connector_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(UserModel(id="owner", username="owner@example.com", role="user"))
        session.add(UserModel(id="other", username="other@example.com", role="user"))
        await session.commit()
    monkeypatch.setattr(connectors, "get_session_factory", lambda: factory)
    yield factory
    await engine.dispose()


def _client(factory, *, user_id: str = "owner") -> TestClient:
    app = FastAPI()
    app.include_router(connectors.router)
    app.dependency_overrides[get_current_rbac_user] = lambda: UserModel(id=user_id, username=f"{user_id}@example.com", role="user")
    return TestClient(app)


def _register_body(**overrides):
    body = {
        "slug": "demo-echo",
        "display_name": "Demo Echo Connector",
        "version": "1.2.0",
        "manifest_hash": "a" * 64,
    }
    body.update(overrides)
    return body


def test_register_creates_owner_scoped_canonical_identity(connector_factory) -> None:
    client = _client(connector_factory)
    response = client.post("/api/connectors", json=_register_body())
    assert response.status_code == 200
    row = response.json()
    assert row["slug"] == "demo-echo"
    assert row["displayName"] == "Demo Echo Connector"
    assert row["version"] == "1.2.0"
    assert row["manifestHash"] == "a" * 64
    connector_id = row["connectorId"]
    assert connector_id

    listed = client.get("/api/connectors")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["connectorId"] for item in items] == [connector_id]


def test_register_is_idempotent_for_same_frozen_identity(connector_factory) -> None:
    client = _client(connector_factory)
    first = client.post("/api/connectors", json=_register_body()).json()
    second = client.post("/api/connectors", json=_register_body()).json()
    assert second["connectorId"] == first["connectorId"]


def test_same_version_with_different_content_is_a_conflict(connector_factory) -> None:
    client = _client(connector_factory)
    assert client.post("/api/connectors", json=_register_body()).status_code == 200
    conflict = client.post("/api/connectors", json=_register_body(manifest_hash="b" * 64))
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "CONNECTOR_IDENTITY_CONFLICT"


def test_version_upgrade_updates_the_identity_row(connector_factory) -> None:
    client = _client(connector_factory)
    first = client.post("/api/connectors", json=_register_body()).json()
    upgraded = client.post("/api/connectors", json=_register_body(version="1.3.0", manifest_hash="c" * 64))
    assert upgraded.status_code == 200
    assert upgraded.json()["connectorId"] == first["connectorId"]
    assert upgraded.json()["version"] == "1.3.0"
    assert upgraded.json()["manifestHash"] == "c" * 64


def test_registration_rejects_credential_shaped_keys(connector_factory) -> None:
    """The fixed key allowlist is the secrets-never-reach-the-Server gate."""
    client = _client(connector_factory)
    for key, value in (
        ("command", ["python", "server.py"]),
        ("env", {"API_KEY": "x"}),
        ("token", "secret"),
        ("entry", "server.py"),
        ("args", {"a": 1}),
        ("secrets", {"k": "v"}),
    ):
        response = client.post("/api/connectors", json={**_register_body(), key: value})
        assert response.status_code == 422, key


def test_registration_validates_identity_fields(connector_factory) -> None:
    client = _client(connector_factory)
    assert client.post("/api/connectors", json=_register_body(slug="../escape")).status_code == 422
    assert client.post("/api/connectors", json=_register_body(slug="d" * 65)).status_code == 422
    assert client.post("/api/connectors", json=_register_body(version="1.2")).status_code == 422
    assert client.post("/api/connectors", json=_register_body(manifest_hash="zz")).status_code == 422
    assert client.post("/api/connectors", json=_register_body(display_name="")).status_code == 422
    assert client.get("/api/connectors").json()["items"] == []


def test_other_account_cannot_see_or_list_foreign_connectors(connector_factory) -> None:
    client = _client(connector_factory, user_id="owner")
    created = client.post("/api/connectors", json=_register_body()).json()

    other = _client(connector_factory, user_id="other")
    assert other.get("/api/connectors").json()["items"] == []
    assert other.get(f"/api/connectors/{created['connectorId']}").status_code == 404
    assert other.delete(f"/api/connectors/{created['connectorId']}").status_code == 404
    # The owner still sees it; an unknown id is a 404 for the owner too.
    assert client.get(f"/api/connectors/{created['connectorId']}").status_code == 200
    assert client.get("/api/connectors/missing").status_code == 404


def test_owner_can_remove_the_identity(connector_factory) -> None:
    client = _client(connector_factory)
    created = client.post("/api/connectors", json=_register_body()).json()
    assert client.delete(f"/api/connectors/{created['connectorId']}").status_code == 204
    assert client.get("/api/connectors").json()["items"] == []
    assert client.get(f"/api/connectors/{created['connectorId']}").status_code == 404


def test_registration_requires_authentication(connector_factory) -> None:
    app = FastAPI()
    app.include_router(connectors.router)
    with TestClient(app) as client:
        assert client.post("/api/connectors", json=_register_body()).status_code in {401, 403}


def test_registration_does_not_leak_payload_into_logs(connector_factory, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    client = _client(connector_factory)
    secret = "super-secret-env-value-12345"
    # Application logs (INFO and up) — the DEBUG-level ORM bound-parameter
    # trace is a shared aiosqlite property of every router, not our surface.
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/connectors",
            json={**_register_body(), "display_name": secret},
        )
    assert response.status_code == 200
    assert secret not in caplog.text
