"""Evidence carrier concurrency and identity-fallback contracts."""

from __future__ import annotations

import asyncio
import sys

import pytest
from agentplatform_extension.evidence import (
    AuthorizationContext,
    RunEvidenceBinding,
    bind_run_evidence,
    current_run_evidence,
    record_tool_receipt,
)


def _binding() -> RunEvidenceBinding:
    return RunEvidenceBinding(snapshots=(), authorization=AuthorizationContext("caller-1", "agent-1", "policy-1"))


@pytest.mark.asyncio
async def test_to_thread_records_never_drop_evidence_items() -> None:
    """``record_*`` callers may run on ``asyncio.to_thread`` threads sharing
    the run's evidence carrier with the event loop; the carrier's
    read-modify-write must be synchronized or concurrent appends are lost
    (report 04-M2)."""
    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        with bind_run_evidence(_binding()):
            total_threads = 16
            per_thread = 25
            await asyncio.gather(
                *(
                    asyncio.to_thread(
                        _record_burst,
                        thread_index,
                        per_thread,
                    )
                    for thread_index in range(total_threads)
                )
            )
            binding = current_run_evidence()
        assert binding is not None
        assert len(binding.tool_receipts) == total_threads * per_thread, "concurrent to_thread records dropped evidence items"
    finally:
        sys.setswitchinterval(previous_interval)


def _record_burst(thread_index: int, count: int) -> None:
    for index in range(count):
        record_tool_receipt({"tool_call_id": f"call-{thread_index}-{index}", "status": "ok"})
