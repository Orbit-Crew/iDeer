"""Desktop local-result artifact upload (issue 105, Desktop contract).

The Desktop Runtime posts exactly one verified local result per explicit user
consent. The Server is the artifact authority: it re-verifies the content
digest, honors the content-hash idempotency key, and stores the payload inside
the owning thread's user-data outputs so the existing artifact listing and its
access control apply unchanged. A replayed upload with the same handle and
digest returns the same artifact; any other difference is a fixed-category
rejection that never widens visibility.
"""

import base64
import binascii
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.gateway.authz import require_permission
from app.gateway.path_utils import resolve_thread_virtual_path
from deerflow.utils.thread_id import ThreadId

router = APIRouter(prefix="/api/threads/{thread_id}/artifacts", tags=["desktop-artifacts"])

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

    user_id = owner_id
    sidecar_path = resolve_thread_virtual_path(str(thread_id), _sidecar_virtual_path(body.sha256, body.name), user_id=user_id)
    payload_path = resolve_thread_virtual_path(str(thread_id), _payload_virtual_path(body.sha256, body.name), user_id=user_id)

    existing = _read_record(sidecar_path)
    if existing is not None:
        if existing.get("sha256") != body.sha256 or existing.get("bytes") != body.bytes:
            raise reject("HASH_CONFLICT", status=409)
        return DesktopArtifactResponse(artifact_id=str(existing["artifact_id"]), thread_id=str(thread_id), name=body.name, sha256=body.sha256, bytes=body.bytes, handle=expected_handle, duplicate=True)

    artifact_id = f"art-{body.sha256[:12]}"
    _write_atomic(payload_path, content)
    record = {
        "artifact_id": artifact_id,
        "thread_id": str(thread_id),
        "name": body.name,
        "sha256": body.sha256,
        "bytes": body.bytes,
        "handle": expected_handle,
        "task_id": body.task_id,
        "run_id": body.run_id,
        "grant_token_sha256": hashlib.sha256(grant.token.encode()).hexdigest(),
    }
    _write_atomic(sidecar_path, json.dumps(record, indent=2).encode("utf-8"))
    response.status_code = 201
    return DesktopArtifactResponse(artifact_id=artifact_id, thread_id=str(thread_id), name=body.name, sha256=body.sha256, bytes=body.bytes, handle=expected_handle, duplicate=False)


@router.get("/{artifact_id}")
@require_permission("threads", "read", owner_check=True, require_existing=True)
async def read_desktop_artifact_meta(thread_id: ThreadId, artifact_id: str, request: Request) -> dict:
    """Read one stored desktop artifact's metadata (never its bytes here)."""
    if not re.match(r"^art-[0-9a-f]{12}$", artifact_id):
        raise _reject("ARTIFACT_ID_INVALID")
    user_id = str(request.state.auth.user.id)
    records_dir = resolve_thread_virtual_path(str(thread_id), f"{_SIDECAR_DIR}/.records", user_id=user_id)
    for candidate in sorted(records_dir.glob("*.json")):
        record = _read_record(candidate)
        if record and record.get("artifact_id") == artifact_id:
            return {key: record[key] for key in ("artifact_id", "thread_id", "name", "sha256", "bytes", "handle", "task_id", "run_id")}
    raise HTTPException(status_code=404, detail={"code": "ARTIFACT_NOT_FOUND"})
