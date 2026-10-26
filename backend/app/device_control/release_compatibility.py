"""Verify operations-signed compatibility before admitting new local work.

This is an additional restriction. It never supplies user/device authorization,
and never changes in-flight tasks, receipts, or historical execution evidence.
"""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from deerflow.config.paths import get_paths

MAX_DOCUMENT_BYTES = 512 * 1024


@dataclass(frozen=True)
class CompatibilityState:
    level: str
    disabled_capabilities: frozenset[str] = field(default_factory=frozenset)
    digest: str = ""
    reason: str = ""

    def rejection(self, operation: str) -> str | None:
        if self.level == "core":
            return "COMPAT_CORE_INCOMPATIBLE"
        if operation in self.disabled_capabilities:
            return "COMPAT_CAPABILITY_DISABLED"
        return None

    def public(self) -> dict:
        return {"level": self.level, "disabledCapabilities": sorted(self.disabled_capabilities), "sha256": self.digest, "reason": self.reason}


def server_release_version() -> str:
    return os.environ.get("SERVER_RELEASE_VERSION", "")


def _level(value: Any, default: dict | None = None) -> tuple[str, frozenset[str]]:
    level = value.get("level", (default or {}).get("level"))
    disabled = value.get("disabledCapabilities", (default or {}).get("disabledCapabilities"))
    if level not in {"compatible", "capability", "core"} or not isinstance(disabled, list):
        raise ValueError("COMPAT_DECLARATION_INVALID")
    if any(not isinstance(cap, str) or not cap or len(cap) > 128 for cap in disabled) or len(set(disabled)) != len(disabled):
        raise ValueError("COMPAT_DECLARATION_INVALID")
    if level != "capability" and disabled:
        raise ValueError("COMPAT_DECLARATION_INVALID")
    return level, frozenset(disabled)


def _combo(value: Any) -> dict:
    if not isinstance(value, dict) or any(not isinstance(value.get(name), str) or not value[name] or len(value[name]) > 128 for name in ("desktop", "runtime", "server")):
        raise ValueError("COMPAT_COMBINATION_INVALID")
    return {name: value[name] for name in ("desktop", "runtime", "server")}


def _legacy_hello(value: dict) -> tuple[str, str] | None:
    legacy = value.get("legacyHello")
    if legacy is None:
        return None
    if not isinstance(legacy, dict) or set(legacy) != {"runtimeVersion", "protocolVersion"}:
        raise ValueError("COMPAT_LEGACY_MAPPING_INVALID")
    if any(not isinstance(legacy[name], str) or not legacy[name] or len(legacy[name]) > 128 for name in legacy):
        raise ValueError("COMPAT_LEGACY_MAPPING_INVALID")
    return legacy["runtimeVersion"], legacy["protocolVersion"]


def _remember(marker: Path, digest: str) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".compat-", dir=marker.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(digest)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, marker)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def evaluate_connection(connection: Any) -> CompatibilityState:
    """Refresh on every dispatch; removed or invalid declarations fail closed."""
    configured = os.environ.get("UPDATES_CONTROLLED_DIR", "")
    root = (Path(configured) if configured else Path.cwd() / "updates-controlled").resolve()
    state_dir = Path(os.environ.get("UPDATES_STATE_DIR", "")) if os.environ.get("UPDATES_STATE_DIR") else get_paths().base_dir / "updates-state"
    marker = state_dir / (hashlib.sha256(str(root).encode()).hexdigest() + ".seen")
    protocol = str(getattr(connection, "protocol_version", "1"))
    try:
        document_path = (root / "compatibility.json").resolve()
        signature_path = (root / "compatibility.sig").resolve()
        if not document_path.is_relative_to(root) or not signature_path.is_relative_to(root):
            raise ValueError("COMPAT_PATH_INVALID")
        if not document_path.exists():
            # Only first-ever publication absence preserves the protocol-1
            # deployment contract. A previously observed release cannot vanish.
            if marker.exists() or signature_path.exists() or protocol != "1":
                raise ValueError("COMPAT_DECLARATION_UNAVAILABLE")
            return CompatibilityState("compatible", reason="legacy-protocol-1")
        if document_path.stat().st_size > MAX_DOCUMENT_BYTES or signature_path.stat().st_size > 1024:
            raise ValueError("COMPAT_DECLARATION_INVALID")
        raw = document_path.read_bytes()
        signature = signature_path.read_text("utf-8").strip()
        trust_file = os.environ.get("UPDATES_TRUSTED_PUBLIC_KEY_FILE", "")
        if not trust_file or not re.fullmatch("[0-9a-fA-F]{128}", signature):
            raise ValueError("COMPAT_SIGNATURE_INVALID")
        key = serialization.load_pem_public_key(Path(trust_file).read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("COMPAT_SIGNATURE_INVALID")
        key.verify(bytes.fromhex(signature), raw)
        document = json.loads(raw)
        if not isinstance(document, dict) or document.get("version") != 1:
            raise ValueError("COMPAT_DECLARATION_INVALID")
        level, disabled = _level(document)
        minimum = document.get("minProtocol")
        if type(minimum) is not int or minimum < 1 or not isinstance(document.get("notes"), str) or len(document["notes"]) > 2000:
            raise ValueError("COMPAT_DECLARATION_INVALID")
        candidate = _combo(document.get("candidateCombo"))
        supported = document.get("supportedCombos", [])
        if not isinstance(supported, list) or len(supported) > 100:
            raise ValueError("COMPAT_COMBINATION_INVALID")
        combinations = [(candidate, (level, disabled), _legacy_hello(document["candidateCombo"]))]
        for item in supported:
            combinations.append((_combo(item), _level(item, document), _legacy_hello(item)))
        if len({tuple(sorted(combo.items())) for combo, _, _ in combinations}) != len(combinations):
            raise ValueError("COMPAT_COMBINATION_INVALID")
        digest = hashlib.sha256(raw).hexdigest()
        _remember(marker, digest)
        actual = {"desktop": getattr(connection, "desktop_version", ""), "runtime": getattr(connection, "runtime_python", ""), "server": server_release_version()}
        if not protocol.isdecimal() or int(protocol) < minimum:
            return CompatibilityState("core", digest=digest, reason="COMPAT_PROTOCOL_INCOMPATIBLE")
        if actual["desktop"] and actual["runtime"]:
            for combo, (level, disabled), _ in combinations:
                if combo == actual:
                    return CompatibilityState(level, disabled, digest)
        elif not actual["desktop"] and not actual["runtime"]:
            # Original clients did not report Desktop/Python identities. Only
            # an explicit signed mapping from the verified old HELLO plus its
            # registration metadata may identify a tested legacy combination.
            reported_runtime = getattr(connection, "runtime_version", "")
            registered_runtime = getattr(connection, "registered_runtime_version", "")
            matches = [(level, disabled) for combo, (level, disabled), legacy in combinations if legacy == (reported_runtime, protocol) and reported_runtime == registered_runtime and combo["server"] == actual["server"]]
            if len(matches) == 1:
                level, disabled = matches[0]
                return CompatibilityState(level, disabled, digest)
        return CompatibilityState("core", digest=digest, reason="COMPAT_COMBINATION_UNVERIFIED")
    except (OSError, ValueError, TypeError, InvalidSignature):
        return CompatibilityState("core", reason="COMPAT_DECLARATION_INVALID")
