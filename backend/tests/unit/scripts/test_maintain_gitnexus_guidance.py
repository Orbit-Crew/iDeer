from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "maintain_gitnexus_guidance.py"
REPO_ROOT = SCRIPT.parent.parent
GENERATED_TEMPLATE = Path(__file__).with_name("fixtures") / "gitnexus-generated-1.6.10.txt"
MANUAL_TEMPLATE = Path(__file__).with_name("fixtures") / "gitnexus-manual-before-compaction.txt"
PREVIOUS_COMPACT = Path(__file__).with_name("fixtures") / "gitnexus-compact-before-g3-fix.txt"


def _candidate(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_bytes((REPO_ROOT / "AGENTS.md").read_bytes())
    (tmp_path / "CLAUDE.md").write_bytes((REPO_ROOT / "CLAUDE.md").read_bytes())
    reference = tmp_path / "docs" / "agents" / "gitnexus-operations.md"
    reference.parent.mkdir(parents=True)
    reference.write_bytes((REPO_ROOT / "docs/agents/gitnexus-operations.md").read_bytes())


def _run(*args: str, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--repo-root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_public_check_rejects_root_over_budget(tmp_path: Path) -> None:
    markers = b"<!-- gitnexus:start -->\n<!-- gitnexus:end -->\n"
    (tmp_path / "AGENTS.md").write_bytes(b"x" * 8193 + markers)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "root budget" in result.stdout


def test_public_normalizer_compacts_only_a_recognized_block_and_is_idempotent(tmp_path: Path) -> None:
    generated = GENERATED_TEMPLATE.read_bytes()
    outside_before = b"Root rules before.\n"
    outside_after = b"\nRoot rules after.\n"
    source = tmp_path / "AGENTS.md"
    source.write_bytes(outside_before + generated + outside_after)

    first = subprocess.run(
        [sys.executable, str(SCRIPT), "--normalize", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    normalized = source.read_bytes()
    second = subprocess.run(
        [sys.executable, str(SCRIPT), "--normalize", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0
    assert second.returncode == 0
    assert normalized == source.read_bytes()
    assert normalized.startswith(outside_before)
    assert normalized.endswith(outside_after)
    assert len(normalized) < len(outside_before + generated + outside_after)
    assert b"**Doc-only commits are exempt from re-indexing.**" in normalized


def test_public_normalizer_rejects_unknown_future_generator_rule_without_partial_write(
    tmp_path: Path,
) -> None:
    source = tmp_path / "AGENTS.md"
    original = GENERATED_TEMPLATE.read_bytes().replace(
        b"<!-- gitnexus:end -->",
        b"## Future generator rules\n- MUST perform a newly introduced validation before editing.\n\n<!-- gitnexus:end -->",
    )
    source.write_bytes(original)

    result = _run("--normalize", root=tmp_path)

    assert result.returncode == 1
    assert "unrecognized generated" in result.stdout
    assert source.read_bytes() == original


def test_public_normalizer_accepts_the_frozen_project_template(tmp_path: Path) -> None:
    source = tmp_path / "AGENTS.md"
    manual_template = MANUAL_TEMPLATE.read_bytes()
    source.write_bytes(
        manual_template.replace(
            b"**AgentPlatform** (47479 symbols, 96181 relationships, 886 execution flows)",
            b"**Clone_42** (9,999 symbols, 22,222 relationships, 3 execution flows)",
        ).replace(b"gitnexus://repo/AgentPlatform/", b"gitnexus://repo/Clone_42/")
    )

    result = _run("--normalize", root=tmp_path)

    assert result.returncode == 0
    assert b"**Doc-only commits are exempt from re-indexing.**" in source.read_bytes()


def test_public_normalizer_migrates_only_the_previous_compact_block(tmp_path: Path) -> None:
    outside_before = b"Root rules before.\n"
    outside_after = b"\nRoot rules after.\n"
    source = tmp_path / "AGENTS.md"
    previous = PREVIOUS_COMPACT.read_bytes()
    original = outside_before + previous + outside_after
    source.write_bytes(original)

    result = _run("--normalize", root=tmp_path)

    normalized = source.read_bytes()
    assert result.returncode == 0
    assert normalized != original
    assert normalized.startswith(outside_before)
    assert normalized.endswith(outside_after)
    assert b"partial but not truncated" in normalized
    assert b"rerun incomplete or zero analysis until complete" in normalized
    assert _run("--normalize", root=tmp_path).returncode == 0
    assert source.read_bytes() == normalized


def test_public_normalizer_rejects_unknown_template_without_partial_write(tmp_path: Path) -> None:
    source = tmp_path / "AGENTS.md"
    original = b"before\n<!-- gitnexus:start -->\nnew format\n<!-- gitnexus:end -->\nafter\n"
    source.write_bytes(original)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--normalize", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "unrecognized generated" in result.stdout
    assert source.read_bytes() == original


def test_public_normalizer_rejects_missing_and_duplicate_markers_without_writes(tmp_path: Path) -> None:
    cases = {
        "missing": b"before\n<!-- gitnexus:start -->\nblock without end\nafter\n",
        "duplicate": (b"<!-- gitnexus:start -->\nfirst\n<!-- gitnexus:end -->\n<!-- gitnexus:start -->\nsecond\n<!-- gitnexus:end -->\n"),
    }

    for name, original in cases.items():
        candidate = tmp_path / name
        candidate.mkdir()
        source = candidate / "AGENTS.md"
        source.write_bytes(original)

        result = _run("--normalize", root=candidate)

        assert result.returncode == 1
        assert "exactly one GitNexus marker pair" in result.stdout
        assert source.read_bytes() == original


def test_public_check_accepts_compact_candidate(tmp_path: Path) -> None:
    _candidate(tmp_path)

    result = _run("--check", root=tmp_path)

    assert result.returncode == 0
    assert "check passed" in result.stdout


def test_public_check_reads_the_requested_revision(tmp_path: Path) -> None:
    _candidate(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "add", "AGENTS.md", "CLAUDE.md", "docs/agents/gitnexus-operations.md"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "valid guidance"], cwd=tmp_path, check=True)
    (tmp_path / "CLAUDE.md").write_text("working tree drift\n")

    revision_result = _run("--check", "--revision", "HEAD", root=tmp_path)
    worktree_result = _run("--check", root=tmp_path)

    assert revision_result.returncode == 0
    assert "revision HEAD" in revision_result.stdout
    assert worktree_result.returncode == 1
    assert "root mirror differs" in worktree_result.stdout


def test_public_check_rejects_managed_block_over_budget(tmp_path: Path) -> None:
    _candidate(tmp_path)
    root = tmp_path / "AGENTS.md"
    contents = root.read_bytes()
    marker = b"<!-- gitnexus:start -->\n"
    root.write_bytes(contents.replace(marker, marker + b" " * 950, 1))

    result = _run("--check", root=tmp_path)

    assert result.returncode == 1
    assert "managed block budget" in result.stdout


def test_public_check_rejects_unrecognized_block_drift(tmp_path: Path) -> None:
    _candidate(tmp_path)
    root = tmp_path / "AGENTS.md"
    updated = root.read_bytes().replace(b"Before editing a symbol", b"Extra note. Before editing a symbol")
    root.write_bytes(updated)
    (tmp_path / "CLAUDE.md").write_bytes(updated)

    result = _run("--check", root=tmp_path)

    assert result.returncode == 1
    assert "not the normalized compact template" in result.stdout


def test_public_check_reports_broken_anchor_missing_exemption_and_mirror_drift(tmp_path: Path) -> None:
    _candidate(tmp_path)
    reference = tmp_path / "docs/agents/gitnexus-operations.md"
    reference.write_text(reference.read_text().replace("## Operations", "## Commands"))
    root = tmp_path / "AGENTS.md"
    root.write_bytes(root.read_bytes().replace(b"**Doc-only commits are exempt from re-indexing.**", b"Documentation commits use the exception."))
    (tmp_path / "CLAUDE.md").write_text("stale mirror\n")

    result = _run("--check", root=tmp_path)

    assert result.returncode == 1
    assert "operational reference is missing anchor" in result.stdout
    assert "missing required rule: Doc-only commits are exempt from re-indexing." in result.stdout
    assert "root mirror differs" in result.stdout


def test_public_markdown_exemption_rejects_non_markdown_candidate_path(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    tracked = tmp_path / "README.md"
    tracked.write_text("base\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    (tmp_path / "config.yaml").write_text("changed\n")
    subprocess.run(["git", "add", "config.yaml"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "configuration"], cwd=tmp_path, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    result = _run("--check-exemption", "--base-ref", base, "--head-ref", head, root=tmp_path)

    assert result.returncode == 1
    assert "Markdown-only exemption rejected" in result.stdout
    assert "config.yaml" in result.stdout


def test_public_markdown_exemption_accepts_markdown_only_candidate(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    tracked = tmp_path / "README.md"
    tracked.write_text("base\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    tracked.write_text("updated\n")
    subprocess.run(["git", "commit", "-am", "markdown"], cwd=tmp_path, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    result = _run("--check-exemption", "--base-ref", base, "--head-ref", head, root=tmp_path)

    assert result.returncode == 0
    assert "Markdown-only exemption applies" in result.stdout


def test_public_markdown_exemption_rejects_renames_that_touch_code_and_accepts_markdown_rename(
    tmp_path: Path,
) -> None:
    cases = (
        ("code-to-markdown", "module.py", "reference.md", 1),
        ("markdown-to-code", "reference.md", "module.py", 1),
        ("markdown-to-markdown", "old.md", "new.md", 0),
    )

    for name, old_path, new_path, expected_status in cases:
        repo = tmp_path / name
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        source = repo / old_path
        source.write_text("content\n")
        subprocess.run(["git", "add", old_path], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        destination = repo / new_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "rename"], cwd=repo, check=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()

        result = _run("--check-exemption", "--base-ref", base, "--head-ref", head, root=repo)

        assert result.returncode == expected_status, name
        if expected_status:
            assert "Markdown-only exemption rejected" in result.stdout
        else:
            assert "Markdown-only exemption applies" in result.stdout
