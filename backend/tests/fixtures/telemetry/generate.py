"""Regenerate the synthetic telemetry ``.dat`` samples in this directory.

Every sample is a pure function of the constants below (no randomness, no
clock), so re-running this script with the repo's Python always reproduces
byte-identical files:

    python3 backend/tests/fixtures/telemetry/generate.py

Frame layout (fixed 32 bytes, big-endian) — the layout the later parse
tickets (#74/#75/#76) assume when reusing these samples:

    offset 0..3   sync word 1A CF FC 1D
    offset 4..7   frame counter (u32)
    offset 8..23  8 telemetry channels (u16 each)
    offset 24..25 checksum: sum of bytes 4..23 (u16)
    offset 26..31 zero padding
"""

from __future__ import annotations

from pathlib import Path

SYNC_WORD = bytes.fromhex("1ACFFC1D")
FRAME_BYTES = 32
FRAME_COUNT = 64


def checksum(payload: bytes) -> int:
    return sum(payload) % 0x10000


def frame(index: int) -> bytes:
    body = index.to_bytes(4, "big") + b"".join(((index * 7 + channel * 937) % 0x10000).to_bytes(2, "big") for channel in range(8))
    padding = b"\x00" * (FRAME_BYTES - len(SYNC_WORD) - len(body) - 2)
    return SYNC_WORD + body + checksum(body).to_bytes(2, "big") + padding


def normal_stream() -> bytes:
    return b"".join(frame(index) for index in range(FRAME_COUNT))


def corrupted_stream() -> bytes:
    frames = [bytearray(frame(index)) for index in range(FRAME_COUNT)]
    frames[5][-1] ^= 0xFF  # checksum no longer matches the body
    frames[17][10] ^= 0x01  # channel byte flipped, checksum left stale
    frames[20][0] ^= 0xFF  # sync word destroyed
    frames[40][-1] ^= 0x55  # second checksum failure
    return b"".join(bytes(item) for item in frames)


def truncated_stream() -> bytes:
    return normal_stream()[: FRAME_BYTES * 40 + 17]


def no_sync_stream() -> bytes:
    # Deterministic LCG byte soup: no sync word ever appears by construction.
    state = 0x5EED
    out = bytearray()
    for _ in range(2048):
        state = (state * 1_103_515_245 + 12_345) % (1 << 31)
        out.append((state >> 16) & 0xFF)
    assert SYNC_WORD not in bytes(out)
    return bytes(out)


SAMPLES: dict[str, bytes] = {
    "normal_frames.dat": normal_stream(),
    "corrupted_frames.dat": corrupted_stream(),
    "truncated.dat": truncated_stream(),
    "no_sync_high_entropy.dat": no_sync_stream(),
}


def main() -> None:
    target_dir = Path(__file__).resolve().parent
    for name, payload in SAMPLES.items():
        (target_dir / name).write_bytes(payload)
        print(f"wrote {name} ({len(payload)} bytes)")


if __name__ == "__main__":
    main()
