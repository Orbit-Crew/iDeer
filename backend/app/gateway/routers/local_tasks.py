"""Owned Thread read projection for local execution and receipt recovery."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from app.device_control.broker import get_device_broker
from app.device_control.protocol import ProtocolError
from app.gateway.authz import require_permission
from deerflow.utils.thread_id import ThreadId

router = APIRouter(prefix="/api/threads/{thread_id}/local-tasks", tags=["local-tasks"])


@router.get("")
@require_permission("threads", "read", owner_check=True, require_existing=True)
async def list_local_tasks(
    thread_id: ThreadId,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1000000),
) -> dict:
    """Read facts for every Run in this Thread, without dispatch or Run mutation."""
    owner_id = str(request.state.auth.user.id)
    try:
        return await get_device_broker().list_thread_tasks(thread_id, owner_id=owner_id, limit=limit, offset=offset)
    except (OSError, SQLAlchemyError, ProtocolError) as exc:
        raise HTTPException(status_code=503, detail="Local task history is unavailable") from exc
