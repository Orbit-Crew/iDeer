"""Regression anchor: device artifact upload must not block the event loop.

`DeviceArtifactStore.upload` writes up to 10 MB per artifact. Under the strict
Blockbuster context (this directory's conftest), any blocking IO reached from
``app.*`` while on the event loop raises ``BlockingError``, so this test fails
while the upload body writes to disk synchronously.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.device_control.artifacts import ArtifactStoreError, DeviceArtifactStore

pytestmark = pytest.mark.asyncio


async def _chunks(*values: bytes):
    for value in values:
        yield value


def _grant(store: DeviceArtifactStore, **overrides):
    values = {
        "device_id": "device-1",
        "session_id": "session-1",
        "run_id": "run-1",
        "task_id": "task-1",
        "thread_id": "thread-1",
        "filename": "result.txt",
        "expires_at": datetime.now(UTC) + timedelta(minutes=1),
    }
    values.update(overrides)
    return store.issue_grant(**values)


async def test_device_artifact_upload_does_not_block_event_loop(tmp_path: Path) -> None:
    store = await asyncio.to_thread(DeviceArtifactStore, tmp_path)
    grant = _grant(store)

    handle, size, digest = await store.upload(grant.token, _chunks(b"hello ", b"world"))

    assert handle == f"local://{digest}/result.txt"
    assert size == len(b"hello world")
    written = await asyncio.to_thread((tmp_path / "thread-1" / "outputs" / f"{digest}-result.txt").read_bytes)
    assert written == b"hello world"


async def test_device_artifact_upload_size_limit_does_not_block_event_loop(
    tmp_path: Path,
) -> None:
    store = await asyncio.to_thread(DeviceArtifactStore, tmp_path)
    grant = _grant(store, max_bytes=1)

    with pytest.raises(ArtifactStoreError, match="size"):
        await store.upload(grant.token, _chunks(b"xx"))

    outputs = tmp_path / "thread-1" / "outputs"

    def _leftovers() -> list[str]:
        return [entry.name for entry in outputs.iterdir()] if outputs.exists() else []

    assert await asyncio.to_thread(_leftovers) == []
