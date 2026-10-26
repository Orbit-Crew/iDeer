"""Read-only publication of operations-reviewed releases and compatibility."""

import asyncio
import hashlib
import json
import logging
import os
import re
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/updates", tags=["updates"])

_SERVED_NAMES = {
    "desktop/manifest.json": "application/json",
    "desktop/manifest.sig": "application/octet-stream",
    "compatibility.json": "application/json",
    "compatibility.sig": "application/octet-stream",
}


def _controlled_dir() -> Path:
    configured = os.environ.get("UPDATES_CONTROLLED_DIR", "")
    return (Path(configured) if configured else Path.cwd() / "updates-controlled").resolve()


def _confined_file(name: str) -> Path:
    root = _controlled_dir()
    target = (root / name).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("not published")
    return target


def _asset(document_path: str) -> Path:
    # Only installation-relative resources declared by the reviewed manifest,
    # or its explicit full installer, can be fetched from this directory.
    manifest_path = _confined_file("desktop/manifest.json")
    if manifest_path.stat().st_size > 512 * 1024:
        raise ValueError("manifest too large")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("invalid manifest")
    if document_path == "desktop/installer.exe":
        entry = manifest.get("installer", {})
        if not isinstance(entry, dict) or entry.get("path") != "installer.exe":
            raise ValueError("installer not published")
    else:
        prefix = "desktop/files/"
        if not document_path.startswith(prefix):
            raise ValueError("not published")
        name = document_path[len(prefix) :]
        parts = PurePosixPath(name).parts
        if not name.startswith("resources/") or "\\" in name or "%" in name or ":" in name or any(part in {"", ".", ".."} for part in name.split("/")):
            raise ValueError("invalid resource path")
        entries = manifest.get("files", [])
        if not isinstance(entries, list):
            raise ValueError("invalid files")
        matches = [value for value in entries if isinstance(value, dict) and value.get("path") == name]
        if len(matches) != 1 or len(parts) < 2:
            raise ValueError("not published")
        entry = matches[0]
    expected_bytes = entry.get("bytes")
    expected_hash = entry.get("sha256")
    if type(expected_bytes) is not int or expected_bytes < 0 or not isinstance(expected_hash, str) or not re.fullmatch("[0-9a-f]{64}", expected_hash):
        raise ValueError("invalid asset metadata")
    target = _confined_file(document_path)
    if target.stat().st_size != expected_bytes:
        raise ValueError("asset size mismatch")
    with target.open("rb") as content:
        if hashlib.file_digest(content, "sha256").hexdigest() != expected_hash:
            raise ValueError("asset hash mismatch")
    return target


@router.get("/{document_path:path}")
async def read_controlled_document(document_path: str, request: Request) -> FileResponse:
    try:
        target = await asyncio.to_thread(_confined_file if document_path in _SERVED_NAMES else _asset, document_path)
    except (OSError, ValueError, TypeError, KeyError):
        raise HTTPException(status_code=404, detail={"code": "DOCUMENT_NOT_PUBLISHED"}) from None
    logger.info("serving reviewed update asset %s", document_path)
    return FileResponse(target, media_type=_SERVED_NAMES.get(document_path, "application/octet-stream"), headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
