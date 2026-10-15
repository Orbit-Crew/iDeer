"""Read-only hex viewer and structure probe for uploaded telemetry ``.dat`` files.

``read_dat`` is the model's first telemetry reading capability: a raw,
byte-accurate look at the ``.dat`` files users drop into this thread's
input area.  It accepts nothing but a fenced upload path under
``/mnt/user-data/uploads/`` (virtual-path resolution and the reason-code
rejections live in :mod:`app.agentplatform.tools.dat_access`, shared with
the later frame tools).  ``mode="view"`` (default) renders a fixed
three-column view — offset, hex bytes, printable ASCII (xxd-style) — and
pages through ``offset``/``length``.  ``mode="structure"`` runs a pure
deterministic structure probe: candidate sync-word n-grams, their gap
regularity, and an inferred frame length, capped and flagged.  The per-call
output caps keep a single response bounded: real telemetry files are
~100 MB and must never be pulled into context wholesale.  The tool is
strictly read-only and never executes file content.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import BinaryIO

from langchain.tools import tool

from app.agentplatform.tools import dat_access
from deerflow.tools.types import Runtime

DEFAULT_VIEW_BYTES = 4096
# Audit semantics: the telemetry page cap is a code constant, never a config
# entry — runtime reconfiguration must not be able to widen it.
DAT_VIEW_MAX_BYTES = 4096
_VIEW_WIDTH = 16

# --- 结构摸底（ticket 74）：纯确定性统计，不含任何语义判断 --------------
#
# 全部上限都是代码常量而非配置项（审计语义不能被运行时改口）；探测只读、
# 分块流式进行，绝不把整文件载入内存，也绝不执行文件内容。相同文件字节
# 必然得到相同结果（无随机数、无时钟、无依赖字典序的输出）。

# 流式分块大小：1 MiB 把内存峰值压在“一块窗口 + 小计数表”量级，
# 百 MB 文件也只需约百次读取。
_STRUCTURE_CHUNK_BYTES = 1024 * 1024
# 探测窗口：只扫描文件前 8 MiB（审计抽样而非全量盘点；8 MiB 足以容纳
# 25 万个 32 字节帧，辨认主导重复结构绰绰有余）。更大文件用
# scan_truncated 明示“只看了前缀”，绝不假装做过全量统计。
_STRUCTURE_MAX_SCAN_BYTES = 8 * 1024 * 1024
# 候选同步字宽度：2/3/4 字节（常见遥测同步字宽度；样例布局为 4 字节）。
_STRUCTURE_NGRAM_LENGTHS = (2, 3, 4)
# 出现少于 3 次的字节模式视为噪声，不进入候选。
_STRUCTURE_MIN_OCCURRENCES = 3
# 3/4 字节候选通过“前 2 字节 ∈ 高频 2 字芽种子”限量追踪：重复 n-gram
# 的前 2 字节必然也是重复 2-gram，故种子覆盖不会漏掉高频结构。64 个种子
# × 256 个尾字节 = 每宽度至多 16384 个键，内存有界。种子按出现次数取前
# 64（并列按字节序），确定性可复核。
_STRUCTURE_MAX_NGRAM_SEEDS = 64
# 进入间隔分析的候选池：每个宽度按出现次数留 24 个（并列按字节序），
# 让“次数稍低但间隔极稳”的模式仍有机会进入最终展示。
_STRUCTURE_RANKING_POOL_PER_LENGTH = 24
# 返回给模型的候选上限：控制上下文体积（整体负载若干 KB 量级）。
_STRUCTURE_MAX_CANDIDATES = 8
# 每个候选最多用前 16 个间隔估计规律性（即 17 个出现位置）；occurrences
# 始终是精确总数，间隔证据是否截断用 gaps_capped 明示，绝不返回原始
# 间隔列表。
_STRUCTURE_MAX_GAP_SAMPLES = 16
# 判定“疑似同步字”的最低证据：至少 4 个已采样间隔（3 次出现只有 2 个
# 间隔，碰巧相等太容易），且 ≥80% 的采样间隔等于主间隔。低于该证据的
# 文件如实返回“未检出”，不编造帧长。
_STRUCTURE_SYNC_MIN_GAP_SAMPLES = 4
_STRUCTURE_SYNC_REGULARITY = 0.8


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


def _iter_scan_windows(handle: BinaryIO, scan_budget: int, overlap: int):
    """流式产出 ``(window, window_start, is_final)``，覆盖文件前 ``scan_budget`` 字节。

    window = 上一块尾部 ``overlap`` 字节 + 新读的块；调用方统计窗口内所有
    “完整装得下”的 n-gram 起点，则跨块边界的 n-gram 恰好在一个窗口内被
    统计一次（尾部 overlap 字节里的出现留给下一个窗口的头部，绝不重复）。
    从调用方持有的已验证句柄读取，定位由调用方 ``seek(0)`` 控制。

    “绝不重复/不漏计”的前提是 ``scan_budget`` 来自同一 fstat 快照（恒等
    于实际可读字节数）：最后一个窗口 ``scanned >= scan_budget`` 必为
    final，不存在被跳过却无人重放的尾部 carry。读取中途文件被并发截断
    属于工具契约之外（内容本身已不确定），不为此补发重放窗口。
    """

    scanned = 0
    carry = b""
    while scanned < scan_budget:
        request = min(_STRUCTURE_CHUNK_BYTES, scan_budget - scanned)
        chunk = handle.read(request)
        if not chunk:
            break
        window = carry + chunk
        window_start = scanned - len(carry)
        scanned += len(chunk)
        is_final = len(chunk) < request or scanned >= scan_budget
        yield window, window_start, is_final
        carry = window[-overlap:] if len(window) > overlap else window


def _count_ngrams(handle: BinaryIO, scan_budget: int, length: int) -> Counter:
    """窗口内全量统计 ``length`` 字节 n-gram 出现次数（2 字芽宽度内存有界）。"""

    counts: Counter = Counter()
    handle.seek(0)
    for window, _start, _final in _iter_scan_windows(handle, scan_budget, length - 1):
        for index in range(len(window) - length + 1):
            counts[window[index : index + length]] += 1
    return counts


def _count_seeded_ngrams(handle: BinaryIO, scan_budget: int, seeds: list[bytes], lengths: tuple[int, ...]) -> dict[int, dict[bytes, int]]:
    """只统计“前 2 字节是高频种子”的 3/4 字节 n-gram，键空间有界。"""

    counts: dict[int, dict[bytes, int]] = {length: {} for length in lengths}
    if not seeds:
        return counts
    seed_set = set(seeds)
    widest = max(lengths)
    overlap = widest - 1
    handle.seek(0)
    for window, _start, is_final in _iter_scan_windows(handle, scan_budget, overlap):
        # 发送侧防重：3 字节模式恰好能完整落进尾部 carry（overlap=3），
        # 若不跳过会在上一窗口与下一窗口头部各计一次；非最终窗口只统计
        # 起点位于 carry 区（最后 overlap 个起点）之前的出现，carry 区内
        # 的出现留给下一窗口唯一计数（4 字节模式装不进 3 字节 carry，
        # 不受影响）。carry 对应本窗口起点 len-overlap..len-1，其余起点
        # （含紧贴 carry 前的那个）都归本窗口。
        limit = len(window) if is_final else len(window) - overlap
        for index in range(min(limit, len(window) - 1)):
            if window[index : index + 2] not in seed_set:
                continue
            for length in lengths:
                end = index + length
                if end <= len(window):
                    key = window[index:end]
                    bucket = counts[length]
                    bucket[key] = bucket.get(key, 0) + 1
    return counts


def _top_patterns(counts: dict[bytes, int] | Counter, limit: int) -> list[bytes]:
    """达到最低出现次数的 n-gram，按（次数降序、字节升序）取前 ``limit`` 个。"""

    qualified = sorted(
        ((count, pattern) for pattern, count in counts.items() if count >= _STRUCTURE_MIN_OCCURRENCES),
        key=lambda item: (-item[0], item[1]),
    )
    return [pattern for _count, pattern in qualified[:limit]]


def _record_first_positions(handle: BinaryIO, scan_budget: int, patterns: list[bytes], need: int) -> dict[bytes, list[int]]:
    """记录每个模式在探测窗口内的前 ``need`` 个出现位置（字节级 find，限量）。"""

    overlap = max(_STRUCTURE_NGRAM_LENGTHS) - 1
    positions: dict[bytes, list[int]] = {pattern: [] for pattern in patterns}
    handle.seek(0)
    for window, window_start, is_final in _iter_scan_windows(handle, scan_budget, overlap):
        limit = len(window) if is_final else len(window) - overlap
        for pattern, seen in positions.items():
            if len(seen) >= need:
                continue
            index = window.find(pattern)
            while index != -1 and index < limit and len(seen) < need:
                seen.append(window_start + index)
                index = window.find(pattern, index + 1)
    return positions


def analyze_dat_structure(handle: BinaryIO, file_size: int) -> dict:
    """对 ``.dat`` 文件做纯确定性结构摸底（只读、分块流式、输出限量）。

    ``handle`` 是围栏打开的已验证句柄，本函数只在其中 ``seek(0)`` 后顺序
    读。三趟有界扫描：① 全量统计 2 字芽（键空间 ≤ 65536）；② 以高频
    2 字芽为种子限量统计 3/4 字节候选；③ 为每宽度前 24 个候选记录前 17 个
    出现位置，计算主间隔与规律性。返回 dict 只含统计事实；候选按（出现次
    数、模式宽度、间隔规律性、字节序）排序后截到 ``_STRUCTURE_MAX_CANDIDATES``，
    截断均以标志明示。
    """

    scan_budget = min(file_size, _STRUCTURE_MAX_SCAN_BYTES)

    counts2 = _count_ngrams(handle, scan_budget, 2)
    seeds = _top_patterns(counts2, _STRUCTURE_MAX_NGRAM_SEEDS)
    seeded_counts = _count_seeded_ngrams(handle, scan_budget, seeds, (3, 4))

    pools = {
        2: _top_patterns(counts2, _STRUCTURE_RANKING_POOL_PER_LENGTH),
        3: _top_patterns(seeded_counts[3], _STRUCTURE_RANKING_POOL_PER_LENGTH),
        4: _top_patterns(seeded_counts[4], _STRUCTURE_RANKING_POOL_PER_LENGTH),
    }
    occurrences: dict[int, dict[bytes, int] | Counter] = {2: counts2, 3: seeded_counts[3], 4: seeded_counts[4]}
    pooled = [pattern for length in sorted(pools) for pattern in pools[length]]
    positions = _record_first_positions(handle, scan_budget, pooled, _STRUCTURE_MAX_GAP_SAMPLES + 1)

    ranked: list[dict] = []
    for pattern in pooled:
        total = occurrences[len(pattern)][pattern]
        seen = positions[pattern]
        gaps = [later - earlier for earlier, later in zip(seen, seen[1:])]
        gap_counts = Counter(gaps)
        if gaps:
            dominant = min(gap_counts, key=lambda gap: (-gap_counts[gap], gap))
            regularity = gap_counts[dominant] / len(gaps)
        else:
            dominant, regularity = None, 0.0
        sync_like = (
            dominant is not None
            # 非重叠重复才是记录边界的迹象：主间隔小于模式自身宽度说明只是
            # 连续自跑（如填充零字节 00 00 的间隔 1），不是周期结构。
            and dominant >= len(pattern)
            and len(gaps) >= _STRUCTURE_SYNC_MIN_GAP_SAMPLES
            and regularity >= _STRUCTURE_SYNC_REGULARITY
        )
        ranked.append(
            {
                "pattern": pattern,
                "pattern_length": len(pattern),
                "occurrences": total,
                "dominant_gap_bytes": dominant,
                "gap_regularity": round(regularity, 4),
                "gap_regular": bool(gaps) and regularity == 1.0,
                "gap_samples": len(gaps),
                "gaps_capped": total - 1 > len(gaps),
                "sync_like": sync_like,
            }
        )
    # 展示排序：出现次数优先；次数相同偏好更长的模式（更长的匹配蕴含更短
    # 模式的匹配，信息量严格更大，完整同步字借此压过它的位移碎片），再按
    # 间隔规律性与字节序，全部并列维度确定性可复核。
    ranked.sort(
        key=lambda item: (
            -item["occurrences"],
            -item["pattern_length"],
            -item["gap_regularity"],
            item["pattern"],
        )
    )

    # 检测结论看全量候选池，展示截断只影响列表——文件里存在稳定结构这个
    # 事实不因展示上限而消失。
    best = next((item for item in ranked if item["sync_like"]), None)
    candidates_truncated = len(ranked) > _STRUCTURE_MAX_CANDIDATES
    candidates = [
        {
            "pattern_hex": _pattern_hex(item["pattern"]),
            "pattern_length": item["pattern_length"],
            "occurrences": item["occurrences"],
            "dominant_gap_bytes": item["dominant_gap_bytes"],
            "gap_regular": item["gap_regular"],
            "gap_regularity": item["gap_regularity"],
            "gap_samples": item["gap_samples"],
            "gaps_capped": item["gaps_capped"],
            "inferred_frame_bytes": item["dominant_gap_bytes"] if item["sync_like"] else None,
        }
        for item in ranked[:_STRUCTURE_MAX_CANDIDATES]
    ]

    summary = _structure_summary(
        scan_budget=scan_budget,
        scan_truncated=scan_budget < file_size,
        best=best,
        candidate_total=len(ranked),
        candidate_returned=len(candidates),
    )
    return {
        "file_size": file_size,
        "scanned_bytes": scan_budget,
        "scan_truncated": scan_budget < file_size,
        "detected": best is not None,
        "inferred_frame_bytes": best["dominant_gap_bytes"] if best else None,
        "candidates": candidates,
        "candidates_truncated": candidates_truncated,
        "summary": summary,
    }


def _pattern_hex(pattern: bytes) -> str:
    """模式十六进制串，逐字节小写、空格分隔（与样例 README 的 1A CF FC 1D 一致）。"""

    return pattern.hex(" ")


def _structure_summary(scan_budget: int, scan_truncated: bool, best: dict | None, candidate_total: int, candidate_returned: int) -> str:
    """为结构摸底结论生成一句中文摘要（描述统计事实，不做语义判断）。"""

    scope = f"已扫描文件前 {scan_budget} 字节"
    if scan_budget == 0:
        return "未检出：文件为空，没有可分析的字节。"
    if best is None:
        conclusion = f"未检出：{scope}，未发现出现 ≥{_STRUCTURE_MIN_OCCURRENCES} 次且间隔稳定（规律性 ≥{_STRUCTURE_SYNC_REGULARITY:.0%}）的重复字节模式，无法推断同步字与帧长。"
    else:
        conclusion = (
            f"已检出疑似同步字 {_pattern_hex(best['pattern'])}：{scope}中出现 {best['occurrences']} 次，"
            f"主间隔 {best['dominant_gap_bytes']} 字节稳定（规律性 {best['gap_regularity']}，"
            f"采样 {best['gap_samples']} 个间隔），推断帧长 {best['dominant_gap_bytes']} 字节；"
            f"候选模式共 {candidate_total} 个，已限量返回 {candidate_returned} 个。"
        )
    if scan_truncated:
        conclusion += "文件较大，本次仅扫描前缀（scan_truncated=true）。"
    return conclusion


def _read_dat_sync(runtime: Runtime, declared_path: str, offset: int, length: int, mode: str) -> str:
    if mode not in ("view", "structure"):
        return _rejection("invalid_mode", f"mode 只支持 view（十六进制视图）或 structure（结构摸底），收到: {mode!r}")
    try:
        handle, file_size = dat_access.open_uploads_dat_file(runtime, declared_path)
    except dat_access.DatAccessRejected as exc:
        return _rejection(exc.reason_code, str(exc))
    try:
        if mode == "structure":
            analysis = analyze_dat_structure(handle, file_size)
            payload = {"path": (declared_path or "").strip(), "mode": "structure", **analysis}
            return json.dumps(payload, ensure_ascii=False)

        if offset < 0 or length < 0:
            return _rejection("invalid_paging", f"offset/length 必须为非负整数，收到 offset={offset}, length={length}")
        if offset > file_size:
            return _rejection("invalid_paging", f"offset 超出文件末尾（file_size={file_size}），收到 offset={offset}")

        handle.seek(offset)
        view = handle.read(min(length, DAT_VIEW_MAX_BYTES))
    finally:
        handle.close()

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
async def read_dat_tool(runtime: Runtime, file_path: str, offset: int = 0, length: int = DEFAULT_VIEW_BYTES, mode: str = "view") -> str:
    """只读查看会话输入区内的 .dat 遥测文件：十六进制视图或结构摸底。

    遥测裸读入口（固定能力）：仅接受本会话输入区（/mnt/user-data/uploads/）
    内的 .dat 文件路径。mode=view（默认）输出类 xxd 的三列视图（偏移量 +
    十六进制 + 可打印 ASCII），默认读取前 4096 字节，用 offset/length 按
    字节偏移翻页，超过单次输出上限会被截断并提示。mode=structure 做纯确
    定性结构摸底：探测候选同步字模式、其出现间隔规律并推断帧长，统计结
    果限量返回，忽略 offset/length；未检出结构时明确返回"未检出"结论。
    围栏外路径、非 .dat 后缀、超过单文件上限的文件、未知 mode 会被结构化
    拒绝并返回原因码；本工具只读，绝不执行文件内容。

    Args:
        file_path: 输入区内的 .dat 遥测文件路径，必须是 /mnt/user-data/uploads/<file>。
        offset: 起始字节偏移量，默认 0（从头开始），超出文件末尾会被拒绝；仅 view 模式使用。
        length: 本次读取的字节数，默认 4096，超过单次输出上限会被截断并提示；仅 view 模式使用。
        mode: 输出模式：view（默认，十六进制视图）或 structure（结构摸底：
            候选同步字、间隔规律、帧长推断的确定性统计）；其他值会被拒绝。
    """
    return await asyncio.to_thread(_read_dat_sync, runtime, file_path, offset, length, mode)
