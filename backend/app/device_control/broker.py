"""In-process outbound device broker for the signed M7 echo task."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy.exc import SQLAlchemyError

from .protocol import (
    MessageType,
    ProtocolError,
    TaskEnvelope,
    is_write_consent_basis,
    payload_digest,
    public_key_text,
    schema_digest,
    sign_envelope,
)
from .receipt_archive import ACTIVE_TASK_STATUSES, ReceiptArchive, safe_logical_target

logger = logging.getLogger(__name__)


class WebSocketLike(Protocol):
    async def send_text(self, data: str) -> None: ...

    async def close(self, code: int = 1000, reason: str = "") -> None: ...


class TaskStatus(StrEnum):
    CREATED = "created"
    SENT = "sent"
    ACKED = "acked"
    CONSENT_REQUIRED = "consent_required"
    PROGRESS = "progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CANCEL_REQUESTED = "cancel_requested"
    DENIED = "denied"
    TIMED_OUT = "timed_out"
    DEVICE_OFFLINE = "device_offline"
    EXPIRED = "expired"
    FAILED = "failed"
    RESULT_NOT_VERIFIED = "result_not_verified"


# Statuses whose records are only kept for late status/receipt lookups; the
# rest of TaskStatus marks a task still in flight on a device.
_TERMINAL_TASK_STATUSES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
        TaskStatus.DENIED,
        TaskStatus.TIMED_OUT,
        TaskStatus.DEVICE_OFFLINE,
        TaskStatus.EXPIRED,
        TaskStatus.FAILED,
        TaskStatus.RESULT_NOT_VERIFIED,
    }
)
# Bound on tracked task records (03-L5): records normally stay only for the
# task's short lifetime; this guards against a device that never answers or
# runs that leak. Oldest terminal records are evicted first so a live task is
# never the one dropped; the receipt bookkeeping below is bounded the same way.
MAX_TRACKED_TASK_RECORDS = 512
MAX_RECORDED_RECEIPTS = 4096


@dataclass
class DeviceConnection:
    device_id: str
    session_id: str
    session_token: str
    public_key: Ed25519PublicKey
    websocket: WebSocketLike
    tasks_allowed: bool = True
    capabilities: frozenset[str] = field(default_factory=frozenset)
    tool_descriptors: dict[str, dict[str, Any]] = field(default_factory=dict)
    owner_id: str | None = None
    server_origin: str = ""
    seen_task_ids: set[str] = field(default_factory=set)
    seen_message_ids: set[str] = field(default_factory=set)


@dataclass
class TaskRecord:
    task_id: str
    device_id: str
    session_id: str
    run_id: str
    tool_call_id: str
    payload: dict[str, Any]
    expires_at: datetime
    status: TaskStatus = TaskStatus.CREATED
    receipt: dict[str, Any] | None = None
    result: Any = None
    error: str | None = None
    error_code: str | None = None
    consent_request: dict[str, Any] | None = None
    authorization_snapshot: dict[str, Any] | None = None
    stop_requested: bool = False
    owner_id: str | None = None
    dispatch_started: bool = False


class DeviceBroker:
    """Register only device-initiated connections and route signed envelopes."""

    def __init__(self, *, server_private_key: Ed25519PrivateKey | None = None, receipt_archive: ReceiptArchive | None = None) -> None:
        self.server_private_key = server_private_key or Ed25519PrivateKey.generate()
        self.receipt_archive = receipt_archive
        self.connections: dict[str, DeviceConnection] = {}
        self.tasks: dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()
        # Insertion-ordered so the cap below can evict the oldest receipt id;
        # membership semantics are the same as the set it replaces.
        self._recorded_receipts: dict[str, None] = {}

    @property
    def server_public_key(self) -> str:
        return public_key_text(self.server_private_key.public_key())

    async def attach(self, connection: DeviceConnection) -> TaskEnvelope:
        async with self._lock:
            previous = self.connections.get(connection.device_id)
            if previous is not None and previous.session_id != connection.session_id:
                await previous.websocket.close(code=4001, reason="session superseded")
            self.connections[connection.device_id] = connection
        hello = sign_envelope(
            private_key=self.server_private_key,
            message_type=MessageType.HELLO,
            device_id=connection.device_id,
            session_id=connection.session_id,
            payload={
                "server_public_key": self.server_public_key,
                "protocol_version": "1",
                "receipt_replay": 1 if self.receipt_archive is not None else 0,
            },
        )
        await connection.websocket.send_text(hello.model_dump_json(by_alias=True))
        return hello

    def receipt_binding(self, connection: DeviceConnection) -> dict[str, str]:
        return {"server_origin": connection.server_origin, "user_id": connection.owner_id or "", "device_id": connection.device_id, "device_public_key": public_key_text(connection.public_key), "broker_public_key": self.server_public_key}

    async def detach(self, device_id: str, session_id: str) -> None:
        affected = []
        async with self._lock:
            connection = self.connections.get(device_id)
            if connection is not None and connection.session_id == session_id:
                self.connections.pop(device_id, None)
            now = datetime.now(UTC)
            for task in self.tasks.values():
                if (
                    task.device_id == device_id
                    and task.session_id == session_id
                    and task.status
                    in {
                        TaskStatus.CREATED,
                        TaskStatus.SENT,
                        TaskStatus.ACKED,
                        TaskStatus.CONSENT_REQUIRED,
                        TaskStatus.CANCEL_REQUESTED,
                        TaskStatus.PROGRESS,
                    }
                ):
                    task.status = TaskStatus.RESULT_NOT_VERIFIED if task.payload.get("operation") == "local.files.write" else TaskStatus.DEVICE_OFFLINE
                    task.error_code = "RESULT_UNCERTAIN" if task.status is TaskStatus.RESULT_NOT_VERIFIED else None
                    task.error = "device disconnected before task completion; write effects require verification"
                    task.expires_at = max(task.expires_at, now + timedelta(seconds=1))
                    affected.append(task)
        for task in affected:
            await self._persist_task(task)

    async def invalidate(self, device_id: str, *, reason: str) -> None:
        """Stop a live device session after an administrative state change."""
        connection = self.connections.get(device_id)
        if connection is None:
            return
        connection.tasks_allowed = False
        affected = []
        now = datetime.now(UTC)
        for task in self.tasks.values():
            if (
                task.device_id == device_id
                and task.session_id == connection.session_id
                and task.status
                in {
                    TaskStatus.CREATED,
                    TaskStatus.SENT,
                    TaskStatus.ACKED,
                    TaskStatus.CONSENT_REQUIRED,
                    TaskStatus.CANCEL_REQUESTED,
                    TaskStatus.PROGRESS,
                }
            ):
                task.status = TaskStatus.RESULT_NOT_VERIFIED if task.payload.get("operation") == "local.files.write" else TaskStatus.DEVICE_OFFLINE
                task.error_code = "RESULT_UNCERTAIN" if task.status is TaskStatus.RESULT_NOT_VERIFIED else None
                task.error = reason
                task.expires_at = max(task.expires_at, now + timedelta(seconds=1))
                affected.append(task)
        try:
            await connection.websocket.close(code=4003, reason=reason)
        finally:
            for task in affected:
                await self._persist_task(task)

    async def send_echo_task(
        self,
        *,
        device_id: str,
        run_id: str,
        tool_call_id: str,
        value: Any,
        expires_in: timedelta = timedelta(minutes=5),
    ) -> TaskRecord:
        return await self.send_task(
            device_id=device_id,
            operation="echo",
            path=value,
            run_id=run_id,
            tool_call_id=tool_call_id,
            expires_in=expires_in,
            payload_extra={"value": value},
        )

    async def send_task(
        self,
        *,
        device_id: str,
        operation: str,
        path: Any,
        run_id: str,
        tool_call_id: str,
        expires_in: timedelta = timedelta(minutes=5),
        payload_extra: dict[str, Any] | None = None,
        authorization_snapshot: dict[str, Any] | None = None,
    ) -> TaskRecord:
        connection = self.connections.get(device_id)
        now = datetime.now(UTC)
        task_id = str(uuid4())
        expires_at = now + expires_in
        payload = {
            "operation": operation,
            "path": path,
            "run_id": run_id,
            "tool_call_id": tool_call_id,
        }
        if payload_extra:
            payload.update(payload_extra)
        record = TaskRecord(
            task_id,
            device_id,
            connection.session_id if connection else "",
            run_id,
            tool_call_id,
            payload,
            expires_at,
            authorization_snapshot=authorization_snapshot,
            owner_id=connection.owner_id if connection else None,
        )
        while len(self.tasks) >= MAX_TRACKED_TASK_RECORDS:
            stale = next(
                (stale_id for stale_id, stale_record in self.tasks.items() if stale_record.status in _TERMINAL_TASK_STATUSES),
                None,
            )
            if stale is None:
                # Degenerate: more in-flight tasks than the cap. Drop the
                # oldest record rather than growing without bound; its late
                # lookups will report TASK_NOT_FOUND.
                stale = next(iter(self.tasks))
            self.tasks.pop(stale)
        self.tasks[task_id] = record
        if connection is None:
            record.status = TaskStatus.DEVICE_OFFLINE
            record.error = "no outbound device session is connected"
            return record
        if not connection.tasks_allowed:
            record.status = TaskStatus.FAILED
            record.error = "device protocol is outdated"
            return record
        if authorization_snapshot is not None:
            allowed = frozenset(authorization_snapshot.get("effective_capabilities", ()))
            if authorization_snapshot.get("device_id") != device_id or operation not in allowed:
                record.status = TaskStatus.DENIED
                record.error_code = "AUTHORIZATION_SNAPSHOT_INVALID"
                record.error = "local task authorization is no longer valid"
                return record
        if operation.startswith("local.") and operation not in connection.capabilities:
            record.status = TaskStatus.FAILED
            record.error_code = "CAPABILITY_UNAVAILABLE"
            record.error = "device capability is unavailable"
            return record
        envelope = sign_envelope(
            private_key=self.server_private_key,
            message_type=MessageType.TASK,
            device_id=device_id,
            session_id=connection.session_id,
            task_id=task_id,
            payload=payload,
            expires_at=expires_at,
        )
        if self.receipt_archive is not None:
            try:
                await self.receipt_archive.admit(
                    self.receipt_binding(connection),
                    {
                        "task_id": task_id,
                        "run_id": run_id,
                        "tool_call_id": tool_call_id,
                        "capability": operation,
                        "request_hash": envelope.payload_hash,
                        "original_session_id": connection.session_id,
                        "task_signature": envelope.signature,
                        "logical_target": safe_logical_target(payload),
                    },
                    thread_id=str(payload.get("thread_id", "")),
                )
            except asyncio.CancelledError:
                await asyncio.shield(self._cancel_before_dispatch(record))
                raise
            except (OSError, SQLAlchemyError, ProtocolError):
                record.status = TaskStatus.FAILED
                record.error_code = "PERSISTENCE_UNAVAILABLE"
                record.error = "task receipt admission could not be saved; nothing was dispatched"
                return record
        if record.stop_requested:
            await self._cancel_before_dispatch(record)
            return record
        record.status = TaskStatus.SENT
        try:
            await self._persist_task(record)
            if record.stop_requested or record.status in _TERMINAL_TASK_STATUSES:
                return record
            record.dispatch_started = True
            await connection.websocket.send_text(envelope.model_dump_json(by_alias=True))
        except asyncio.CancelledError:
            if record.dispatch_started:
                await asyncio.shield(self.cancel_task(record.task_id))
            else:
                await asyncio.shield(self._cancel_before_dispatch(record))
            raise
        except Exception:
            if record.status not in _TERMINAL_TASK_STATUSES and record.receipt is None:
                record.status = TaskStatus.RESULT_NOT_VERIFIED if operation == "local.files.write" else TaskStatus.DEVICE_OFFLINE
                record.error_code = "RESULT_UNCERTAIN" if operation == "local.files.write" else "DEVICE_OFFLINE"
                record.error = "device delivery failed; execution outcome requires verification"
            await self._persist_task(record)
        return record

    async def cancel_task(self, task_id: str) -> TaskRecord:
        record = self._task(task_id)
        if record.status in _TERMINAL_TASK_STATUSES or record.status is TaskStatus.CANCEL_REQUESTED:
            return record
        if not record.dispatch_started:
            await self._cancel_before_dispatch(record)
            return record
        record.stop_requested = True
        record.status = TaskStatus.CANCEL_REQUESTED
        connection = self.connections.get(record.device_id)
        if connection is not None and connection.session_id == record.session_id:
            envelope = sign_envelope(
                private_key=self.server_private_key,
                message_type=MessageType.TASK_CANCEL,
                device_id=record.device_id,
                session_id=record.session_id,
                task_id=record.task_id,
                payload={"reason": "cancelled by caller"},
            )
            try:
                await connection.websocket.send_text(envelope.model_dump_json(by_alias=True))
            except Exception:
                if record.status not in _TERMINAL_TASK_STATUSES and record.receipt is None:
                    record.status = TaskStatus.RESULT_NOT_VERIFIED if record.payload.get("operation") == "local.files.write" else TaskStatus.DEVICE_OFFLINE
                    record.error_code = "RESULT_UNCERTAIN" if record.status is TaskStatus.RESULT_NOT_VERIFIED else "DEVICE_OFFLINE"
                    record.error = "cancel delivery failed; execution outcome requires verification"
        await self._persist_task(record)
        return record

    async def send_consent_decision(self, task_id: str, *, approved: bool, actor_id: str) -> TaskRecord:
        record = self._task(task_id)
        if record.payload.get("operation") == "local.files.write":
            raise ProtocolError("LOCAL_APPROVAL_REQUIRED", "workspace writes require approval on the original Desktop")
        if record.status is not TaskStatus.CONSENT_REQUIRED:
            raise ProtocolError("CONSENT_NOT_PENDING", "task is not waiting for consent")
        connection = self.connections.get(record.device_id)
        if connection is None or connection.session_id != record.session_id:
            record.status = TaskStatus.DEVICE_OFFLINE
            record.error = "no outbound device session is connected"
            return record
        request_hash = str((record.consent_request or {}).get("request_hash", ""))
        envelope = sign_envelope(
            private_key=self.server_private_key,
            message_type=MessageType.CONSENT_DECISION,
            device_id=record.device_id,
            session_id=record.session_id,
            task_id=record.task_id,
            payload={
                "approved": approved,
                "actor_id": actor_id,
                "request_hash": request_hash,
            },
            expires_at=record.expires_at,
        )
        await connection.websocket.send_text(envelope.model_dump_json(by_alias=True))
        return record

    async def receive(self, connection: DeviceConnection, envelope: TaskEnvelope) -> TaskRecord | None:
        envelope.verify(
            public_key=connection.public_key,
            expected_device_id=connection.device_id,
            expected_session_id=connection.session_id,
            seen_task_ids=connection.seen_task_ids,
            seen_message_ids=connection.seen_message_ids,
        )
        if self.connections.get(connection.device_id) is not connection or not connection.tasks_allowed:
            raise ProtocolError("SESSION_MISMATCH", "device session is no longer current")
        if envelope.type == MessageType.RECEIPT_UPLOAD:
            if self.connections.get(connection.device_id) is not connection or not connection.tasks_allowed or self.receipt_archive is None:
                raise ProtocolError("RECEIPT_SESSION_INVALID", "receipt connection is no longer legal")
            if not isinstance(envelope.payload.get("task"), dict) or envelope.task_id != envelope.payload["task"].get("task_id"):
                raise ProtocolError("RECEIPT_TASK_MISMATCH", "receipt task identity does not match")
            acknowledgment = await self.receipt_archive.accept(self.receipt_binding(connection), envelope.payload)
            reply = sign_envelope(private_key=self.server_private_key, message_type=MessageType.RECEIPT_ACK, device_id=connection.device_id, session_id=connection.session_id, task_id=envelope.task_id, payload=acknowledgment)
            await connection.websocket.send_text(reply.model_dump_json(by_alias=True))
            return None
        if envelope.type == MessageType.HEARTBEAT:
            return None
        if envelope.type == MessageType.CAPABILITY_UPDATE:
            values = envelope.payload.get("capabilities", ())
            if not isinstance(values, (list, tuple, set)):
                raise ProtocolError("CAPABILITIES_INVALID", "capability update is invalid")
            connection.capabilities = frozenset(str(value) for value in values)
            descriptors = envelope.payload.get("tool_descriptors", {})
            if not isinstance(descriptors, dict):
                raise ProtocolError("TOOL_DESCRIPTORS_INVALID", "tool descriptors must be an object")
            normalized: dict[str, dict[str, Any]] = {}
            for name, descriptor in descriptors.items():
                if not isinstance(name, str) or not isinstance(descriptor, dict):
                    raise ProtocolError(
                        "TOOL_DESCRIPTORS_INVALID",
                        "tool descriptors must be objects keyed by capability",
                    )
                if name not in connection.capabilities:
                    continue
                schema = descriptor.get("input_schema", {})
                if schema is not None and not isinstance(schema, dict):
                    raise ProtocolError(
                        "TOOL_DESCRIPTORS_INVALID",
                        "tool input schema must be an object",
                    )
                schema = dict(schema or {})
                schema_hash = str(descriptor.get("schema_hash", ""))
                if schema_hash and schema_hash != schema_digest(schema):
                    raise ProtocolError(
                        "TOOL_SCHEMA_HASH_MISMATCH",
                        "tool input schema hash does not match its schema",
                    )
                normalized[name] = {
                    "description": str(descriptor.get("description", "")),
                    "input_schema": schema,
                    "schema_hash": schema_hash,
                }
            connection.tool_descriptors = normalized
            return None
        if envelope.task_id is None:
            raise ProtocolError("TASK_ID_REQUIRED", "task lifecycle messages require task_id")
        record = self._task(envelope.task_id)
        self._expire_if_needed(record)
        if record.device_id != connection.device_id or record.session_id != connection.session_id:
            raise ProtocolError("SESSION_MISMATCH", "task belongs to another device session")
        receipt = envelope.payload.get("receipt")
        is_write = record.payload.get("operation") == "local.files.write"
        if record.status in _TERMINAL_TASK_STATUSES:
            late_write_receipt = (
                is_write
                and record.receipt is None
                and record.status in {TaskStatus.CANCELLED, TaskStatus.DEVICE_OFFLINE, TaskStatus.EXPIRED, TaskStatus.RESULT_NOT_VERIFIED}
                and envelope.type in {MessageType.TASK_RESULT, MessageType.ERROR}
                and isinstance(receipt, dict)
            )
            if not late_write_receipt:
                return record
        if is_write and envelope.type in {MessageType.TASK_RESULT, MessageType.ERROR}:
            if envelope.type == MessageType.TASK_RESULT or receipt is not None:
                expected = {"task_id": record.task_id, "run_id": record.run_id, "capability": "local.files.write", "request_hash": payload_digest(record.payload), "payload_hash": payload_digest(record.payload)}
                if not isinstance(receipt, dict) or any(receipt.get(key) != value for key, value in expected.items()):
                    raise ProtocolError("RECEIPT_TASK_MISMATCH", "write receipt does not match its signed request")
                if receipt.get("status") not in {"completed", "cancelled", "timed_out", "denied", "policy_denied", "failed", "result_not_verified"} or (
                    receipt.get("status") == "completed" and not is_write_consent_basis(receipt.get("consent_decision"))
                ):
                    raise ProtocolError("RECEIPT_TASK_MISMATCH", "write receipt has no valid local execution basis")
        if record.status is TaskStatus.CANCEL_REQUESTED and envelope.type in {MessageType.TASK_ACK, MessageType.TASK_PROGRESS, MessageType.CONSENT_REQUIRED}:
            return record
        if envelope.type == MessageType.TASK_ACK:
            record.status = TaskStatus.ACKED
        elif envelope.type == MessageType.CONSENT_REQUIRED:
            request_payload = envelope.payload.get("payload")
            request_hash = envelope.payload.get("request_hash")
            if not isinstance(request_payload, dict) or not isinstance(request_hash, str) or request_hash != payload_digest(request_payload) or request_payload != record.payload:
                raise ProtocolError(
                    "CONSENT_HASH_MISMATCH",
                    "consent request does not match the task payload",
                )
            record.status = TaskStatus.CONSENT_REQUIRED
            record.consent_request = dict(envelope.payload)
        elif envelope.type == MessageType.TASK_PROGRESS:
            record.status = TaskStatus.PROGRESS
        elif envelope.type == MessageType.TASK_RESULT:
            record.result = envelope.payload.get("result")
            record.receipt = envelope.payload.get("receipt") or envelope.payload
            receipt_status = str((record.receipt or {}).get("status", "completed"))
            if receipt_status == "result_not_verified":
                record.status = TaskStatus.RESULT_NOT_VERIFIED
                record.error_code = "RESULT_UNCERTAIN"
                record.error = "write effects require verification"
            elif receipt_status == "cancelled":
                record.status = TaskStatus.CANCELLED
                record.error_code = receipt_status.upper()
                record.error = receipt_status.replace("_", " ")
            elif receipt_status == "timed_out":
                record.status = TaskStatus.TIMED_OUT
                record.error_code = receipt_status.upper()
                record.error = receipt_status.replace("_", " ")
            elif receipt_status in {"denied", "upload_denied", "policy_denied"}:
                record.status = TaskStatus.DENIED
                record.error_code = receipt_status.upper()
                record.error = receipt_status.replace("_", " ")
            elif receipt_status == "failed":
                record.status = TaskStatus.FAILED
                record.error_code = receipt_status.upper()
                record.error = receipt_status.replace("_", " ")
            elif receipt_status == "completed":
                record.status = TaskStatus.COMPLETED
                record.error_code = None
                record.error = None
            else:
                record.status = TaskStatus.RESULT_NOT_VERIFIED
                record.error_code = "RESULT_UNCERTAIN"
                record.error = "task result requires verification"
        elif envelope.type == MessageType.ERROR:
            record.error_code = str(envelope.payload.get("error_code", "DEVICE_ERROR"))
            record.error = str(envelope.payload.get("message", "device reported an error"))
            record.receipt = envelope.payload.get("receipt")
            receipt_status = str((record.receipt or {}).get("status", "failed"))
            if receipt_status == "result_not_verified" or record.error_code in {"RESULT_UNCERTAIN", "TASK_REPLAYED"}:
                record.status = TaskStatus.RESULT_NOT_VERIFIED
                record.error_code = "RESULT_UNCERTAIN"
            elif receipt_status == "cancelled":
                record.status = TaskStatus.CANCELLED
            elif receipt_status == "timed_out":
                record.status = TaskStatus.TIMED_OUT
            elif receipt_status in {"denied", "upload_denied", "policy_denied"}:
                record.status = TaskStatus.DENIED
            else:
                record.status = TaskStatus.FAILED
        else:
            raise ProtocolError("MESSAGE_UNEXPECTED", f"unexpected device message: {envelope.type}")
        if record.receipt is not None and record.task_id not in self._recorded_receipts:
            while len(self._recorded_receipts) >= MAX_RECORDED_RECEIPTS:
                self._recorded_receipts.pop(next(iter(self._recorded_receipts)))
            self._recorded_receipts[record.task_id] = None
            try:
                from agentplatform_extension.evidence import (
                    record_local_execution_receipt,
                )

                record_local_execution_receipt(record.receipt, tool_call_id=record.tool_call_id)
            except (ImportError, KeyError, RuntimeError, TypeError, ValueError):
                pass
        await self._persist_task(record)
        return record

    async def _cancel_before_dispatch(self, record: TaskRecord) -> None:
        record.stop_requested = True
        record.status = TaskStatus.CANCELLED
        record.error_code = "CANCELLED"
        record.error = "cancelled before task dispatch"
        await self._persist_task(record)

    async def _persist_task(self, record: TaskRecord) -> None:
        if self.receipt_archive is None or record.owner_id is None:
            return
        try:
            await self.receipt_archive.observe(
                record.task_id,
                owner_id=record.owner_id,
                status=record.status.value,
                stop_requested=record.stop_requested,
                receipt=record.receipt,
                error_code=record.error_code,
            )
        except (OSError, SQLAlchemyError, ProtocolError):
            # The signed receipt outbox can reconcile history after persistence
            # recovers. Transport cancellation must still reach the Runtime.
            logger.warning("Local task observation could not be persisted", exc_info=True)

    async def list_thread_tasks(self, thread_id: str, *, owner_id: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if self.receipt_archive is None:
            raise ProtocolError("PERSISTENCE_UNAVAILABLE", "task history persistence is unavailable")
        page = await self.receipt_archive.list_by_thread(thread_id, owner_id=owner_id, limit=limit, offset=offset)
        for item in page["tasks"]:
            live = self.tasks.get(item["task_id"])
            if live is not None and live.owner_id == owner_id and item["receipt"] is None:
                self._expire_if_needed(live)
                item["status"] = live.status.value
                item["stop_requested"] = item["stop_requested"] or live.stop_requested
                item["error_code"] = live.error_code
                if live.status.value in ACTIVE_TASK_STATUSES:
                    item["recovery_status"] = live.status.value
        return page

    def _task(self, task_id: str) -> TaskRecord:
        record = self.tasks.get(task_id)
        if record is None:
            raise ProtocolError("TASK_NOT_FOUND", "task id is unknown")
        return record

    def get_task(self, task_id: str) -> TaskRecord:
        record = self._task(task_id)
        self._expire_if_needed(record)
        return record

    @staticmethod
    def _expire_if_needed(record: TaskRecord) -> None:
        if record.status in {
            TaskStatus.CREATED,
            TaskStatus.SENT,
            TaskStatus.ACKED,
            TaskStatus.CONSENT_REQUIRED,
            TaskStatus.CANCEL_REQUESTED,
            TaskStatus.PROGRESS,
        } and record.expires_at <= datetime.now(UTC):
            record.status = TaskStatus.RESULT_NOT_VERIFIED if record.payload.get("operation") == "local.files.write" else TaskStatus.EXPIRED
            record.error_code = "RESULT_UNCERTAIN" if record.status is TaskStatus.RESULT_NOT_VERIFIED else None
            record.error = "task delivery or execution deadline elapsed"


_broker: DeviceBroker | None = None
_broker_lock = threading.Lock()


def get_device_broker() -> DeviceBroker:
    global _broker
    if _broker is None:
        with _broker_lock:
            if _broker is None:
                from .identity import persistent_broker_key

                _broker = DeviceBroker(server_private_key=persistent_broker_key(), receipt_archive=ReceiptArchive())
    return _broker
