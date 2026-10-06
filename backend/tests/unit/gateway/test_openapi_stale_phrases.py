"""Sweep the Gateway OpenAPI operation descriptions for stale copy-paste phrases.

FastAPI fills each operation's ``summary``/``description`` from the handler
function's docstring, so a docstring pasted from the wrong endpoint leaks
straight into the user-visible API documentation (Swagger UI / openapi.json).
Tickets 09 (0bc63c3de) and 14 (0b0b7a66d) cleaned five "knowledge regression"
copy-paste residues out of ``backend/app/gateway/routers/resources.py``; this
test keeps that class of residue from coming back.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Banned-phrase registry
# ---------------------------------------------------------------------------

# (banned_phrase, allowed_path_regex) pairs.
#
# Admission criterion for a NEW banned phrase: it must be a phrase that
# historically spread by copy-paste across handlers and surfaced in
# user-visible OpenAPI operation descriptions -- not a generic style
# preference. Precedent: tickets 09 (0bc63c3de) and 14 (0b0b7a66d) removed
# five "knowledge regression" residues of that kind from
# backend/app/gateway/routers/resources.py.
#
# allowed_path_regex is searched against the route path and carves out the
# legitimate uses of a phrase. "knowledge regression" is ACCURATE on the
# knowledge eval-case API family -- e.g. DELETE
# /api/resources/{resource_id}/eval-cases/{case_id} ("Delete one knowledge
# regression case.") -- so it is banned only OUTSIDE paths matching /eval.
BANNED_PHRASES: list[tuple[str, str]] = [
    ("knowledge regression", r".*/eval.*"),
]


def find_stale_phrases(routes: Iterable[Any]) -> list[str]:
    """Return one human-readable violation per banned-phrase hit.

    Each violation names the HTTP method, route path, offending phrase, and
    the full operation description so the responsible handler function is easy
    to locate. Duck-typed on ``path``/``methods``/``summary``/``description``
    so both real ``APIRoute`` entries and lightweight test fakes work; entries
    without any description text (Mount, APIWebSocketRoute, ...) are skipped.
    """
    violations: list[str] = []
    for route in routes:
        path = getattr(route, "path", None)
        summary = getattr(route, "summary", None) or ""
        description = getattr(route, "description", None) or ""
        if path is None or not (summary or description):
            continue
        methods = sorted(getattr(route, "methods", None) or ()) or ("<unknown>",)
        text = f"{summary}\n{description}"
        for phrase, allowed_path_pattern in BANNED_PHRASES:
            if phrase not in text:
                continue
            if re.search(allowed_path_pattern, path):
                continue
            for method in methods:
                violations.append(f"{method} {path}: banned phrase {phrase!r} in operation description (copy-paste residue?)\n  summary: {summary!r}\n  description: {description!r}")
    return violations


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def gateway_app():
    from app.gateway.app import create_app

    return create_app()


def _fake_route(
    path: str,
    summary: str = "",
    description: str = "",
    methods: tuple[str, ...] = ("GET",),
) -> SimpleNamespace:
    """Minimal duck-typed stand-in for fastapi.routing.APIRoute."""
    return SimpleNamespace(
        path=path,
        methods=frozenset(methods),
        summary=summary,
        description=description,
    )


# ---------------------------------------------------------------------------
# Helper unit tests (fake routes)
# ---------------------------------------------------------------------------


def test_helper_flags_residue_on_non_eval_path():
    """The ticket-09 first case: eval-case docstring pasted onto an import route."""
    residue = _fake_route(
        "/api/resources/import/skill",
        summary="Import a skill resource.",
        description="List knowledge regression cases.",
        methods=("POST",),
    )

    violations = find_stale_phrases([residue])

    assert len(violations) == 1
    message = violations[0]
    assert "POST" in message
    assert "/api/resources/import/skill" in message
    assert "knowledge regression" in message
    assert "List knowledge regression cases." in message


def test_helper_allows_eval_case_paths():
    """Legitimate use: the knowledge eval-case API family (resources.py delete_eval_case)."""
    legit = _fake_route(
        "/api/resources/{resource_id}/eval-cases/{case_id}",
        summary="Delete Eval Case",
        description="Delete one knowledge regression case.",
        methods=("DELETE",),
    )

    assert find_stale_phrases([legit]) == []


def test_helper_skips_routes_without_descriptions():
    """Entries without summary/description (Mount, APIWebSocketRoute, ...) are skipped."""
    mount_like = SimpleNamespace(path="/mnt/static")

    assert find_stale_phrases([mount_like]) == []


# ---------------------------------------------------------------------------
# Real-app OpenAPI sweep
# ---------------------------------------------------------------------------


def test_real_app_openapi_descriptions_are_clean(gateway_app):
    described = [route for route in gateway_app.routes if getattr(route, "summary", None) or getattr(route, "description", None)]
    # Guard against a vacuous sweep: the real app must expose descriptions.
    assert described, "sweep traversed no described routes"

    violations = find_stale_phrases(gateway_app.routes)

    assert not violations, "\n".join(violations)


def test_injected_residue_on_real_route_is_flagged(gateway_app, monkeypatch):
    """Inject a stale docstring onto a live route; the sweep must catch it."""
    target = next(route for route in gateway_app.routes if getattr(route, "path", "") == "/health")
    monkeypatch.setattr(target, "description", "List knowledge regression cases.", raising=False)

    violations = find_stale_phrases(gateway_app.routes)

    assert violations, "injected residue was not flagged"
    assert all("/health" in violation for violation in violations)
    assert all("knowledge regression" in violation for violation in violations)
