"""Regression tests for the skill_loader helper used by the skill-script suites.

``load()`` executes ``resources/skills/<skill>/scripts/generate.py`` in place.
The default SourceFileLoader writes ``__pycache__/*.pyc`` NEXT TO that source,
i.e. into a shipped skill package; the skill review scan
(``backend/tests/test_skill_review_core.py``) then fails those directories as
"not NUL-free UTF-8" and the pr-standard backend lane goes red. The loader
must not write anything into the package.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_loader import REPO_ROOT, load  # noqa: E402

SKILL_NAMES = ["image-generation", "music-generation", "podcast-generation", "video-generation"]


def _scripts_dir(skill_name: str) -> Path:
    return REPO_ROOT / "resources" / "skills" / skill_name / "scripts"


@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_load_writes_no_bytecode_cache_into_skill_package(skill_name):
    scripts_dir = _scripts_dir(skill_name)
    cache_dir = scripts_dir / "__pycache__"
    assert not cache_dir.exists(), f"pre-existing cache would mask this test; remove {cache_dir}"

    module = load(skill_name)

    assert module is not None
    assert not cache_dir.exists()
    assert not list(scripts_dir.glob("*.pyc"))
