"""Desktop local-result artifact upload (issue 105, Desktop contract).

The Desktop Runtime posts exactly one verified local result per explicit user
consent. The Server is the artifact authority: it re-verifies the content
digest, honors the content-hash idempotency key, and stores the payload inside
the owning thread's user-data outputs so the existing artifact listing and its
access control apply unchanged. A replayed upload with the same handle and
digest returns the same artifact; any other difference is a fixed-category
rejection that never widens visibility.
"""

import asyncio
import base64
import binascii
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.device_control.artifacts import ArtifactStoreError, DeviceArtifactStore
from app.device_control.broker import get_device_broker
from app.device_control.models import DeviceStatus
from app.device_control.release_compatibility import evaluate_connection
from app.device_control.service import DeviceControlError, DeviceControlService
from app.gateway.authz import require_permission
from app.gateway.path_utils import resolve_thread_virtual_path
from app.gateway.routers.artifacts import reserve_artifact_write
from deerflow.persistence.engine import get_session_factory
from deerflow.runtime import ConflictError
from deerflow.utils.thread_id import ThreadId

router = APIRouter(prefix="/api/threads/{thread_id}/artifacts", tags=["desktop-artifacts"])

_grant_store = DeviceArtifactStore(Path(tempfile.gettempdir()) / "ideer-desktop-artifact-grants")

MAX_DESKTOP_ARTIFACT_BYTES = 65536
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_NAME_PATTERN = re.compile(r"^[^/\\\0]{1,255}$")
_SIDECAR_DIR = "/mnt/user-data/outputs/desktop-artifacts"
_PAYLOAD_VIRTUAL_DIR = "/mnt/user-data/outputs/desktop-artifacts"


class DesktopArtifactGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=256)
    task_id: str = Field(min_length=1, max_length=256)
    thread_id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=255)
    token: str = Field(min_length=8, max_length=128)


class DesktopArtifactGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, max_length=36)
    run_id: str = Field(min_length=1, max_length=256)
    task_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0, le=MAX_DESKTOP_ARTIFACT_BYTES)


class DesktopArtifactUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    kind: str
    task_id: str = Field(min_length=1, max_length=256)
    run_id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0)
    content: str
    handle: str = Field(min_length=1, max_length=512)
    grant: DesktopArtifactGrant


class DesktopArtifactResponse(BaseModel):
    artifact_id: str
    thread_id: str
    name: str
    sha256: str
    bytes: int
    handle: str
    duplicate: bool


def _reject(code: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


def _payload_virtual_path(sha256: str, name: str) -> str:
    return f"{_PAYLOAD_VIRTUAL_DIR}/{sha256}-{name}"


def _sidecar_virtual_path(sha256: str, name: str) -> str:
    return f"{_PAYLOAD_VIRTUAL_DIR}/.records/{sha256}-{name}.json"


def _write_atomic(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".desktop-artifact-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _read_record(actual_sidecar: Path) -> dict | None:
    try:
        return json.loads(actual_sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


async def _authorized_source(thread_id: str, owner_id: str, device_id: str, run_id: str, task_id: str, request: Request) -> tuple[dict, str]:
    archive = get_device_broker().receipt_archive
    if archive is None:
        raise _reject("ARTIFACT_AUTH_UNAVAILABLE", 503)
    original = await archive.get(task_id, owner_id=owner_id)
    if original is None or original["thread_id"] != thread_id or original["task"].get("run_id") != run_id or original["task"].get("capability") != "local.files.write" or original["binding"].get("device_id") != device_id:
        raise _reject("ARTIFACT_SOURCE_INVALID", 403)
    token = request.headers.get("X-Device-Session", "")
    if not token:
        raise _reject("DEVICE_SESSION_INVALID", 401)
    factory = get_session_factory()
    if factory is None:
        raise _reject("ARTIFACT_AUTH_UNAVAILABLE", 503)
    async with factory() as session:
        service = DeviceControlService(session)
        try:
            device, device_session = await service._authorized_session(device_id, token)
        except DeviceControlError as exc:
            raise _reject(exc.code, exc.status_code) from None
        if device.owner_id != owner_id or device.public_key != original["binding"].get("device_public_key"):
            raise _reject("DEVICE_FORBIDDEN", 403)
        if device.status in {DeviceStatus.REVOKED, DeviceStatus.BLOCKED}:
            raise _reject("DEVICE_REVOKED", 403)
        session_id = device_session.id
    compatibility = await asyncio.to_thread(evaluate_connection, get_device_broker().connections.get(device_id))
    if rejection := compatibility.rejection("local.artifacts.upload"):
        raise _reject(rejection, 409)
    if not original.get("receipt_hash") or (original.get("receipt") or {}).get("status") != "completed":
        raise _reject("RESULT_NOT_VERIFIED", 409)
    metadata = (original.get("evidence") or {}).get("local_result")
    if not isinstance(metadata, dict):
        raise _reject("RESULT_METADATA_UNAVAILABLE", 409)
    return metadata, session_id


@router.post("/grant")
@require_permission("threads", "write", owner_check=True, require_existing=True)
async def issue_desktop_artifact_grant(thread_id: ThreadId, request: Request, body: DesktopArtifactGrantRequest) -> dict:
    owner_id = str(request.state.auth.user.id)
    metadata, session_id = await _authorized_source(str(thread_id), owner_id, body.device_id, body.run_id, body.task_id, request)
    if metadata != {"name": body.name, "sha256": body.sha256, "bytes": body.bytes}:
        raise _reject("ARTIFACT_CONTENT_MISMATCH", 409)
    grant = _grant_store.issue_grant(
        device_id=body.device_id,
        session_id=session_id,
        run_id=body.run_id,
        task_id=body.task_id,
        thread_id=str(thread_id),
        filename=body.name,
        expected_sha256=body.sha256,
        max_bytes=body.bytes,
        expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    return {"token": grant.token, "device_id": body.device_id, "run_id": body.run_id, "task_id": body.task_id, "thread_id": str(thread_id), "name": body.name, "expires_at": grant.expires_at.isoformat()}


@router.post("", response_model=DesktopArtifactResponse)
@require_permission("threads", "write", owner_check=True, require_existing=True)
async def upload_desktop_artifact(thread_id: ThreadId, request: Request, response: Response, body: DesktopArtifactUpload) -> DesktopArtifactResponse:
    owner_id = str(request.state.auth.user.id)

    def reject(code: str, status: int = 400) -> HTTPException:
        return _reject(code, status)

    if body.version != 1:
        raise reject("VERSION_UNSUPPORTED")
    if body.kind != "local_result":
        raise reject("KIND_INVALID")
    if not _NAME_PATTERN.match(body.name) or body.name in {".", ".."}:
        raise reject("NAME_INVALID")
    if body.bytes > MAX_DESKTOP_ARTIFACT_BYTES:
        raise reject("TOO_LARGE", status=413)
    if not SHA256_PATTERN.match(body.sha256):
        raise reject("HASH_INVALID")
    expected_handle = f"local://{body.sha256}/{body.name}"
    if body.handle != expected_handle:
        raise reject("HANDLE_MISMATCH")
    idempotency_key = request.headers.get("Idempotency-Key", "")
    if idempotency_key != expected_handle:
        raise reject("IDEMPOTENCY_KEY_MISMATCH")
    grant = body.grant
    if (grant.task_id, grant.run_id, grant.thread_id, grant.name) != (
        body.task_id,
        body.run_id,
        str(thread_id),
        body.name,
    ):
        raise reject("GRANT_MISMATCH")

    try:
        content = base64.b64decode(body.content, validate=True)
    except (binascii.Error, ValueError):
        raise reject("CONTENT_INVALID") from None
    if len(content) != body.bytes:
        raise reject("BYTES_MISMATCH")
    digest = hashlib.sha256(content).hexdigest()
    if digest != body.sha256:
        raise reject("HASH_MISMATCH")

    try:
        issued = _grant_store.get_grant(grant.token, allow_consumed=True)
    except ArtifactStoreError as exc:
        raise reject(exc.code, status=410 if exc.code == "GRANT_EXPIRED" else 403) from None
    if (issued.run_id, issued.task_id, issued.thread_id, issued.filename, issued.expected_sha256, issued.max_bytes) != (body.run_id, body.task_id, str(thread_id), body.name, body.sha256, body.bytes):
        raise reject("GRANT_INVALID", status=403)
    metadata, session_id = await _authorized_source(str(thread_id), owner_id, issued.device_id, body.run_id, body.task_id, request)
    if session_id != issued.session_id or metadata != {"name": body.name, "sha256": body.sha256, "bytes": body.bytes}:
        raise reject("GRANT_INVALID", status=403)

    identity = hashlib.sha256(f"{body.run_id}:{body.task_id}:{expected_handle}".encode()).hexdigest()
    sidecar_path = resolve_thread_virtual_path(str(thread_id), f"{_SIDECAR_DIR}/.records/{identity}.json", user_id=owner_id)
    payload_path = resolve_thread_virtual_path(str(thread_id), _payload_virtual_path(body.sha256, body.name), user_id=owner_id)
    record = {
        "artifact_id": f"art-{identity[:32]}",
        "thread_id": str(thread_id),
        "name": body.name,
        "sha256": body.sha256,
        "bytes": body.bytes,
        "handle": expected_handle,
        "task_id": body.task_id,
        "run_id": body.run_id,
    }

    def commit() -> bool:
        existing = _read_record(sidecar_path)
        if existing is not None:
            if any(existing.get(key) != value for key, value in record.items()) or not payload_path.is_file() or payload_path.read_bytes() != content:
                raise reject("ARTIFACT_CONFLICT", status=409)
            return True
        if issued.consumed:
            raise reject("GRANT_INVALID", status=403)
        _write_atomic(payload_path, content)
        _write_atomic(sidecar_path, json.dumps(record).encode("utf-8"))
        issued.consumed = True
        return False

    try:
        async with reserve_artifact_write(request, str(thread_id), user_id=owner_id):
            duplicate = await asyncio.to_thread(commit)
    except ConflictError:
        raise reject("ARTIFACT_BUSY", status=409) from None
    except OSError:
        raise reject("ARTIFACT_STORAGE_UNAVAILABLE", status=503) from None
    response.status_code = 200 if duplicate else 201
    return DesktopArtifactResponse(**record, duplicate=duplicate)


def _records(thread_id: str, owner_id: str) -> list[dict]:
    records_dir = resolve_thread_virtual_path(thread_id, f"{_SIDECAR_DIR}/.records", user_id=owner_id)
    records = []
    for candidate in sorted(records_dir.glob("*.json")):
        safe_path = resolve_thread_virtual_path(thread_id, f"{_SIDECAR_DIR}/.records/{candidate.name}", user_id=owner_id)
        record = _read_record(safe_path)
        if not record or record.get("thread_id") != thread_id:
            continue
        if not re.fullmatch(r"art-[0-9a-f]{12,64}", str(record.get("artifact_id", ""))) or not SHA256_PATTERN.fullmatch(str(record.get("sha256", ""))):
            continue
        if not _NAME_PATTERN.fullmatch(str(record.get("name", ""))) or record["name"] in {".", ".."}:
            continue
        if not all(key in record for key in ("bytes", "task_id", "run_id", "handle")):
            continue
        records.append({key: record[key] for key in ("artifact_id", "thread_id", "name", "sha256", "bytes", "handle", "task_id", "run_id")})
    return records


@router.get("")
@require_permission("threads", "read", owner_check=True, require_existing=True)
async def list_desktop_artifacts(thread_id: ThreadId, request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000)) -> dict:
    try:
        records = await asyncio.to_thread(_records, str(thread_id), str(request.state.auth.user.id))
    except OSError:
        raise _reject("ARTIFACT_STORAGE_UNAVAILABLE", 503) from None
    has_more = len(records) > offset + limit
    return {"artifacts": records[offset : offset + limit], "has_more": has_more, "next_offset": offset + limit if has_more else None}


@router.get("/{artifact_id}")
@require_permission("threads", "read", owner_check=True, require_existing=True)
async def read_desktop_artifact_meta(thread_id: ThreadId, artifact_id: str, request: Request) -> dict:
    """Read owned platform metadata without needing the original device."""
    if not re.fullmatch(r"art-[0-9a-f]{12,64}", artifact_id):
        raise _reject("ARTIFACT_ID_INVALID")
    try:
        records = await asyncio.to_thread(_records, str(thread_id), str(request.state.auth.user.id))
    except OSError:
        raise _reject("ARTIFACT_STORAGE_UNAVAILABLE", 503) from None
    for record in records:
        if record["artifact_id"] == artifact_id:
            return record
    raise _reject("ARTIFACT_NOT_FOUND", 404)


@router.get("/{artifact_id}/download")
@require_permission("threads", "read", owner_check=True, require_existing=True)
async def download_desktop_artifact(thread_id: ThreadId, artifact_id: str, request: Request) -> Response:
    record = await read_desktop_artifact_meta(thread_id=thread_id, artifact_id=artifact_id, request=request)
    target = resolve_thread_virtual_path(str(thread_id), _payload_virtual_path(record["sha256"], record["name"]), user_id=str(request.state.auth.user.id))
    try:
        content = await asyncio.to_thread(target.read_bytes)
    except OSError:
        raise _reject("ARTIFACT_STORAGE_UNAVAILABLE", 503) from None
    if len(content) != record["bytes"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
        raise _reject("ARTIFACT_CONTENT_MISMATCH", 409)
    from urllib.parse import quote

    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(record["name"]),
            "X-Content-Type-Options": "nosniff",
            "X-Content-SHA256": record["sha256"],
            "ETag": '"' + record["sha256"] + '"',
            "Cache-Control": "private, no-store",
        },
    )
