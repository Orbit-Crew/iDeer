"""Canonical Connector identity endpoints (#123).

A connector installed on the user's own device registers exactly one thing
here: its platform-canonical identity — slug, display name, declared version
and the frozen manifest hash. The registration body is a fixed key allowlist
(``extra="forbid"``), so a runnable binding (command, entry, environment,
credentials) is unrepresentable: those stay on the installing device. There
is no visibility column, no share, publish or sync endpoint — the identity is
owner-scoped by construction, so another account cannot see, list, or run
another user's connector, and a second device of the same owner learns at
most the identity, never a runnable configuration.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentplatform.rbac_models import UserModel
from app.agentplatform.resource_models import ConnectorIdentityRow
from app.gateway.authz import get_current_rbac_user
from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

logger = logging.getLogger(__name__)


class ConnectorRegisterRequest(BaseModel):
    """The fixed identity projection; every other key is rejected with 422."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=32, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    manifest_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


def _projection(row: ConnectorIdentityRow) -> dict[str, Any]:
    return {
        "connectorId": row.id,
        "slug": row.slug,
        "displayName": row.display_name,
        "version": row.version,
        "manifestHash": row.manifest_hash,
    }


def _session_scope():
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"code": "PERSISTENCE_UNAVAILABLE"})
    return factory()


async def _owned_row(session: AsyncSession, connector_id: str, owner_id: str) -> ConnectorIdentityRow:
    row = await session.get(ConnectorIdentityRow, connector_id)
    # Invisible, never forbidden: a foreign or unknown id is the same 404.
    if row is None or row.owner_id != owner_id:
        raise HTTPException(status_code=404, detail={"code": "CONNECTOR_NOT_FOUND"})
    return row


@router.post("")
async def register_connector(
    payload: ConnectorRegisterRequest,
    current_user: UserModel = Depends(get_current_rbac_user),
) -> dict[str, Any]:
    """Register or re-confirm one connector's canonical identity (owner-gated).

    The frozen binding rule: one version binds exactly one manifest hash.
    Re-registering the same version with different content is a conflict the
    device must resolve (a genuine upgrade declares a new version); the same
    identity again is an idempotent confirmation.
    """
    owner_id = str(current_user.id)
    async with _session_scope() as session:
        row = (
            await session.execute(
                select(ConnectorIdentityRow).where(
                    ConnectorIdentityRow.owner_id == owner_id,
                    ConnectorIdentityRow.slug == payload.slug,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = ConnectorIdentityRow(
                id=str(uuid.uuid4()),
                owner_id=owner_id,
                slug=payload.slug,
                display_name=payload.display_name,
                version=payload.version,
                manifest_hash=payload.manifest_hash,
            )
            session.add(row)
        elif row.version == payload.version and row.manifest_hash != payload.manifest_hash:
            raise HTTPException(status_code=409, detail={"code": "CONNECTOR_IDENTITY_CONFLICT"})
        else:
            row.display_name = payload.display_name
            row.version = payload.version
            row.manifest_hash = payload.manifest_hash
        await session.commit()
        await session.refresh(row)
        # Log identity facts only — never request bodies or values.
        logger.info("connector identity registered slug=%s", row.slug)
        return _projection(row)


@router.get("")
async def list_connectors(
    current_user: UserModel = Depends(get_current_rbac_user),
) -> dict[str, Any]:
    """List the caller's own canonical connectors; nobody else's ever appear."""
    owner_id = str(current_user.id)
    async with _session_scope() as session:
        rows = list((await session.execute(select(ConnectorIdentityRow).where(ConnectorIdentityRow.owner_id == owner_id).order_by(ConnectorIdentityRow.created_at, ConnectorIdentityRow.id))).scalars())
        return {"items": [_projection(row) for row in rows], "total": len(rows)}


@router.get("/{connector_id}")
async def get_connector(
    connector_id: str,
    current_user: UserModel = Depends(get_current_rbac_user),
) -> dict[str, Any]:
    async with _session_scope() as session:
        row = await _owned_row(session, connector_id, str(current_user.id))
        return _projection(row)


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(
    connector_id: str,
    current_user: UserModel = Depends(get_current_rbac_user),
) -> None:
    async with _session_scope() as session:
        row = await _owned_row(session, connector_id, str(current_user.id))
        await session.delete(row)
        await session.commit()
