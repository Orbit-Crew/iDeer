"""Keep the pinned broker identity across Gateway restarts."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat


def persistent_broker_key(path: str | Path | None = None) -> Ed25519PrivateKey:
    if path is None:
        from deerflow.config.paths import get_paths

        path = get_paths().base_dir / "device-control" / "broker-signing.key"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_name(".broker-key-" + uuid4().hex)
        try:
            raw = Ed25519PrivateKey.generate().private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
            try:
                # Atomic publish without replacing another worker's identity.
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
    if path.is_symlink():
        raise ValueError("BROKER_IDENTITY_UNAVAILABLE")
    # A corrupt or unreadable identity must fail, never silently rotate.
    return Ed25519PrivateKey.from_private_bytes(path.read_bytes())
