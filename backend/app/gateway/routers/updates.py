"""Controlled update/compatibility address (issue 107, Server side).

Operations review places signed release documents — the Desktop update
manifest, its detached signature, and the compatibility declaration — into
one controlled directory; this router serves those exact files at the
controlled address the Desktop already derives from its paired Server origin
(``/updates/desktop/manifest.json``, ``.../manifest.sig``,
``/updates/compatibility.json``, ``.../compatibility.sig``). The router is a
read-only view: it publishes exactly what operations reviewed, never
generates or mutates a document, and reports 404 honestly while nothing is
published. The Desktop keeps verifying every signature locally, so serving
stale or unreviewed files can never install or gate anything by itself.
"""

import logging
import os
from pathlib import Path

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
    """The operations-managed directory holding reviewed release documents.

    Deployment sets UPDATES_CONTROLLED_DIR to the reviewed directory; the
    default keeps the endpoint honest (404) while nothing is published.
    """
    configured = os.environ.get("UPDATES_CONTROLLED_DIR", "")
    directory = Path(configured) if configured else Path.cwd() / "updates-controlled"
    return directory if directory.is_absolute() else Path.cwd() / directory


@router.get("/{document_path:path}")
async def read_controlled_document(document_path: str, request: Request) -> FileResponse:
    if document_path not in _SERVED_NAMES:
        raise HTTPException(status_code=404, detail={"code": "DOCUMENT_NOT_PUBLISHED"})
    target = (_controlled_dir() / document_path).resolve()
    if not target.is_relative_to(_controlled_dir().resolve()) or not target.is_file():
        raise HTTPException(status_code=404, detail={"code": "DOCUMENT_NOT_PUBLISHED"})
    logger.info("serving controlled update document %s to %s", document_path, request.client.host if request.client else "unknown")
    return FileResponse(target, media_type=_SERVED_NAMES[document_path], headers={"Cache-Control": "no-store"})
