"""S3 seam: the ``parse_dat`` frame decoder over uploaded telemetry ``.dat`` files.

Ticket 75: the model translates the Telemetry Format Document into a Frame
Layout Spec (closed-vocabulary declarative JSON: sync word, frame length —
fixed or length-field derived —, fields with linear scaling, checksum
algorithm enum) and the tool deterministically decodes a requested frame
window.  Layout problems (JSON errors, vocabulary-external declarations,
out-of-bounds offsets) are rejected with ``reason_code=invalid_layout``
naming the JSON position *before* any byte is decoded — never half results.
Bad frames are annotated per frame (``checksum_failed`` / ``truncated``) and
counted without interrupting good frames; field/channel subsetting keeps the
context cost bounded; the receipt echoes the exact layout string the model
passed (audit).  Fence and reason codes are the shared ``read_dat``
behavior; the tool is read-only and never executes file content.

Everything here drives the tool coroutine directly (the builtin-tool test
convention) against seeded uploads on a temporary filesystem home plus the
committed synthetic samples under ``backend/tests/fixtures/telemetry/``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agentplatform.tools import dat_access
from app.agentplatform.tools import parse_dat_tool as tool_module
from deerflow.config.paths import Paths

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "telemetry"
NORMAL_FRAMES = (FIXTURES_DIR / "normal_frames.dat").read_bytes()
CORRUPTED_FRAMES = (FIXTURES_DIR / "corrupted_frames.dat").read_bytes()
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


async def _call_raw(runtime, file_path: str, layout: str, **kwargs) -> str:
    return await tool_module.parse_dat_tool.coroutine(runtime=runtime, file_path=file_path, layout=layout, **kwargs)


async def _call(runtime, file_path: str, layout: str, **kwargs) -> dict:
    return json.loads(await _call_raw(runtime, file_path, layout, **kwargs))


LAYOUT_EXACT = json.dumps(
    {
        "sync_word": "1ACFFC1D",
        "frame": {"size": 32},
        "fields": [
            {"name": "frame_counter", "offset": 4, "type": "u32", "endian": "big"},
            {"name": "ch0", "offset": 8, "type": "u16", "endian": "big", "scale": 0.1},
            {"name": "ch1", "offset": 10, "type": "u16", "endian": "big", "scale": 0.1},
        ],
        "checksum": {"algorithm": "sum16", "offset": 24, "endian": "big", "coverage": {"start": 4, "end": 24}},
    }
)


def _layout(**overrides) -> str:
    doc = json.loads(LAYOUT_EXACT)
    doc.update(overrides)
    return json.dumps(doc, ensure_ascii=False)


# --- 解码主路径（AC1）：合法布局 + 区间 → 分页帧表，类型/字节序/缩放换算 --


@pytest.mark.asyncio
async def test_decodes_fixture_frames_with_scale_and_paging_window(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT)

    assert "error" not in payload
    assert payload["path"] == "/mnt/user-data/uploads/frames.dat"
    assert payload["file_size"] == len(NORMAL_FRAMES)
    assert payload["total_frames_scanned"] == 64
    assert payload["scan_truncated"] is False
    assert payload["skipped_bytes"] == 0
    assert payload["frame_window"] == {"start": 0, "requested_count": 25, "count": 25, "returned": 25}
    assert payload["next_start_frame"] == 25
    assert payload["frames_truncated"] is False
    first = payload["frames"][0]
    assert first["index"] == 0
    assert first["offset"] == 0
    assert first["status"] == "ok"
    # u32 大端帧计数 + u16 大端通道 × 线性缩放（937 × 0.1 = 93.7 精确可复核）。
    assert first["values"] == {"frame_counter": 0, "ch0": 0.0, "ch1": 93.7}
    assert payload["frames"][1]["values"] == {"frame_counter": 1, "ch0": 7 * 0.1, "ch1": 944 * 0.1}
    assert payload["status_counts"] == {"ok": 64, "checksum_failed": 0, "truncated": 0}
    assert payload["summary"]


@pytest.mark.asyncio
async def test_paging_reaches_the_last_frame_and_reports_no_next_window(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT, start_frame=60, frame_count=25)

    assert [frame["index"] for frame in payload["frames"]] == [60, 61, 62, 63]
    assert payload["frame_window"]["returned"] == 4
    assert payload["next_start_frame"] is None
    assert payload["frames"][-1]["values"]["frame_counter"] == 63


@pytest.mark.asyncio
async def test_scale_multiplies_raw_value_exactly(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    layout = _layout(
        fields=[
            {"name": "frame_counter", "offset": 4, "type": "u32", "endian": "big", "scale": 2},
            {"name": "ch1_half", "offset": 10, "type": "u16", "endian": "big", "scale": 0.5},
        ]
    )

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", layout, frame_count=1)

    # raw=937，scale=0.5 → 468.5；scale=2（整数）保持精确整数 0×2=0。
    assert payload["frames"][0]["values"] == {"frame_counter": 0, "ch1_half": 937 * 0.5}


# --- 坏帧语义（AC3）：逐帧标注、计数、不中断 --------------------------------


@pytest.mark.asyncio
async def test_corrupted_stream_annotates_bad_frames_and_counts_without_stopping(env) -> None:
    # 固定样例的实际字节（generate.py 确定性生成）：第 17 帧通道字节翻转未
    # 更新校验和 → checksum_failed；第 20 帧同步字被毁 → 整帧 32 字节成为
    # 同步间隙（skipped_bytes=32）；第 5/40 帧只翻转了填充字节，校验和仍然
    # 正确（generate.py 的注释与字节不符，测试以真实字节为准）。
    _seed_upload(env, "corrupted.dat", CORRUPTED_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/corrupted.dat", LAYOUT_EXACT, frame_count=100)

    assert "error" not in payload
    assert payload["total_frames_scanned"] == 63
    assert payload["skipped_bytes"] == 32
    statuses = {frame["index"]: frame["status"] for frame in payload["frames"]}
    assert statuses[17] == "checksum_failed"
    assert set(statuses) - {17} == set(range(63)) - {17}
    # 坏帧照常解出字段值（标注可疑而非丢弃），好帧在其前后不中断。
    assert payload["frames"][17]["values"]["frame_counter"] == 17
    assert payload["frames"][16]["status"] == "ok"
    assert payload["frames"][18]["status"] == "ok"
    # 被毁同步字之后的帧序号连续前移：序号 20 对应文件第 21 帧。
    assert payload["frames"][20]["values"]["frame_counter"] == 21
    assert payload["status_counts"] == {"ok": 62, "checksum_failed": 1, "truncated": 0}


@pytest.mark.asyncio
async def test_truncated_tail_frame_is_marked_with_empty_values(env) -> None:
    _seed_upload(env, "cut.dat", TRUNCATED_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/cut.dat", LAYOUT_EXACT, frame_count=100)

    assert "error" not in payload
    assert payload["total_frames_scanned"] == 41
    assert payload["file_size"] == len(TRUNCATED_FRAMES)
    assert payload["frames"][-1]["index"] == 40
    assert payload["frames"][-1]["status"] == "truncated"
    assert payload["frames"][-1]["values"] == {}
    assert payload["frames"][39]["status"] == "ok"
    assert payload["status_counts"] == {"ok": 40, "checksum_failed": 0, "truncated": 1}
    assert payload["skipped_bytes"] == 0


@pytest.mark.asyncio
async def test_no_sync_file_reports_zero_frames_and_skipped_bytes_honestly(env) -> None:
    _seed_upload(env, "noise.dat", NO_SYNC_ENTROPY)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/noise.dat", LAYOUT_EXACT)

    assert "error" not in payload
    assert payload["frames"] == []
    assert payload["total_frames_scanned"] == 0
    assert payload["skipped_bytes"] == len(NO_SYNC_ENTROPY)
    assert payload["status_counts"] == {"ok": 0, "checksum_failed": 0, "truncated": 0}


# --- 长度字段派生帧长：定长之外的合法词汇 ------------------------------------


def _derived_stream() -> bytes:
    frames = []
    for seq in range(3):
        body = seq.to_bytes(2, "big") + b"\x00\x00"
        frames.append(b"\xaa\x55" + (2 + len(body)).to_bytes(2, "little") + body)
    return b"".join(frames) + b"\xaa\x55" + (6).to_bytes(2, "little") + b"\x05"


@pytest.mark.asyncio
async def test_length_field_derived_frames_decode_and_tail_is_truncated(env) -> None:
    stream = _derived_stream()
    _seed_upload(env, "derived.dat", stream)
    layout = json.dumps(
        {
            "sync_word": "AA55",
            "frame": {
                "size_field": {
                    "offset": 0,
                    "type": "u16",
                    "endian": "little",
                    "offset_from": "after_sync",
                    "includes": "payload_only",
                    "adjustment": 0,
                }
            },
            "fields": [{"name": "seq", "offset": 4, "type": "u16", "endian": "big"}],
        }
    )

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/derived.dat", layout, frame_count=10)

    assert "error" not in payload
    assert payload["total_frames_scanned"] == 4
    assert [frame["values"]["seq"] for frame in payload["frames"][:3]] == [0, 1, 2]
    assert payload["frames"][3]["status"] == "truncated"
    assert payload["frames"][3]["values"] == {}
    assert payload["status_counts"] == {"ok": 3, "checksum_failed": 0, "truncated": 1}


# --- 布局校验（AC2）：词汇表外/非法值 → invalid_layout 指明位置，无半成品 ----


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("layout", "fragment"),
    [
        ('{"sync_word": "1ACF", "frame": {"size": 8}, "fields": [', "JSON"),  # 非法 JSON
        ("[]", "顶层"),  # 顶层不是对象
        ('{"sync_word": "1ACF", "frame": {"size": 8}, "fields": [{"name": "a", "offset": 0, "type": "u8", "endian": "big"}], "extra": 1}', "extra"),  # 词汇表外的顶层键
        ('{"fields": [{"name": "a", "offset": 0, "type": "u8", "endian": "big"}]}', "layout.frame"),  # 缺帧长声明
        (_layout(fields=[{"name": "a", "offset": 0, "type": "float64", "endian": "big"}]), "fields[0].type"),
        (_layout(checksum={"algorithm": "crc32", "offset": 24, "endian": "big", "coverage": {"start": 4, "end": 24}}), "checksum.algorithm"),
        (_layout(fields=[{"name": "a", "offset": 40, "type": "u16", "endian": "big"}]), "fields[0].offset"),
        ('{"sync_word": "1ACF", "frame": {"size": 0}, "fields": [{"name": "a", "offset": 0, "type": "u8", "endian": "big"}]}', "frame.size"),
        ('{"sync_word": "1ACF", "frame": {"size": 70000}, "fields": [{"name": "a", "offset": 0, "type": "u8", "endian": "big"}]}', "frame.size"),
        (_layout(fields=[{"name": "a", "offset": 0, "type": "u8", "endian": " sideways"}]), "fields[0].endian"),
    ],
)
async def test_invalid_layouts_are_rejected_with_position_and_no_frames(env, layout: str, fragment: str) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", layout)

    assert payload["reason_code"] == "invalid_layout"
    assert fragment in payload["error"]
    assert "frames" not in payload  # 绝不产出半成品结果
    assert payload["layout"] == layout  # 回执原样保存模型的布局输入（审计）


@pytest.mark.asyncio
async def test_fields_filter_with_unknown_name_is_invalid_layout(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT, fields_filter="ch0,unknown_ch")

    assert payload["reason_code"] == "invalid_layout"
    assert "unknown_ch" in payload["error"]
    assert "frames" not in payload


# --- 字段子集筛选（AC4）：未选字段不进返回 ----------------------------------


@pytest.mark.asyncio
async def test_fields_filter_returns_only_selected_fields(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT, fields_filter="ch0")

    assert payload["frames"][0]["values"].keys() == {"ch0"}
    assert payload["frames"][0]["values"]["ch0"] == 0.0
    assert payload["frames"][1]["values"]["ch0"] == 7 * 0.1
    # 筛选只影响返回视图，不改帧状态语义。
    assert payload["frames"][0]["status"] == "ok"


# --- 审计回执（AC5）：layout 原样回显 ----------------------------------------


@pytest.mark.asyncio
async def test_layout_echo_is_exact_input_string_on_success(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    layout = '{"sync_word": "1ACFFC1D",  "frame": {"size": 32}, "fields": [{"name": "frame_counter", "offset": 4, "type": "u32", "endian": "big"}]}'

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", layout)

    assert payload["layout"] == layout  # 含原样空白，非重新序列化


# --- 围栏与原因码（AC6）：与 read_dat 完全一致 -------------------------------


@pytest.mark.asyncio
async def test_fence_rejections_match_read_dat_reason_codes(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    _seed_upload(env, "notes.txt", b"plain text")

    for declared, expected in [
        ("/mnt/user-data/workspace/frames.dat", "path_out_of_bounds"),
        ("/mnt/user-data/uploads/../etc/passwd", "path_out_of_bounds"),
        ("frames.dat", "path_out_of_bounds"),
    ]:
        payload = await _call(_runtime(env), declared, LAYOUT_EXACT)
        assert payload["reason_code"] == expected, declared
        assert payload["allowed_pattern"] == "/mnt/user-data/uploads/<file>"

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/notes.txt", LAYOUT_EXACT)
    assert payload["reason_code"] == "suffix_mismatch"


@pytest.mark.asyncio
async def test_thread_context_missing_is_reported(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    runtime = _runtime(env)
    runtime.state = None

    payload = await _call(runtime, "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT)

    assert payload["reason_code"] == "thread_context_missing"


@pytest.mark.asyncio
async def test_fence_rejection_wins_over_invalid_layout(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)

    payload = await _call(_runtime(env), "/mnt/user-data/workspace/frames.dat", "{not json")

    assert payload["reason_code"] == "path_out_of_bounds"


@pytest.mark.asyncio
async def test_negative_frame_window_is_invalid_paging(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)

    for kwargs in ({"start_frame": -1}, {"frame_count": -3}):
        payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT, **kwargs)
        assert payload["reason_code"] == "invalid_paging", kwargs


# --- 只读（AC6）与确定性 ------------------------------------------------------


@pytest.mark.asyncio
async def test_calls_leave_source_file_unchanged(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    target = env.paths.sandbox_uploads_dir("thread-1", user_id="owner-1") / "frames.dat"
    before = (target.stat().st_size, target.stat().st_mtime_ns, hashlib.sha256(target.read_bytes()).hexdigest())

    await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT, frame_count=100)
    await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", "{not json")
    await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT, start_frame=-1)

    after = (target.stat().st_size, target.stat().st_mtime_ns, hashlib.sha256(target.read_bytes()).hexdigest())
    assert after == before


@pytest.mark.asyncio
async def test_same_layout_and_file_produce_byte_identical_output(env) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    runtime = _runtime(env)

    first = await _call_raw(runtime, "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT)
    second = await _call_raw(runtime, "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT)

    assert first == second


# --- 上限即代码常量：分页上限与扫描上限 --------------------------------------


def test_caps_are_binding_code_constants() -> None:
    assert tool_module.DAT_PARSE_MAX_FRAMES == 100
    assert tool_module.DAT_PARSE_SCAN_MAX_FRAMES == 100_000
    assert tool_module.DEFAULT_FRAME_COUNT == 25


@pytest.mark.asyncio
async def test_frame_count_over_cap_truncates_with_visible_flag(env, monkeypatch) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    monkeypatch.setattr(tool_module, "DAT_PARSE_MAX_FRAMES", 2)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT, frame_count=10)

    assert len(payload["frames"]) == 2
    assert payload["frames_truncated"] is True
    assert payload["frame_window"]["returned"] == 2
    assert payload["next_start_frame"] == 2


@pytest.mark.asyncio
async def test_scan_cap_stops_the_scan_with_visible_flags(env, monkeypatch) -> None:
    _seed_upload(env, "frames.dat", NORMAL_FRAMES)
    monkeypatch.setattr(tool_module, "DAT_PARSE_SCAN_MAX_FRAMES", 3)

    payload = await _call(_runtime(env), "/mnt/user-data/uploads/frames.dat", LAYOUT_EXACT, frame_count=100)

    assert payload["total_frames_scanned"] == 3
    assert payload["scan_truncated"] is True
    assert payload["scanned_bytes"] == 96  # 3 × 32 字节帧
    assert payload["status_counts"] == {"ok": 3, "checksum_failed": 0, "truncated": 0}
    assert "未完整扫描" in payload["summary"]


# --- 围栏共享实现冒烟：dat_access 复用（不重复实现） -------------------------


@pytest.mark.asyncio
async def test_rejections_carry_the_shared_allowed_pattern(env) -> None:
    payload = await _call(_runtime(env), "/mnt/user-data/uploads/missing.dat", LAYOUT_EXACT)

    assert payload["reason_code"] == "file_not_found"
    assert payload["allowed_pattern"] == dat_access.UPLOADS_DAT_FILE_PATTERN
