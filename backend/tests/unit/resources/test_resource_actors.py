"""Regression tests for the single role-to-permission ladder (resources.actors)."""

from __future__ import annotations

from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resources.actors import actor_from_user, role_permissions
from app.agentplatform.resources.service import ResourceAction


def _user(role: UserRole | str, *, department_id: str | None = None) -> UserModel:
    return UserModel(
        id="user-1",
        username="ladder",
        role=role,
        department_id=department_id,
    )


def test_viewer_role_gets_read_only() -> None:
    assert role_permissions(UserRole.VIEWER) == frozenset({ResourceAction.READ})


def test_user_role_gets_read_use_write() -> None:
    assert role_permissions(UserRole.USER) == frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE})


def test_department_admin_role_gets_approve() -> None:
    assert role_permissions(UserRole.DEPARTMENT_ADMIN) == frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE, ResourceAction.APPROVE})


def test_super_admin_role_gets_every_action() -> None:
    assert role_permissions(UserRole.SUPER_ADMIN) == frozenset(ResourceAction)


def test_string_roles_match_enum_roles() -> None:
    for role in UserRole:
        assert role_permissions(role.value) == role_permissions(role)


def test_unknown_string_role_falls_back_to_read() -> None:
    assert role_permissions("unknown") == frozenset({ResourceAction.READ})
    assert role_permissions("") == frozenset({ResourceAction.READ})


def test_actor_from_user_carries_identity_fields() -> None:
    actor = actor_from_user(_user(UserRole.DEPARTMENT_ADMIN, department_id="dept-7"))
    assert actor.user_id == "user-1"
    assert actor.department_id == "dept-7"
    assert actor.role == "department_admin"
    assert actor.tool_groups is None
    assert actor.permissions == role_permissions(UserRole.DEPARTMENT_ADMIN)


def test_actor_from_user_defaults_department_and_grants_read_floor() -> None:
    actor = actor_from_user(_user(UserRole.VIEWER))
    assert actor.department_id is None
    assert actor.role == "viewer"
    assert actor.can(ResourceAction.READ)
    assert not actor.can(ResourceAction.WRITE)
