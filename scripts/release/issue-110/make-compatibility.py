"""Issue 110 maintainer tooling: build and verify the signed compatibility
declaration served at the controlled address.

The signing key never enters the repository: read it from
COMPAT_PRIVATE_KEY_PEM or --private-key <file>. The canonical declaration is
the exact bytes signed and served; the Desktop verifies the detached Ed25519
signature against its pinned public key and applies the same structural
contract asserted in test_compatibility_contract.py.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

KNOWN_LEVELS = ("compatible", "capability", "core")
KNOWN_CAPABILITIES = (
    "local.files.read",
    "local.files.write",
    "local.files.list",
    "local.files.search",
    "local.python",
    "local.artifacts.upload",
)


def validate(declaration: dict) -> list[str]:
    """The structural contract the Desktop enforces; keep both sides in step."""
    problems: list[str] = []
    if declaration.get("version") != 1:
        problems.append("version must be 1")
    level = declaration.get("level")
    if level not in KNOWN_LEVELS:
        problems.append(f"level must be one of {KNOWN_LEVELS}")
    disabled = declaration.get("disabledCapabilities")
    if not isinstance(disabled, list) or any(cap not in KNOWN_CAPABILITIES for cap in disabled):
        problems.append(f"disabledCapabilities entries must all be in {KNOWN_CAPABILITIES}")
    if len(disabled or []) != len(set(disabled or [])):
        problems.append("disabledCapabilities must not repeat an entry")
    if level == "compatible" and disabled:
        problems.append("a compatible declaration carries no disabledCapabilities")
    if level == "core" and disabled:
        problems.append("a core declaration carries no disabledCapabilities")
    if not isinstance(declaration.get("minProtocol"), int) or declaration.get("minProtocol", 0) < 1:
        problems.append("minProtocol must be a positive integer")
    notes = declaration.get("notes")
    if not isinstance(notes, str) or len(notes) > 2000:
        problems.append("notes must be a string of at most 2000 characters")
    combo = declaration.get("candidateCombo")
    if not isinstance(combo, dict) or any(
        not isinstance(combo.get(field), str) or not combo.get(field) or len(combo[field]) > 128
        for field in ("desktop", "runtime", "server")
    ):
        problems.append("candidateCombo must name desktop, runtime and server")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--declaration", required=True, help="canonical declaration JSON file")
    parser.add_argument("--out", required=True, help="output directory for compatibility.json + .sig")
    parser.add_argument("--private-key", help="PEM file; overrides COMPAT_PRIVATE_KEY_PEM")
    args = parser.parse_args(argv)

    key_pem = sys.stdin.read() if False else None
    key_pem = Path(args.private_key).read_text(encoding="utf-8") if args.private_key else None
    key_pem = key_pem or __import__("os").environ.get("COMPAT_PRIVATE_KEY_PEM")
    if not key_pem:
        print("no signing key: pass --private-key or set COMPAT_PRIVATE_KEY_PEM", file=sys.stderr)
        return 2

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    declaration_text = Path(args.declaration).read_text(encoding="utf-8")
    problems = validate(json.loads(declaration_text))
    if problems:
        for problem in problems:
            print(f"contract violation: {problem}", file=sys.stderr)
        return 2
    key = load_pem_private_key(key_pem.encode(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        print("the signing key must be an Ed25519 private key", file=sys.stderr)
        return 2
    signature = key.sign(declaration_text.encode("utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "compatibility.json").write_text(declaration_text, encoding="utf-8")
    (out / "compatibility.sig").write_text(
        base64.b16encode(signature).decode("ascii").lower() + "\n", encoding="utf-8"
    )
    print(f"signed compatibility declaration written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
