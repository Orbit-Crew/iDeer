"""Ownership-checked durable acknowledgments, independent of live Run state."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .protocol import ProtocolError, payload_digest
from .receipt_models import DeviceTaskReceiptModel

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

    async def admit(self, binding: dict, task: dict) -> None:
        """Persist metadata of the exact signed task before the socket send."""
        async with self._factory()() as session:
            session.add(DeviceTaskReceiptModel(task_id=task["task_id"], owner_id=binding["user_id"], binding=dict(binding), task=dict(task)))
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
            if row.receipt_hash is None:
                from agentplatform_extension.local_runtime.receipts import tool_receipt_from_local

                acknowledgment = str(uuid4())
                try:
                    await session.execute(
                        update(DeviceTaskReceiptModel)
                        .where(DeviceTaskReceiptModel.task_id == row.task_id, DeviceTaskReceiptModel.receipt_hash.is_(None))
                        .values(receipt_id=upload["receipt_id"], receipt_hash=upload["receipt_hash"], receipt=receipt, evidence=tool_receipt_from_local(receipt, tool_call_id=task["tool_call_id"]), acknowledgment=acknowledgment)
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
            return {"task_id": row.task_id, "binding": row.binding, "task": row.task, "receipt_id": row.receipt_id, "receipt_hash": row.receipt_hash, "receipt": row.receipt, "evidence": row.evidence, "acknowledgment": row.acknowledgment}
