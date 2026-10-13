"""Read-only hex viewer for uploaded telemetry ``.dat`` files (ticket 73).

``read_dat`` is the model's first telemetry reading capability: a raw,
byte-accurate look at the ``.dat`` files users drop into this thread's
input area.  It accepts nothing but a fenced upload path under
``/mnt/user-data/uploads/`` (virtual-path resolution and the reason-code
rejections live in :mod:`app.agentplatform.tools.dat_access`, shared with
the later frame tools), renders a fixed three-column view — offset, hex
bytes, printable ASCII (xxd-style) — and pages through ``offset``/``length``.
The per-call output cap keeps a single response bounded: real telemetry
files are ~100 MB and must never be pulled into context wholesale.  The
tool is strictly read-only and never executes file content.
"""

from __future__ import annotations

import asyncio
import json

from langchain.tools import tool

from app.agentplatform.tools import dat_access
from deerflow.tools.types import Runtime

DEFAULT_VIEW_BYTES = 4096
# Audit semantics: the telemetry page cap is a code constant, never a config
# entry — runtime reconfiguration must not be able to widen it.
DAT_VIEW_MAX_BYTES = 4096
_VIEW_WIDTH = 16


def _format_hex_view(data: bytes, base_offset: int) -> str:
    lines: list[str] = []
    for start in range(0, len(data), _VIEW_WIDTH):
        chunk = data[start : start + _VIEW_WIDTH]
        left = " ".join(f"{byte:02x}" for byte in chunk[:8])
        right = " ".join(f"{byte:02x}" for byte in chunk[8:])
        printable = "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in chunk)
        lines.append(f"{base_offset + start:08x}  {left:<23}  {right:<23} |{printable}|")
    return "\n".join(lines)


def _rejection(reason_code: str, message: str) -> str:
    return json.dumps(
        {"error": message, "reason_code": reason_code, "allowed_pattern": dat_access.UPLOADS_DAT_FILE_PATTERN},
        ensure_ascii=False,
    )


def _next_action(truncated: bool, has_more: bool, next_offset: int) -> str:
    if truncated:
        return f"单次输出上限 {DAT_VIEW_MAX_BYTES} 字节已截断，请用 offset={next_offset} 继续翻页读取。"
    if has_more:
        return f"文件还有未读内容，可用 offset={next_offset} 继续翻页。"
    return "已读到文件末尾。十六进制视图仅供只读检查 .dat 遥测文件，不会执行文件内容。"


def _read_dat_sync(runtime: Runtime, declared_path: str, offset: int, length: int) -> str:
    try:
        target = dat_access.resolve_uploads_dat_file(runtime, declared_path)
    except dat_access.DatAccessRejected as exc:
        return _rejection(exc.reason_code, str(exc))
    file_size = target.stat().st_size
    if offset < 0 or length < 0:
        return _rejection("invalid_paging", f"offset/length 必须为非负整数，收到 offset={offset}, length={length}")
    if offset > file_size:
        return _rejection("invalid_paging", f"offset 超出文件末尾（file_size={file_size}），收到 offset={offset}")

    with target.open("rb") as handle:
        handle.seek(offset)
        view = handle.read(min(length, DAT_VIEW_MAX_BYTES))

    truncated = length > DAT_VIEW_MAX_BYTES
    has_more = offset + len(view) < file_size
    next_offset = offset + len(view)
    payload = {
        "path": (declared_path or "").strip(),
        "file_size": file_size,
        "offset": offset,
        "length": len(view),
        "max_view_bytes": DAT_VIEW_MAX_BYTES,
        "truncated": truncated,
        "has_more": has_more,
        "next_offset": next_offset,
        "hex_view": _format_hex_view(view, offset),
        "next_action": _next_action(truncated, has_more, next_offset),
    }
    return json.dumps(payload, ensure_ascii=False)


@tool("read_dat", parse_docstring=True)
async def read_dat_tool(runtime: Runtime, file_path: str, offset: int = 0, length: int = DEFAULT_VIEW_BYTES) -> str:
    """以十六进制 + ASCII 视图只读查看会话输入区内的 .dat 遥测文件。

    遥测裸读入口（固定能力）：仅接受本会话输入区（/mnt/user-data/uploads/）
    内的 .dat 文件路径，输出类 xxd 的三列视图（偏移量 + 十六进制 + 可打印
    ASCII）。默认读取前 4096 字节，用 offset/length 按字节偏移翻页；超过
    单次输出上限会被截断并提示。围栏外路径、非 .dat 后缀、超过单文件上限
    的文件会被结构化拒绝并返回原因码；本工具只读，绝不执行文件内容。

    Args:
        file_path: 输入区内的 .dat 遥测文件路径，必须是 /mnt/user-data/uploads/<file>。
        offset: 起始字节偏移量，默认 0（从头开始），超出文件末尾会被拒绝。
        length: 本次读取的字节数，默认 4096，超过单次输出上限会被截断并提示。
    """
    return await asyncio.to_thread(_read_dat_sync, runtime, file_path, offset, length)
