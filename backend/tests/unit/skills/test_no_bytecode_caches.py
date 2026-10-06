"""Guard against bytecode caches leaking into shipped skill packages.

Skill scripts are executed via ``spec_from_file_location`` (see
``backend/tests/unit/skills/skill_loader.py``). Any loader that runs with
bytecode writing enabled makes CPython drop ``__pycache__/*.pyc`` NEXT TO the
sources, i.e. inside the skill package; the package scan then fails those
directories. Ticket 02 fixed the loaders via ``sys.dont_write_bytecode``;
this test is the tree-level backstop so a recurrence cannot rely on memory.
"""

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]

CACHE_DIR_NAME = "__pycache__"
CACHE_FILE_SUFFIXES = {".pyc", ".pyo"}

SKILL_TREES = [
    REPO_ROOT / "skills",
    REPO_ROOT / "resources" / "skills",
]


def _bytecode_offenders(tree: Path) -> list[str]:
    """Return repo-relative bytecode cache paths under ``tree``, pruning caches."""
    offenders: list[str] = []
    for root, dirs, files in os.walk(tree):
        if CACHE_DIR_NAME in dirs:
            offenders.append(str(Path(root) / CACHE_DIR_NAME))
            dirs.remove(CACHE_DIR_NAME)
        offenders.extend(str(Path(root) / name) for name in files if Path(name).suffix in CACHE_FILE_SUFFIXES)
    return offenders


@pytest.mark.parametrize("tree", SKILL_TREES, ids=lambda tree: str(tree.relative_to(REPO_ROOT)))
def test_skill_tree_contains_no_bytecode_caches(tree):
    offenders = _bytecode_offenders(tree)
    assert not offenders, (
        "bytecode caches found under "
        f"{tree.relative_to(REPO_ROOT)}:\n  " + "\n  ".join(str(Path(p).relative_to(REPO_ROOT)) for p in offenders) + "\nCause: a loader imported or executed skill sources with bytecode "
        "writing enabled, so CPython wrote __pycache__/*.pyc next to the "
        "sources inside the skill package (see backend/tests/unit/skills/"
        "skill_loader.py; ticket 02)."
        "\nRemedy: delete the __pycache__ directories and *.pyc/*.pyo files, "
        "and keep the sys.dont_write_bytecode suppression in every loader "
        "that executes skill scripts."
    )
