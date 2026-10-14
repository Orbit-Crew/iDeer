"""Regression: the serve.sh gateway binds per BIND_HOST, loopback by default (08-M12).

The local serve.sh stack launched the gateway with ``uvicorn --host 0.0.0.0``,
so any LAN host could bypass the nginx single entry (and its unified
audit/access surface) and hit the backend API directly. The container stacks
already default their published ports to loopback; the host-run stack now
follows the same rule: ``BIND_HOST`` defaults to ``127.0.0.1`` and operators
opt into LAN exposure explicitly.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVE_SH = REPO_ROOT / "scripts" / "serve.sh"


def test_serve_gateway_defaults_to_loopback_bind_host() -> None:
    script = SERVE_SH.read_text(encoding="utf-8")

    assert 'BIND_HOST="${BIND_HOST:-127.0.0.1}"' in script, "serve.sh must define BIND_HOST with a loopback default so the local stack keeps nginx as the single entry (08-M12)"
    assert "--host '$BIND_HOST'" in script, "the gateway uvicorn command must bind BIND_HOST instead of a hardcoded address, so the loopback default is actually enforced"
    assert "--host 0.0.0.0" not in script, "serve.sh must not hardcode the gateway onto all interfaces; LAN exposure is an explicit BIND_HOST override (08-M12)"
