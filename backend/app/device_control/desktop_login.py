"""Short-lived Desktop login approval over the existing platform identity."""

from __future__ import annotations

import base64
import hmac
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from sqlalchemy import delete, update

from app.agentplatform.rbac_models import UserModel
from deerflow.persistence.user.model import UserRow

from .models import DesktopLoginModel, DeviceModel, DeviceStatus
from .pairing import hash_secret
from .protocol import load_public_key
from .service import DeviceControlError, DeviceControlService, _as_utc

LOGIN_TTL = timedelta(minutes=5)


class DesktopLoginService:
    def __init__(self, devices: DeviceControlService):
        self.devices = devices
        self.session = devices.session

    async def start(self, *, initiator_secret: str, public_key: str, name: str, existing_device_id: str | None = None) -> dict:
        try:
            load_public_key(public_key)
        except (ValueError, TypeError) as exc:
            raise DeviceControlError("DEVICE_KEY_INVALID", "device key invalid", 400) from exc
        if existing_device_id:
            device = await self.session.get(DeviceModel, existing_device_id)
            if device is None or device.public_key != public_key or device.status in {DeviceStatus.REVOKED, DeviceStatus.BLOCKED}:
                raise DeviceControlError("LOGIN_BINDING_INVALID", "existing device is unavailable", 401)
            name = device.name
        now = datetime.now(UTC)
        # Expired approvals contain no credentials and cannot become sessions.
        await self.session.execute(delete(DesktopLoginModel).where(DesktopLoginModel.expires_at < now - timedelta(days=1)))
        login = DesktopLoginModel(id=str(uuid4()), initiator_digest=hash_secret(initiator_secret), public_key=public_key, name=name, state="pending", expires_at=now + LOGIN_TTL, existing_device_id=existing_device_id)
        self.session.add(login)
        await self.session.commit()
        return {"login_id": login.id, "expires_in": 300}

    async def _get(self, login_id: str) -> DesktopLoginModel:
        login = await self.session.get(DesktopLoginModel, login_id)
        if login is None:
            raise DeviceControlError("LOGIN_NOT_FOUND", "login is unavailable", 404)
        if _as_utc(login.expires_at) <= datetime.now(UTC):
            raise DeviceControlError("LOGIN_EXPIRED", "login expired; start again from Desktop", 410)
        return login

    async def _check_existing_owner(self, login: DesktopLoginModel, owner_id: str) -> None:
        if login.existing_device_id:
            device = await self.session.get(DeviceModel, login.existing_device_id)
            if device is None or device.owner_id != owner_id or device.public_key != login.public_key or device.status in {DeviceStatus.REVOKED, DeviceStatus.BLOCKED}:
                raise DeviceControlError("LOGIN_OWNER_MISMATCH", "existing device does not belong to this account", 403)

    async def describe(self, login_id: str, owner_id: str) -> dict:
        login = await self._get(login_id)
        await self._check_existing_owner(login, owner_id)
        if login.owner_id and login.owner_id != owner_id:
            raise DeviceControlError("LOGIN_OWNER_MISMATCH", "login belongs to another account", 403)
        return {"name": login.name, "verification": hash_secret(login.public_key)[:12], "state": login.state}

    async def confirm(self, login_id: str, owner_id: str) -> dict:
        login = await self._get(login_id)
        await self._check_existing_owner(login, owner_id)
        if login.owner_id and login.owner_id != owner_id:
            raise DeviceControlError("LOGIN_OWNER_MISMATCH", "login belongs to another account", 403)
        user = await self.session.get(UserRow, owner_id)
        owner = await self.session.get(UserModel, owner_id)
        if user is None or owner is None or owner.disabled or user.needs_setup:
            raise DeviceControlError("LOGIN_ACCOUNT_UNAVAILABLE", "account cannot authorize Desktop", 403)
        result = await self.session.execute(
            update(DesktopLoginModel)
            .where(
                DesktopLoginModel.id == login_id,
                DesktopLoginModel.state == "pending",
                DesktopLoginModel.expires_at > datetime.now(UTC),
            )
            .values(state="approved", owner_id=owner_id, token_version=user.token_version)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        if result.rowcount != 1:
            raise DeviceControlError("LOGIN_ALREADY_USED", "login already confirmed or consumed", 409)
        return {"state": "approved"}

    async def complete(self, login_id: str, *, initiator_secret: str, public_key: str, device_proof: str | None = None) -> dict | None:
        login = await self._get(login_id)
        if not hmac.compare_digest(login.initiator_digest, hash_secret(initiator_secret)) or login.public_key != public_key:
            raise DeviceControlError("LOGIN_BINDING_INVALID", "login initiator or device does not match", 401)
        if login.state == "pending":
            return None
        if login.state != "approved":
            raise DeviceControlError("LOGIN_ALREADY_USED", "login completion already consumed", 409)
        await self._check_existing_owner(login, login.owner_id)
        if login.existing_device_id:
            try:
                load_public_key(public_key).verify(base64.b64decode(device_proof or "", validate=True), f"desktop-login\n{login_id}\n{initiator_secret}".encode())
            except (InvalidSignature, ValueError, TypeError) as exc:
                raise DeviceControlError("LOGIN_BINDING_INVALID", "existing device signature is invalid", 401) from exc
        user = await self.session.get(UserRow, login.owner_id)
        owner = await self.session.get(UserModel, login.owner_id)
        if user is None or owner is None or owner.disabled or user.needs_setup or user.token_version != login.token_version:
            raise DeviceControlError("LOGIN_ACCOUNT_UNAVAILABLE", "account approval is no longer valid", 403)
        # Compare-and-swap survives concurrent pollers and multiple workers.
        result = await self.session.execute(
            update(DesktopLoginModel)
            .where(
                DesktopLoginModel.id == login_id,
                DesktopLoginModel.state == "approved",
                DesktopLoginModel.expires_at > datetime.now(UTC),
            )
            .values(state="consumed")
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        if result.rowcount != 1:
            raise DeviceControlError("LOGIN_ALREADY_USED", "login completion already consumed", 409)
        # Retain the same four security transitions as manual pairing. No claim
        # or pairing credential ever reaches the browser or the renderer.
        if login.existing_device_id:
            registered = await self.devices.renew_login_session(login.existing_device_id, owner_id=user.id, public_key=public_key)
        else:
            challenge = await self.devices.create_pairing(user.id)
            claim = await self.devices.register_device(pairing_code=challenge.code, name=login.name, public_key=public_key, protocol_version="1", runtime_version="0.1.0", capabilities=[], policy_hash=None)
            await self.devices.confirm_pairing(claim.pairing_id, owner_id=user.id, code=challenge.code)
            registered = await self.devices.complete_registration(device_id=claim.device.id, public_key=public_key, claim_token=claim.claim_token)
        from app.gateway.auth import create_access_token

        expires = datetime.now(UTC) + timedelta(hours=1)
        return {
            "account": {"id": user.id, "name": user.email},
            "business_token": create_access_token(user.id, expires_delta=timedelta(hours=1), token_version=user.token_version),
            "business_expires_at": expires.isoformat(),
            "registered": registered,
            "reauthenticated": bool(login.existing_device_id),
        }
