"""Content-bound Skill script authorization protocol (#122).

Custom Skill scripts are OFF by default. A grant is remembered per
(user, execution target, device, skill, script path) and binds the exact
content — the script SHA-256 and the declared environment fingerprint — plus
the scope it was approved for (AC2). Changed script bytes or a changed
declaration therefore require re-authorization, while a prose-only SKILL.md
edit (a new version whose script bytes and declaration are unchanged) keeps
the existing grant valid and must not re-ask. Grants never cross accounts or
devices: rows are owner-scoped and the device leg keeps its own registry, so
another account or device can never reuse an authorization (AC4). Directory
grants, Skill sharing, and built-in identity do not enter this decision —
only an explicit script grant does (AC3); the local runtime additionally
enforces its own DENY-first policy on the device.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.agentplatform.resources.skill_environment import (
    APPROVAL_REQUIRED,
    AUTHORIZATION_REVOKED,
    GRANTED,
    REAUTHORIZATION_REQUIRED,
    evaluate_grant,
    script_sha256,
)

__all__ = [
    "APPROVAL_REQUIRED",
    "AUTHORIZATION_REVOKED",
    "GRANTED",
    "REAUTHORIZATION_REQUIRED",
    "EXECUTION_TARGETS",
    "MAX_GRANTS_PER_USER",
    "SkillScriptAuthorizationRepository",
    "authorization_identity",
    "evaluate_grant",
    "script_sha256",
]

EXECUTION_TARGETS = ("server", "user_device")

MAX_GRANTS_PER_USER = 200


def authorization_identity(
    *,
    user_id: str,
    execution_target: str,
    device_id: str,
    skill_resource_id: str,
    script_path: str,
    script_digest: str,
    requirements_hash: str,
) -> str:
    """The deterministic grant identity for one bound content/scope pair."""
    payload = [user_id, execution_target, device_id, skill_resource_id, script_path, script_digest, requirements_hash]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class SkillScriptAuthorizationRepository:
    """Durable per-user script grants; owner-scoped like every preference row."""

    def __init__(self, sessions) -> None:
        self._sessions = sessions

    def _session(self):
        factory = self._sessions
        if callable(factory) and not hasattr(factory, "kw"):
            factory = factory()
        return factory()

    @staticmethod
    def _projection(row) -> dict[str, Any]:
        return {
            "authorization_id": row.id,
            "skill_resource_id": row.skill_resource_id,
            "slug": row.slug,
            "execution_target": row.execution_target,
            "device_id": row.device_id,
            "skill_version": int(row.skill_version),
            "skill_content_hash": row.skill_content_hash,
            "script_path": row.script_path,
            "script_sha256": row.script_sha256,
            "requirements_hash": row.requirements_hash,
            "created_at": row.created_at,
            "revoked_at": row.revoked_at,
        }

    async def active(
        self,
        user_id: str,
        skill_resource_id: str,
        *,
        execution_target: str,
        device_id: str,
        script_path: str,
    ) -> dict[str, Any] | None:
        from app.agentplatform.resource_models import SkillScriptAuthorizationRow

        async with self._session() as session:
            row = (
                await session.execute(
                    select(SkillScriptAuthorizationRow)
                    .where(
                        SkillScriptAuthorizationRow.user_id == user_id,
                        SkillScriptAuthorizationRow.skill_resource_id == skill_resource_id,
                        SkillScriptAuthorizationRow.execution_target == execution_target,
                        SkillScriptAuthorizationRow.device_id == device_id,
                        SkillScriptAuthorizationRow.script_path == script_path,
                    )
                    .order_by(SkillScriptAuthorizationRow.created_at.desc())
                )
            ).scalars().first()
            return self._projection(row) if row is not None else None

    async def grant(
        self,
        user_id: str,
        skill_resource_id: str,
        *,
        execution_target: str,
        device_id: str,
        slug: str,
        skill_version: int,
        skill_content_hash: str,
        script_path: str,
        script_digest: str,
        requirements_hash: str,
    ) -> dict[str, Any]:
        """Remember (or refresh) the one grant for this content/scope binding.

        A re-authorization after a content or scope change replaces the
        binding's row: the old bytes' grant no longer exists, only its audit
        trail does.
        """
        from app.agentplatform.resource_models import SkillScriptAuthorizationRow

        identity = authorization_identity(
            user_id=user_id,
            execution_target=execution_target,
            device_id=device_id,
            skill_resource_id=skill_resource_id,
            script_path=script_path,
            script_digest=script_digest,
            requirements_hash=requirements_hash,
        )
        now = datetime.now(UTC)
        async with self._session() as session, session.begin():
            row = (
                await session.execute(
                    select(SkillScriptAuthorizationRow).where(
                        SkillScriptAuthorizationRow.user_id == user_id,
                        SkillScriptAuthorizationRow.execution_target == execution_target,
                        SkillScriptAuthorizationRow.device_id == device_id,
                        SkillScriptAuthorizationRow.skill_resource_id == skill_resource_id,
                        SkillScriptAuthorizationRow.script_path == script_path,
                    )
                )
            ).scalars().first()
            if row is not None and row.id != identity:
                # Changed content or scope: the old binding's grant is replaced
                # by a new row under the new identity; it never carries over.
                await session.delete(row)
                await session.flush()
                row = None
            if row is None:
                count = len(
                    (
                        await session.execute(
                            select(SkillScriptAuthorizationRow.id).where(SkillScriptAuthorizationRow.user_id == user_id)
                        )
                    ).all()
                )
                if count >= MAX_GRANTS_PER_USER:
                    raise ValueError("script authorization limit reached")
                row = SkillScriptAuthorizationRow(
                    id=identity,
                    user_id=user_id,
                    skill_resource_id=skill_resource_id,
                    execution_target=execution_target,
                    device_id=device_id,
                    script_path=script_path,
                )
                session.add(row)
            row.slug = slug
            row.skill_version = int(skill_version)
            row.skill_content_hash = skill_content_hash
            row.script_sha256 = script_digest
            row.requirements_hash = requirements_hash
            row.created_at = now
            row.revoked_at = None
            row.updated_at = now
            await session.flush()
            return self._projection(row)

    async def revoke(self, user_id: str, authorization_id: str) -> bool:
        """Revoke one owned grant; revoked rows refuse future executions."""
        from app.agentplatform.resource_models import SkillScriptAuthorizationRow

        now = datetime.now(UTC)
        async with self._session() as session, session.begin():
            row = await session.get(SkillScriptAuthorizationRow, authorization_id)
            if row is None or row.user_id != user_id or row.revoked_at is not None:
                return False
            row.revoked_at = now
            row.updated_at = now
            return True

    async def list(self, user_id: str, skill_resource_id: str | None = None) -> list[dict[str, Any]]:
        from app.agentplatform.resource_models import SkillScriptAuthorizationRow

        clause = [SkillScriptAuthorizationRow.user_id == user_id]
        if skill_resource_id is not None:
            clause.append(SkillScriptAuthorizationRow.skill_resource_id == skill_resource_id)
        async with self._session() as session:
            rows = (
                await session.execute(
                    select(SkillScriptAuthorizationRow)
                    .where(*clause)
                    .order_by(SkillScriptAuthorizationRow.created_at.desc())
                )
            ).scalars()
            return [self._projection(row) for row in rows]
