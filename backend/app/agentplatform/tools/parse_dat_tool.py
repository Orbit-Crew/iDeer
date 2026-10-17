"""Deterministic frame decoder for uploaded telemetry ``.dat`` files.

``parse_dat`` (ticket 75) is the model's regular telemetry decoding
capability.  The model translates the mission's Telemetry Format Document
into a *Frame Layout Spec* — a closed-vocabulary declarative JSON document —
and the tool deterministically decodes a requested frame window: it scans
for the sync word, validates checksums, applies type/endian/linear-scale
conversion, and pages the frame table.  Decoding is deterministic: the same
layout string over the same file yields byte-identical output, so every
decoded number can be re-verified against its declared layout.  The receipt
echoes the layout string exactly as the model passed it (audit: every
telemetry number traces back to the layout it was decoded with).

Frame Layout Spec grammar (closed vocabulary — any key or value outside it
is rejected with ``reason_code=invalid_layout`` naming the JSON position,
before any byte is decoded; no partial results):

    layout := {
      "sync_word": <hex string, 1..16 bytes, e.g. "1ACFFC1D"> | null
                   # null（或缺省）→ 不用同步字：定长帧从字节 0 起按网格
                   # 取帧；长度字段派生帧从字节 0 起顺序步进
      "frame": {"size": <int 1..65536>}                                # 定长
             | {"size_field": {                                        # 长度字段派生
                   "offset": <int ≥ 0>,          # 长度字段在帧内的偏移
                   "type": "u8" | "u16" | "u32",
                   "endian": "big" | "little",
                   "offset_from": "frame_start" | "after_sync",
                   "includes": "header" | "payload_only",
                       # header: 值即整帧字节数；payload_only: 值只计同步字之后的字节
                   "adjustment": <int -65535..65535>}}>                # 派生帧长 = 基值 + adjustment
      "fields": [ {"name": <非空且不含逗号的字符串>,      # 必填，名单内唯一
                   "offset": <int ≥ 0>,                  # 必填，字段须落在帧长内
                   "type": "u8"|"u16"|"u32"|"i8"|"i16"|"i32",   # 必填
                   "endian": "big" | "little",           # 必填
                   "scale": <有限数值, 缺省 1.0>} ]      # 值 = raw × scale（仅线性缩放）
                   # fields 必须是非空数组；scale 为 1（含缺省）时输出整数
      "checksum": {"algorithm": "sum16" | "sum32" | "none",   # 可整体缺省
                   "offset": <int ≥ 0>, "endian": "big" | "little",
                   "coverage": {"start": <int>, "end": <int>}}
                   # 字节区间 [start, end) 求和 mod 2^16/2^32（end 排他）；
                   # "none" 跳过校验（此时其余键可省略）
    }

派生帧长与定长共用同一 65536 字节帧长上限；字段/校验声明的静态越界按"派生
帧长上界"校验（定长即帧长）。解码期若某实际帧容纳不下任何已声明字段或校验
声明，该帧标注为 truncated（帧状态与 fields_filter 无关）。帧扫描有代码常
量上限（``DAT_PARSE_SCAN_MAX_FRAMES``）：更大文件以 ``scan_truncated`` 明示
"未完整扫描"，绝不假装做过全量。路径围栏与拒绝原因码与 ``read_dat`` 完全
一致（:mod:`app.agentplatform.tools.dat_access`）。工具只读、绝不执行文件
内容，全部实现仅用标准库。

整文件扫描模式（``mode="scan"``，ticket 76）：全量解码在服务端一次完成，
只返回聚合——总帧数、各状态计数、限量坏帧位置列表（附"还有更多"标志）、
各字段 min/max/mean（缩放后工程值，均值按 ``DAT_SCAN_MEAN_DECIMALS`` 位小
数舍入）——绝不返回任何原始帧数据，百 MB 级文件一次调用即得全文件结论而
不撑爆上下文（实测 100 MiB / 328 万帧全量扫描约 3.5s；扫描上限与 60s 时限
之内是完整全量，触限以 scan_truncated/scan_timeout 如实降级）。扫描忽略分
页/筛选参数（整文件语义）。坏帧清单限量
（``DAT_SCAN_MAX_BAD_FRAME_LIST``）与单次调用时限
（``DAT_PARSE_SCAN_TIMEOUT_SECONDS``，解码循环逐帧检查单调时钟）同样是代
码常量：触限即以结构化拒绝 ``reason_code=scan_timeout`` 回报已扫描的部分
进度，审计语义不被运行时改口。扫描聚合与逐窗解码确定性对账：同一布局同
一文件，两种模式的帧数/状态计数必然一致。
"""

from __future__ import annotations

import asyncio
import json
import math
import mmap
import struct
import time
from collections import Counter

from langchain.tools import tool

from app.agentplatform.tools import dat_access
from deerflow.tools.types import Runtime

DEFAULT_FRAME_COUNT = 25
# Audit semantics: the telemetry page/scan caps are code constants, never
# config entries — runtime reconfiguration must not be able to widen them.
DAT_PARSE_MAX_FRAMES = 100
# 全量扫描的帧数上限：病态布局（极小帧）的兜底，而非常规遥测的操作边界。
# 实测（本仓库 venv，3.28M 帧 / 100 MiB 定长 32B 文件）全量扫描 3.5s、
# ~94 万帧/秒：4M 帧约 4.3s，在 60s 时限内留足余量，且覆盖"百 MB 级
# 单文件 ≈ 320 万帧"的 spec 尺度事实；真正的操作边界是下方 60s 时限，
# 逐帧检查单调时钟兜底一切布局。触顶即停，并以 scan_truncated 明示未完整扫描。
DAT_PARSE_SCAN_MAX_FRAMES = 4_000_000
# 整文件扫描（mode="scan"）的审计常量：坏帧清单限量、单次调用时限、均值小数
# 位——与分页/扫描上限一样是代码常量，绝不做成配置项（运行时改口会让"全文件
# 结论"的审计语义失真）。
DAT_SCAN_MAX_BAD_FRAME_LIST = 50
# 扫描时限（秒）：解码循环逐帧检查单调时钟，触限即停并以 scan_timeout 回报
# 部分进度——模型学到"已查到哪里"，而不是得到一个看似完整的半成品。
DAT_PARSE_SCAN_TIMEOUT_SECONDS = 60
# field_stats 均值的固定小数位（缩放后工程值的算术平均；确定性舍入）。
DAT_SCAN_MEAN_DECIMALS = 6
_MAX_FRAME_BYTES = 65536
_MAX_SYNC_BYTES = 16

# 基本类型词汇：struct 格式字符与字节数（字节序由声明单独给出）。
_FIELD_TYPES: dict[str, tuple[str, int]] = {
    "u8": ("B", 1),
    "i8": ("b", 1),
    "u16": ("H", 2),
    "i16": ("h", 2),
    "u32": ("I", 4),
    "i32": ("i", 4),
}
_SIZE_FIELD_TYPES = ("u8", "u16", "u32")
_SIZE_TYPE_MAX = {"u8": 0xFF, "u16": 0xFFFF, "u32": 0xFFFFFFFF}
# 校验和算法词汇：宽度与求和模数（字节区间和 mod 2^16 / 2^32）。
_CHECKSUM_SPECS: dict[str, tuple[int, int]] = {"sum16": (2, 0x10000), "sum32": (4, 0x1_0000_0000)}
_STATUS_OK = "ok"
_STATUS_CHECKSUM_FAILED = "checksum_failed"
_STATUS_TRUNCATED = "truncated"


class _LayoutInvalid(ValueError):
    """帧布局声明含词汇表外条目或非法值；message 指明 JSON 位置。"""


class _ScanTimeout(Exception):
    """整文件扫描超出代码常量时限；携带部分进度供结构化回报。"""

    def __init__(self, spans: list, scanned_bytes: int) -> None:
        super().__init__("scan deadline exceeded")
        self.spans = spans
        self.scanned_bytes = scanned_bytes


def _format_for(type_name: str, endian: str) -> str:
    return (">" if endian == "big" else "<") + _FIELD_TYPES[type_name][0]


def _require_int(container: dict, key: str, where: str, minimum: int | None = None, maximum: int | None = None) -> int:
    if key not in container:
        raise _LayoutInvalid(f"{where}.{key}: 缺少必填声明")
    value = container[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise _LayoutInvalid(f"{where}.{key}: 必须是整数，收到 {value!r}")
    if minimum is not None and value < minimum:
        raise _LayoutInvalid(f"{where}.{key}: 不能小于 {minimum}，收到 {value}")
    if maximum is not None and value > maximum:
        raise _LayoutInvalid(f"{where}.{key}: 不能大于 {maximum}，收到 {value}")
    return value


def _require_enum(container: dict, key: str, where: str, allowed: tuple[str, ...] | dict) -> str:
    if key not in container:
        raise _LayoutInvalid(f"{where}.{key}: 缺少必填声明")
    value = container[key]
    if value not in allowed:
        raise _LayoutInvalid(f"{where}.{key}: 不允许的取值 {value!r}，词汇表仅允许 {'/'.join(allowed)}")
    return value


def _reject_unknown_keys(node: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(node) - allowed)
    if unknown:
        listed = "、".join(unknown)
        raise _LayoutInvalid(f"{where}.{listed}: 词汇表外的声明，允许的键：{'/'.join(sorted(allowed))}")


def _parse_sync_word(value: object) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _LayoutInvalid(f"layout.sync_word: 必须是十六进制字符串或 null，收到 {value!r}")
    text = value.strip()
    if not text:
        raise _LayoutInvalid("layout.sync_word: 不能为空字符串，请声明十六进制同步字或 null")
    if len(text) % 2:
        raise _LayoutInvalid(f"layout.sync_word: 十六进制字符数必须为偶数，收到 {len(text)} 个字符")
    try:
        sync = bytes.fromhex(text)
    except ValueError:
        raise _LayoutInvalid(f"layout.sync_word: 无法解析为十六进制字节串：{value!r}") from None
    if len(sync) > _MAX_SYNC_BYTES:
        raise _LayoutInvalid(f"layout.sync_word: 同步字最长 {_MAX_SYNC_BYTES} 字节，收到 {len(sync)} 字节")
    return sync


def _parse_frame(node: object, sync_word: bytes | None) -> dict:
    if not isinstance(node, dict):
        raise _LayoutInvalid(f"layout.frame: 必须是 JSON 对象，收到 {node!r}")
    _reject_unknown_keys(node, {"size", "size_field"}, "layout.frame")
    has_size = "size" in node
    has_derived = "size_field" in node
    if has_size and has_derived:
        raise _LayoutInvalid("layout.frame: size 与 size_field 只能二选一")
    if not has_size and not has_derived:
        raise _LayoutInvalid("layout.frame: 缺少帧长声明，需要 size（定长）或 size_field（长度字段派生）")
    if has_size:
        return {"size": _require_int(node, "size", "layout.frame", minimum=1, maximum=_MAX_FRAME_BYTES), "size_field": None}
    field = node["size_field"]
    if not isinstance(field, dict):
        raise _LayoutInvalid(f"layout.frame.size_field: 必须是 JSON 对象，收到 {field!r}")
    _reject_unknown_keys(field, {"offset", "type", "endian", "offset_from", "includes", "adjustment"}, "layout.frame.size_field")
    offset = _require_int(field, "offset", "layout.frame.size_field", minimum=0)
    type_name = _require_enum(field, "type", "layout.frame.size_field", _SIZE_FIELD_TYPES)
    endian = _require_enum(field, "endian", "layout.frame.size_field", ("big", "little"))
    offset_from = _require_enum(field, "offset_from", "layout.frame.size_field", ("frame_start", "after_sync"))
    includes = _require_enum(field, "includes", "layout.frame.size_field", ("header", "payload_only"))
    adjustment = _require_int(field, "adjustment", "layout.frame.size_field", minimum=-65535, maximum=65535)
    if offset_from == "after_sync" and sync_word is None:
        raise _LayoutInvalid("layout.frame.size_field.offset_from: after_sync 需要同时声明 sync_word")
    if includes == "payload_only" and sync_word is None:
        raise _LayoutInvalid("layout.frame.size_field.includes: payload_only 需要同时声明 sync_word")
    sync_len = len(sync_word) if sync_word else 0
    # 派生帧长的静态上界（同一 65536 帧长上限）：字段/校验声明的越界校验基准。
    max_size = _SIZE_TYPE_MAX[type_name] + adjustment + (0 if includes == "header" else sync_len)
    max_size = min(max_size, _MAX_FRAME_BYTES)
    if max_size <= 0:
        raise _LayoutInvalid(f"layout.frame.size_field: 派生帧长上界为 {max_size}，任何帧都无法成立，请检查 adjustment")
    width = _FIELD_TYPES[type_name][1]
    return {
        "size": None,
        "size_field": {
            "offset": offset,
            "format": _format_for(type_name, endian),
            "width": width,
            "offset_from": offset_from,
            "includes": includes,
            "adjustment": adjustment,
            "max_size": max_size,
        },
    }


def _parse_fields(node: object, frame_bound: int) -> list[dict]:
    if not isinstance(node, list) or not node:
        raise _LayoutInvalid(f"layout.fields: 必须是非空数组，收到 {node!r}")
    fields: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(node):
        where = f"layout.fields[{index}]"
        if not isinstance(item, dict):
            raise _LayoutInvalid(f"{where}: 必须是 JSON 对象，收到 {item!r}")
        _reject_unknown_keys(item, {"name", "offset", "type", "endian", "scale"}, where)
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise _LayoutInvalid(f"{where}.name: 必须是非空字符串，收到 {name!r}")
        if "," in name:
            raise _LayoutInvalid(f'{where}.name: 字段名不能包含逗号（fields_filter 以逗号分隔），收到 "{name}"')
        if name in seen:
            raise _LayoutInvalid(f'{where}.name: 字段名重复："{name}"')
        seen.add(name)
        type_name = _require_enum(item, "type", where, tuple(_FIELD_TYPES))
        endian = _require_enum(item, "endian", where, ("big", "little"))
        offset = _require_int(item, "offset", where, minimum=0)
        size = _FIELD_TYPES[type_name][1]
        if offset + size > frame_bound:
            raise _LayoutInvalid(f"{where}.offset: 字段越界（offset {offset} + {size} 字节超出帧长上界 {frame_bound}）")
        scale = item.get("scale", 1.0)
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale):
            raise _LayoutInvalid(f"{where}.scale: 必须是有限数值，收到 {scale!r}")
        fields.append({"name": name, "offset": offset, "format": _format_for(type_name, endian), "width": size, "scale": scale})
    return fields


def _parse_checksum(node: object, frame_bound: int) -> dict | None:
    if node is None:
        return None
    if not isinstance(node, dict):
        raise _LayoutInvalid(f"layout.checksum: 必须是 JSON 对象，收到 {node!r}")
    _reject_unknown_keys(node, {"algorithm", "offset", "endian", "coverage"}, "layout.checksum")
    algorithm = _require_enum(
        node,
        "algorithm",
        "layout.checksum",
        tuple(_CHECKSUM_SPECS) + ("none",),
    )
    if algorithm == "none":
        return None
    width, modulus = _CHECKSUM_SPECS[algorithm]
    offset = _require_int(node, "offset", "layout.checksum", minimum=0)
    endian = _require_enum(node, "endian", "layout.checksum", ("big", "little"))
    if offset + width > frame_bound:
        raise _LayoutInvalid(f"layout.checksum.offset: 校验字段越界（offset {offset} + {width} 字节超出帧长上界 {frame_bound}）")
    coverage = node.get("coverage")
    if not isinstance(coverage, dict):
        raise _LayoutInvalid(f"layout.checksum.coverage: 必须是 JSON 对象（start/end 字节区间），收到 {coverage!r}")
    _reject_unknown_keys(coverage, {"start", "end"}, "layout.checksum.coverage")
    start = _require_int(coverage, "start", "layout.checksum.coverage", minimum=0)
    end = _require_int(coverage, "end", "layout.checksum.coverage", minimum=0)
    if start >= end:
        raise _LayoutInvalid(f"layout.checksum.coverage: 区间为空（start {start} ≥ end {end}），end 为排他边界")
    if end > frame_bound:
        raise _LayoutInvalid(f"layout.checksum.coverage.end: 求和区间越界（end {end} 超出帧长上界 {frame_bound}）")
    return {"format": _format_for("u16" if width == 2 else "u32", endian), "offset": offset, "width": width, "start": start, "end": end, "modulus": modulus}


def _parse_layout(raw: str) -> dict:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _LayoutInvalid(f"layout 不是合法 JSON：{exc.msg}（第 {exc.lineno} 行第 {exc.colno} 列）") from exc
    if not isinstance(document, dict):
        kind = "array" if isinstance(document, list) else type(document).__name__
        raise _LayoutInvalid(f"layout 顶层必须是 JSON 对象，收到 {kind}")
    _reject_unknown_keys(document, {"sync_word", "frame", "fields", "checksum"}, "layout")
    sync_word = _parse_sync_word(document.get("sync_word"))
    if "frame" not in document:
        raise _LayoutInvalid("layout.frame: 缺少帧长声明，需要 size（定长）或 size_field（长度字段派生）")
    frame = _parse_frame(document["frame"], sync_word)
    if "fields" not in document:
        raise _LayoutInvalid("layout.fields: 缺少字段声明，必须是非空数组")
    frame_bound = frame["size"] if frame["size"] is not None else frame["size_field"]["max_size"]
    fields = _parse_fields(document["fields"], frame_bound)
    checksum = _parse_checksum(document.get("checksum"), frame_bound)
    # 解码期帧容纳底线：任一已声明元素放不下 → 该帧标注 truncated。
    required_ends = [field["offset"] + field["width"] for field in fields]
    if checksum is not None:
        required_ends += [checksum["offset"] + checksum["width"], checksum["end"]]
    return {
        "sync_word": sync_word,
        "frame": frame,
        "fields": fields,
        "checksum": checksum,
        "min_frame_bytes": max(required_ends, default=0),
    }


def _select_fields(layout: dict, fields_filter: str) -> list[dict]:
    text = (fields_filter or "").strip()
    if not text:
        return layout["fields"]
    selected: list[dict] = []
    names = {field["name"]: field for field in layout["fields"]}
    for position, token in enumerate(text.split(","), start=1):
        name = token.strip()
        if not name:
            raise _LayoutInvalid(f"fields_filter 第 {position} 项为空字段名（检查连续逗号或首尾逗号）：{fields_filter!r}")
        if name not in names:
            declared = "/".join(field["name"] for field in layout["fields"])
            raise _LayoutInvalid(f'fields_filter: 未在布局中声明的字段名 "{name}"，布局声明的字段：{declared}')
        if names[name] not in selected:
            selected.append(names[name])
    return selected


def _read_derived_size(data, start: int, size_field: dict, sync_len: int) -> int | None:
    base = start + size_field["offset"] + (sync_len if size_field["offset_from"] == "after_sync" else 0)
    if base + size_field["width"] > len(data):
        return None
    raw = struct.unpack_from(size_field["format"], data, base)[0]
    size = raw + size_field["adjustment"] + (0 if size_field["includes"] == "header" else sync_len)
    return size


def _scan_frames(data, layout: dict, deadline: float | None = None) -> tuple[list[tuple[int, int, str]], int, bool]:
    """有界确定性扫描：返回 ``(帧跨度列表, 已扫描字节数, 是否触顶截断)``。

    帧跨度为 ``(起始字节, 申报帧覆盖到的字节, 状态)``（截断帧的覆盖按文件
    末尾收敛）。坏帧只标注不中断：定长/派生帧按布局推进，截断帧在同步字
    模式下从下一字节重新搜索同步字。``deadline`` 非空时逐帧检查单调时钟
    （不是入口一次性检查），触限抛出 ``_ScanTimeout`` 携带部分进度；帧模
    式不传时限，行为不变。
    """

    total = len(data)
    sync = layout["sync_word"]
    sync_len = len(sync) if sync else 0
    frame = layout["frame"]
    fixed_size = frame["size"]
    size_field = frame["size_field"]
    min_frame_bytes = layout["min_frame_bytes"]
    checksum = layout["checksum"]
    spans: list[tuple[int, int, str]] = []
    scan_truncated = False
    pos = 0
    while pos < total:
        if deadline is not None and time.monotonic() >= deadline:
            raise _ScanTimeout(spans, pos)
        if len(spans) >= DAT_PARSE_SCAN_MAX_FRAMES:
            scan_truncated = True
            break
        if sync is not None:
            hit = data.find(sync, pos)
            if hit == -1:
                pos = total  # 剩余字节全部不成帧，计入 skipped（已完整搜索）
                break
            start = hit
        else:
            start = pos
        if fixed_size is not None:
            size = fixed_size
        else:
            size = _read_derived_size(data, start, size_field, sync_len)
        if size is None or size <= 0 or size > _MAX_FRAME_BYTES or size < min_frame_bytes:
            # 帧长不可读、非法或容纳不下已声明字段：标注截断，绝不解出半个字段。
            # 派生帧长可为负（长度字段小值 + 负 adjustment）：覆盖按 0 收敛，
            # 保证 span 不出现 end < start、claimed 不被负值抵扣。
            declared_size = size if size is not None and size > 0 else 0
            spans.append((start, min(start + declared_size, total), _STATUS_TRUNCATED))
            if sync is None:
                pos = total  # 无同步字模式下无法确定下一帧位置，顺序步进终止
            else:
                pos = start + 1  # 从下一字节重新搜索同步字
            continue
        end = start + size
        if end > total:
            spans.append((start, total, _STATUS_TRUNCATED))
            if sync is None:
                pos = total
            else:
                pos = start + 1
            continue
        status = _STATUS_OK
        if checksum is not None:
            stored = struct.unpack_from(checksum["format"], data, start + checksum["offset"])[0]
            computed = sum(data[start + checksum["start"] : start + checksum["end"]]) % checksum["modulus"]
            if stored != computed:
                status = _STATUS_CHECKSUM_FAILED
        spans.append((start, end, status))
        pos = end
    return spans, pos, scan_truncated


def _frame_values(data, start: int, fields: list[dict]) -> dict:
    values: dict = {}
    for field in fields:
        raw = struct.unpack_from(field["format"], data, start + field["offset"])[0]
        scale = field["scale"]
        # scale 为 1（含缺省）时保持整数精确值，避免无谓的浮点化。
        values[field["name"]] = raw if scale == 1 else raw * scale
    return values


def _summary(spans_count: int, counts: Counter, skipped: int, window_start: int, returned: int, frames_truncated: bool, scan_truncated: bool, next_start: int | None) -> str:
    text = (
        f"已按帧布局扫描 {spans_count} 帧（正常 {counts.get(_STATUS_OK, 0)} / "
        f"校验和失败 {counts.get(_STATUS_CHECKSUM_FAILED, 0)} / 截断 {counts.get(_STATUS_TRUNCATED, 0)}），"
        f"跳过非帧字节 {skipped} 字节；本次返回第 {window_start} 帧起 {returned} 帧。"
    )
    if frames_truncated:
        text += f"单次返回上限 {DAT_PARSE_MAX_FRAMES} 帧，已截断。"
    if next_start is not None:
        text += f"可用 start_frame={next_start} 继续翻页。"
    if scan_truncated:
        text += f"扫描在第 {DAT_PARSE_SCAN_MAX_FRAMES} 帧上限处停止，文件未完整扫描。"
    return text


def _tally_spans(spans: list[tuple[int, int, str]], scanned_bytes: int) -> tuple[Counter, int, dict[str, int]]:
    """decode/scan 共享的 span 簿记：状态计数、跳过字节与规范化 status_counts。

    claimed（帧覆盖字节）与 skipped（scanned − claimed，非负收敛）在两条
    输出路径必须逐字一致——扫描聚合与逐窗解码的对账契约靠这一点。
    """
    counts = Counter(status for _start, _end, status in spans)
    claimed = sum(end - start for start, end, _status in spans)
    skipped = max(0, scanned_bytes - claimed)
    status_counts = {
        _STATUS_OK: counts.get(_STATUS_OK, 0),
        _STATUS_CHECKSUM_FAILED: counts.get(_STATUS_CHECKSUM_FAILED, 0),
        _STATUS_TRUNCATED: counts.get(_STATUS_TRUNCATED, 0),
    }
    return counts, skipped, status_counts


def _decode_payload(data, file_size: int, layout: dict, selected: list[dict], start_frame: int, frame_count: int) -> dict:
    spans, scanned_bytes, scan_truncated = _scan_frames(data, layout)
    clamped = min(frame_count, DAT_PARSE_MAX_FRAMES)
    frames_truncated = frame_count > DAT_PARSE_MAX_FRAMES
    window = spans[start_frame : start_frame + clamped]
    frames = []
    for index, (start, _end, status) in enumerate(window, start=start_frame):
        frames.append(
            {
                "index": index,
                "offset": start,
                "status": status,
                "values": {} if status == _STATUS_TRUNCATED else _frame_values(data, start, selected),
            }
        )
    returned = len(frames)
    next_start = start_frame + returned if returned > 0 and start_frame + returned < len(spans) else None
    counts, skipped, status_counts = _tally_spans(spans, scanned_bytes)
    return {
        "file_size": file_size,
        "scanned_bytes": scanned_bytes,
        "scan_truncated": scan_truncated,
        "total_frames_scanned": len(spans),
        "skipped_bytes": skipped,
        "frame_window": {"start": start_frame, "requested_count": frame_count, "count": clamped, "returned": returned},
        "frames_truncated": frames_truncated,
        "next_start_frame": next_start,
        "max_frames_per_call": DAT_PARSE_MAX_FRAMES,
        "frames": frames,
        "status_counts": status_counts,
        "summary": _summary(len(spans), counts, skipped, start_frame, returned, frames_truncated, scan_truncated, next_start),
    }


def _scan_summary(total: int, counts: Counter, skipped: int, bad_listed: int, bad_total: int, scan_truncated: bool) -> str:
    text = f"共 {total} 帧：{counts.get(_STATUS_OK, 0)} 正常、{counts.get(_STATUS_CHECKSUM_FAILED, 0)} 校验和失败、{counts.get(_STATUS_TRUNCATED, 0)} 截断；跳过非帧字节 {skipped} 字节。"
    if bad_listed < bad_total:
        text += f"坏帧仅列出前 {bad_listed} 个（共 {bad_total} 个）。"
    if scan_truncated:
        text += f"扫描在第 {DAT_PARSE_SCAN_MAX_FRAMES} 帧上限处停止，文件未完整扫描。"
    return text


def _scan_payload(data, file_size: int, layout: dict) -> dict:
    """整文件扫描聚合（mode="scan"）：全量解码在服务端一次完成，只回聚合。

    field_stats 覆盖每一个能解出字段值的帧——ok 与 checksum_failed 都参与
    （坏帧的值可疑但仍是全量结论的一部分），truncated 帧解不出任何字段值、
    不参与。mean 是缩放后工程值的算术平均，按 DAT_SCAN_MEAN_DECIMALS 位小数
    确定性舍入。逐帧只累积 min/max/sum/count，绝不保留逐帧值数组——内存与
    返回负载都不含任何原始帧数据。
    """
    deadline = time.monotonic() + DAT_PARSE_SCAN_TIMEOUT_SECONDS
    spans, scanned_bytes, scan_truncated = _scan_frames(data, layout, deadline=deadline)
    counts, skipped, status_counts = _tally_spans(spans, scanned_bytes)
    bad_total = counts.get(_STATUS_CHECKSUM_FAILED, 0) + counts.get(_STATUS_TRUNCATED, 0)
    bad_frames = []
    for index, (start, _end, status) in enumerate(spans):
        if status == _STATUS_OK:
            continue
        if len(bad_frames) >= DAT_SCAN_MAX_BAD_FRAME_LIST:
            break
        bad_frames.append({"index": index, "offset": start, "status": status})
    # 逐帧聚合（entry = [min, max, sum, count]），坏帧值一并参与。
    agg: dict[str, list] = {field["name"]: [None, None, 0, 0] for field in layout["fields"]}
    for start, _end, status in spans:
        if status == _STATUS_TRUNCATED:
            continue
        for name, value in _frame_values(data, start, layout["fields"]).items():
            entry = agg[name]
            if entry[3] == 0:
                entry[0] = entry[1] = value
            else:
                if value < entry[0]:
                    entry[0] = value
                if value > entry[1]:
                    entry[1] = value
            entry[2] += value
            entry[3] += 1
    field_stats = {name: {"min": entry[0], "max": entry[1], "mean": round(entry[2] / entry[3], DAT_SCAN_MEAN_DECIMALS)} for name, entry in agg.items() if entry[3]}
    payload = {
        "mode": "scan",
        "file_size": file_size,
        # total_frames 是扫描上限内的帧数：触顶时由 scan_truncated 明示
        # "未完整扫描"，绝不假装做过全量。
        "total_frames": len(spans),
        "status_counts": status_counts,
        "bad_frames": bad_frames,
        "bad_frames_truncated": bad_total > len(bad_frames),
        "field_stats": field_stats,
        "skipped_bytes": skipped,
        "scanned_bytes": scanned_bytes,
        "scan_truncated": scan_truncated,
        "summary": _scan_summary(len(spans), counts, skipped, len(bad_frames), bad_total, scan_truncated),
    }
    if payload["bad_frames_truncated"]:
        payload["bad_frame_count_total"] = bad_total
    return payload


def _rejection(reason_code: str, message: str, layout_raw: str | None = None) -> str:
    payload: dict = {"error": message, "reason_code": reason_code, "allowed_pattern": dat_access.UPLOADS_DAT_FILE_PATTERN}
    if layout_raw is not None:
        payload["layout"] = layout_raw
    return json.dumps(payload, ensure_ascii=False)


def _parse_dat_sync(runtime: Runtime, declared_path: str, layout_raw: str, start_frame: int, frame_count: int, fields_filter: str, mode: str) -> str:
    if mode not in ("frames", "scan"):
        return _rejection("invalid_mode", f"mode 只支持 frames（分页帧表）或 scan（整文件扫描聚合），收到: {mode!r}")
    try:
        handle, file_size = dat_access.open_uploads_dat_file(runtime, declared_path)
    except dat_access.DatAccessRejected as exc:
        return _rejection(exc.reason_code, str(exc))
    try:
        try:
            layout = _parse_layout(layout_raw)
            # scan 是整文件语义：fields_filter 与分页参数一样被忽略（也不校验）。
            selected = _select_fields(layout, fields_filter) if mode == "frames" else layout["fields"]
        except _LayoutInvalid as exc:
            return _rejection("invalid_layout", str(exc), layout_raw)
        if mode == "frames" and (isinstance(start_frame, bool) or isinstance(frame_count, bool) or start_frame < 0 or frame_count < 0):
            return _rejection("invalid_paging", f"start_frame/frame_count 必须为非负整数，收到 start_frame={start_frame}, frame_count={frame_count}", layout_raw)
        try:
            data = mmap.mmap(handle.fileno(), file_size, access=mmap.ACCESS_READ) if file_size else b""
        except (ValueError, OSError):
            data = handle.read()
        try:
            if mode == "scan":
                result = _scan_payload(data, file_size, layout)
            else:
                result = _decode_payload(data, file_size, layout, selected, start_frame, frame_count)
        except _ScanTimeout as exc:
            return json.dumps(
                {
                    "error": (f"整文件扫描超出单次调用时限（{DAT_PARSE_SCAN_TIMEOUT_SECONDS} 秒，代码常量），已按已扫描部分停止；请改用更小的文件或与上游约定分段上传。"),
                    "reason_code": "scan_timeout",
                    "allowed_pattern": dat_access.UPLOADS_DAT_FILE_PATTERN,
                    "path": (declared_path or "").strip(),
                    "layout": layout_raw,
                    "scanned_bytes": exc.scanned_bytes,
                    "frames_scanned_so_far": len(exc.spans),
                },
                ensure_ascii=False,
            )
        finally:
            if isinstance(data, mmap.mmap):
                data.close()
    finally:
        handle.close()
    payload = {"path": (declared_path or "").strip(), "layout": layout_raw, **result}
    return json.dumps(payload, ensure_ascii=False)


@tool("parse_dat", parse_docstring=True)
async def parse_dat_tool(
    runtime: Runtime,
    file_path: str,
    layout: str,
    start_frame: int = 0,
    frame_count: int = DEFAULT_FRAME_COUNT,
    fields_filter: str = "",
    mode: str = "frames",
) -> str:
    """按帧布局参数（Frame Layout Spec）确定性解码输入区 .dat 遥测：分页帧表或整文件扫描聚合。

    遥测常规解析入口（固定能力）：模型把遥测格式文档翻译成封闭词汇表的帧
    布局 JSON（同步字、帧长：定长或经长度字段派生、字段：名称/偏移/基本
    类型/字节序/线性缩放、校验和算法枚举 sum16/sum32/none）传入，工具确定
    性扫描同步字并解码。mode=frames（默认）分页返回帧表（每帧：全局帧号/
    文件偏移/状态/工程值）；坏帧逐帧标注（checksum_failed/truncated）并计
    数，不打断好帧解码；fields_filter 可只返回关注的字段/通道子集。mode=
    scan 做整文件扫描聚合：服务端一次解码全文件（百 MB 级文件一次调用即
    可，扫描帧上限与时限之内的文件保证全量、触限如实降级），只返回总帧
    数、各状态计数、限量坏帧位置列表（附"还有更多"标志与
    坏帧总数）、各字段 min/max/mean（缩放后工程值），绝不返回任何原始帧数
    据——分页与筛选参数被忽略；扫描时限为代码常量，触限以
    reason_code=scan_timeout 回报已扫描的部分进度。布局解析失败、词汇表外
    声明或非法值会被结构化拒绝（reason_code=invalid_layout 并指明位置），
    绝不产出半成品结果；回执原样记录传入的布局参数以便审计。路径围栏与原
    因码与 read_dat 完全一致；解码是确定性的：同一布局重解同一文件必然逐
    字节一致（扫描聚合与逐窗解码的帧数/状态计数也对账一致）；本工具只读，
    绝不执行文件内容。

    Args:
        file_path: 输入区内的 .dat 遥测文件路径，必须是 /mnt/user-data/uploads/<file>。
        layout: 帧布局参数 JSON 字符串（Frame Layout Spec，封闭词汇表，语法见
            模块 docstring：sync_word/frame/fields/checksum）；回执会原样保存。
        start_frame: 起始全局帧号（从 0 开始），默认 0；仅 frames 模式使用。
        frame_count: 本次返回的帧数上限，默认 25；超过单次上限（100）会被截断
            并以 frames_truncated 标记；仅 frames 模式使用。
        fields_filter: 逗号分隔的字段名子集，默认空（返回全部字段）；出现布局
            未声明的字段名会被拒绝（invalid_layout）；仅 frames 模式使用。
        mode: 输出模式：frames（默认，分页帧表）或 scan（整文件扫描聚合：只
            回总帧数/各状态计数/限量坏帧位置/各字段 min-max-mean，忽略
            start_frame/frame_count/fields_filter）；其他值会被拒绝。
    """
    return await asyncio.to_thread(_parse_dat_sync, runtime, file_path, layout, start_frame, frame_count, fields_filter, mode)
