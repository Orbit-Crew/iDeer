# Synthetic telemetry `.dat` samples

Small, deterministic binary samples for the telemetry `.dat` tools
(`read_dat` ticket #73; structure stats / frame parse tickets #74/#75/#76
reuse the same set). Regenerate byte-identical copies with the repo Python:

```bash
python3 backend/tests/fixtures/telemetry/generate.py
```

All frames use the fixed 32-byte layout documented in `generate.py`
(sync word `1A CF FC 1D`, u32 counter, 8×u16 channels, u16 checksum,
zero padding).

| 文件 | 内容 | 覆盖点 |
| --- | --- | --- |
| `normal_frames.dat` | 64 个全部校验和正确的定长帧（2048 字节） | 合法 `.dat` 的分页十六进制视图、正常帧流解码 |
| `corrupted_frames.dat` | 64 个帧，其中第 5/40 帧校验和坏、第 17 帧通道字节翻转未更新校验和、第 20 帧同步字被破坏 | 坏帧逐帧标注、坏帧计数、好帧不中断 |
| `truncated.dat` | 40 个完整帧 + 第 41 帧的前 17 字节 | 尾部截断帧的状态标注 |
| `no_sync_high_entropy.dat` | 2048 字节确定性伪随机字节流，构造上不含同步字 | 无同步字结构文件的结构摸底/拒绝路径 |

字节均为纯常量的函数（无随机数、无时钟），重跑生成脚本结果逐字节一致。
文件均为 KB 级，绝不接近 `DAT_MAX_FILE_BYTES`（512 MiB）单文件上限；
超大文件分支在测试中通过对常量打猴子补丁覆盖。
