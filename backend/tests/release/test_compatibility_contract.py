"""Compatibility declaration contract (issue 110, Server side).

The Server publishes the declaration at the controlled address (issue 107
router); the Desktop verifies the signature and applies this same structural
contract. These tests keep both sides in step: a declaration the Server
publishes must always pass the Desktop's parser, and one it would reject must
never be signable with the maintainer tooling.
"""

import importlib.util
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

TOOL_PATH = Path(__file__).resolve().parents[3] / "scripts" / "release" / "issue-110" / "make-compatibility.py"
_tool_spec = importlib.util.spec_from_file_location("make_compatibility", TOOL_PATH)
make_compatibility_module = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(make_compatibility_module)
make_compatibility = make_compatibility_module.main

KEY = Ed25519PrivateKey.generate()
PUBLIC_PEM = KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def declaration(**overrides):
    body = {
        "version": 1,
        "level": "compatible",
        "disabledCapabilities": [],
        "minProtocol": 1,
        "notes": "Server 6a819f3 or newer",
        "candidateCombo": {"desktop": "0.2.0", "runtime": "3.12.10", "server": "6a819f3"},
    }
    body.update(overrides)
    return body


def run_tool(tmp_path, body, *, private=True):
    declaration_path = tmp_path / "declaration.json"
    declaration_path.write_text(json.dumps(body), encoding="utf-8")
    out = tmp_path / "signed"
    key_file = None
    if private:
        key_file = tmp_path / "key.pem"
        key_file.write_text(KEY.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode(), encoding="utf-8")
    code = make_compatibility(["--declaration", str(declaration_path), "--out", str(out), *(["--private-key", str(key_file)] if private else [])])
    return code, out


def desktop_style_verify(text: str, signature_hex: str, public_bytes: bytes) -> bool:
    """Mirror the Desktop's node:crypto Ed25519 verification of the exact bytes."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(bytes.fromhex(signature_hex), text.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError):
        return False


def test_tool_signs_the_canonical_bytes_the_desktop_verifies(tmp_path):
    code, out = run_tool(tmp_path, declaration())
    assert code == 0
    text = (out / "compatibility.json").read_text(encoding="utf-8")
    signature = (out / "compatibility.sig").read_text(encoding="utf-8").strip()
    assert desktop_style_verify(text, signature, PUBLIC_PEM)
    # The signature covers the exact served bytes, so a rewritten note fails.
    assert not desktop_style_verify(text.replace("6a819f3", "rewritten"), signature, PUBLIC_PEM)


@pytest.mark.parametrize(
    "overrides",
    [
        {"level": "aggressive"},
        {"level": "compatible", "disabledCapabilities": ["local.python"]},
        {"level": "core", "disabledCapabilities": ["local.python"]},
        {"disabledCapabilities": ["local.files.execute"]},
        {"disabledCapabilities": ["local.python", "local.python"]},
        {"minProtocol": 0},
        {"candidateCombo": {"desktop": "0.2.0"}},
    ],
)
def test_tool_refuses_declarations_the_desktop_would_reject(tmp_path, overrides):
    code, out = run_tool(tmp_path, declaration(**overrides))
    assert code == 2
    assert not (out / "compatibility.json").exists()


def test_tool_requires_a_key_and_reports_missing_signing_material(tmp_path):
    code, out = run_tool(tmp_path, declaration(), private=False)
    assert code == 2
    assert not (out / "compatibility.sig").exists()
