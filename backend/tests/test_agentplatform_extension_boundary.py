from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from agentplatform_extension import install
from agentplatform_extension.evidence import (
    AuthorizationContext,
    EvidenceLifecycleContributor,
    ResourceSnapshotRef,
    RunEvidenceBinding,
    bind_run_evidence,
    build_run_evidence_envelope,
    current_run_evidence,
    record_local_execution_receipt,
    record_subagent_verification,
    record_tool_receipt,
)
from agentplatform_extension.network_policy import NetworkPolicy
from deerflow_extension_api import ExtensionData, RunEvidenceEnvelope, TaskInfo, TaskOutcome

from deerflow.extensions import get_loaded_extensions, resolve_runtime_evidence_hooks, set_loaded_extensions
from deerflow.extensions.registry import ExtensionRegistry

_BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_run_evidence_envelope_freezes_resource_identity_and_caller_boundary() -> None:
    envelope = build_run_evidence_envelope(
        run_id="run-1",
        thread_id="thread-1",
        snapshots=[
            ResourceSnapshotRef("workflow-1", 3, "a" * 64, "root"),
            {"resource_id": "skill-1", "version": 2, "content_hash": "b" * 64},
        ],
        authorization=AuthorizationContext(
            caller_user_id="caller",
            effective_agent_id="agent-1",
            policy_revision="policy-7",
            allowed_tools=("read_file",),
        ),
        runtime_assembly_fingerprint="assembly-1",
    )

    assert envelope.resource_snapshots == (
        {"resource_id": "workflow-1", "version": 3, "content_hash": "a" * 64, "selection_role": "root"},
        {"resource_id": "skill-1", "version": 2, "content_hash": "b" * 64, "selection_role": "resolved"},
    )
    assert envelope.authorization_context == {
        "caller_user_id": "caller",
        "effective_agent_id": "agent-1",
        "policy_revision": "policy-7",
        "allowed_tools": ["read_file"],
        "memory_scope": "caller",
    }
    assert "credential" not in str(envelope.authorization_context).lower()


def test_evidence_rejects_duplicate_or_invalid_snapshot() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build_run_evidence_envelope(
            run_id="run-1",
            thread_id="thread-1",
            snapshots=[
                ResourceSnapshotRef("agent-1", 1, "a" * 64),
                ResourceSnapshotRef("agent-1", 2, "b" * 64),
            ],
            authorization=AuthorizationContext("caller", "agent", "policy"),
        )

    with pytest.raises(ValueError, match="SHA-256"):
        ResourceSnapshotRef("agent-1", 1, "not-a-hash")


def test_shared_agent_memory_scope_cannot_be_owner_scoped() -> None:
    with pytest.raises(ValueError, match="caller-scoped"):
        AuthorizationContext("caller", "agent", "policy", memory_scope="owner")


def test_run_evidence_binding_exposes_only_caller_safe_metadata_projection() -> None:
    binding = RunEvidenceBinding(
        snapshots=[ResourceSnapshotRef("agent-1", 2, "a" * 64, "root")],
        authorization=AuthorizationContext("caller-1", "agent-1", "policy-2", memory_scope="caller-1"),
        runtime_assembly_fingerprint="b" * 64,
    )

    projection = binding.as_mapping()

    assert projection["resource_snapshots"] == [
        {
            "resource_id": "agent-1",
            "version": 2,
            "content_hash": "a" * 64,
            "selection_role": "root",
        }
    ]
    assert projection["authorization_context"]["memory_scope"] == "caller-1"
    assert "owner_credential" not in projection


def test_run_evidence_binding_collects_runtime_receipts() -> None:
    binding = RunEvidenceBinding(
        snapshots=[ResourceSnapshotRef("agent-1", 2, "a" * 64, "root")],
        authorization=AuthorizationContext("caller-1", "agent-1", "policy-2"),
    )

    with bind_run_evidence(binding):
        record_tool_receipt({"tool_name": "read_file", "status": "success"})
        record_subagent_verification({"task_id": "task-1", "verdict": "VERIFIED"})
        projection = current_run_evidence().as_mapping()

    assert projection["tool_receipts"] == [{"tool_name": "read_file", "status": "success"}]
    assert projection["subagent_verification"] == [{"task_id": "task-1", "verdict": "VERIFIED"}]


def test_network_policy_defaults_to_intranet_allowlist_and_public_deny() -> None:
    policy = NetworkPolicy(allowed_hosts=("vllm.internal",))

    assert policy.allows("https://vllm.internal/v1")
    assert not policy.allows("https://example.com")
    assert not policy.allows("http://127.0.0.1:8080")
    assert NetworkPolicy(allow_public=True).allows("https://example.com")


@pytest.mark.asyncio
async def test_evidence_lifecycle_contributor_binds_snapshot_and_terminal_outcome() -> None:
    contributor = EvidenceLifecycleContributor(
        snapshots=[ResourceSnapshotRef("agent-1", 2, "a" * 64)],
        authorization=AuthorizationContext("caller", "agent", "policy"),
        runtime_assembly_fingerprint="assembly-1",
    )
    store = ExtensionData("task-1")
    info = TaskInfo(task_id="task-1", run_id="run-1", thread_id="thread-1", kind="lead")

    await contributor.on_task_start(ExtensionData("app"), store, info)
    started = store.get(RunEvidenceEnvelope)
    assert started is not None
    assert started.resource_snapshots[0]["version"] == 2
    assert started.authorization_context["caller_user_id"] == "caller"

    await contributor.on_task_stop(ExtensionData("app"), store, info, TaskOutcome.COMPLETED)
    stopped = store.get(RunEvidenceEnvelope)
    assert stopped is not None and stopped.outcome is TaskOutcome.COMPLETED


@pytest.mark.asyncio
async def test_evidence_lifecycle_publishes_collected_receipts() -> None:
    contributor = EvidenceLifecycleContributor(
        snapshots=[ResourceSnapshotRef("agent-1", 2, "a" * 64)],
        authorization=AuthorizationContext("caller", "agent", "policy"),
    )
    store = ExtensionData("task-receipts")
    info = TaskInfo(task_id="task-receipts", run_id="run-1", thread_id="thread-1", kind="lead")
    binding = RunEvidenceBinding(
        snapshots=[ResourceSnapshotRef("agent-1", 2, "a" * 64)],
        authorization=AuthorizationContext("caller", "agent", "policy"),
    )

    with bind_run_evidence(binding):
        await contributor.on_task_start(ExtensionData("app"), store, info)
        record_tool_receipt({"tool_name": "write_file", "status": "success"})
        await contributor.on_task_stop(ExtensionData("app"), store, info, TaskOutcome.COMPLETED)

    envelope = store.get(RunEvidenceEnvelope)
    assert envelope is not None
    assert envelope.tool_receipts == ({"tool_name": "write_file", "status": "success"},)


def test_local_execution_receipt_is_attached_to_the_tool_receipt_ledger() -> None:
    binding = RunEvidenceBinding(
        snapshots=[],
        authorization=AuthorizationContext("caller", "agent", "policy"),
    )
    with bind_run_evidence(binding):
        record_local_execution_receipt(
            {"capability": "local.python", "request_hash": "a" * 64, "status": "completed"},
            tool_call_id="call-1",
        )
        receipt = current_run_evidence().tool_receipts[0]

    assert receipt["receipt_kind"] == "tool"
    assert receipt["tool_call_id"] == "call-1"
    assert receipt["local_execution_receipt"]["request_hash"] == "a" * 64


def test_install_registers_boundary_only_with_explicit_authorization() -> None:
    empty = ExtensionRegistry()
    install(empty, {})
    assert not empty.build().has_task_lifecycle

    configured = ExtensionRegistry()
    with configured.attributed_to("agentplatform:install"):
        install(
            configured,
            {
                "authorization": {
                    "caller_user_id": "caller",
                    "effective_agent_id": "agent",
                    "policy_revision": "policy",
                },
                "resource_snapshots": [],
            },
        )
    loaded = configured.build()
    assert loaded.has_task_lifecycle


@pytest.mark.asyncio
async def test_shared_agent_install_projects_caller_permissions_without_owner_state() -> None:
    registry = ExtensionRegistry()
    with registry.attributed_to("agentplatform:install"):
        install(
            registry,
            {
                "authorization": {
                    "caller_user_id": "caller",
                    "effective_agent_id": "shared-agent",
                    "policy_revision": "policy-2",
                    "allowed_tools": ["read_file"],
                    "memory_scope": "caller",
                    "owner_user_id": "owner",
                    "owner_credential": "must-not-cross-runtime-boundary",
                    "owner_memory_scope": "owner",
                },
            },
        )

    contributor = registry.build().task_lifecycle[0][1]
    store = ExtensionData("task-1")
    info = TaskInfo(task_id="task-1", run_id="run-1", thread_id="thread-1", kind="lead")

    await contributor.on_task_start(ExtensionData("app"), store, info)
    envelope = store.get(RunEvidenceEnvelope)
    assert envelope is not None
    assert envelope.authorization_context == {
        "caller_user_id": "caller",
        "effective_agent_id": "shared-agent",
        "policy_revision": "policy-2",
        "allowed_tools": ["read_file"],
        "memory_scope": "caller",
    }
    assert "owner" not in str(envelope.authorization_context)
    assert "credential" not in str(envelope.authorization_context).lower()


@pytest.mark.asyncio
async def test_dynamic_install_uses_the_run_bound_snapshot_and_caller_context() -> None:
    registry = ExtensionRegistry()
    with registry.attributed_to("agentplatform:install"):
        install(registry, {"dynamic_context": True})

    contributor = registry.build().task_lifecycle[0][1]
    store = ExtensionData("task-1")
    info = TaskInfo(task_id="task-1", run_id="run-1", thread_id="thread-1", kind="lead")
    binding = RunEvidenceBinding(
        snapshots=[ResourceSnapshotRef("agent-1", 7, "a" * 64, "root")],
        authorization=AuthorizationContext(
            "caller",
            "agent-1",
            "resource-authz-3",
            allowed_tools=("read_file",),
        ),
        runtime_assembly_fingerprint="assembly-7",
    )

    with bind_run_evidence(binding):
        await contributor.on_task_start(ExtensionData("app"), store, info)

    envelope = store.get(RunEvidenceEnvelope)
    assert envelope is not None
    assert envelope.resource_snapshots[0]["version"] == 7
    assert envelope.authorization_context["caller_user_id"] == "caller"
    assert envelope.runtime_assembly_fingerprint == "assembly-7"


# --- Single-track evidence hook registration (04-M6) ------------------------


def _run_probe(source: str) -> subprocess.CompletedProcess[str]:
    """Run ``source`` in a fresh interpreter so import order cannot mask side effects."""
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=_BACKEND_DIR,
        timeout=120,
    )


def test_importing_extension_package_has_no_process_global_side_effect() -> None:
    """Importing the package must not install process-global evidence hooks.

    The documented contract (``install()`` docstring) is that the extension is
    registered only when the host explicitly enables it; a module-top-level
    ``set_runtime_evidence_hooks(...)`` would let mere import order flip host
    behaviour.
    """
    probe = "\n".join(
        [
            "import agentplatform_extension",
            "import agentplatform_extension.evidence",
            "from deerflow_extension_api import get_runtime_evidence_hooks",
            "hooks = get_runtime_evidence_hooks()",
            "assert hooks is None, f'import installed process-global evidence hooks: {hooks!r}'",
        ]
    )
    result = _run_probe(probe)
    assert result.returncode == 0, result.stderr


def test_host_without_enabled_extension_keeps_runtime_evidence_hooks_dormant() -> None:
    """A process that never enabled the extension must resolve no evidence hooks.

    The fresh interpreter imports the extension the way any consumer would, then
    resolves hooks against the process default loaded set (no extensions enabled).
    """
    probe = "\n".join(
        [
            "import agentplatform_extension",
            "from deerflow.extensions import get_loaded_extensions, resolve_runtime_evidence_hooks",
            "hooks = resolve_runtime_evidence_hooks(get_loaded_extensions())",
            "assert hooks is None, f'hooks active although the host enabled no extension: {hooks!r}'",
        ]
    )
    result = _run_probe(probe)
    assert result.returncode == 0, result.stderr


def test_registry_registered_hooks_resolve_and_behave_for_a_run() -> None:
    """Host enabled the extension: the registry track serves runtime dispatch.

    Behavioural equivalence control for the single-track migration: hooks handed
    out from ``LoadedExtensions`` must project receipts exactly like the direct
    extension functions do.
    """
    registry = ExtensionRegistry()
    with registry.attributed_to("agentplatform:install"):
        install(registry, {"dynamic_context": True})

    hooks = resolve_runtime_evidence_hooks(registry.build())
    assert hooks is not None

    binding = RunEvidenceBinding(snapshots=(), authorization=AuthorizationContext("caller", "agent", "policy"))
    with bind_run_evidence(binding):
        hooks.record_tool_receipt({"tool_call_id": "call-1", "tool_name": "bash", "status": "success"})
        hooks.record_subagent_verification({"task_id": "child-1", "status": "PASSED"})
        stored = current_run_evidence()

    assert stored is not None
    assert [receipt["tool_call_id"] for receipt in stored.tool_receipts] == ["call-1"]
    assert [verification["task_id"] for verification in stored.subagent_verification] == ["child-1"]


def test_run_without_snapshot_resolves_the_host_registry_track() -> None:
    """Hook resolution without a run snapshot falls back to the host's loaded set.

    ``task_tool`` resolves hooks with ``resolve_run_extensions(context)`` which is
    ``None`` in host processes that never embed a snapshot (workflow worker);
    resolution must then follow the same ``get_loaded_extensions()`` fallback the
    executor and run worker already apply, so the registry track stays effective.
    """
    registry = ExtensionRegistry()
    with registry.attributed_to("agentplatform:install"):
        install(registry, {"dynamic_context": True})

    previous = get_loaded_extensions()
    set_loaded_extensions(registry.build())
    try:
        assert resolve_runtime_evidence_hooks(None) is not None
        assert resolve_runtime_evidence_hooks(None) is resolve_runtime_evidence_hooks(get_loaded_extensions())
    finally:
        set_loaded_extensions(previous)
