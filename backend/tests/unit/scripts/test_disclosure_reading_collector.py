import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "scripts" / "disclosure_reading_collector.py"
RUNNER = ROOT / "scripts" / "run_disclosure_reading_session.py"


def run(*args, input_text=None):
    return subprocess.run(
        [sys.executable, str(CLI), *map(str, args)],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def candidate(tmp_path):
    root = tmp_path / "candidate"
    root.mkdir()
    (root / "AGENTS.md").write_text("# Test candidate\nRead this complete root guide.\n", encoding="utf-8")
    (root / "notes.md").write_text("café marker\nsecond line\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    assert run("manifest", "--root", root, "--out", manifest).returncode == 0
    return root, manifest


def start(tmp_path, root, manifest, run_id="trial-1", *extra):
    record = tmp_path / f"{run_id}.json"
    result = run(
        "start",
        "--root",
        root,
        "--manifest",
        manifest,
        "--record",
        record,
        "--run-id",
        run_id,
        "--candidate",
        "after",
        "--task",
        "history",
        "--task-hash",
        "a" * 64,
        "--model-config",
        "gpt-6.1-sol; reasoning=medium",
        "--tool-config-sha256",
        "b" * 64,
        *extra,
    )
    assert result.returncode == 0, result.stderr
    return record


def test_help_explains_complete_read_search_submit_contract():
    result = run("--help")
    assert result.returncode == 0
    assert "complete AGENTS.md" in result.stdout
    assert "UTF-8" in result.stdout
    assert all(field in result.stdout for field in ("entry", "constraints", "authorities", "relevant_decisions", "validation", "unknowns"))
    assert "scoring" not in result.stdout.lower()


def test_session_records_root_read_search_and_saves_structural_answer(tmp_path):
    root, manifest = candidate(tmp_path)
    record = start(tmp_path, root, manifest)
    root_read = run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md")
    assert root_read.returncode == 0, root_read.stderr
    search = run("search", "--manifest", manifest, "--record", record, "--query", "café", "--glob", "*.md")
    assert search.returncode == 0, search.stderr
    answer = {field: "intentionally generic and possibly incorrect" for field in ("entry", "constraints", "authorities", "relevant_decisions", "validation", "unknowns")}
    submitted = run("submit", "--record", record, input_text=json.dumps(answer))
    assert submitted.returncode == 0, submitted.stderr
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["status"] in {"submitted", "timeout"}
    assert saved["answer"] == answer
    assert saved["events"][0]["ranges"] == [{"path": "AGENTS.md", "start": 1, "end": 2}]
    assert saved["events"][1]["kind"] == "search"
    assert saved["events"][1]["content_bytes"] == len("café marker\n".encode())
    assert saved["model_config"] == "gpt-6.1-sol; reasoning=medium"
    assert saved["elapsed_seconds"] == round(saved["submitted_monotonic"] - saved["started_monotonic"], 3)


def test_read_rejects_non_root_first_read_and_hash_drift(tmp_path):
    root, manifest = candidate(tmp_path)
    record = start(tmp_path, root, manifest)
    denied = run("read", "--manifest", manifest, "--record", record, "--path", "notes.md")
    assert denied.returncode == 2
    assert "complete AGENTS.md" in denied.stderr
    (root / "notes.md").write_text("changed after manifest\n", encoding="utf-8")
    drift = run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md")
    assert drift.returncode == 2
    assert "candidate contents differ" in drift.stderr or "hash differs" in drift.stderr


def test_invalid_or_missing_session_record_prevents_submit_persistence(tmp_path):
    answer = json.dumps(
        {
            field: "structurally present"
            for field in (
                "entry",
                "constraints",
                "authorities",
                "relevant_decisions",
                "validation",
                "unknowns",
            )
        }
    )
    missing = run("submit", "--record", tmp_path / "missing-record.json", input_text=answer)
    assert missing.returncode == 2
    assert "No such file" in missing.stderr
    assert not (tmp_path / "missing-record.json").exists()

    root, manifest = candidate(tmp_path)
    record = start(tmp_path, root, manifest)
    assert run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md").returncode == 0
    malformed = run("submit", "--record", record, input_text=json.dumps({"entry": "only one field"}))
    assert malformed.returncode == 2
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["status"] == "started"
    assert "answer" not in saved


def test_overlap_union_counts_utf8_bytes_and_rejects_escape(tmp_path):
    root, manifest = candidate(tmp_path)
    record = start(tmp_path, root, manifest)
    first = run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md")
    assert first.returncode == 0
    read = run("read", "--manifest", manifest, "--record", record, "--path", "notes.md", "--start", "1")
    overlap = run("read", "--manifest", manifest, "--record", record, "--path", "notes.md", "--start", "1", "--end", "2")
    assert read.returncode == overlap.returncode == 0
    escaped = run("read", "--manifest", manifest, "--record", record, "--path", "../manifest.json")
    assert escaped.returncode == 2
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["events"][-1]["unique_bytes_read"] == len("café marker\nsecond line\n".encode())
    assert "safe, candidate-relative" in escaped.stderr


def test_public_heading_listing_and_full_hierarchy_read(tmp_path):
    root, _ = candidate(tmp_path)
    (root / "guide.md").write_text(
        "# Permissions\n\nIntro.\n\n## Visibility\n\n可见范围。\n\n### Before pagination\n\nFilter first.\n\n## Roles\n\nMatrix.\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "headings-manifest.json"
    assert run("manifest", "--root", root, "--out", manifest).returncode == 0
    record = start(tmp_path, root, manifest, "headings")
    assert run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md").returncode == 0

    listed = run("headings", "--manifest", manifest, "--record", record, "--path", "guide.md")
    assert listed.returncode == 0, listed.stderr
    rows = json.loads(listed.stdout)["headings"]
    assert [row["path"] for row in rows] == [
        ["Permissions"],
        ["Permissions", "Visibility"],
        ["Permissions", "Visibility", "Before pagination"],
        ["Permissions", "Roles"],
    ]

    section = run(
        "read",
        "--manifest",
        manifest,
        "--record",
        record,
        "--path",
        "guide.md",
        "--heading-path",
        '["Permissions", "Visibility"]',
    )
    assert section.returncode == 0, section.stderr
    payload = json.loads(section.stdout)
    assert payload["content"] == "## Visibility\n\n可见范围。\n\n### Before pagination\n\nFilter first.\n\n"
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["events"][-1]["content_bytes"] == len(payload["content"].encode("utf-8"))
    assert saved["events"][-1]["unique_bytes_read"] == len(payload["content"].encode("utf-8"))


def test_heading_reads_reject_duplicates_missing_titles_and_fenced_pseudo_headings(tmp_path):
    root, _ = candidate(tmp_path)
    (root / "guide.md").write_text(
        "# Parent\n\n```md\n## Fake\n```\n\n## Same\nOne.\n\n## Same\nTwo.\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "headings-manifest.json"
    assert run("manifest", "--root", root, "--out", manifest).returncode == 0
    record = start(tmp_path, root, manifest, "heading-errors")
    assert run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md").returncode == 0

    listed = run("headings", "--manifest", manifest, "--record", record, "--path", "guide.md")
    assert listed.returncode == 0, listed.stderr
    assert [row["path"] for row in json.loads(listed.stdout)["headings"]] == [["Parent"], ["Parent", "Same"], ["Parent", "Same"]]
    duplicate = run("read", "--manifest", manifest, "--record", record, "--path", "guide.md", "--heading-path", '["Parent", "Same"]')
    missing = run("read", "--manifest", manifest, "--record", record, "--path", "guide.md", "--heading-path", '["Parent", "Absent"]')
    assert duplicate.returncode == missing.returncode == 2
    assert "duplicate" in duplicate.stderr.lower()
    assert "not found" in missing.stderr.lower()
    out_of_bounds = run(
        "read",
        "--manifest",
        manifest,
        "--record",
        record,
        "--path",
        "guide.md",
        "--start",
        "99",
    )
    assert out_of_bounds.returncode == 2
    assert "invalid line range" in out_of_bounds.stderr
    assert run("read", "--manifest", manifest, "--record", record, "--path", "guide.md", "--heading-path", '["Parent", "Fake"]').returncode == 2


def test_heading_listing_preserves_literal_hash_and_includes_setext_headings(tmp_path):
    root, _ = candidate(tmp_path)
    (root / "guide.md").write_text("# Literal title#\n\nSetext\nmulti-line title\n===\n", encoding="utf-8")
    manifest = tmp_path / "setext-manifest.json"
    assert run("manifest", "--root", root, "--out", manifest).returncode == 0
    record = start(tmp_path, root, manifest, "setext")
    assert run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md").returncode == 0
    result = run("headings", "--manifest", manifest, "--record", record, "--path", "guide.md")
    assert result.returncode == 0, result.stderr
    assert [row["path"] for row in json.loads(result.stdout)["headings"]] == [
        ["Literal title#"],
        ["Setext multi-line title"],
    ]
    saved = json.loads(record.read_text(encoding="utf-8"))
    event = saved["events"][-1]
    assert event["ranges"] == [
        {"path": "guide.md", "start": 1, "end": 1},
        {"path": "guide.md", "start": 3, "end": 5},
    ]
    assert event["content_bytes"] == len(b"# Literal title#\nSetext\nmulti-line title\n===\n")


def test_heading_tools_are_advertised_by_mcp_and_reject_forbidden_paths(tmp_path):
    assert "headings" in run("--help").stdout
    assert "heading-path" in run("read", "--help").stdout
    root, manifest = candidate(tmp_path)
    record = start(tmp_path, root, manifest, "heading-forbidden")
    listed = run(
        "mcp",
        "--manifest",
        manifest,
        "--record",
        record,
        input_text=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) + "\n",
    )
    tools = json.loads(listed.stdout)["result"]["tools"]
    assert "list_candidate_headings" in {tool["name"] for tool in tools}
    read_schema = next(tool for tool in tools if tool["name"] == "read_candidate")["inputSchema"]
    assert "heading_path" in read_schema["properties"]
    assert run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md").returncode == 0
    denied = run("headings", "--manifest", manifest, "--record", record, "--path", "docs/specs/private.md")
    assert denied.returncode == 2
    assert "forbidden" in denied.stderr.lower()


def test_cost_report_implementation_is_not_readable_during_a_session(tmp_path):
    root, _ = candidate(tmp_path)
    evaluator_file = root / "scripts" / "report_disclosure_costs.py"
    evaluator_file.parent.mkdir()
    evaluator_file.write_text("# private evaluator\n", encoding="utf-8")
    manifest = tmp_path / "evaluator-manifest.json"
    assert run("manifest", "--root", root, "--out", manifest).returncode == 0
    record = start(tmp_path, root, manifest, "evaluator-read-denied")
    assert run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md").returncode == 0
    denied = run(
        "read",
        "--manifest",
        manifest,
        "--record",
        record,
        "--path",
        "scripts/report_disclosure_costs.py",
    )
    assert denied.returncode == 2
    assert "forbidden for evaluation" in denied.stderr.lower()


def test_parallel_public_reads_preserve_every_recorded_event(tmp_path):
    root, manifest = candidate(tmp_path)
    record = start(tmp_path, root, manifest)
    assert run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md").returncode == 0

    def read_line(line):
        return run(
            "read",
            "--manifest",
            manifest,
            "--record",
            record,
            "--path",
            "notes.md",
            "--start",
            str(line),
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(read_line, [1, 2] * 6))

    assert all(result.returncode == 0 for result in results)
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert len(saved["events"]) == 13
    assert [event["ranges"][0]["path"] for event in saved["events"]].count("notes.md") == 12


def test_failure_close_cannot_replace_a_persisted_submission(tmp_path):
    root, manifest = candidate(tmp_path)
    record = start(tmp_path, root, manifest)
    assert run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md").returncode == 0
    answer = {field: f"answer for {field}" for field in ("entry", "constraints", "authorities", "relevant_decisions", "validation", "unknowns")}
    submitted = run("submit", "--record", record, input_text=json.dumps(answer))
    assert submitted.returncode == 0

    late_failure = run(
        "failed",
        "--record",
        record,
        "--reason",
        "late runner failure",
        "--failure-class",
        "infrastructure",
    )

    assert late_failure.returncode == 2
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["status"] == "submitted"
    assert saved["answer"] == answer
    assert "failure_reason" not in saved


def test_runner_timeout_cleans_only_its_child_process_group(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    marker = tmp_path / "orphan-was-not-killed"
    child_pid = tmp_path / "child.pid"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import os, subprocess, sys, time\n"
        "if '--version' in sys.argv: print('codex-cli test')\n"
        "elif sys.argv[1:3] == ['debug', 'models']: print('{\"models\":[{\"slug\":\"gpt-6.1-sol\"}]}')\n"
        "else:\n"
        f"    child = subprocess.Popen([sys.executable, '-c', \"import pathlib,time; time.sleep(0.7); pathlib.Path('{marker}').touch()\"])\n"
        f"    pathlib = __import__('pathlib'); pathlib.Path('{child_pid}').write_text(str(child.pid))\n"
        "    time.sleep(5)\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    root, manifest = candidate(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("A generic task prompt.\n", encoding="utf-8")
    sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--root",
                str(root),
                "--manifest",
                str(manifest),
                "--candidate",
                "after",
                "--task",
                "history",
                "--prompt-file",
                str(prompt),
                "--out-dir",
                str(tmp_path / "runner-output"),
                "--startup-timeout-seconds",
                "0.1",
            ],
            text=True,
            capture_output=True,
            env={**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]},
            check=False,
        )
        assert result.returncode == 124
        run_data = json.loads(result.stdout)
        record = json.loads(Path(run_data["record"]).read_text(encoding="utf-8"))
        assert record["status"] == "failed"
        assert record["failure_class"] == "workspace_load"
        assert Path(run_data["trace"]).is_file()
        time.sleep(0.9)
        assert not marker.exists()
        assert sibling.poll() is None
        assert child_pid.exists()
    finally:
        sibling.terminate()
        sibling.wait()


def test_runner_sigterm_cleans_child_group_and_records_interruption(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    marker = tmp_path / "cancelled-child-ran"
    child_pid = tmp_path / "cancelled-child.pid"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, subprocess, sys, time\n"
        "if '--version' in sys.argv: print('codex-cli test')\n"
        "elif sys.argv[1:3] == ['debug', 'models']: print('{\"models\":[{\"slug\":\"gpt-6.1-sol\"}]}')\n"
        "else:\n"
        f"    child = subprocess.Popen([sys.executable, '-c', \"import pathlib,time; time.sleep(0.7); pathlib.Path('{marker}').touch()\"])\n"
        f"    pathlib.Path('{child_pid}').write_text(str(child.pid))\n"
        "    time.sleep(10)\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    root, manifest = candidate(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("A generic task prompt.\n", encoding="utf-8")
    sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    runner = subprocess.Popen(
        [
            sys.executable,
            str(RUNNER),
            "--root",
            str(root),
            "--manifest",
            str(manifest),
            "--candidate",
            "after",
            "--task",
            "history",
            "--prompt-file",
            str(prompt),
            "--out-dir",
            str(tmp_path / "cancel-output"),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]},
    )
    try:
        deadline = time.monotonic() + 10
        while not child_pid.exists() and runner.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert child_pid.exists()
        os.kill(runner.pid, signal.SIGTERM)
        stdout, stderr = runner.communicate(timeout=5)

        assert runner.returncode == 128 + signal.SIGTERM
        assert stderr == ""
        result_data = json.loads(stdout)
        record = json.loads(Path(result_data["record"]).read_text(encoding="utf-8"))
        assert record["status"] == "interrupted"
        assert record["failure_class"] == "infrastructure"
        assert Path(result_data["trace"]).is_file()
        assert sibling.poll() is None
        time.sleep(0.9)
        assert not marker.exists()
    finally:
        if runner.poll() is None:
            runner.kill()
            runner.wait()
        sibling.terminate()
        sibling.wait()


def test_only_one_linked_retry_for_infrastructure_or_protocol_failure(tmp_path):
    root, manifest = candidate(tmp_path)
    original = start(tmp_path, root, manifest)
    failed = run("failed", "--record", original, "--reason", "collector process exited before submit", "--failure-class", "protocol")
    assert failed.returncode == 0
    retry = start(tmp_path, root, manifest, "trial-2", "--retry-of", original, "--retry-reason", "collector process exited before submit")
    original_data = json.loads(original.read_text(encoding="utf-8"))
    retry_data = json.loads(retry.read_text(encoding="utf-8"))
    assert original_data["retry_run_id"] == "trial-2"
    assert retry_data["retry_of"] == "trial-1"
    assert retry_data["attempt_no"] == 2
    assert run("interrupted", "--record", retry, "--reason", "retry interrupted", "--failure-class", "infrastructure").returncode == 0
    denied = run(
        "start",
        "--root",
        root,
        "--manifest",
        manifest,
        "--record",
        tmp_path / "trial-3.json",
        "--run-id",
        "trial-3",
        "--candidate",
        "after",
        "--task",
        "history",
        "--task-hash",
        "a" * 64,
        "--model-config",
        "gpt-6.1-sol; reasoning=medium",
        "--tool-config-sha256",
        "b" * 64,
        "--retry-of",
        retry,
        "--retry-reason",
        "second retry must be rejected",
    )
    assert denied.returncode == 2
    assert "already been used" in denied.stderr


def test_concurrent_retry_launches_claim_only_one_retry_slot(tmp_path):
    root, manifest = candidate(tmp_path)
    original = start(tmp_path, root, manifest)
    assert (
        run(
            "failed",
            "--record",
            original,
            "--reason",
            "collector process exited before submit",
            "--failure-class",
            "protocol",
        ).returncode
        == 0
    )

    def launch(run_id):
        return run(
            "start",
            "--root",
            root,
            "--manifest",
            manifest,
            "--record",
            tmp_path / f"{run_id}.json",
            "--run-id",
            run_id,
            "--candidate",
            "after",
            "--task",
            "history",
            "--task-hash",
            "a" * 64,
            "--model-config",
            "gpt-6.1-sol; reasoning=medium",
            "--tool-config-sha256",
            "b" * 64,
            "--retry-of",
            original,
            "--retry-reason",
            "one retry is permitted",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(launch, ("retry-a", "retry-b")))

    assert sorted(result.returncode for result in attempts) == [0, 2]
    prior = json.loads(original.read_text(encoding="utf-8"))
    assert prior["retry_run_id"] in {"retry-a", "retry-b"}


def test_mcp_exposes_only_collector_operations_and_submits_answer(tmp_path):
    root, manifest = candidate(tmp_path)
    record = start(tmp_path, root, manifest)
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "read_candidate", "arguments": {"path": "AGENTS.md"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "list_candidate_headings", "arguments": {"path": "AGENTS.md"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "read_candidate", "arguments": {"path": "AGENTS.md", "heading_path": ["Test candidate"]}},
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "submit_answer",
                "arguments": {"answer": {field: "generic" for field in ("entry", "constraints", "authorities", "relevant_decisions", "validation", "unknowns")}},
            },
        },
    ]
    result = run("mcp", "--manifest", manifest, "--record", record, input_text="\n".join(map(json.dumps, requests)) + "\n")
    assert result.returncode == 0
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    names = [item["name"] for item in replies[1]["result"]["tools"]]
    assert names == ["read_candidate", "list_candidate_headings", "search_candidate", "submit_answer", "report_session_event"]
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["status"] == "submitted"
    assert saved["answer"]["entry"] == "generic"


def test_manifest_hashes_but_never_exposes_scoring_or_benchmark_material(tmp_path):
    root, manifest = candidate(tmp_path)
    hidden = {
        "docs/governance/document-policy.json": "private scoring anchor marker\n",
        "docs/governance/disclosure-scoring-rubric-2026-10-07.md": "private scoring anchor marker\n",
        "scripts/score_disclosure_readability.py": "private scoring anchor marker\n",
        "backend/tests/unit/scripts/test_score_disclosure_readability.py": "private scoring anchor marker\n",
        "docs/specs/evaluation-prompt.md": "private scoring anchor marker\n",
        "docs/zero_agent_eval_cases/case_04/prompt.md": "private scoring anchor marker\n",
        "docs/governance/disclosure-reading-collector-2026-10-07.md": "private scoring anchor marker\n",
    }
    for rel, text in hidden.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert run("manifest", "--root", root, "--out", manifest).returncode == 0
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    excluded_paths = {entry["path"] for entry in manifest_data["exclusions"]}
    assert set(hidden) == excluded_paths
    assert len(manifest_data["exclusion_sha256"]) == 64
    record = start(tmp_path, root, manifest)
    assert run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md").returncode == 0
    for rel in hidden:
        denied = run("read", "--manifest", manifest, "--record", record, "--path", rel)
        assert denied.returncode == 2
        assert "forbidden" in denied.stderr
    searched = run("search", "--manifest", manifest, "--record", record, "--query", "private scoring anchor marker", "--glob", "**/*.md")
    assert searched.returncode == 0
    assert json.loads(searched.stdout)["matches"] == []


def test_empty_search_is_rejected_and_mcp_tools_declare_scope(tmp_path):
    root, manifest = candidate(tmp_path)
    record = start(tmp_path, root, manifest)
    assert run("read", "--manifest", manifest, "--record", record, "--path", "AGENTS.md").returncode == 0
    empty = run("search", "--manifest", manifest, "--record", record, "--query", "")
    assert empty.returncode == 2
    assert "must not be empty" in empty.stderr
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    listed = run("mcp", "--manifest", manifest, "--record", record, input_text=json.dumps(request) + "\n")
    assert listed.returncode == 0
    tools = json.loads(listed.stdout)["result"]["tools"]
    assert all(tool["annotations"]["openWorldHint"] is False for tool in tools)
    assert tools[0]["annotations"]["readOnlyHint"] is True
    assert tools[1]["annotations"]["readOnlyHint"] is True
    assert tools[2]["annotations"]["destructiveHint"] is False


def test_timeout_cannot_be_retried_and_external_help_is_audited(tmp_path):
    root, manifest = candidate(tmp_path)
    original = start(tmp_path, root, manifest)
    timeout = run("timeout", "--record", original, "--reason", "session exceeded the fixed task limit")
    assert timeout.returncode == 0
    assert json.loads(original.read_text(encoding="utf-8"))["failure_class"] == "task_timeout"
    retry = run(
        "start",
        "--root",
        root,
        "--manifest",
        manifest,
        "--record",
        tmp_path / "retry.json",
        "--run-id",
        "retry",
        "--candidate",
        "after",
        "--task",
        "history",
        "--task-hash",
        "a" * 64,
        "--model-config",
        "gpt-6.1-sol; reasoning=medium",
        "--tool-config-sha256",
        "b" * 64,
        "--retry-of",
        original,
        "--retry-reason",
        "do not redraw a timeout",
    )
    assert retry.returncode == 2
    assert "only failed or interrupted infrastructure" in retry.stderr
    next_record = start(tmp_path, root, manifest, "trial-help")
    audited = run(
        "mark",
        "--record",
        next_record,
        "--event",
        "external-help",
        "--details",
        "A maintainer clarified the generic task wording.",
    )
    assert audited.returncode == 0
    saved = json.loads(next_record.read_text(encoding="utf-8"))
    assert saved["external_help"][0]["details"].startswith("A maintainer")


def test_runner_config_identity_ignores_candidate_and_record_paths(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        "if '--version' in sys.argv:\n"
        "    print('codex-cli 0.160.0')\n"
        "elif sys.argv[1:3] == ['debug', 'models']:\n"
        "    Path(os.environ['CODEX_DEBUG_MODELS_CALLS']).write_text('called', encoding='utf-8')\n"
        '    print(\'{\\"models\\":[{\\"slug\\":\\"gpt-6.1-sol\\",\\"apply_patch_tool_type\\":\\"freeform\\"}]}\')\n'
        "elif 'exec' in sys.argv and os.environ.get('CODEX_CAPTURE'):\n"
        "    raw = next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('model_catalog_json='))\n"
        "    catalog_path = json.loads(raw)\n"
        "    catalog = json.loads(Path(catalog_path).read_text(encoding='utf-8'))\n"
        "    Path(os.environ['CODEX_CAPTURE']).write_text(json.dumps({'argv': sys.argv, 'catalog_path': catalog_path, 'catalog': catalog}), encoding='utf-8')\n"
        "    sys.stderr.write(\"Error: unexpected argument '--not-valid' found\\n\")\n"
        "    sys.exit(1)\n"
        "elif os.environ.get('CODEX_MODE') == 'hang':\n"
        "    time.sleep(3)\n"
        "elif os.environ.get('CODEX_MODE') == 'clean':\n"
        "    pass\n"
        "else:\n"
        "    sys.stderr.write(\"Error: unexpected argument '--not-valid' found\\n\")\n"
        "    sys.exit(1)\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    roots = [tmp_path / "baseline", tmp_path / "after"]
    manifests = []
    for root in roots:
        root.mkdir()
        (root / "AGENTS.md").write_text("generic root\n", encoding="utf-8")
        manifest = tmp_path / f"{root.name}.manifest.json"
        assert run("manifest", "--root", root, "--out", manifest).returncode == 0
        manifests.append(manifest)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("A generic task prompt.\n", encoding="utf-8")
    model_catalog = tmp_path / "pinned-model-catalog.json"
    model_catalog.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "gpt-6.1-sol",
                        "tool_mode": "code_mode_only",
                        "shell_type": "unified_exec",
                        "apply_patch_tool_type": "freeform",
                        "experimental_supported_tools": ["send_user_message_async", "clock"],
                        "catalog_note": "stable pinned catalog",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
        "CODEX_MODE": "protocol",
        "CODEX_DEBUG_MODELS_CALLS": str(tmp_path / "debug-models-called"),
    }
    fingerprints = []
    configs = []
    invocations = [
        ("baseline", roots[0], manifests[0], tmp_path / "output-baseline", None, "formal", True),
        ("after", roots[1], manifests[1], tmp_path / "output-after", None, "formal", True),
        ("baseline", roots[0], manifests[0], tmp_path / "output-baseline-retry", 0, "formal", True),
        ("baseline", roots[0], manifests[0], tmp_path / "output-baseline-default", None, None, True),
        ("baseline", roots[0], manifests[0], tmp_path / "output-live-catalog", None, None, False),
    ]
    for side, root, manifest, output, retry_index, stage, use_pinned_catalog in invocations:
        capture_path = tmp_path / f"{output.name}.capture.json"
        invocation_env = {**env, "CODEX_CAPTURE": str(capture_path)}
        command = [
            sys.executable,
            str(RUNNER),
            "--root",
            str(root),
            "--manifest",
            str(manifest),
            "--candidate",
            side,
            "--task",
            "history",
            "--prompt-file",
            str(prompt),
            "--out-dir",
            str(output),
        ]
        if use_pinned_catalog:
            command.extend(("--model-catalog-file", str(model_catalog)))
        if stage is not None:
            command.extend(("--stage", stage))
        if retry_index is not None:
            command.extend(
                (
                    "--retry-of",
                    json.loads(Path(invocations[retry_index][3] / "result.json").read_text(encoding="utf-8"))["record"],
                    "--retry-reason",
                    "synthetic protocol setup failure",
                )
            )
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            env=invocation_env,
            check=False,
        )
        assert result.returncode == 1, result.stderr
        result_data = json.loads(result.stdout)
        config_path = result_data["config"]
        configs.append(json.loads(Path(config_path).read_text(encoding="utf-8")))
        fingerprints.append(configs[-1]["tool_config_sha256"])
        captured = json.loads(capture_path.read_text(encoding="utf-8"))
        expected_stage = stage or "non-scored"
        assert configs[-1]["config"]["stage"] == expected_stage
        expected_prompt = "Complete one independent formal reading session." if expected_stage == "formal" else "Complete one independent, non-scored reading session."
        assert captured["argv"][-1].startswith(expected_prompt)
        assert captured["catalog"]["models"][0]["apply_patch_tool_type"] is None
        assert captured["catalog"]["models"][0]["slug"] == "gpt-6.1-sol"
        assert "tools.update_plan.enabled=false" in captured["argv"]
        assert "tools.experimental_request_user_input.enabled=false" in captured["argv"]
        assert not Path(captured["catalog_path"]).exists()
        debug_models_called = Path(env["CODEX_DEBUG_MODELS_CALLS"]).exists()
        assert debug_models_called is (not use_pinned_catalog)
        assert configs[-1]["config"]["model_catalog_source"] == ("pinned-file" if use_pinned_catalog else "codex-debug-models")
        assert configs[-1]["config"]["model_catalog_source_sha256"] == (hashlib.sha256(model_catalog.read_bytes()).hexdigest() if use_pinned_catalog else None)
        assert configs[-1]["config"]["model_tool_metadata_original"]["apply_patch_tool_type"] == "freeform"
        assert configs[-1]["config"]["model_tool_metadata_effective"]["apply_patch_tool_type"] is None
        assert configs[-1]["config"]["mcp_resource_handlers"] == [
            "list_mcp_resources",
            "list_mcp_resource_templates",
            "read_mcp_resource",
        ]
        assert configs[-1]["config"]["model_metadata_tools"] == {
            "send_user_message_async": [
                "request_user_input_async (legacy alias)",
                "send_message_to_user_async",
            ],
            "clock": ["current_time"],
        }
        assert configs[-1]["config"]["core_utility_tools_disabled"] == [
            "update_plan",
            "request_user_input",
        ]
        output.mkdir(exist_ok=True)
        (output / "result.json").write_text(result.stdout, encoding="utf-8")
    assert fingerprints[0] == fingerprints[1]
    assert configs[0]["candidate_root"] != configs[1]["candidate_root"]
    assert configs[0]["effective_command"] != configs[1]["effective_command"]
    assert len(configs[0]["config"]["mcp_tool_schema_sha256"]) == 64
    assert configs[0]["config"]["mcp_tool_schema_sha256"] == configs[1]["config"]["mcp_tool_schema_sha256"]
    assert configs[0]["config"]["task_timeout_seconds"] == 300
    assert {"view_image", "request_permissions_tool"}.issubset(configs[0]["config"]["disabled_features"])
    assert configs[0]["config"]["resolved_model_version"] is None
    assert "not the resolved backend model revision" in configs[0]["config"]["model_version_limit"]
    assert fingerprints[0] == fingerprints[2]
    assert fingerprints[0] != fingerprints[3]
    retry_record = json.loads(Path(json.loads((invocations[2][3] / "result.json").read_text(encoding="utf-8"))["record"]).read_text(encoding="utf-8"))
    original_record = json.loads(Path(json.loads((invocations[0][3] / "result.json").read_text(encoding="utf-8"))["record"]).read_text(encoding="utf-8"))
    assert retry_record["retry_of"] == original_record["run_id"]
    assert retry_record["attempt_no"] == 2
    assert original_record["retry_run_id"] == retry_record["run_id"]
    assert original_record["failure_class"] == "protocol"

    invalid_catalog = tmp_path / "invalid-model-catalog.json"
    invalid_catalog.write_text('{"models": [null]}', encoding="utf-8")
    invalid_env = {
        **env,
        "CODEX_DEBUG_MODELS_CALLS": str(tmp_path / "invalid-debug-models-called"),
    }
    invalid_result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--root",
            str(roots[0]),
            "--manifest",
            str(manifests[0]),
            "--candidate",
            "baseline",
            "--task",
            "history",
            "--prompt-file",
            str(prompt),
            "--out-dir",
            str(tmp_path / "output-invalid-catalog"),
            "--model-catalog-file",
            str(invalid_catalog),
        ],
        text=True,
        capture_output=True,
        env=invalid_env,
        check=False,
    )
    assert invalid_result.returncode == 2
    assert "pinned model catalog must contain the selected model" in invalid_result.stderr


def test_runner_no_submit_is_terminal_and_pre_read_hang_has_finite_deadline(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys, time\n"
        "if '--version' in sys.argv:\n"
        "    print('codex-cli 0.160.0')\n"
        "elif sys.argv[1:3] == ['debug', 'models']:\n"
        '    print(\'{\\"models\\":[{\\"slug\\":\\"gpt-6.1-sol\\",\\"apply_patch_tool_type\\":\\"freeform\\"}]}\')\n'
        "elif os.environ.get('CODEX_MODE') == 'hang':\n"
        "    time.sleep(3)\n"
        "elif os.environ.get('CODEX_MODE') == 'clean':\n"
        "    pass\n"
        "elif os.environ.get('CODEX_MODE') == 'usage':\n"
        '    print(\'{"type":"error","message":"You have hit your usage limit. Try again at 12:02 PM."}\')\n'
        "    sys.exit(1)\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    root, manifest = candidate(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("A generic task prompt.\n", encoding="utf-8")
    for mode, expected_class in (
        ("clean", "task"),
        ("hang", "workspace_load"),
        ("usage", "quota_exhausted"),
    ):
        out_dir = tmp_path / f"output-{mode}"
        env = {
            **os.environ,
            "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
            "CODEX_MODE": mode,
        }
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--root",
                str(root),
                "--manifest",
                str(manifest),
                "--candidate",
                "after",
                "--task",
                "history",
                "--prompt-file",
                str(prompt),
                "--out-dir",
                str(out_dir),
                "--startup-timeout-seconds",
                "0.05",
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        if expected_class == "task":
            assert result.returncode == 2
        elif mode == "hang":
            assert result.returncode == 124
        else:
            assert result.returncode == 1
        result_data = json.loads(result.stdout)
        record = json.loads(Path(result_data["record"]).read_text(encoding="utf-8"))
        assert record["status"] == "failed"
        assert record["failure_class"] == expected_class
        assert record["startup_timeout_seconds"] == 0.05
        if mode == "hang":
            assert result_data["startup_timed_out"] is True
            assert "no successful first read" in record["failure_reason"]
        elif mode == "usage":
            assert result.returncode == 1
            assert "classified as quota_exhausted" in record["failure_reason"]
            trace = Path(result_data["trace"]).read_text(encoding="utf-8")
            assert "usage limit" in trace.lower()
        else:
            assert "classified as task" in record["failure_reason"]
            retry = run(
                "start",
                "--root",
                root,
                "--manifest",
                manifest,
                "--record",
                tmp_path / "must-not-retry-task.json",
                "--run-id",
                "task-retry",
                "--candidate",
                "after",
                "--task",
                "history",
                "--task-hash",
                record["task_sha256"],
                "--model-config",
                record["model_config"],
                "--tool-config-sha256",
                record["tool_config_sha256"],
                "--retry-of",
                result_data["record"],
                "--retry-reason",
                "must reject terminal task failure",
            )
            assert retry.returncode == 2
            assert "only failed or interrupted infrastructure" in retry.stderr


def test_runner_quota_exhaustion_stops_later_dispatches(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    calls = tmp_path / "exec-calls"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "if '--version' in sys.argv: print('codex-cli test')\n"
        "elif sys.argv[1:3] == ['debug', 'models']: print('{\"models\":[{\"slug\":\"gpt-6.1-sol\"}]}')\n"
        "else:\n"
        f"    with open('{calls}', 'a', encoding='utf-8') as output: output.write('started\\n')\n"
        '    print(\'{"type":"error","message":"You have hit your usage limit."}\')\n'
        "    sys.exit(1)\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    root, manifest = candidate(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("A generic task prompt.\n", encoding="utf-8")
    output = tmp_path / "runner-output"
    env = {**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]}
    command = [
        sys.executable,
        str(RUNNER),
        "--root",
        str(root),
        "--manifest",
        str(manifest),
        "--candidate",
        "after",
        "--task",
        "history",
        "--prompt-file",
        str(prompt),
        "--out-dir",
        str(output),
    ]
    exhausted = subprocess.run(command, text=True, capture_output=True, env=env, check=False)
    assert exhausted.returncode == 1
    stopped = subprocess.run(command, text=True, capture_output=True, env=env, check=False)

    assert stopped.returncode == 75
    assert json.loads(stopped.stdout)["status"] == "dispatch_stopped"
    assert calls.read_text(encoding="utf-8").splitlines() == ["started"]


def test_runner_recovers_quota_stop_from_record_without_marker(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    called = tmp_path / "codex-was-launched"
    fake_codex.write_text(
        f"#!/usr/bin/env python3\nimport pathlib\npathlib.Path('{called}').touch()\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    root, manifest = candidate(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("A generic task prompt.\n", encoding="utf-8")
    output = tmp_path / "runner-output"
    output.mkdir()
    (output / "quota-attempt.json").write_text(
        json.dumps({"run_id": "quota-attempt", "status": "failed", "failure_class": "quota_exhausted"}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--root",
            str(root),
            "--manifest",
            str(manifest),
            "--candidate",
            "after",
            "--task",
            "history",
            "--prompt-file",
            str(prompt),
            "--out-dir",
            str(output),
        ],
        text=True,
        capture_output=True,
        env={**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]},
        check=False,
    )

    assert result.returncode == 75
    assert json.loads(result.stdout)["blocked_by_run_id"] == "quota-attempt"
    assert not called.exists()
    assert (output / "quota-exhausted.json").is_file()
