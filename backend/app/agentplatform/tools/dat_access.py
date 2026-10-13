"""Shared thread-input access constraint for telemetry ``.dat`` tools.

``read_dat`` (ticket 73) and the later frame tools (#74/#75/#76) accept
nothing but ``.dat`` files in this thread's input area under the virtual
root ``/mnt/user-data/uploads/`` — the same fence target as
``start_zeroing_run``'s ``upload_paths``.  The declared virtual path is
resolved through the thread's own ``thread_data`` mapping, then the resolved
host path must still sit inside the canonical thread uploads dir (defense
in depth: a tampered mapping cannot widen the fence).  The model never sees
a host path and can never point the tools elsewhere.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.agentplatform.tools.code_evidence_access import get_thread_id
from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.sandbox.tools import get_thread_data, replace_virtual_path
from deerflow.tools.types import Runtime

DAT_SUFFIX = ".dat"
# Audit semantics: the telemetry size/page caps are code constants, never
# config entries — runtime reconfiguration must not be able to widen them.
DAT_MAX_FILE_BYTES = 512 * 1024 * 1024
UPLOADS_VIRTUAL_ROOT = f"{VIRTUAL_PATH_PREFIX}/uploads"
UPLOADS_DAT_FILE_PATTERN = f"{UPLOADS_VIRTUAL_ROOT}/<file>"


class DatAccessRejected(ValueError):
    """The declared telemetry input is outside the fence or unreadable."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def resolve_uploads_dat_file(runtime: Runtime, declared: str) -> Path:
    """Resolve a fenced ``/mnt/user-data/uploads/...`` ``.dat`` to its host path.

    Check chain (each failure raises :class:`DatAccessRejected` with its own
    reason code): thread context → fence shape → virtual resolution +
    containment inside the canonical thread uploads dir → existence →
    ``.dat`` suffix (case-insensitive) → per-file size cap.
    """

    thread_id = get_thread_id(runtime)
    if not thread_id:
        raise DatAccessRejected("thread_context_missing", "当前会话缺少 thread 上下文，无法读取输入区遥测文件")
    normalized = (declared or "").strip()
    prefix = f"{UPLOADS_VIRTUAL_ROOT}/"
    if not normalized.startswith(prefix):
        raise DatAccessRejected(
            "path_out_of_bounds",
            f"遥测 .dat 读取只接受本会话输入区路径 {UPLOADS_DAT_FILE_PATTERN}，收到: {normalized or '<空>'}",
        )
    relative_str = normalized[len(prefix) :]
    relative = PurePosixPath(relative_str)
    if not relative_str or relative_str.endswith("/") or relative.is_absolute() or ".." in relative.parts:
        raise DatAccessRejected("path_out_of_bounds", f"上传路径不合法，必须是输入区内的 .dat 文件: {normalized}")
    thread_data = get_thread_data(runtime) or {}
    if not thread_data.get("uploads_path"):
        raise DatAccessRejected("thread_context_missing", "当前会话缺少输入区（uploads）映射，无法读取 .dat 遥测文件")

    resolved = Path(replace_virtual_path(normalized, thread_data))
    uploads_root = get_paths().sandbox_uploads_dir(thread_id, user_id=resolve_runtime_user_id(runtime)).resolve()
    target = resolved.resolve()
    if not target.is_relative_to(uploads_root):
        raise DatAccessRejected("path_out_of_bounds", f"路径越出本会话输入区（uploads）边界: {normalized}")
    if not target.is_file():
        raise DatAccessRejected("file_not_found", f"输入区不存在该文件: {relative_str}")
    if target.suffix.lower() != DAT_SUFFIX:
        suffix = target.suffix.lower() or "<无后缀>"
        raise DatAccessRejected("suffix_mismatch", f"{relative_str} 的后缀 {suffix} 不是 .dat；遥测裸读仅接受 .dat 文件")
    if target.stat().st_size > DAT_MAX_FILE_BYTES:
        raise DatAccessRejected(
            "file_too_large",
            f".dat 遥测文件超过单文件上限 {DAT_MAX_FILE_BYTES} 字节: {relative_str}",
        )
    return target
