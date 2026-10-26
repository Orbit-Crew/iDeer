"""Ownership-checked durable acknowledgments, independent of live Run state."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .protocol import ProtocolError, is_write_consent_basis, payload_digest
from .receipt_models import DeviceTaskReceiptModel

ACTIVE_TASK_STATUSES = frozenset({"created", "sent", "acked", "consent_required", "progress", "cancel_requested"})
_VERIFIED_TASK_STATUSES = frozenset({"completed", "cancelled", "denied", "timed_out", "failed"})


def public_receipt(receipt: dict | None) -> dict | None:
    """Return bounded evidence metadata without task arguments or credentials."""
    if receipt is None:
        return None
    return {key: value[:1024] if isinstance(value, str) else value for key, value in receipt.items() if key in RECEIPT_FIELDS and isinstance(value, (str, int, float, bool, type(None)))}


def receipt_status(receipt: dict) -> str:
    status = receipt.get("status")
    if not isinstance(status, str):
        return "result_not_verified"
    if status in {"policy_denied", "upload_denied"}:
        return "denied"
    return status if status in _VERIFIED_TASK_STATUSES else "result_not_verified"


BINDING_FIELDS = frozenset(("server_origin", "user_id", "device_id", "device_public_key", "broker_public_key"))
RECEIPT_FIELDS = frozenset(
    (
        "run_id",
        "task_id",
        "capability",
        "policy_decision",
        "status",
        "payload_hash",
        "request_hash",
        "result_hash",
        "policy_version",
        "consent_decision",
        "stdout_hash",
        "stderr_hash",
        "runtime_version",
        "exit_code",
        "started_at",
        "finished_at",
        "error_code",
    )
)


def receipt_digest(value: dict) -> str:
    return payload_digest(value)


def safe_logical_target(payload: dict) -> str:
    arguments = payload.get("arguments", payload.get("args", payload))
    value = arguments.get("path") if isinstance(arguments, dict) else None
    if (
        isinstance(value, str)
        and re.match(r"^/workspace/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:/|$)", value)
        and len(value) <= 1024
        and not any(character in value for character in ("\\", ":", "\x00"))
        and ".." not in value.split("/")
    ):
        return value
    return "sha256:" + payload_digest(value)


class ReceiptArchive:
    def __init__(self, session_factory=None):
        self.session_factory = session_factory

    def _factory(self):
        if self.session_factory is not None:
            return self.session_factory
        from deerflow.persistence.engine import get_session_factory

        factory = get_session_factory()
        if factory is None:
            raise ProtocolError("PERSISTENCE_UNAVAILABLE", "receipt persistence is unavailable")
        return factory

    async def admit(self, binding: dict, task: dict, *, thread_id: str = "", local_result: dict | None = None) -> None:
        """Persist metadata of the exact signed task before the socket send."""
        async with self._factory()() as session:
            session.add(
                DeviceTaskReceiptModel(
                    task_id=task["task_id"],
                    owner_id=binding["user_id"],
                    binding=dict(binding),
                    task=dict(task),
                    thread_id=thread_id,
                    status="created",
                    evidence={"local_result": local_result} if local_result is not None else None,
                )
            )
            await session.commit()

    async def accept(self, binding: dict, upload: dict) -> dict:
        if set(upload) != {"receipt_id", "receipt_hash", "binding", "task", "receipt"} or set(binding) != BINDING_FIELDS or upload.get("binding") != binding:
            raise ProtocolError("RECEIPT_OWNER_MISMATCH", "receipt ownership does not match the current connection")
        receipt = upload.get("receipt")
        task = upload.get("task")
        if (
            not isinstance(receipt, dict)
            or not isinstance(task, dict)
            or set(receipt) - RECEIPT_FIELDS
            or not isinstance(upload.get("receipt_id"), str)
            or not 1 <= len(upload["receipt_id"]) <= 36
            or upload.get("receipt_hash") != receipt_digest({key: value for key, value in upload.items() if key != "receipt_hash"})
        ):
            raise ProtocolError("RECEIPT_INVALID", "receipt metadata is invalid")
        async with self._factory()() as session:
            row = await session.get(DeviceTaskReceiptModel, task.get("task_id"))
            if row is None or row.owner_id != binding["user_id"] or row.binding != binding:
                raise ProtocolError("RECEIPT_OWNER_MISMATCH", "original task ownership does not match")
            if row.task != task:
                raise ProtocolError("RECEIPT_TASK_MISMATCH", "receipt does not match original signed task")
            for field in ("task_id", "run_id", "capability", "request_hash"):
                if receipt.get(field) != task[field]:
                    raise ProtocolError("RECEIPT_TASK_MISMATCH", "receipt does not match original signed task")
            if receipt.get("payload_hash") != task["request_hash"]:
                raise ProtocolError("RECEIPT_TASK_MISMATCH", "receipt request hash does not match")
            if task["capability"] == "local.files.write" and receipt.get("status") == "completed" and not is_write_consent_basis(receipt.get("consent_decision")):
                raise ProtocolError("RECEIPT_TASK_MISMATCH", "write receipt has no valid local execution basis")
            if row.receipt_hash is None:
                from agentplatform_extension.local_runtime.receipts import tool_receipt_from_local

                acknowledgment = str(uuid4())
                try:
                    await session.execute(
                        update(DeviceTaskReceiptModel)
                        .where(DeviceTaskReceiptModel.task_id == row.task_id, DeviceTaskReceiptModel.receipt_hash.is_(None))
                        .values(
                            receipt_id=upload["receipt_id"],
                            receipt_hash=upload["receipt_hash"],
                            receipt=receipt,
                            status=receipt_status(receipt),
                            updated_at=datetime.now(UTC),
                            evidence={**(row.evidence or {}), **tool_receipt_from_local(receipt, tool_call_id=task["tool_call_id"])},
                            acknowledgment=acknowledgment,
                        )
                    )
                    await session.commit()
                except IntegrityError as exc:
                    await session.rollback()
                    raise ProtocolError("RECEIPT_CONFLICT", "receipt identity conflict") from exc
                await session.refresh(row)
            if row.receipt_hash != upload["receipt_hash"] or row.receipt_id != upload["receipt_id"]:
                raise ProtocolError("RECEIPT_CONFLICT", "receipt conflict with previously confirmed evidence")
            return {"receipt_id": row.receipt_id, "receipt_hash": row.receipt_hash, "acknowledgment": row.acknowledgment}

    async def get(self, task_id: str, *, owner_id: str) -> dict[str, Any] | None:
        async with self._factory()() as session:
            row = (await session.execute(select(DeviceTaskReceiptModel).where(DeviceTaskReceiptModel.task_id == task_id, DeviceTaskReceiptModel.owner_id == owner_id))).scalar_one_or_none()
            if row is None:
                return None
            return {
                "task_id": row.task_id,
                "thread_id": row.thread_id,
                "binding": row.binding,
                "task": row.task,
                "receipt_id": row.receipt_id,
                "receipt_hash": row.receipt_hash,
                "receipt": row.receipt,
                "evidence": row.evidence,
                "acknowledgment": row.acknowledgment,
            }

    async def observe(self, task_id: str, *, owner_id: str, status: str, stop_requested: bool = False, receipt: dict | None = None, error_code: str | None = None) -> None:
        """Persist transport observations without replacing a verified fact."""
        async with self._factory()() as session:
            owned = (DeviceTaskReceiptModel.task_id == task_id, DeviceTaskReceiptModel.owner_id == owner_id)
            if stop_requested:
                await session.execute(update(DeviceTaskReceiptModel).where(*owned).values(stop_requested=True))
            values = {"status": status, "updated_at": datetime.now(UTC), "error_code": str(error_code)[:64] if error_code is not None else None}
            if status in ACTIVE_TASK_STATUSES:
                values["recovery_status"] = status
            if receipt is not None:
                values["observed_receipt"] = public_receipt(receipt)
            await session.execute(update(DeviceTaskReceiptModel).where(*owned, DeviceTaskReceiptModel.receipt_hash.is_(None), DeviceTaskReceiptModel.status.not_in(_VERIFIED_TASK_STATUSES)).values(**values))
            await session.commit()

    async def list_by_thread(self, thread_id: str, *, owner_id: str, limit: int, offset: int) -> dict[str, Any]:
        """Read original Thread history without reconstructing dispatchable tasks."""
        async with self._factory()() as session:
            rows = (
                (
                    await session.execute(
                        select(DeviceTaskReceiptModel)
                        .where(DeviceTaskReceiptModel.owner_id == owner_id, DeviceTaskReceiptModel.thread_id == thread_id)
                        .order_by(DeviceTaskReceiptModel.created_at, DeviceTaskReceiptModel.task_id)
                        .offset(offset)
                        .limit(limit + 1)
                    )
                )
                .scalars()
                .all()
            )
            tasks = []
            for row in rows[:limit]:
                receipt = public_receipt(row.receipt or row.observed_receipt)
                status = receipt_status(receipt) if receipt is not None else row.status
                if status in ACTIVE_TASK_STATUSES:
                    status = "result_not_verified"
                tasks.append(
                    {
                        "task_id": row.task_id,
                        "thread_id": row.thread_id,
                        "run_id": row.task.get("run_id", ""),
                        "tool_call_id": row.task.get("tool_call_id", ""),
                        "device_id": row.binding.get("device_id", ""),
                        "capability": row.task.get("capability", ""),
                        "logical_target": row.task.get("logical_target", ""),
                        "status": status,
                        "stop_requested": row.stop_requested,
                        "recovery_status": row.recovery_status,
                        "receipt": receipt,
                        "receipt_pending": row.acknowledgment is None,
                        "error_code": "RESULT_UNCERTAIN" if status == "result_not_verified" else (receipt or {}).get("error_code", row.error_code),
                        "updated_at": row.updated_at.replace(tzinfo=UTC).isoformat() if row.updated_at.tzinfo is None else row.updated_at.isoformat(),
                    }
                )
            has_more = len(rows) > limit
            return {"tasks": tasks, "has_more": has_more, "next_offset": offset + limit if has_more else None}
