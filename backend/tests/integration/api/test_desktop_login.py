"""Desktop login is an initiator-bound exchange, separate from browser auth."""

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agentplatform.rbac_models import UserModel
from app.device_control import desktop_login
from app.device_control.protocol import public_key_text
from app.gateway.app import register_exception_handlers
from app.gateway.authz import get_current_rbac_user
from app.gateway.routers import devices
from deerflow.persistence.base import Base
from deerflow.persistence.user.model import UserRow


@pytest_asyncio.fixture
async def login_client(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'login.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner = UserModel(id=str(uuid4()), username="desktop@example.com", role="user")
    other = UserModel(id=str(uuid4()), username="other@example.com", role="user")
    async with factory() as session:
        session.add(owner)
        session.add(other)
        session.add(UserRow(id=owner.id, email=owner.username, token_version=7))
        session.add(UserRow(id=other.id, email=other.username))
        await session.commit()
    monkeypatch.setattr(devices, "get_session_factory", lambda: factory)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(devices.router)
    app.dependency_overrides[get_current_rbac_user] = lambda: owner
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://official.example") as client:
        yield client, owner, app, other
    await engine.dispose()


@pytest.mark.asyncio
async def test_browser_confirmation_does_not_create_desktop_session_until_exchange(login_client):
    client, owner, _, _ = login_client
    public_key = public_key_text(Ed25519PrivateKey.generate().public_key())
    start = await client.post(
        "/api/devices/login/start",
        json={
            "initiator_secret": "a" * 43,
            "public_key": public_key,
            "name": "Desktop D1",
        },
    )
    assert start.status_code == 200
    login_id = start.json()["login_id"]
    exchange = {"initiator_secret": "a" * 43, "public_key": public_key}
    pending = await client.post(f"/api/devices/login/{login_id}/complete", json=exchange)
    assert pending.status_code == 202
    assert "token" not in pending.text
    confirmed = await client.post(f"/api/devices/login/{login_id}/confirm", json={"confirm_own_device": True})
    assert confirmed.status_code == 200
    assert "token" not in confirmed.text
    completed = await client.post(f"/api/devices/login/{login_id}/complete", json=exchange)
    assert completed.status_code == 200
    result = completed.json()
    assert result["account"]["id"] == owner.id
    assert result["device"]["owner_id"] == owner.id
    assert result["business_token"] != result["session_token"]
    assert result["device"]["status"] == "pending"
    replay = await client.post(f"/api/devices/login/{login_id}/complete", json=exchange)
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "LOGIN_ALREADY_USED"


async def start_login(client, key=None):
    key = key or Ed25519PrivateKey.generate()
    payload = {"initiator_secret": "a" * 43, "public_key": public_key_text(key.public_key())}
    response = await client.post("/api/devices/login/start", json={**payload, "name": "D1"})
    assert response.status_code == 200
    return response.json()["login_id"], payload


@pytest.mark.asyncio
async def test_wrong_initiator_device_or_owner_never_creates_a_session(login_client):
    client, _, app, other = login_client
    login_id, payload = await start_login(client)
    endpoint = f"/api/devices/login/{login_id}"
    for invalid in [
        {**payload, "initiator_secret": "b" * 43},
        {**payload, "public_key": public_key_text(Ed25519PrivateKey.generate().public_key())},
    ]:
        response = await client.post(endpoint + "/complete", json=invalid)
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "LOGIN_BINDING_INVALID"
    assert (await client.get("/api/devices")).json() == []
    assert (await client.post(endpoint + "/confirm", json={"confirm_own_device": False})).status_code == 400
    assert (await client.post(endpoint + "/confirm", json={"confirm_own_device": True})).status_code == 200
    app.dependency_overrides[get_current_rbac_user] = lambda: other
    for response in [await client.get(endpoint), await client.post(endpoint + "/confirm", json={"confirm_own_device": True})]:
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "LOGIN_OWNER_MISMATCH"


@pytest.mark.asyncio
async def test_expired_exchange_cannot_confirm_or_complete(login_client, monkeypatch):
    client, _, _, _ = login_client
    login_id, payload = await start_login(client)
    future = datetime.now(UTC) + timedelta(seconds=301)

    class FutureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return future

    monkeypatch.setattr(desktop_login, "datetime", FutureClock)
    for response in [
        await client.post(f"/api/devices/login/{login_id}/confirm", json={"confirm_own_device": True}),
        await client.post(f"/api/devices/login/{login_id}/complete", json=payload),
    ]:
        assert response.status_code == 410
        assert response.json()["detail"]["code"] == "LOGIN_EXPIRED"
    assert (await client.get("/api/devices")).json() == []


@pytest.mark.asyncio
async def test_concurrent_completion_has_exactly_one_winner(login_client):
    client, _, _, _ = login_client
    login_id, payload = await start_login(client)
    endpoint = f"/api/devices/login/{login_id}"
    await client.post(endpoint + "/confirm", json={"confirm_own_device": True})
    results = await asyncio.gather(*[client.post(endpoint + "/complete", json=payload) for _ in range(2)])
    assert sorted(response.status_code for response in results) == [200, 409]
    assert len((await client.get("/api/devices")).json()) == 1


@pytest.mark.asyncio
async def test_same_device_reauthentication_requires_owner_and_stored_key_proof(login_client):
    client, owner, app, other = login_client
    key = Ed25519PrivateKey.generate()
    login_id, payload = await start_login(client, key)
    await client.post(f"/api/devices/login/{login_id}/confirm", json={"confirm_own_device": True})
    first = (await client.post(f"/api/devices/login/{login_id}/complete", json=payload)).json()
    device_id = first["device"]["id"]
    online = await client.post(f"/api/devices/{device_id}/heartbeat", json={}, headers={"X-Device-Session": first["session_token"]})
    assert online.json()["status"] == "online"
    started = await client.post("/api/devices/login/start", json={**payload, "existing_device_id": device_id, "name": "D1"})
    assert started.status_code == 200
    renewal_id = started.json()["login_id"]
    endpoint = f"/api/devices/login/{renewal_id}"
    app.dependency_overrides[get_current_rbac_user] = lambda: other
    denied = await client.post(endpoint + "/confirm", json={"confirm_own_device": True})
    assert denied.status_code == 403
    app.dependency_overrides[get_current_rbac_user] = lambda: owner
    assert (await client.post(endpoint + "/confirm", json={"confirm_own_device": True})).status_code == 200
    assert (await client.post(endpoint + "/complete", json=payload)).status_code == 401
    proof = base64.b64encode(key.sign(f"desktop-login\n{renewal_id}\n{payload['initiator_secret']}".encode())).decode()
    response = await client.post(endpoint + "/complete", json={**payload, "device_proof": proof})
    assert response.status_code == 200
    renewed = response.json()
    assert renewed["device"]["id"] == device_id
    assert renewed["device"]["owner_id"] == owner.id
    assert renewed["device"]["status"] == "offline"
    assert renewed["session_token"] != first["session_token"]
    old_session = await client.post(f"/api/devices/{device_id}/heartbeat", json={}, headers={"X-Device-Session": first["session_token"]})
    assert old_session.status_code == 401
    current_session = await client.post(f"/api/devices/{device_id}/heartbeat", json={}, headers={"X-Device-Session": renewed["session_token"]})
    assert current_session.status_code == 200
    assert len((await client.get("/api/devices")).json()) == 1
