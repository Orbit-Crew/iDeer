"""Skill trigger preferences: per-user matching metadata resolved Server-side (#121).

The Desktop only configures preferences through Server endpoints; matching
happens here, in the control plane, and rides the platform's existing
selection rules — no second trigger path is introduced:

- ONE preferred Skill per Run: ``ResourceService.create_run_snapshot`` carries
  exactly one ``selected_resource_id`` (snapshot ``selection_role`` is
  constrained to ``root``/``resolved``/``preferred``), so preference matching
  selects at most ``MAX_TRIGGERED_SKILLS_PER_RUN`` skills and reuses that
  existing seam.
- The Agent's resolved dependency closure stays the only candidate set: the
  closure walk already enforces caller visibility, published availability
  (``latest_version >= 1``) and the dependency edges, and a preference-selected
  Skill passes through the exact same validation. A preference can therefore
  never activate an invisible, unpublished, or out-of-closure Skill.
- An explicit user selection keeps the existing hard failure
  (``skill_outside_agent_closure``); a preference is auto-trigger metadata, so
  when its Skill fails the same validation the Run proceeds WITHOUT it and the
  skip is audited — an automatic trigger never fails a Run and never escalates.
- Preference matching only runs when the request carries no explicit Skill
  (``skill_resource_id``/``skill_name``): the existing explicit-selection rule
  always wins.

Field bounds are fixed protocol constants (documented here, pinned by tests);
they are not derived from any implementation output.
"""

from __future__ import annotations

import unicodedata
import uuid
from typing import Any

from sqlalchemy import select

# Fixed protocol bounds for one preference document.
MAX_KEYWORDS = 16
KEYWORD_MAX_CHARS = 64
MAX_APPLICABLE_AGENTS = 32
PRIORITY_MIN = -1000
PRIORITY_MAX = 1000
# How many Skill preferences one account may hold.
MAX_PREFERENCES_PER_USER = 200
# How much of the Run's user message text matching may read.
PREFERENCE_MESSAGE_LIMIT = 4000
# The existing run snapshot supports exactly one preferred Skill.
MAX_TRIGGERED_SKILLS_PER_RUN = 1


def normalize_text(value: str) -> str:
    """Unicode-normalized, case-folded, whitespace-collapsed matching text."""

    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return " ".join(normalized.split())


def keyword_hit(keywords: list[str], text: str) -> bool:
    """Whether any configured keyword occurs in the message text.

    Literal containment on the normalized texts: deterministic, locale-free,
    and the same NFKC casefold discipline the Skill catalog search uses.
    """

    if not isinstance(keywords, list):
        return False
    haystack = normalize_text(text)
    if not haystack:
        return False
    for keyword in keywords:
        needle = normalize_text(keyword) if isinstance(keyword, str) else ""
        if needle and needle in haystack:
            return True
    return False


def preference_matches(preference: dict[str, Any], *, agent_id: str, message_text: str) -> bool:
    """The documented matching rule for one preference against one Run.

    - ``enabled`` must be true;
    - ``applicable_agent_ids`` empty means every Agent, otherwise the Run's
      Agent resource id must be listed;
    - ``always_inject`` matches every message; empty keywords always inject
      (the preserved rule); otherwise any keyword hit matches.
    """

    if preference.get("enabled") is not True:
        return False
    agents = preference.get("applicable_agent_ids")
    if isinstance(agents, list) and agents and str(agent_id) not in {str(item) for item in agents}:
        return False
    keywords = preference.get("keywords")
    has_keywords = isinstance(keywords, list) and len(keywords) > 0
    if preference.get("always_inject") is True or not has_keywords:
        return True
    return keyword_hit(keywords, message_text)


def select_preference(
    preferences: list[dict[str, Any]],
    *,
    agent_id: str,
    message_text: str,
) -> dict[str, Any] | None:
    """Pick the ONE preference that triggers a Skill for this Run.

    Among matching preferences the highest ``priority`` wins; ties break on the
    lexicographically smaller ``skill_resource_id`` so the outcome is total and
    reproducible. At most one Skill is returned — the run snapshot's existing
    single-preferred-Skill capacity.
    """

    matches = [preference for preference in preferences if isinstance(preference, dict) and preference_matches(preference, agent_id=agent_id, message_text=message_text)]
    if not matches:
        return None
    return min(
        matches,
        key=lambda item: (-int(item.get("priority") or 0), str(item.get("skill_resource_id") or "")),
    )


def message_text_from_input(run_input: Any) -> str:
    """Extract the bounded user-message text of THIS run request.

    Only the messages carried by the run request participate: earlier thread
    history is re-sent by clients when they mean it. Unreadable shapes match
    nothing (empty text) — always-inject and empty-keyword preferences still
    apply, keyword preferences do not.
    """

    if not isinstance(run_input, dict):
        return ""
    messages = run_input.get("messages")
    if not isinstance(messages, (list, tuple)):
        return ""
    parts: list[str] = []
    total = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("type") or message.get("role") or "")
        if role not in {"human", "user"}:
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
            total += len(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                    total += len(item["text"])
        if total >= PREFERENCE_MESSAGE_LIMIT:
            break
    return "\n".join(parts)[:PREFERENCE_MESSAGE_LIMIT]


def validate_preference_document(*, keywords: Any, applicable_agent_ids: Any, priority: Any) -> tuple[list[str], list[str], int]:
    """Validate the client-supplied preference fields against the fixed bounds.

    Returns the normalized ``(keywords, applicable_agent_ids, priority)`` triple
    or raises ``ValueError`` with a fixed message (the router surfaces 422).
    """

    if not isinstance(keywords, list) or len(keywords) > MAX_KEYWORDS:
        raise ValueError(f"keywords must be a list of at most {MAX_KEYWORDS} strings")
    normalized_keywords: list[str] = []
    for keyword in keywords:
        if not isinstance(keyword, str):
            raise ValueError("keywords must be strings")
        stripped = unicodedata.normalize("NFKC", keyword).strip()
        if not stripped or len(stripped) > KEYWORD_MAX_CHARS:
            raise ValueError(f"each keyword must be 1..{KEYWORD_MAX_CHARS} characters")
        normalized_keywords.append(stripped)
    if len(set(normalize_text(item) for item in normalized_keywords)) != len(normalized_keywords):
        raise ValueError("keywords must not repeat")
    if not isinstance(applicable_agent_ids, list) or len(applicable_agent_ids) > MAX_APPLICABLE_AGENTS:
        raise ValueError(f"applicable_agent_ids must be a list of at most {MAX_APPLICABLE_AGENTS} agent ids")
    normalized_agents: list[str] = []
    for agent_id in applicable_agent_ids:
        if not isinstance(agent_id, str):
            raise ValueError("applicable_agent_ids must be strings")
        try:
            normalized = str(uuid.UUID(agent_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("applicable_agent_ids must contain canonical agent resource UUIDs") from exc
        if normalized in normalized_agents:
            raise ValueError("applicable_agent_ids must not repeat")
        normalized_agents.append(normalized)
    if isinstance(priority, bool) or not isinstance(priority, int) or not PRIORITY_MIN <= priority <= PRIORITY_MAX:
        raise ValueError(f"priority must be an integer in [{PRIORITY_MIN}, {PRIORITY_MAX}]")
    return normalized_keywords, normalized_agents, priority


class SkillTriggerPreferenceRepository:
    """Durable per-(user, skill) trigger preferences; owner-scoped by key.

    ``sessions`` accepts either the persistence sessionmaker or a zero-arg
    factory returning it (both shapes exist across the Gateway seams).
    """

    def __init__(self, sessions) -> None:
        self._sessions = sessions

    def _session(self):
        factory = self._sessions
        # A sessionmaker instance carries ``.kw``; a plain factory function
        # must be invoked once to yield the sessionmaker. Either way the
        # sessionmaker is called to open one session.
        if callable(factory) and not hasattr(factory, "kw"):
            factory = factory()
        return factory()

    @staticmethod
    def _row_projection(row) -> dict[str, Any]:
        return {
            "skill_resource_id": row.skill_resource_id,
            "enabled": bool(row.enabled),
            "keywords": list(row.keywords or []),
            "always_inject": bool(row.always_inject),
            "applicable_agent_ids": list(row.applicable_agent_ids or []),
            "priority": int(row.priority),
        }

    async def list(self, user_id: str) -> list[dict[str, Any]]:
        from app.agentplatform.resource_models import SkillTriggerPreferenceRow

        async with self._session() as session:
            rows = (await session.execute(select(SkillTriggerPreferenceRow).where(SkillTriggerPreferenceRow.user_id == user_id).order_by(SkillTriggerPreferenceRow.priority.desc(), SkillTriggerPreferenceRow.skill_resource_id))).scalars()
            return [self._row_projection(row) for row in rows]

    async def get(self, user_id: str, skill_resource_id: str) -> dict[str, Any] | None:
        from app.agentplatform.resource_models import SkillTriggerPreferenceRow

        async with self._session() as session:
            row = await session.get(SkillTriggerPreferenceRow, (user_id, skill_resource_id))
            return self._row_projection(row) if row is not None else None

    async def count(self, user_id: str) -> int:
        from sqlalchemy import func

        from app.agentplatform.resource_models import SkillTriggerPreferenceRow

        async with self._session() as session:
            return int((await session.execute(select(func.count()).select_from(SkillTriggerPreferenceRow).where(SkillTriggerPreferenceRow.user_id == user_id))).scalar_one())

    async def upsert(
        self,
        user_id: str,
        skill_resource_id: str,
        *,
        enabled: bool,
        keywords: list[str],
        always_inject: bool,
        applicable_agent_ids: list[str],
        priority: int,
    ) -> dict[str, Any]:
        from datetime import UTC, datetime

        from app.agentplatform.resource_models import SkillTriggerPreferenceRow

        async with self._session() as session, session.begin():
            row = await session.get(SkillTriggerPreferenceRow, (user_id, skill_resource_id))
            if row is None:
                row = SkillTriggerPreferenceRow(user_id=user_id, skill_resource_id=skill_resource_id)
                session.add(row)
            row.enabled = bool(enabled)
            row.keywords = list(keywords)
            row.always_inject = bool(always_inject)
            row.applicable_agent_ids = list(applicable_agent_ids)
            row.priority = int(priority)
            row.updated_at = datetime.now(UTC)
            await session.flush()
            return self._row_projection(row)

    async def delete(self, user_id: str, skill_resource_id: str) -> bool:
        from sqlalchemy import delete

        from app.agentplatform.resource_models import SkillTriggerPreferenceRow

        async with self._session() as session:
            deleted = await session.execute(
                delete(SkillTriggerPreferenceRow).where(
                    SkillTriggerPreferenceRow.user_id == user_id,
                    SkillTriggerPreferenceRow.skill_resource_id == skill_resource_id,
                )
            )
            await session.commit()
            return bool(deleted.rowcount)
