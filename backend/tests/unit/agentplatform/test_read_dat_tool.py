"""S3 seam: the ``read_dat`` tool over uploaded telemetry ``.dat`` files.

Ticket 73: the tool is the model's first telemetry reading capability — a
read-only hex view of ``.dat`` files in this thread's input area (virtual
root ``/mnt/user-data/uploads/``), paged by byte offset.  It accepts nothing
but fenced upload paths (virtual-path resolution + containment inside the
thread uploads dir), rejects anything else structurally with
machine-distinguishable reason codes (``path_out_of_bounds`` /
``suffix_mismatch`` / ``file_too_large`` / ``file_not_found`` /
``invalid_paging`` / ``thread_context_missing``), and never writes to or
executes the file.

Ticket 74: ``mode="structure"`` adds a deterministic structure probe on the
same tool — candidate sync-word n-grams, their gap regularity, and an
inferred frame length — with all caps as code constants, streaming/bounded
scans, visible truncation flags, and an explicit 未检出 conclusion when no
repeating structure exists.  ``mode="view"`` stays the default and is
byte-for-byte the ticket-73 behavior.

Everything here drives the tool coroutine directly (the builtin-tool test
convention) against seeded uploads on a temporary filesystem home plus the
committed synthetic samples under ``backend/tests/fixtures/telemetry/``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agentplatform.tools import dat_access
from app.agentplatform.tools import read_dat_tool as tool_module
from deerflow.config.paths import Paths

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "telemetry"
NORMAL_FRAMES = (FIXTURES_DIR / "normal_frames.dat").read_bytes()
TRUNCATED_FRAMES = (FIXTURES_DIR / "truncated.dat").read_bytes()
NO_SYNC_ENTROPY = (FIXTURES_DIR / "no_sync_high_entropy.dat").read_bytes()


def _runtime(env, thread_id: str = "thread-1", user_id: str = "owner-1") -> SimpleNamespace:
    context: dict = {"thread_id": thread_id, "user_id": user_id, "user_role": "user"}
    thread_data = {
        "workspace_path": str(env.paths.sandbox_work_dir(thread_id, user_id=user_id)),
        "uploads_path": str(env.paths.sandbox_uploads_dir(thread_id, user_id=user_id)),
        "outputs_path": str(env.paths.sandbox_outputs_dir(thread_id, user_id=user_id)),
    }
    return SimpleNamespace(
        state={"thread_data": thread_data},
        context=context,
        config={"configurable": {"thread_id": thread_id}},
    )


def _seed_upload(env, name: str, payload: bytes) -> None:
    uploads = env.paths.sandbox_uploads_dir("thread-1", user_id="owner-1")
    target = uploads / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


@pytest.fixture
def env(tmp_path, monkeypatch):
    paths = Paths(tmp_path)
    monkeypatch.setattr("app.agentplatform.tools.dat_access.get_paths", lambda: paths)
    return SimpleNamespace(paths=paths, tmp_path=tmp_path, monkeypatch=monkeypatch)


async def _call(runtime, file_path: str, **kwargs) -> dict:
    raw = await tool_module.read_dat_tool.coroutine(runtime=runtime, file_path=file_path, **kwargs)
    return json.loads(raw)


@pytest.mark.asyncio
async def test_renders_paged_hex_view_for_committed_dat_sample(env) -> None:
    _seed_upload(env, "telemetry.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/telemetry.dat", length=64)

    assert "error" not in payload
    assert payload["path"] == "/mnt/user-data/uploads/telemetry.dat"
    assert payload["file_size"] == len(NORMAL_FRAMES)
    assert payload["offset"] == 0
    assert payload["length"] == 64
    assert payload["max_view_bytes"] == tool_module.DAT_VIEW_MAX_BYTES
    assert payload["truncated"] is False
    assert payload["has_more"] is True
    assert payload["next_offset"] == 64
    lines = payload["hex_view"].splitlines()
    assert len(lines) == 4
    assert lines[0] == "00000000  1a cf fc 1d 00 00 00 00  00 00 03 a9 07 52 0a fb |.............R..|"
    assert "next_action" in payload


@pytest.mark.asyncio
async def test_reads_dat_nested_in_upload_subdirectories(env) -> None:
    _seed_upload(env, "orbit/ch-2.dat", bytes(range(16)))

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/orbit/ch-2.dat")

    assert "error" not in payload
    assert payload["length"] == 16
    assert payload["has_more"] is False


@pytest.mark.asyncio
async def test_pages_with_offset_and_length(env) -> None:
    _seed_upload(env, "blob.dat", bytes(range(32)))

    second_page = await _call(_runtime(env), "/mnt/user-data/uploads/blob.dat", offset=16, length=16)
    assert second_page["offset"] == 16
    assert second_page["length"] == 16
    assert second_page["hex_view"] == ("00000010  10 11 12 13 14 15 16 17  18 19 1a 1b 1c 1d 1e 1f |................|")
    assert second_page["has_more"] is False

    first_page = await _call(_runtime(env), "/mnt/user-data/uploads/blob.dat", offset=0, length=8)
    assert first_page["length"] == 8
    assert first_page["has_more"] is True
    assert first_page["next_offset"] == 8


@pytest.mark.asyncio
async def test_length_beyond_single_output_limit_is_truncated_with_notice(env, monkeypatch) -> None:
    _seed_upload(env, "blob.dat", bytes(range(32)))
    monkeypatch.setattr(tool_module, "DAT_VIEW_MAX_BYTES", 8)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/blob.dat", length=100)

    assert payload["length"] == 8
    assert payload["truncated"] is True
    assert payload["max_view_bytes"] == 8
    assert payload["has_more"] is True
    assert "offset=8" in payload["next_action"]


@pytest.mark.asyncio
async def test_offset_at_exact_end_of_file_returns_empty_view(env) -> None:
    _seed_upload(env, "blob.dat", bytes(range(32)))

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/blob.dat", offset=32)

    assert "error" not in payload
    assert payload["offset"] == 32
    assert payload["length"] == 0
    assert payload["hex_view"] == ""
    assert payload["has_more"] is False


@pytest.mark.asyncio
async def test_offset_past_end_of_file_is_invalid_paging(env) -> None:
    _seed_upload(env, "blob.dat", bytes(range(32)))

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/blob.dat", offset=33)

    assert payload["reason_code"] == "invalid_paging"
    assert payload["allowed_pattern"] == "/mnt/user-data/uploads/<file>"


@pytest.mark.asyncio
async def test_negative_offset_or_length_is_invalid_paging(env) -> None:
    _seed_upload(env, "blob.dat", bytes(range(32)))

    for kwargs in ({"offset": -1}, {"length": -1}):
        payload = await _call(_runtime(env), "/mnt/user-data/uploads/blob.dat", **kwargs)
        assert payload["reason_code"] == "invalid_paging", kwargs


@pytest.mark.asyncio
async def test_paths_outside_the_thread_uploads_fence_are_structurally_rejected(env) -> None:
    _seed_upload(env, "telemetry.dat", NORMAL_FRAMES)

    for declared in [
        "/mnt/user-data/workspace/telemetry.dat",
        "/mnt/user-data/outputs/telemetry.dat",
        "/mnt/user-data/code-evidence/pkg-1/source/telemetry.dat",
        "/mnt/user-data/uploads",
        "/mnt/user-data/uploads/",
        "/mnt/user-data/uploads/../etc/passwd",
        "/etc/passwd",
        "telemetry.dat",
        "",
    ]:
        payload = await _call(_runtime(env), declared)
        assert payload["reason_code"] == "path_out_of_bounds", declared
        assert payload["allowed_pattern"] == "/mnt/user-data/uploads/<file>"
        assert "error" in payload


@pytest.mark.asyncio
async def test_symlink_escape_out_of_uploads_dir_is_rejected(env) -> None:
    outside = env.tmp_path / "outside.dat"
    outside.write_bytes(NORMAL_FRAMES)
    uploads = env.paths.sandbox_uploads_dir("thread-1", user_id="owner-1")
    uploads.mkdir(parents=True, exist_ok=True)
    os.symlink(outside, uploads / "leak.dat")

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/leak.dat")

    assert payload["reason_code"] == "path_out_of_bounds"


@pytest.mark.asyncio
async def test_non_dat_uploads_are_rejected_with_suffix_mismatch(env) -> None:
    _seed_upload(env, "notes.txt", b"plain text")
    _seed_upload(env, "blob.datx", bytes(range(8)))

    for name in ("notes.txt", "blob.datx"):
        payload = await _call(_runtime(env), f"/mnt/user-data/uploads/{name}")
        assert payload["reason_code"] == "suffix_mismatch", name
        assert name in payload["error"]


@pytest.mark.asyncio
async def test_dat_suffix_match_is_case_insensitive(env) -> None:
    _seed_upload(env, "TELEMETRY.DAT", bytes(range(16)))

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/TELEMETRY.DAT")

    assert "error" not in payload
    assert payload["length"] == 16


@pytest.mark.asyncio
async def test_oversized_dat_is_rejected_with_constant_limit(env, monkeypatch) -> None:
    _seed_upload(env, "big.dat", bytes(64))
    monkeypatch.setattr(dat_access, "DAT_MAX_FILE_BYTES", 32)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/big.dat")

    assert payload["reason_code"] == "file_too_large"
    assert "32" in payload["error"]


@pytest.mark.asyncio
async def test_default_size_cap_is_the_binding_constant() -> None:
    assert dat_access.DAT_MAX_FILE_BYTES == 512 * 1024 * 1024


@pytest.mark.asyncio
async def test_thread_context_is_required(env) -> None:
    _seed_upload(env, "telemetry.dat", NORMAL_FRAMES)

    missing_thread_id = _runtime(env)
    missing_thread_id.context = {}
    missing_thread_id.config = {"configurable": {}}

    no_thread_data = _runtime(env)
    no_thread_data.state = None

    for runtime in (missing_thread_id, no_thread_data):
        payload = await _call(runtime, "/mnt/user-data/uploads/telemetry.dat")
        assert payload["reason_code"] == "thread_context_missing", runtime


@pytest.mark.asyncio
async def test_missing_upload_file_is_reported(env) -> None:
    payload = await _call(_runtime(env), "/mnt/user-data/uploads/missing.dat")

    assert payload["reason_code"] == "file_not_found"
    assert "missing.dat" in payload["error"]


@pytest.mark.asyncio
async def test_calls_leave_source_file_unchanged(env) -> None:
    _seed_upload(env, "telemetry.dat", NORMAL_FRAMES)
    _seed_upload(env, "notes.txt", b"plain text")
    target = env.paths.sandbox_uploads_dir("thread-1", user_id="owner-1") / "telemetry.dat"
    before = (target.stat().st_size, target.stat().st_mtime_ns, hashlib.sha256(target.read_bytes()).hexdigest())

    await _call(_runtime(env), "/mnt/user-data/uploads/telemetry.dat", offset=128, length=32)
    await _call(_runtime(env), "/mnt/user-data/uploads/telemetry.dat", offset=-5)
    await _call(_runtime(env), "/mnt/user-data/uploads/notes.txt")
    await _call(_runtime(env), "/mnt/user-data/uploads/../../etc/passwd")

    after = (target.stat().st_size, target.stat().st_mtime_ns, hashlib.sha256(target.read_bytes()).hexdigest())
    assert after == before


# --- ticket 74: mode="structure" — deterministic structure probe ---------


def _candidate(payload: dict, pattern_hex: str) -> dict | None:
    return next((item for item in payload["candidates"] if item["pattern_hex"] == pattern_hex), None)


@pytest.mark.asyncio
async def test_structure_mode_detects_sync_word_frame_length_and_caps_output(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", mode="structure")

    assert "error" not in payload
    assert payload["mode"] == "structure"
    assert payload["path"] == "/mnt/user-data/uploads/frames.dat"
    assert payload["file_size"] == len(NORMAL_FRAMES)
    assert payload["scanned_bytes"] == len(NORMAL_FRAMES)
    assert payload["scan_truncated"] is False
    # The fixture layout is documented (32-byte frames, sync 1A CF FC 1D), so
    # asserting the concrete finding is legitimate: the detector must find it
    # generically, this asserts it did.
    sync = _candidate(payload, "1a cf fc 1d")
    assert sync is not None
    assert sync["occurrences"] == 64
    assert sync["dominant_gap_bytes"] == 32
    assert sync["gap_regular"] is True
    assert sync["gap_regularity"] == 1.0
    assert sync["inferred_frame_bytes"] == 32
    # Occurrence totals are exact but gap evidence is a bounded sample — the
    # cap must be visible instead of silently implied.
    assert sync["gap_samples"] == tool_module._STRUCTURE_MAX_GAP_SAMPLES
    assert sync["gaps_capped"] is True
    assert payload["detected"] is True
    assert payload["inferred_frame_bytes"] == 32
    # Output caps are code constants and truncation is visible.
    assert len(payload["candidates"]) == tool_module._STRUCTURE_MAX_CANDIDATES
    assert payload["candidates_truncated"] is True
    assert payload["summary"]


@pytest.mark.asyncio
async def test_structure_mode_reports_explicit_not_detected_for_unstructured_file(env) -> None:
    _seed_upload(env, "noise.dat", NO_SYNC_ENTROPY)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/noise.dat", mode="structure")

    assert "error" not in payload
    assert payload["detected"] is False
    assert payload["inferred_frame_bytes"] is None
    # An explicit conclusion, never a bare empty result.
    assert "未检出" in payload["summary"]
    for candidate in payload["candidates"]:
        assert candidate["inferred_frame_bytes"] is None


@pytest.mark.asyncio
async def test_structure_mode_on_truncated_stream_detects_frames_without_fabricating(env) -> None:
    _seed_upload(env, "cut.dat", TRUNCATED_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/cut.dat", mode="structure")

    assert "error" not in payload
    assert payload["file_size"] == len(TRUNCATED_FRAMES)  # 40 full frames + 17-byte tail
    assert payload["detected"] is True
    sync = _candidate(payload, "1a cf fc 1d")
    assert sync is not None
    # 40 full frames plus the visible sync word of the cut 41st frame — the
    # tail is counted honestly (a partial frame is never fabricated: gap
    # regularity and the frame-length inference stay untouched by it).
    assert sync["occurrences"] == 41
    assert sync["dominant_gap_bytes"] == 32
    assert sync["gap_regular"] is True
    assert sync["inferred_frame_bytes"] == 32
    assert payload["inferred_frame_bytes"] == 32


@pytest.mark.asyncio
async def test_structure_mode_is_deterministic_across_calls(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    runtime = _runtime(env)

    first = await tool_module.read_dat_tool.coroutine(runtime=runtime, file_path="/mnt/user-data/uploads/frames.dat", mode="structure")
    second = await tool_module.read_dat_tool.coroutine(runtime=runtime, file_path="/mnt/user-data/uploads/frames.dat", mode="structure")

    assert first == second


@pytest.mark.asyncio
async def test_structure_caps_are_enforced_and_marked_in_payload(env, monkeypatch) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    monkeypatch.setattr(tool_module, "_STRUCTURE_MAX_CANDIDATES", 2)
    monkeypatch.setattr(tool_module, "_STRUCTURE_MAX_GAP_SAMPLES", 4)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", mode="structure")

    assert len(payload["candidates"]) == 2
    assert payload["candidates_truncated"] is True
    for candidate in payload["candidates"]:
        assert candidate["gap_samples"] <= 4
    # Detection is a property of the file, not of the display cap: the sync
    # structure stays reported even when the candidate list itself is capped.
    assert payload["detected"] is True
    assert payload["inferred_frame_bytes"] == 32


@pytest.mark.asyncio
async def test_unknown_mode_is_rejected_with_invalid_mode(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", mode="parse")

    assert payload["reason_code"] == "invalid_mode"
    assert payload["allowed_pattern"] == "/mnt/user-data/uploads/<file>"


@pytest.mark.asyncio
async def test_explicit_view_mode_matches_default_output(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    runtime = _runtime(env)

    default_raw = await tool_module.read_dat_tool.coroutine(runtime=runtime, file_path="/mnt/user-data/uploads/frames.dat", length=32)
    explicit_raw = await tool_module.read_dat_tool.coroutine(runtime=runtime, file_path="/mnt/user-data/uploads/frames.dat", length=32, mode="view")

    assert explicit_raw == default_raw


@pytest.mark.asyncio
async def test_structure_mode_leaves_source_file_unchanged(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    target = env.paths.sandbox_uploads_dir("thread-1", user_id="owner-1") / "frames.dat"
    before = (target.stat().st_size, target.stat().st_mtime_ns, hashlib.sha256(target.read_bytes()).hexdigest())

    await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", mode="structure")

    after = (target.stat().st_size, target.stat().st_mtime_ns, hashlib.sha256(target.read_bytes()).hexdigest())
    assert after == before


@pytest.mark.asyncio
async def test_structure_mode_enforces_the_same_uploads_fence(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/workspace/frames.dat", mode="structure")

    assert payload["reason_code"] == "path_out_of_bounds"
    assert payload["allowed_pattern"] == "/mnt/user-data/uploads/<file>"


@pytest.mark.asyncio
async def test_internal_symlink_is_rejected_without_following(env) -> None:
    """打开与校验必须是同一动作：围栏内指向围栏内的符号链接也按 O_NOFOLLOW 拒绝。"""
    _seed_upload(env, "real.dat", NORMAL_FRAMES)
    uploads = env.paths.sandbox_uploads_dir("thread-1", user_id="owner-1")
    os.symlink(uploads / "real.dat", uploads / "alias.dat")

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/alias.dat")

    assert payload["reason_code"] == "not_regular_file"


@pytest.mark.asyncio
async def test_fifo_is_rejected_without_blocking(env) -> None:
    """O_NONBLOCK 让无写端 FIFO 的 open 立即返回：由 S_ISREG 拒绝而不是挂起工作线程。"""
    _seed_upload(env, "real.dat", NORMAL_FRAMES)
    uploads = env.paths.sandbox_uploads_dir("thread-1", user_id="owner-1")
    os.mkfifo(uploads / "hang.dat")

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/hang.dat")

    assert payload["reason_code"] == "not_regular_file"


@pytest.mark.asyncio
async def test_nul_byte_in_declared_path_is_structurally_rejected(env) -> None:
    _seed_upload(env, "telemetry.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/telemetry\u0000.dat")

    assert payload["reason_code"] == "path_unresolvable"
    assert "error" in payload


@pytest.mark.asyncio
async def test_unreadable_file_is_structurally_rejected(env) -> None:
    _seed_upload(env, "secret.dat", NORMAL_FRAMES)
    target = env.paths.sandbox_uploads_dir("thread-1", user_id="owner-1") / "secret.dat"
    target.chmod(0o000)
    try:
        payload = await _call(_runtime(env), "/mnt/user-data/uploads/secret.dat")
    finally:
        target.chmod(0o644)

    assert payload["reason_code"] == "unreadable"


@pytest.mark.asyncio
async def test_structure_counts_do_not_double_count_at_chunk_boundaries(env, monkeypatch) -> None:
    """分块边界上的 n-gram 必须恰好统计一次（发送侧跳过尾部 carry 区起点）。"""
    _seed_upload(env, "telemetry.dat", NORMAL_FRAMES)
    monkeypatch.setattr(tool_module, "_STRUCTURE_CHUNK_BYTES", 16)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/telemetry.dat", mode="structure")

    triple = next(c for c in payload["candidates"] if c["pattern_hex"] == "00 00 00")
    reference = sum(1 for i in range(len(NORMAL_FRAMES) - 2) if NORMAL_FRAMES[i : i + 3] == b"\x00\x00\x00")
    assert triple["occurrences"] == reference
