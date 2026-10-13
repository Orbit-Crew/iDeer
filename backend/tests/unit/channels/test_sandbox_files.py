"""Direct unit tests for ``app/channels/sandbox_files.py``.

The module had no direct test references (code review 09-M5); channel-level
tests exercise it only through heavy integration paths, so these tests pin
its four observable branches with a stubbed sandbox lease:

- thread-data-mount providers skip the sandbox sync entirely (True);
- local-sandbox leases skip the remote ``update_file`` (True);
- a lease without a resolved sandbox client reports failure (False);
- a remote lease performs exactly one ``update_file`` under the lease and
  always releases the lease afterwards (True / release-on-error).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.channels.sandbox_files import sync_file_to_thread_sandbox


class _FakeLease:
    def __init__(self, sandbox_id: str, sandbox=None, run_sync_error: Exception | None = None):
        self.sandbox_id = sandbox_id
        self.sandbox = sandbox
        self.run_sync_calls: list[tuple] = []
        self.released = False
        self._run_sync_error = run_sync_error

    async def run_sync(self, func, /, *args, **kwargs):
        self.run_sync_calls.append((func, args, kwargs))
        if self._run_sync_error is not None:
            raise self._run_sync_error
        return func(*args, **kwargs)

    async def release(self):
        self.released = True


@pytest.fixture
def _leases(monkeypatch):
    captured: list[_FakeLease] = []

    def install(lease: _FakeLease):
        captured.append(lease)

        async def _fake_acquire(provider, thread_id, *, user_id, owner_prefix, release_on_last):
            return lease

        monkeypatch.setattr("app.channels.sandbox_files.acquire_sandbox_client_lease", _fake_acquire)

    install.captured = captured
    return install


@pytest.mark.anyio
async def test_thread_data_mount_provider_skips_sandbox_sync(_leases):
    provider = SimpleNamespace(uses_thread_data_mounts=True)

    synced = await sync_file_to_thread_sandbox(
        provider,
        thread_id="t1",
        user_id="u1",
        virtual_path="/uploads/a.bin",
        content=b"x",
        owner_prefix="test",
    )

    assert synced is True
    assert _leases.captured == []


@pytest.mark.anyio
async def test_local_sandbox_lease_skips_remote_update(_leases):
    lease = _FakeLease("local")
    _leases(lease)
    sandbox = SimpleNamespace(update_file=lambda *a: pytest.fail("must not be called"))

    synced = await sync_file_to_thread_sandbox(
        sandbox,
        thread_id="t1",
        user_id="u1",
        virtual_path="/uploads/a.bin",
        content=b"x",
        owner_prefix="test",
    )

    assert synced is True
    assert lease.run_sync_calls == []
    assert lease.released is True


@pytest.mark.asyncio
@pytest.mark.parametrize("sandbox_id", ["local", "local:thread-t1"])
async def test_local_sandbox_id_prefix_variants_skip_remote_update(sandbox_id, _leases):
    lease = _FakeLease(sandbox_id)
    _leases(lease)

    synced = await sync_file_to_thread_sandbox(
        SimpleNamespace(),
        thread_id="t1",
        user_id="u1",
        virtual_path="/uploads/a.bin",
        content=b"x",
        owner_prefix="test",
    )

    assert synced is True
    assert lease.run_sync_calls == []
    assert lease.released is True


@pytest.mark.anyio
async def test_lease_without_sandbox_reports_failure(_leases):
    lease = _FakeLease("remote-box")
    _leases(lease)

    synced = await sync_file_to_thread_sandbox(
        SimpleNamespace(),
        thread_id="t1",
        user_id="u1",
        virtual_path="/uploads/a.bin",
        content=b"x",
        owner_prefix="test",
    )

    assert synced is False
    assert lease.run_sync_calls == []
    assert lease.released is True


@pytest.mark.anyio
async def test_remote_lease_updates_file_once_and_releases(_leases):
    sandbox = SimpleNamespace(update_file=lambda path, data: "updated")
    lease = _FakeLease("remote-box", sandbox=sandbox)
    _leases(lease)

    synced = await sync_file_to_thread_sandbox(
        SimpleNamespace(),
        thread_id="t1",
        user_id="u1",
        virtual_path="/uploads/a.bin",
        content=b"payload",
        owner_prefix="test",
    )

    assert synced is True
    assert len(lease.run_sync_calls) == 1
    func, args, kwargs = lease.run_sync_calls[0]
    assert func is sandbox.update_file
    assert args == ("/uploads/a.bin", b"payload")
    assert kwargs == {}
    assert lease.released is True


@pytest.mark.anyio
async def test_update_file_failure_still_releases_lease(_leases):
    sandbox = SimpleNamespace(update_file=lambda *a: None)
    lease = _FakeLease("remote-box", sandbox=sandbox, run_sync_error=RuntimeError("transport down"))
    _leases(lease)

    with pytest.raises(RuntimeError, match="transport down"):
        await sync_file_to_thread_sandbox(
            SimpleNamespace(),
            thread_id="t1",
            user_id="u1",
            virtual_path="/uploads/a.bin",
            content=b"x",
            owner_prefix="test",
        )

    assert lease.released is True
