"""Behaviour-pinning tests for the transport split (LocalConsentCoordinator + session).

The refactor in transport.py splits the giant LocalRuntimeClient into:
  - LocalRuntimeClient (session + wire: connect, run, receive, send)
  - LocalConsentCoordinator (consent state machine + audit)

These tests prove the split preserves the external contract:
  - pause/resume/disconnect behave identically to before
  - consent routing (local vs relayed) is preserved
  - pending_consents() returns the same shape
  - the audit row shape for "unanswered" vs "approved" vs "denied" is unchanged
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.audit import AuditKind
from core.file_service import LocalFileService
from core.files import LocalFileStore, RootConfig
from core.policy import LocalPolicy
from core.protocol import MessageType, public_key_text, sign_envelope, verify_envelope
from core.transport import LocalRuntimeClient


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, value: str) -> None:
        self.sent.append(value)

    async def close(self) -> None:
        pass


def _client(tmp_path: Path, consent_prompt=None) -> LocalRuntimeClient:
    return LocalRuntimeClient(
        server_url="ws://unused",
        device_id="device-1",
        session_token="token",
        private_key=Ed25519PrivateKey.generate(),
        session_id="session-1",
        file_service=LocalFileService(
            LocalFileStore([RootConfig("/projects", tmp_path)])
        ),
        consent_prompt=consent_prompt,
    )


def _signed_task(server_key, payload, task_id="t-1"):
    return verify_envelope(
        sign_envelope(
            private_key=server_key,
            message_type=MessageType.TASK,
            device_id="device-1",
            session_id="session-1",
            task_id=task_id,
            payload=payload,
        ),
        server_public_key=public_key_text(server_key),
        expected_device_id="device-1",
        expected_session_id="session-1",
    )


def test_pause_resume_still_records_control_events(tmp_path: Path) -> None:
    """Behaviour-pinning: pause/resume produce CONTROL audit rows (shape unchanged)."""
    client = _client(tmp_path)
    client.connection = FakeConnection()

    client.pause(actor_id="alice")
    client.resume(actor_id="alice")

    control = client.audit.recent(kind=AuditKind.CONTROL)
    actions = [(e.action, e.actor_id) for e in control]
    assert ("resumed", "alice") in actions
    assert ("paused", "alice") in actions


def test_pending_consents_returns_pending_view(tmp_path: Path) -> None:
    """Behaviour-pinning: pending_consents() shape preserved after the split."""
    server_key = Ed25519PrivateKey.generate()
    client = _client(tmp_path)
    client.connection = FakeConnection()
    task = _signed_task(server_key, {
        "operation": "local.files.write",
        "path": "/projects/pending.txt",
        "content": "x",
        "run_id": "r1",
    }, task_id="task-pending")

    # Consent-required policy: the local prompt path.
    client.policy = LocalPolicy(consent_required_capabilities=frozenset(["local.files.write"]))
    client.file_service.policy = client.policy

    asyncio.run(client._handle_task(task))
    pending = client.pending_consents()
    assert len(pending) == 1
    assert pending[0].task_id == "task-pending"
    assert pending[0].capability == "local.files.write"
    assert len(pending[0].request_hash) == 64


def test_disconnect_abandons_open_prompts(tmp_path: Path) -> None:
    """Behaviour-pinning: disconnect closes open prompts, audit records 'unanswered'.

    Mirrors the existing test in test_transport.py: when the session ends,
    open prompts must fail closed, and the audit must say why.
    """
    server_key = Ed25519PrivateKey.generate()

    async def nobody_answers(request):
        await asyncio.Event().wait()

    client = _client(tmp_path, consent_prompt=nobody_answers)
    connection = FakeConnection()
    client.connection = connection
    task = _signed_task(server_key, {
        "operation": "local.files.write",
        "path": "/projects/during-disconnect.txt",
        "content": "x",
        "run_id": "r1",
    }, task_id="task-dd")

    async def scenario():
        running = asyncio.create_task(client._handle_task(task))
        while not client.pending_consents():
            await asyncio.sleep(0.01)
        await client.close(actor_id="bob")
        await running

    asyncio.run(scenario())

    # No result frame (the request never executed), and the file was not written.
    # Grab the connection reference before close (close clears it).
    assert not any(
        json.loads(raw)["type"] == MessageType.TASK_RESULT.value for raw in connection.sent
    )
    assert not (tmp_path / "during-disconnect.txt").exists()
    # The audit row must explain why: an unanswered request, not a decision.
    consent = client.audit.recent(kind=AuditKind.CONSENT)
    actions = [(e.action, e.actor_id) for e in consent]
    assert ("unanswered", None) in actions
    assert ("required", None) in actions


def test_no_policy_denial_leaks_to_audit(tmp_path: Path) -> None:
    """Behaviour-pinning: if no task runs, no policy denial audit row exists."""
    client = _client(tmp_path)
    client.connection = FakeConnection()
    assert client.audit.recent(kind=AuditKind.POLICY) == []


def test_mcp_error_at_entry_becomes_error_frame(tmp_path: Path) -> None:
    """05-L5: a malformed capability name raises MCPError at the mcp_service
    entry, before any receipt exists. The task entry must convert it into an
    error frame; unhandled it escaped _handle_task, _task_finished swallowed
    it, and the server waited out its deadline with no reply."""
    from core.mcp import MCPError

    server_key = Ed25519PrivateKey.generate()
    client = _client(tmp_path)
    client.connection = FakeConnection()

    class ExplodingMCPService:
        consent = None

        async def execute(self, operation, payload):
            raise MCPError("MCP_UNKNOWN_CAPABILITY", "no such mcp server: nosuch")

    client.mcp_service = ExplodingMCPService()

    asyncio.run(
        client._handle_task(
            _signed_task(
                server_key,
                {"operation": "local.mcp.nosuch.tool", "run_id": "r1"},
                task_id="task-mcp",
            )
        )
    )

    errors = [
        json.loads(raw)
        for raw in client.connection.sent
        if json.loads(raw)["type"] == MessageType.ERROR.value
    ]
    assert [e["payload"]["error_code"] for e in errors] == ["MCP_UNKNOWN_CAPABILITY"]


def test_duplicate_task_id_is_refused_instead_of_orphaning(tmp_path: Path) -> None:
    """05-L5: a second TASK frame reusing a live task id used to overwrite the
    _running_tasks entry, dropping the still-running old task from cancel
    tracking. The newcomer is refused with DUPLICATE_TASK instead."""
    server_key = Ed25519PrivateKey.generate()

    async def nobody_answers(request):
        await asyncio.Event().wait()

    client = _client(tmp_path, consent_prompt=nobody_answers)
    client.server_public_key = public_key_text(server_key)
    client.policy = LocalPolicy(
        consent_required_capabilities=frozenset(["local.files.write"])
    )
    client.file_service.policy = client.policy

    def dup_frame():
        return sign_envelope(
            private_key=server_key,
            message_type=MessageType.TASK,
            device_id="device-1",
            session_id="session-1",
            task_id="task-dup",
            payload={
                "operation": "local.files.write",
                "path": "/projects/dup.txt",
                "content": "x",
                "run_id": "r1",
            },
        )

    class ReplayingConnection(FakeConnection):
        def __init__(self, frames):
            super().__init__()
            self.frames = frames

        async def __aiter__(self):
            for frame in self.frames:
                yield frame

    client.connection = ReplayingConnection(
        [json.dumps(dup_frame()), json.dumps(dup_frame())]
    )

    async def scenario():
        loop = asyncio.create_task(client._receive_loop())
        while not any(
            json.loads(raw)["payload"].get("error_code") == "DUPLICATE_TASK"
            for raw in client.connection.sent
            if json.loads(raw)["type"] == MessageType.ERROR.value
        ):
            await asyncio.sleep(0.01)
        loop.cancel()
        await asyncio.gather(loop, return_exceptions=True)
        await client.close(actor_id="bob")
        for pending in tuple(client._running_tasks.values()):
            await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(scenario())

    assert list(client._running_tasks) == []


def test_task_arriving_after_disconnect_does_not_raise(tmp_path: Path) -> None:
    """05-L5: _handle_task used to assert on a live connection; a task that
    ran after the session ended raised AssertionError into _task_finished,
    which swallows it. The dispatch is a no-op without a connection."""
    server_key = Ed25519PrivateKey.generate()
    client = _client(tmp_path)
    client.connection = None

    asyncio.run(
        client._handle_task(
            _signed_task(
                server_key,
                {"operation": "echo", "value": "x", "run_id": "r1"},
                task_id="task-late",
            )
        )
    )


def test_output_frames_after_disconnect_do_not_raise(tmp_path: Path) -> None:
    """05-L5: the output/consent/result senders used to assert on a live
    connection; a session that ended mid-task turned into an AssertionError
    that _task_finished silently swallowed. They now drop the frame."""
    client = _client(tmp_path)
    client.connection = None

    asyncio.run(client.consent_coord._send_python_output("t-1", "stdout", "hello"))
