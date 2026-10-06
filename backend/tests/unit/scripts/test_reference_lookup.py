from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "scripts" / "test_reference_lookup.py"

_spec = importlib.util.spec_from_file_location("ideer_test_reference_lookup", SCRIPT_PATH)
assert _spec is not None
assert _spec.loader is not None
lookup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lookup)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True, stderr=subprocess.DEVNULL)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")


# ---------------------------------------------------------------------------
# normalize: quote/slash collapsing so pathlib segment constructions match
# ---------------------------------------------------------------------------


def test_normalize_collapses_pathlib_segment_construction() -> None:
    content = 'content = (REPO_ROOT / "resources" / "skills" / "fault-zeroing" / "SKILL.md").read_text(encoding="utf-8")'
    normalized = lookup.normalize_source(content)
    assert "resources/skills/fault-zeroing/SKILL.md" in normalized


def test_normalize_keeps_plain_paths_intact() -> None:
    content = 'import { translations } from "@/core/i18n/locales/en-US";'
    normalized = lookup.normalize_source(content)
    assert "core/i18n/locales/en-US" in normalized


# ---------------------------------------------------------------------------
# matching: path suffix keys against normalized test content
# ---------------------------------------------------------------------------


def test_match_reports_test_that_reads_the_changed_file() -> None:
    changed = ["resources/skills/fault-zeroing/SKILL.md"]
    tests = {
        "backend/tests/unit/scripts/test_visual_outputs.py": ('content = (REPO_ROOT / "resources" / "skills" / "fault-zeroing" / "SKILL.md").read_text(encoding="utf-8")'),
        "backend/tests/unit/other_test.py": "unrelated = 1",
    }
    matches = lookup.match_references(changed, tests)
    assert matches[changed[0]] == [("backend/tests/unit/scripts/test_visual_outputs.py", "path")]


def test_match_strips_extension_for_import_specifiers() -> None:
    changed = ["frontend/src/core/i18n/locales/types.ts"]
    tests = {"frontend/tests/unit/i18n.test.ts": ('import { Translations } from "@/core/i18n/locales/types";')}
    matches = lookup.match_references(changed, tests)
    assert ("frontend/tests/unit/i18n.test.ts", "path") in matches[changed[0]]


def test_match_keys_never_drop_below_two_segments() -> None:
    changed = ["frontend/src/app/workspace/page.tsx"]
    tests = {"frontend/tests/unit/a.test.ts": "const name = 'page';"}
    assert lookup.match_references(changed, tests) == {}


def test_match_ignores_changed_test_files_as_lookup_targets() -> None:
    changed = ["backend/tests/unit/knowledge/test_documents.py"]
    tests = {"backend/tests/unit/knowledge/test_documents.py": "from app import x"}
    assert lookup.match_references(changed, tests) == {}


# ---------------------------------------------------------------------------
# surface mapping: curated prefix -> consumer suites without static references
# ---------------------------------------------------------------------------


def test_surface_mapping_reports_consumer_suites(tmp_path: Path) -> None:
    test_file = tmp_path / "frontend/tests/e2e/smoke/welcome.spec.ts"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("assert welcome renders", encoding="utf-8")
    surfaces = {
        "frontend/src/core/i18n/locales/": ["frontend/tests/e2e/smoke/**"],
    }
    matches = lookup.match_references(
        ["frontend/src/core/i18n/locales/en-US.ts"],
        {},
        root=tmp_path,
        surfaces=surfaces,
    )
    assert (
        "frontend/tests/e2e/smoke/welcome.spec.ts",
        "surface",
    ) in matches["frontend/src/core/i18n/locales/en-US.ts"]


def test_surface_mapping_ignores_unmapped_prefixes(tmp_path: Path) -> None:
    surfaces = {
        "frontend/src/core/i18n/locales/": ["frontend/tests/e2e/smoke/**"],
    }
    matches = lookup.match_references(["backend/app/agentplatform/actors.py"], {}, root=tmp_path, surfaces=surfaces)
    assert matches == {}


def test_load_surfaces_reads_the_seeded_json(tmp_path: Path) -> None:
    surfaces_dir = tmp_path / "scripts"
    surfaces_dir.mkdir()
    (surfaces_dir / "test_reference_surfaces.json").write_text(json.dumps({"surfaces": {"docs/": ["backend/tests/**"]}}), encoding="utf-8")
    assert lookup.load_surfaces(tmp_path) == {"docs/": ["backend/tests/**"]}


def test_load_surfaces_tolerates_a_missing_file(tmp_path: Path) -> None:
    assert lookup.load_surfaces(tmp_path) == {}


# ---------------------------------------------------------------------------
# changed-file collection: worktree candidate and explicit ranges
# ---------------------------------------------------------------------------


def test_changed_files_reads_worktree_changes_and_untracked(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    (tmp_path / "app.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("y = 1\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("z = 1\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")

    files = lookup.changed_files(tmp_path)

    assert "app.py" in files
    assert "new.py" in files
    assert "ignored.py" not in files


def test_changed_files_supports_explicit_commit_range(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "first.py").write_text("a = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "first")
    base = _git(tmp_path, "rev-parse", "HEAD").strip()
    (tmp_path / "second.py").write_text("b = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "second")

    files = lookup.changed_files(tmp_path, base=base, head="HEAD")

    assert "second.py" in files
    assert "first.py" not in files


def test_cli_reports_matches_as_json(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    module = tmp_path / "backend/app/models/user.py"
    module.parent.mkdir(parents=True)
    module.write_text("name = 'user'\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    module.write_text("name = 'user v2'\n", encoding="utf-8")
    test_file = tmp_path / "backend/tests/unit/test_user.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("from app.models.user import name\n", encoding="utf-8")

    out = subprocess.check_output(
        [
            "python3",
            str(REPO_ROOT / "scripts" / "test_reference_lookup.py"),
            "--root",
            str(tmp_path),
            "--json",
        ],
        text=True,
    )
    payload = json.loads(out)
    assert payload["matches"]["backend/app/models/user.py"] == [{"test": "backend/tests/unit/test_user.py", "kind": "path"}]


# ---------------------------------------------------------------------------
# regression fixtures: the two real misses this check exists for
# ---------------------------------------------------------------------------

TICKET_07_RANGE = ("8f0d61c16", "63cfed75c")
TICKET_09_RANGE = ("39d3ce3fa", "69b2130df")


def _range_available(base: str, head: str) -> bool:
    for ref in (base, head):
        probe = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--verify", f"{ref}^{{commit}}"],
            capture_output=True,
            check=False,
        )
        if probe.returncode != 0:
            return False
    return True


_SCAN_CACHE: dict[str, object] = {}


def _repo_scan() -> dict[str, str]:
    if "tests" not in _SCAN_CACHE:
        _SCAN_CACHE["tests"] = lookup.scan_test_files(REPO_ROOT)
    return _SCAN_CACHE["tests"]  # type: ignore[return-value]


@pytest.mark.skipif(
    not _range_available(*TICKET_07_RANGE),
    reason="architecture-deepening ticket 07 commits are not on this checkout",
)
def test_replays_ticket_07_fault_zeroing_miss() -> None:
    matches = lookup.match_references(
        lookup.changed_files(REPO_ROOT, base=TICKET_07_RANGE[0], head=TICKET_07_RANGE[1]),
        _repo_scan(),
        root=REPO_ROOT,
        surfaces=lookup.load_surfaces(REPO_ROOT),
    )
    reported = {entry for hits in matches.values() for entry in hits}
    assert (
        "backend/tests/unit/scripts/test_fault_zeroing_visual_outputs.py",
        "path",
    ) in reported


@pytest.mark.skipif(
    not _range_available(*TICKET_09_RANGE),
    reason="architecture-deepening ticket 09 commits are not on this checkout",
)
def test_replays_ticket_09_locale_miss() -> None:
    matches = lookup.match_references(
        lookup.changed_files(REPO_ROOT, base=TICKET_09_RANGE[0], head=TICKET_09_RANGE[1]),
        _repo_scan(),
        root=REPO_ROOT,
        surfaces=lookup.load_surfaces(REPO_ROOT),
    )
    reported = {entry for hits in matches.values() for entry in hits}
    assert (
        "frontend/tests/e2e/smoke/workbuddy-cascade.spec.ts",
        "surface",
    ) in reported
