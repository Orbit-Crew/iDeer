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
