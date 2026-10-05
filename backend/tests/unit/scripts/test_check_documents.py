"""External behavior tests for scripts/check_documents.py (ticket 02).

The checker is read-only: it validates document contracts on a candidate
(worktree or a selected revision) against docs/governance/document-policy.json.
Tests build synthetic git repositories in tmp_path; the real repository is
never touched.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_documents.py"
SPEC = importlib.util.spec_from_file_location("check_documents", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check = importlib.util.module_from_spec(SPEC)
sys.modules["check_documents"] = check
SPEC.loader.exec_module(check)

POLICY_PATH = "docs/governance/document-policy.json"

CLEAN_MD = """---
id: clean-doc
kind: reference
status: current
owner: maintainers
scope: checker-tests
last-verified: 2026-10-04
verified-against: commit 9fba97b97
---

# Clean doc

See [other][other-ref], [anchors](other.md#other-doc), [top](#clean-doc)
and [site](https://example.com/docs).

![logo](../vendor/logo.png)

[other-ref]: other.md
"""

OTHER_MD = """---
id: other-doc
kind: index
status: draft
owner: maintainers
scope: checker-tests
---

# Other doc

Body text.
"""

VENDOR_README = "upstream readme body\n"
LOGO_PNG = b"\x89PNG\r\n\x1a\nfake-bytes\n"
SCRATCH_NOTES = "scratch notes\n"
ARCHIVE_OLD = "archived note\n"
AGENTS_MD = "# Rules\n\nGuidance source for mirrors.\n"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _row(path: str, classification: str, content: bytes, protected: bool = False) -> dict:
    return {
        "path": path,
        "classification": classification,
        "protected": protected,
        "sha256": _sha256(content),
        "lines": content.decode("utf-8").count("\n"),
    }


def _base_files() -> dict[str, bytes]:
    return {
        "docs/clean.md": CLEAN_MD.encode("utf-8"),
        "docs/other.md": OTHER_MD.encode("utf-8"),
        "vendor/README.md": VENDOR_README.encode("utf-8"),
        "vendor/logo.png": LOGO_PNG,
        "scratch/notes.md": SCRATCH_NOTES.encode("utf-8"),
        "archive/old.md": ARCHIVE_OLD.encode("utf-8"),
        "AGENTS.md": AGENTS_MD.encode("utf-8"),
    }


def _base_policy(files: dict[str, bytes]) -> dict:
    inventory = [
        _row("AGENTS.md", "agent-guidance", files["AGENTS.md"]),
        _row("docs/clean.md", "engineering-body-review", files["docs/clean.md"]),
        _row("docs/other.md", "engineering-body-review", files["docs/other.md"]),
        _row("vendor/README.md", "protected-baseline", files["vendor/README.md"], protected=True),
    ]
    return {
        "schema_version": 1,
        "policy_id": "checker-test-policy",
        "baseline": {"commit": "f" * 40, "baseline_delta": []},
        "inventory": {
            "count": len(inventory),
            "classification_counts": {
                "agent-guidance": 1,
                "engineering-body-review": 2,
                "protected-baseline": 1,
            },
            "files": inventory,
        },
        "exclusions": {
            "total_tracked_markdown": 6,
            "excluded_count": 2,
            "categories": [
                {"id": "scratch", "count": 1, "reason": "scratch pad", "paths": ["scratch/notes.md"]},
                {"id": "archive", "count": 1, "reason": "archive", "path_prefixes": ["archive/"]},
            ],
        },
        "protected_files": {
            "count": 1,
            "source": "test baseline",
            "outside_inventory_count": 0,
            "rule": "protected upstream and immutable baseline files",
            "fingerprints": [{"path": "vendor/README.md", "sha256": _sha256(files["vendor/README.md"])}],
        },
        "authority_topics": [
            {
                "topic": "checker-topic",
                "scope": "checker tests",
                "authorities": ["docs/clean.md"],
                "declared_by": "test",
            }
        ],
    }


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _materialize(root: Path, files: dict[str, bytes], policy: dict, commit: bool = True) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for relative, data in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    policy_file = root / POLICY_PATH
    policy_file.parent.mkdir(parents=True, exist_ok=True)
    policy_file.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    _git(root, "-c", "init.defaultBranch=main", "init", "-q")
    _git(root, "add", "-A")
    if commit:
        _git(root, "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-qm", "fixture")


def _materialize_base(root: Path) -> dict:
    files = _base_files()
    _materialize(root, files, _base_policy(files))
    return files


def _invoke(capsys, root: Path, *args: str) -> tuple[int, str, str]:
    code = check.main(["--repo-root", str(root), *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _invoke_json(capsys, root: Path, *args: str) -> tuple[int, dict, str]:
    code, out, err = _invoke(capsys, root, "--json", *args)
    return code, json.loads(out), err


def _findings_by_rule(payload: dict, rule: str) -> list[dict]:
    return [finding for finding in payload["findings"] if finding["rule"] == rule]


# --- Slice 1: CLI skeleton, exit codes, JSON output, metadata rules ---


def test_missing_repo_root_reports_operational_error(tmp_path: Path, capsys) -> None:
    code, out, err = _invoke(capsys, tmp_path / "does-not-exist")
    assert code == 2
    assert "ERROR" in err
    assert out == ""


def test_unresolvable_revision_reports_operational_error(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    code, out, err = _invoke(capsys, tmp_path, "--revision", "no-such-revision")
    assert code == 2
    assert "ERROR" in err
    assert out == ""


def test_missing_policy_reports_operational_error(tmp_path: Path, capsys) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "-c", "init.defaultBranch=main", "init", "-q")
    code, out, err = _invoke(capsys, root)
    assert code == 2
    assert "ERROR" in err


def test_malformed_policy_reports_operational_error(tmp_path: Path, capsys) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "-c", "init.defaultBranch=main", "init", "-q")
    policy_file = root / POLICY_PATH
    policy_file.parent.mkdir(parents=True)
    policy_file.write_text("{not json", encoding="utf-8")
    _git(root, "add", "-A")
    code, out, err = _invoke(capsys, root)
    assert code == 2
    assert "ERROR" in err


def test_clean_candidate_exits_zero(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    code, out, err = _invoke(capsys, tmp_path)
    assert code == 0, out + err
    assert err == ""
    assert "worktree" in out


def test_json_clean_reports_candidate_counts_and_empty_findings(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    code, payload, err = _invoke_json(capsys, tmp_path)
    assert code == 0
    assert payload["candidate"]["mode"] == "worktree"
    assert payload["candidate"]["revision"] is None
    assert payload["candidate"]["head"]
    assert payload["counts"]["findings"] == 0
    assert payload["findings"] == []


def test_metadata_missing_field_is_reported_with_stable_rule(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("owner: maintainers\n", "").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "metadata-shape")
    assert len(hits) == 1
    assert hits[0]["file"] == "docs/clean.md"
    assert hits[0]["severity"] == "error"
    assert "owner" in hits[0]["reason"]
    assert hits[0]["location"]


def test_missing_frontmatter_block_is_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/other.md"] = b"# Other doc\n\nNo frontmatter here.\n"
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "metadata-shape")
    assert len(hits) == 1
    assert hits[0]["file"] == "docs/other.md"
    assert "frontmatter" in hits[0]["reason"]


def test_invalid_status_value_is_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/other.md"] = OTHER_MD.replace("status: draft", "status: finished").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "metadata-shape")
    assert len(hits) == 1
    assert "status" in hits[0]["reason"]


def test_json_finding_objects_carry_rule_severity_file_location_reason(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("owner: maintainers\n", "").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    finding = payload["findings"][0]
    assert set(finding) == {"rule", "severity", "file", "location", "reason"}


def test_counts_by_rule_and_totals_are_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("owner: maintainers\n", "").encode("utf-8")
    files["docs/other.md"] = OTHER_MD.replace("status: draft", "status: finished").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    assert payload["counts"]["findings"] == 2
    assert payload["counts"]["by_rule"] == {"metadata-shape": 2}
    assert payload["counts"]["errors"] == 2


def test_agent_guidance_files_are_exempt_from_frontmatter(tmp_path: Path, capsys) -> None:
    # The base fixture already contains AGENTS.md (agent-guidance) without
    # frontmatter; the clean run must stay clean because rule files and their
    # generated mirrors do not require frontmatter.
    _materialize_base(tmp_path)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 0
    assert _findings_by_rule(payload, "metadata-shape") == []


# --- Slice 2: revision isolation and read-only behavior ---


def _snapshot(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): _sha256(path.read_bytes()) for path in sorted(root.rglob("*")) if path.is_file() and ".git" not in path.relative_to(root).parts}


def test_revision_mode_ignores_worktree_only_content_changes(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    broken = CLEAN_MD.replace("owner: maintainers\n", "")
    (tmp_path / "docs/clean.md").write_text(broken, encoding="utf-8")
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    code, payload, _ = _invoke_json(capsys, tmp_path, "--revision", "HEAD")
    assert code == 0, json.dumps(payload, ensure_ascii=False)[:2000]
    assert payload["candidate"]["mode"] == "revision"
    assert payload["candidate"]["revision"] == "HEAD"
    assert payload["counts"]["findings"] == 0


def test_revision_mode_ignores_worktree_only_deletions(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    (tmp_path / "docs/other.md").unlink()
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    assert _findings_by_rule(payload, "inventory-coverage")
    code, payload, _ = _invoke_json(capsys, tmp_path, "--revision", "HEAD")
    assert code == 0
    assert payload["counts"]["findings"] == 0


def test_revision_mode_reads_policy_from_the_revision(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    # Uncommitted worktree edit drops the docs/other.md inventory row.
    files = _base_files()
    reduced = _base_policy(files)
    reduced["inventory"]["files"] = [row for row in reduced["inventory"]["files"] if row["path"] != "docs/other.md"]
    reduced["inventory"]["count"] = 3
    reduced["inventory"]["classification_counts"] = {
        "agent-guidance": 1,
        "engineering-body-review": 1,
        "protected-baseline": 1,
    }
    _materialize_policy_only(tmp_path, reduced)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    assert _findings_by_rule(payload, "inventory-coverage")
    # The committed policy still covers docs/other.md; revision mode must use it.
    code, payload, _ = _invoke_json(capsys, tmp_path, "--revision", "HEAD")
    assert code == 0, json.dumps(payload, ensure_ascii=False)[:2000]


def _materialize_policy_only(root: Path, policy: dict) -> None:
    (root / POLICY_PATH).write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    _git(root, "add", "-A")


def test_revision_mode_accepts_committed_sha(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True).stdout.decode().strip()
    (tmp_path / "docs/clean.md").write_text("worktree noise\n", encoding="utf-8")
    code, payload, _ = _invoke_json(capsys, tmp_path, "--revision", head)
    assert code == 0
    assert payload["candidate"]["head"] == head


def test_checker_never_mutates_the_worktree(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("owner: maintainers\n", "").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    before = _snapshot(tmp_path)
    code, _, _ = _invoke(capsys, tmp_path)
    assert code == 1
    after = _snapshot(tmp_path)
    assert before == after


# --- Slice 3: remaining rule groups ---


def test_inventory_uncovered_tracked_markdown_is_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/extra.md"] = b"# Extra\n\nUnregistered document.\n"
    policy = _base_policy(files)
    policy["exclusions"]["total_tracked_markdown"] = 7
    _materialize(tmp_path, files, policy)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "inventory-coverage")
    assert [hit["file"] for hit in hits] == ["docs/extra.md"]


def test_inventory_missing_candidate_path_is_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    policy = _base_policy(files)
    ghost = _row("docs/ghost.md", "engineering-body-review", b"ghost\n")
    policy["inventory"]["files"].append(ghost)
    policy["inventory"]["count"] = 5
    policy["inventory"]["classification_counts"]["engineering-body-review"] = 3
    _materialize(tmp_path, files, policy)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "inventory-coverage")
    assert [hit["file"] for hit in hits if hit["file"] != POLICY_PATH] == ["docs/ghost.md"]


def test_excluded_prefix_paths_need_no_inventory_row(tmp_path: Path, capsys) -> None:
    # archive/old.md is covered by the archive/ prefix exclusion; scratch/notes.md
    # by an exact exclusion path. The clean fixture already proves both.
    _materialize_base(tmp_path)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 0
    assert _findings_by_rule(payload, "inventory-coverage") == []


def test_protected_fingerprint_mismatch_is_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    policy = _base_policy(files)
    files["vendor/README.md"] = b"tampered upstream body\n"
    _materialize(tmp_path, files, policy)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "protected-fingerprint-mismatch")
    assert len(hits) == 1
    assert hits[0]["file"] == "vendor/README.md"
    assert "fingerprint mismatch" in hits[0]["reason"]


def test_protected_file_missing_from_candidate_is_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    policy = _base_policy(files)
    del files["vendor/README.md"]
    _materialize(tmp_path, files, policy)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "protected-fingerprint-mismatch")
    assert len(hits) == 1
    assert "missing" in hits[0]["reason"]


def test_duplicate_document_ids_are_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/other.md"] = OTHER_MD.replace("id: other-doc", "id: clean-doc").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "duplicate-id")
    assert len(hits) == 1
    assert hits[0]["file"] == "docs/other.md"
    assert "clean-doc" in hits[0]["reason"]


def test_duplicate_authority_topic_declarations_are_reported(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    policy = json.loads((tmp_path / POLICY_PATH).read_text(encoding="utf-8"))
    policy["authority_topics"].append({"topic": "checker-topic", "scope": "checker tests", "authorities": ["docs/other.md"], "declared_by": "test"})
    _materialize_policy_only(tmp_path, policy)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "authority-conflict")
    assert len(hits) == 1
    assert "checker-topic" in hits[0]["reason"]


def test_same_authority_path_under_same_scope_is_reported(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    policy = json.loads((tmp_path / POLICY_PATH).read_text(encoding="utf-8"))
    policy["authority_topics"].append({"topic": "second-topic", "scope": "checker tests", "authorities": ["docs/clean.md"], "declared_by": "test"})
    _materialize_policy_only(tmp_path, policy)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "authority-conflict")
    assert len(hits) == 1
    assert "docs/clean.md" in hits[0]["reason"]


def test_distinct_scopes_may_share_an_authority_path(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    policy = json.loads((tmp_path / POLICY_PATH).read_text(encoding="utf-8"))
    policy["authority_topics"].append({"topic": "second-topic", "scope": "upstream implementation", "authorities": ["docs/clean.md"], "declared_by": "test"})
    _materialize_policy_only(tmp_path, policy)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 0
    assert _findings_by_rule(payload, "authority-conflict") == []


def test_broken_local_link_is_reported_with_line_location(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("[other-ref]: other.md", "[other-ref]: missing.md").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "broken-link")
    assert len(hits) == 1
    assert hits[0]["file"] == "docs/clean.md"
    assert hits[0]["location"].isdigit()
    assert "missing.md" in hits[0]["reason"]


def test_broken_anchor_is_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("(other.md#other-doc)", "(other.md#no-such-section)").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "broken-anchor")
    assert len(hits) == 1
    assert hits[0]["file"] == "docs/clean.md"
    assert "no-such-section" in hits[0]["reason"]


def test_links_inside_code_spans_and_fences_are_ignored(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = (CLEAN_MD + "Fenced example:\n\n```markdown\n[fake](missing.md)\n```\n\nInline `code [fake](missing.md)` span.\n").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 0
    assert _findings_by_rule(payload, "broken-link") == []


def test_directory_links_with_trailing_slash_are_accepted(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = (CLEAN_MD + "Browse [docs](../docs/) and [vendor](../vendor/).\n").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 0
    assert _findings_by_rule(payload, "broken-link") == []


def test_duplicate_headings_produce_numbered_anchors(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/other.md"] = (OTHER_MD + "\n## Repeat\n\nbody\n\n## Repeat\n").encode("utf-8")
    files["docs/clean.md"] = (CLEAN_MD + "Jump to [first](other.md#repeat) and [second](other.md#repeat-1).\n").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 0
    assert _findings_by_rule(payload, "broken-anchor") == []


def test_malformed_external_url_is_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("(https://example.com/docs)", "(https://)").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "broken-link")
    assert len(hits) == 1
    assert "https://" in hits[0]["reason"]


def test_route_entries_must_reach_existing_targets(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    policy = json.loads((tmp_path / POLICY_PATH).read_text(encoding="utf-8"))
    policy["task_routes"] = [
        {
            "route": "docs/clean.md",
            "targets": ["docs/other.md", "docs/ghost.md"],
            "validation": "docs/testing-lane.md",
        }
    ]
    _materialize_policy_only(tmp_path, policy)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "route-incomplete")
    assert len(hits) == 2
    assert {hit["file"] for hit in hits} == {"docs/clean.md"}
    reasons = " ".join(hit["reason"] for hit in hits)
    assert "docs/ghost.md" in reasons and "docs/testing-lane.md" in reasons


def test_complete_route_entries_report_nothing(tmp_path: Path, capsys) -> None:
    _materialize_base(tmp_path)
    policy = json.loads((tmp_path / POLICY_PATH).read_text(encoding="utf-8"))
    policy["task_routes"] = [{"route": "docs/clean.md", "targets": ["docs/other.md"], "validation": "docs/other.md"}]
    _materialize_policy_only(tmp_path, policy)
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 0
    assert _findings_by_rule(payload, "route-incomplete") == []


def test_superseded_document_requires_replacement(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/other.md"] = OTHER_MD.replace("status: draft", "status: superseded").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "supersession-invalid")
    assert len(hits) == 1
    assert hits[0]["file"] == "docs/other.md"
    assert "superseded-by" in hits[0]["reason"]


def test_valid_supersession_with_back_reference_reports_nothing(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/other.md"] = OTHER_MD.replace(
        "status: draft",
        "status: superseded\nsuperseded-by: docs/clean.md",
    ).encode("utf-8")
    files["docs/clean.md"] = CLEAN_MD.replace("verified-against: commit 9fba97b97", "verified-against: commit 9fba97b97\nsupersedes: docs/other.md").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 0
    assert _findings_by_rule(payload, "supersession-invalid") == []


def test_supersession_missing_back_reference_is_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/other.md"] = OTHER_MD.replace(
        "status: draft",
        "status: superseded\nsuperseded-by: docs/clean.md",
    ).encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "supersession-invalid")
    assert len(hits) == 1
    assert "supersedes" in hits[0]["reason"]
    assert hits[0]["file"] == "docs/clean.md"


def test_supersession_cycles_are_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace(
        "status: current",
        "status: superseded\nsuperseded-by: docs/other.md",
    ).encode("utf-8")
    files["docs/other.md"] = OTHER_MD.replace(
        "status: draft",
        "status: superseded\nsuperseded-by: docs/clean.md",
    ).encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "supersession-invalid")
    assert {hit["file"] for hit in hits} == {"docs/clean.md", "docs/other.md"}
    assert any("cycle" in hit["reason"] for hit in hits)


def test_current_reference_requires_verification_evidence(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("last-verified: 2026-10-04\n", "").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "evidence-missing")
    assert len(hits) == 1
    assert hits[0]["file"] == "docs/clean.md"
    assert "last-verified" in hits[0]["reason"]


def test_current_reference_requires_verified_against(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("verified-against: commit 9fba97b97\n", "").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "evidence-missing")
    assert len(hits) == 1
    assert "verified-against" in hits[0]["reason"]


def test_invalid_last_verified_date_is_reported(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("last-verified: 2026-10-04", "last-verified: recently").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "evidence-missing")
    assert len(hits) == 1
    assert "last-verified" in hits[0]["reason"]


def test_findings_are_sorted_and_deterministic(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("owner: maintainers\n", "").encode("utf-8")
    files["docs/other.md"] = OTHER_MD.replace("id: other-doc", "id: clean-doc").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    first = _invoke_json(capsys, tmp_path)
    second = _invoke_json(capsys, tmp_path)
    assert first[0] == second[0] == 1
    assert first[1] == second[1]
    keys = [(finding["rule"], finding["file"], finding["location"]) for finding in first[1]["findings"]]
    assert keys == sorted(keys)


def test_text_output_lists_findings_and_summary(tmp_path: Path, capsys) -> None:
    files = _base_files()
    files["docs/clean.md"] = CLEAN_MD.replace("owner: maintainers\n", "").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, out, err = _invoke(capsys, tmp_path)
    assert code == 1
    assert "metadata-shape" in out
    assert "findings=1" in out


# --- Ticket 04 slice 1: stale package paths in current documents ---

STALE_PATH_APPENDIX = "vLLM 推理模型应使用 `ideer.models.vllm_provider:VllmChatModel`。\n\n官网见 https://ideer.tech ，历史命令仅作展示：\n\n```bash\npython -m ideer.scripts.resource_catalog_v2 audit\n```\n"


def test_current_document_with_stale_package_path_is_reported(tmp_path: Path, capsys) -> None:
    # The inline-code old package path is the document's own claim about the
    # current system and is reported. The URL form (ideer.tech), the fenced
    # command, and the draft document are outside the rule.
    files = _base_files()
    files["docs/clean.md"] = (CLEAN_MD + STALE_PATH_APPENDIX).encode("utf-8")
    files["docs/other.md"] = (OTHER_MD + "Draft notes cite ideer.config too.\n").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "stale-package-path")
    assert [hit["file"] for hit in hits] == ["docs/clean.md"]
    assert hits[0]["severity"] == "error"
    assert hits[0]["location"].isdigit()
    assert "ideer.models.vllm_provider" in hits[0]["reason"]


# --- Ticket 04 slice 2: blockquote metadata residue beside frontmatter ---


def test_frontmatter_document_with_bold_blockquote_metadata_is_reported(tmp_path: Path, capsys) -> None:
    # The bold Chinese-key status/date blockquotes are the pre-frontmatter
    # header format; with frontmatter present they are migration residue.
    # The sanctioned lowercase-key header (docs/README.md style) and
    # documents without frontmatter are outside the rule.
    files = _base_files()
    files["docs/other.md"] = OTHER_MD.replace(
        "# Other doc\n",
        "# Other doc\n\n> **状态**: archived\n> **日期**: 2026-09-01\n",
    ).encode("utf-8")
    files["docs/clean.md"] = (CLEAN_MD + "\n> status: current<br>\n").encode("utf-8")
    files["AGENTS.md"] = (AGENTS_MD + "\n> **状态**: none\n").encode("utf-8")
    _materialize(tmp_path, files, _base_policy(files))
    code, payload, _ = _invoke_json(capsys, tmp_path)
    assert code == 1
    hits = _findings_by_rule(payload, "blockquote-metadata-residue")
    assert [hit["file"] for hit in hits] == ["docs/other.md", "docs/other.md"]
    assert all(hit["severity"] == "error" and hit["location"].isdigit() for hit in hits)
    keys = " ".join(hit["reason"] for hit in hits)
    assert "状态" in keys and "日期" in keys
