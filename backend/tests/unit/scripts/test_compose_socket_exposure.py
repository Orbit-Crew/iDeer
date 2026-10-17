"""Contract: the host Docker socket is never mounted by default (08-H2).

The host Docker socket grants the receiving container root-equivalent control
of the host. The opt-in ``docker/docker-compose.dood.yaml`` overlay documents
itself as "OPT-IN, NOT loaded by default", but the production and intranet base
compose files unconditionally mounted the socket into ``gateway`` (and, on the
intranet, ``workflow-worker``), so every sandbox mode — local and provisioner
included — silently held that capability. The default compose files must mount
no Docker socket; the capability exists only through the overlay, which
``scripts/deploy.sh``, ``scripts/docker.sh`` and ``scripts/deploy-intranet.sh``
append only when the runtime config selects the aio (DooD) sandbox provider.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DOCKER_DIR = _REPO_ROOT / "docker"
_DOOD_OVERLAY = _DOCKER_DIR / "docker-compose.dood.yaml"


def _load_compose(name: str) -> dict:
    path = _DOCKER_DIR / name
    assert path.is_file(), f"expected compose file to exist: {path}"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return doc


def _docker_socket_mounts(doc: dict) -> list[str]:
    """Return "<service>: <volume>" entries that reference a host Docker socket.

    Short-syntax volumes may embed the socket in an interpolation expression
    (``${IDEER_DOCKER_SOCKET:-/var/run/docker.sock}:/var/run/docker.sock``), so
    the raw volume text is matched instead of splitting on ':' — any docker
    socket path (default or custom) means host daemon control.
    """
    mounts: list[str] = []
    for service, config in (doc.get("services") or {}).items():
        for volume in (config or {}).get("volumes") or []:
            if isinstance(volume, str):
                text = volume
            elif isinstance(volume, dict):
                text = f"{volume.get('source', '')}:{volume.get('target', '')}"
            else:
                continue
            if "docker.sock" in text:
                mounts.append(f"{service}: {text}")
    return mounts


def test_default_compose_files_mount_no_docker_socket() -> None:
    """gateway/workflow-worker in the default prod, dev and intranet compose files must not receive the host Docker socket."""
    for name in (
        "docker-compose.yaml",
        "docker-compose-dev.yaml",
        "docker-compose.intranet.yaml",
    ):
        mounts = _docker_socket_mounts(_load_compose(name))
        assert not mounts, (
            f"{name} mounts the host Docker socket by default ({mounts}); the socket grants "
            "root-equivalent host control and must only enter containers through the opt-in "
            "docker-compose.dood.yaml overlay that deploy.sh / docker.sh / deploy-intranet.sh "
            "append in aio sandbox mode (issue 08-H2)"
        )


def test_only_the_opt_in_dood_overlay_mounts_the_docker_socket() -> None:
    """Across docker/, only docker-compose.dood.yaml may reference the socket — and it must cover gateway and workflow-worker."""
    allowed: dict[str, list[str]] = {}
    for path in sorted(_DOCKER_DIR.glob("docker-compose*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        mounts = _docker_socket_mounts(doc)
        if mounts:
            allowed[path.name] = mounts
    assert set(allowed) == {_DOOD_OVERLAY.name}, f"only the opt-in {_DOOD_OVERLAY.name} may mount the host Docker socket, found mounts in {allowed}"
    services = {entry.split(":", 1)[0] for entry in allowed[_DOOD_OVERLAY.name]}
    assert services == {"gateway", "workflow-worker"}, f"the DooD overlay must mount the socket into exactly gateway and workflow-worker (both run sandboxes in aio mode), got {sorted(services)}"


def test_dood_overlay_stays_opt_in_with_threat_model_note() -> None:
    """The overlay header must keep the opt-in declaration and the root-equivalent warning."""
    header = _DOOD_OVERLAY.read_text(encoding="utf-8")
    assert "OPT-IN" in header, "the overlay header must keep the OPT-IN declaration"
    assert "root-equivalent" in header, "the overlay header must keep the host root-equivalent warning"


def test_deploy_scripts_append_the_overlay_inside_the_aio_gate() -> None:
    """deploy.sh and docker.sh must append the overlay only in the aio branch of the sandbox-mode gate."""
    for name, aio_gate, append in (
        ("deploy.sh", 'if [ "$sandbox_mode" = "aio" ]; then', "docker-compose.dood.yaml"),
        ("docker.sh", 'if [ "$sandbox_mode" = "aio" ]; then', "docker-compose.dood.yaml"),
    ):
        script = (_REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
        gate = script.index(aio_gate)
        overlay = script.index(append, gate)
        assert gate < overlay, f"{name} must reference {append} only after its aio sandbox-mode gate"
    intranet = (_REPO_ROOT / "scripts" / "deploy-intranet.sh").read_text(encoding="utf-8")
    assert "detect_sandbox_mode" in intranet, "deploy-intranet.sh must detect the sandbox mode like deploy.sh"
    assert "docker-compose.dood.yaml" in intranet, "deploy-intranet.sh must append the opt-in DooD overlay for aio mode"
