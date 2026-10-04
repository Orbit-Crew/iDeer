"""Single home for the role-to-permission ladder of canonical resources.

Resource Governance derives every actor's permission set from
:func:`role_permissions`, either directly or through :func:`actor_from_user`.
Account-state policies (e.g. missing or disabled users keep a READ floor) and
runtime context extraction stay at their call sites; only the role mapping
lives here.
"""

from __future__ import annotations

from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resources.service import ResourceAction, ResourceActor

_READ_FLOOR = frozenset({ResourceAction.READ})


def role_permissions(role: UserRole | str) -> frozenset[ResourceAction]:
    """Map a user role onto canonical resource permissions.

    Accepts ``UserRole`` members or their string values; an unknown string
    falls back to the READ floor (the viewer grant).
    """
    try:
        resolved = role if isinstance(role, UserRole) else UserRole(str(role))
    except ValueError:
        return _READ_FLOOR
    permissions = {ResourceAction.READ}
    if resolved in {UserRole.USER, UserRole.DEPARTMENT_ADMIN, UserRole.SUPER_ADMIN}:
        permissions.update({ResourceAction.USE, ResourceAction.WRITE})
    if resolved in {UserRole.DEPARTMENT_ADMIN, UserRole.SUPER_ADMIN}:
        permissions.add(ResourceAction.APPROVE)
    if resolved == UserRole.SUPER_ADMIN:
        permissions.update(ResourceAction)
    return frozenset(permissions)


def actor_from_user(user: UserModel) -> ResourceActor:
    """Build the canonical resource actor for a user via the shared ladder."""
    return ResourceActor(
        user_id=str(user.id),
        department_id=str(user.department_id) if user.department_id is not None else None,
        role=str(user.role),
        permissions=role_permissions(user.role),
        tool_groups=None,
    )
