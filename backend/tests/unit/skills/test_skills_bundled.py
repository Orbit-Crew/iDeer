"""Registry behavior for the bundled (resources/skills) skill tree.

The bundled-tree frontmatter sweep lives in
``backend/tests/unit/skills/test_public_skill_catalog.py`` — the resources
tree is the authoritative bundled skill set and is governed by the app-side
enterprise validator whose key set matches it. The upstream harness validator
(``deerflow.skills.validation``) keeps its own synthetic unit coverage in
``backend/tests/test_skills_validation.py``; it is an installer-path contract
and is deliberately not swept over the enterprise tree (its upstream key set
does not accept the enterprise governance keys, and the runtime never applies
it to the bundled tree). See the 2026-10-06 batch in
``docs/testing/test-migration-ledger.md``.
"""

from pathlib import Path

from deerflow.skills.storage import get_or_new_skill_storage


def test_runtime_registry_excludes_eval_fixture_skills(tmp_path: Path) -> None:
    """Nested ``evals/fixtures`` SKILL.md files must never register as skills.

    The registry walks the whole ``public/`` tree, so a fixture package nested
    under an owner skill's ``evals/fixtures/`` is physically present; the
    storage must filter it out by path rather than by trust in the tree shape.
    """
    skills_root = tmp_path / "skills"
    owner = skills_root / "public" / "fixture-owner"
    (owner / "evals" / "fixtures" / "blocked").mkdir(parents=True)
    (owner / "SKILL.md").write_text(
        "---\nname: fixture-owner\ndescription: Owner skill that must register.\n---\n",
        encoding="utf-8",
    )
    (owner / "evals" / "fixtures" / "blocked" / "SKILL.md").write_text(
        "---\nname: blocked-fixture\ndescription: Nested fixture skill that must not register.\n---\n",
        encoding="utf-8",
    )

    skills = get_or_new_skill_storage(skills_path=skills_root).load_skills(enabled_only=False)
    names = {skill.name for skill in skills}

    assert "fixture-owner" in names
    assert "blocked-fixture" not in names
    assert all("evals/fixtures" not in skill.skill_file.as_posix() for skill in skills)
