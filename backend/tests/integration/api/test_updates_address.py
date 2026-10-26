"""Controlled update address contract (issue 107, Server side)."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import updates


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    controlled = tmp_path / "reviewed"
    controlled.mkdir()
    monkeypatch.setenv("UPDATES_CONTROLLED_DIR", str(controlled))
    app = FastAPI()
    app.include_router(updates.router)
    transport = httpx.ASGITransport(app=app)
    return controlled, httpx.AsyncClient(transport=transport, base_url="http://fixture.invalid")


@pytest.mark.asyncio
async def test_serves_reviewed_documents_at_the_controlled_address(client):
    controlled, http = client
    (controlled / "desktop").mkdir()
    (controlled / "desktop" / "manifest.json").write_text('{"version": 1}', encoding="utf-8")
    (controlled / "desktop" / "manifest.sig").write_text("ab" * 64, encoding="utf-8")
    (controlled / "compatibility.json").write_text('{"version": 1, "level": "compatible"}', encoding="utf-8")
    async with http as http_client:
        manifest = await http_client.get("/updates/desktop/manifest.json")
        assert manifest.status_code == 200
        assert manifest.json()["version"] == 1
        assert manifest.headers["cache-control"] == "no-store"
        signature = await http_client.get("/updates/desktop/manifest.sig")
        assert signature.status_code == 200
        compatibility = await http_client.get("/updates/compatibility.json")
        assert compatibility.status_code == 200


@pytest.mark.asyncio
async def test_reports_honest_404_while_nothing_is_published(client):
    _, http = client
    async with http as http_client:
        for path in ("/updates/desktop/manifest.json", "/updates/compatibility.json"):
            response = await http_client.get(path)
            assert response.status_code == 404
            assert response.json()["detail"]["code"] == "DOCUMENT_NOT_PUBLISHED"


@pytest.mark.asyncio
async def test_serves_exactly_the_published_names_and_nothing_else(client):
    controlled, http = client
    (controlled / "secret.txt").write_text("internal", encoding="utf-8")
    (controlled / "desktop").mkdir()
    (controlled / "desktop" / "old.json").write_text("{}", encoding="utf-8")
    async with http as http_client:
        for path in ("/updates/secret.txt", "/updates/desktop/old.json", "/updates/../secret.txt", "/updates/desktop/manifest.json.bak"):
            response = await http_client.get(path)
            assert response.status_code == 404, path
        # A traversal name never escapes the controlled directory even if it
        # were whitelisted: the whitelist match is on the request path itself.
        escape = await http_client.get("/updates/%2e%2e%2fsecret.txt")
        assert escape.status_code == 404


@pytest.mark.asyncio
async def test_published_assets_must_be_manifest_listed_and_match_digest(client):
    import hashlib
    import json

    controlled, http = client
    files = controlled / "desktop" / "files" / "resources"
    files.mkdir(parents=True)
    content = b"reviewed-app"
    (files / "app.asar").write_bytes(content)
    (files / "not-reviewed.asar").write_bytes(b"unreviewed")
    (controlled / "desktop" / "manifest.json").write_text(json.dumps({"files": [{"path": "resources/app.asar", "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}]}))
    async with http as http_client:
        served = await http_client.get("/updates/desktop/files/resources/app.asar")
        assert served.status_code == 200, served.text
        assert served.content == content
        assert (await http_client.get("/updates/desktop/files/resources/not-reviewed.asar")).status_code == 404
        (files / "app.asar").write_bytes(b"corrupt")
        assert (await http_client.get("/updates/desktop/files/resources/app.asar")).status_code == 404


def test_formal_gateway_exposes_controlled_documents_without_business_session(gateway_app, tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    reviewed = tmp_path / "reviewed"
    (reviewed / "desktop").mkdir(parents=True)
    (reviewed / "desktop" / "manifest.json").write_text('{"version":1}')
    monkeypatch.setenv("UPDATES_CONTROLLED_DIR", str(reviewed))
    with TestClient(gateway_app) as http_client:
        response = http_client.get("/updates/desktop/manifest.json")
        assert response.status_code == 200, response.text
        assert response.json() == {"version": 1}
        assert http_client.get("/updates/private.txt").status_code == 404
        assert http_client.get("/updates-evil/private.txt").status_code == 401


# Reuse the isolated production-app factory, including the actual middleware.
from tests.integration.api import test_devices_router_auth_gate as gateway_fixtures  # noqa: E402

gateway_app = gateway_fixtures.gateway_app


@pytest.mark.external
def test_nginx_public_origin_serves_real_gateway_release(gateway_app, tmp_path, monkeypatch):
    import hashlib
    import json
    import shutil
    import socket
    import subprocess
    import threading
    import time

    import uvicorn

    nginx = shutil.which("nginx") or "/usr/sbin/nginx"
    assert Path(nginx).is_file(), "real nginx is required for controlled-public-origin acceptance"

    def free_port():
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    gateway_port, public_port = free_port(), free_port()
    reviewed = tmp_path / "reviewed"
    assets = reviewed / "desktop" / "files" / "resources"
    assets.mkdir(parents=True)
    content = b"T107-public-reviewed-release"
    installer = b"T107-full-installer"
    (assets / "app.asar").write_bytes(content)
    (reviewed / "desktop" / "installer.exe").write_bytes(installer)
    manifest = {
        "version": 1,
        "files": [{"path": "resources/app.asar", "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}],
        "installer": {"path": "installer.exe", "sha256": hashlib.sha256(installer).hexdigest(), "bytes": len(installer)},
    }
    (reviewed / "desktop" / "manifest.json").write_text(json.dumps(manifest))
    (reviewed / "desktop" / "manifest.sig").write_text("ab" * 64)
    (assets / "unlisted.txt").write_text("private")
    monkeypatch.setenv("UPDATES_CONTROLLED_DIR", str(reviewed))
    prefix = tmp_path / "nginx"
    (prefix / "logs").mkdir(parents=True)
    # Exercise the actual checked-in public routing, changing only isolated
    # ports and keeping logs/PID inside this test's private prefix.
    source = Path(__file__).resolve().parents[4] / "docker" / "nginx" / "nginx.local.conf"
    config = source.read_text().replace("127.0.0.1:8001", f"127.0.0.1:{gateway_port}").replace("listen 2026;", f"listen 127.0.0.1:{public_port};").replace("        listen [::]:2026;\n", "")
    config_path = prefix / "nginx.conf"
    config_path.write_text(config)
    subprocess.run([nginx, "-p", str(prefix) + "/", "-c", str(config_path), "-t"], check=True, capture_output=True)
    server = uvicorn.Server(uvicorn.Config(gateway_app, host="127.0.0.1", port=gateway_port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    process = None
    try:
        for _ in range(200):
            if server.started:
                break
            if not thread.is_alive():
                raise AssertionError("formal Gateway exited before startup")
            time.sleep(0.025)
        assert server.started, "Gateway startup timed out"
        process = subprocess.Popen([nginx, "-p", str(prefix) + "/", "-c", str(config_path), "-g", "daemon off;"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        with httpx.Client(base_url=f"http://127.0.0.1:{public_port}", timeout=5) as http_client:
            for _ in range(100):
                try:
                    response = http_client.get("/updates/desktop/manifest.json")
                    break
                except httpx.ConnectError:
                    time.sleep(0.025)
            else:
                raise AssertionError("isolated nginx did not start")
            assert response.status_code == 200, response.text
            assert response.json() == manifest
            for path, expected in [("files/resources/app.asar", content), ("installer.exe", installer)]:
                response = http_client.get(f"/updates/desktop/{path}")
                assert response.status_code == 200, response.text
                assert hashlib.sha256(response.content).hexdigest() == hashlib.sha256(expected).hexdigest()
            assert http_client.get("/updates/desktop/files/resources/unlisted.txt").status_code == 404
            assert http_client.get("/updates/desktop/files/resources/%2e%2e/manifest.json").status_code == 404
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=5)
        server.should_exit = True
        thread.join(timeout=10)
    assert not thread.is_alive(), "isolated Gateway must stop after acceptance"
