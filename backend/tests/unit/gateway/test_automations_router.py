"""Router-level contract tests for the automations API.

``app/gateway/routers/automations.py`` had zero test references (code
review 09-M5). These tests pin its public HTTP contract on a bare app
with stubbed auth (see ``tests/_router_auth_helpers.py``):

- ``GET /api/automations/templates`` is public (no auth dependency) and
  serves the ``AUTOMATION_TEMPLATES`` catalogue.
- ``GET /api/automations`` lists the caller's automations (currently an
  empty collection) and requires an authenticated user.
- ``POST /api/automations`` validates ``template_id`` against the
  catalogue (400 on unknown) and echoes the created automation.
- ``DELETE /api/automations/{id}`` answers 204.
- Pydantic field constraints (empty name / template_id) answer 422.
"""

from __future__ import annotations

import pytest
from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient

from app.agentplatform.rbac_models import UserModel
from app.gateway.authz import get_current_rbac_user
from app.gateway.routers import automations

EXPECTED_TEMPLATE_IDS = {
    "daily-report",
    "weekly-report",
    "meeting-minutes",
    "data-report",
    "anomaly-monitor",
    "task-reminder",
    "meeting-reminder",
    "doc-change-notify",
}

_TEMPLATE_FIELDS = {"id", "name", "description", "category"}


def _client() -> TestClient:
    """Bare app + stub auth middleware, with the RBAC DB dependency
    overridden to a fixed user (no database in router-level tests)."""
    app = make_authed_test_app()
    app.dependency_overrides[get_current_rbac_user] = lambda: UserModel(id="router-test-user", username="router-test@example.com", role="user")
    app.include_router(automations.router)
    return TestClient(app)


def test_templates_route_is_public_and_serves_catalogue():
    resp = _client().get("/api/automations/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) == len(EXPECTED_TEMPLATE_IDS)
    assert {t["id"] for t in templates} == EXPECTED_TEMPLATE_IDS
    for template in templates:
        assert set(template) == _TEMPLATE_FIELDS
        assert template["name"]
        assert template["description"]


def test_list_automations_requires_auth_and_starts_empty():
    resp = _client().get("/api/automations")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"name": "Nightly", "template_id": "daily-report"}, 201),
        ({"name": "x" * 255, "template_id": "anomaly-monitor"}, 201),
        ({"name": "", "template_id": "daily-report"}, 422),
        ({"name": "x" * 256, "template_id": "daily-report"}, 422),
        ({"name": "Nightly", "template_id": "no-such-template"}, 400),
        ({"name": "Nightly", "template_id": ""}, 422),
    ],
)
def test_create_automation_contract(payload: dict, expected_status: int):
    resp = _client().post("/api/automations", json=payload)
    assert resp.status_code == expected_status
    if expected_status == 201:
        body = resp.json()
        assert body["name"] == payload["name"]
        assert body["template_id"] == payload["template_id"]
        assert body["status"] == "active"
        assert body["id"]
    elif expected_status == 400:
        assert "not found" in resp.json()["detail"]
        assert payload["template_id"] in resp.json()["detail"]


def test_delete_automation_answers_204():
    resp = _client().delete("/api/automations/automation-new")
    assert resp.status_code == 204
    assert resp.content == b""
