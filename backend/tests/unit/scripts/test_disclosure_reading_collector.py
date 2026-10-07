import json
import os
import subprocess
import sys
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
    assert names == ["read_candidate", "search_candidate", "submit_answer", "report_session_event"]
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
    assert "only failed or interrupted infrastructure/protocol attempts" in retry.stderr
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
        "import os, sys, time\n"
        "if '--version' in sys.argv:\n"
        "    print('codex-cli 0.160.0')\n"
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
    env = {
        **os.environ,
        "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
        "CODEX_MODE": "protocol",
    }
    fingerprints = []
    configs = []
    invocations = [
        ("baseline", roots[0], manifests[0], tmp_path / "output-baseline", None),
        ("after", roots[1], manifests[1], tmp_path / "output-after", None),
        ("baseline", roots[0], manifests[0], tmp_path / "output-baseline-retry", 0),
    ]
    for side, root, manifest, output, retry_index in invocations:
        result = subprocess.run(
            [
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
                *(
                    [
                        "--retry-of",
                        json.loads(Path(invocations[retry_index][3] / "result.json").read_text(encoding="utf-8"))["record"],
                        "--retry-reason",
                        "synthetic protocol setup failure",
                    ]
                    if retry_index is not None
                    else []
                ),
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        assert result.returncode == 1, result.stderr
        result_data = json.loads(result.stdout)
        config_path = result_data["config"]
        configs.append(json.loads(Path(config_path).read_text(encoding="utf-8")))
        fingerprints.append(configs[-1]["tool_config_sha256"])
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
    retry_record = json.loads(Path(json.loads((invocations[2][3] / "result.json").read_text(encoding="utf-8"))["record"]).read_text(encoding="utf-8"))
    original_record = json.loads(Path(json.loads((invocations[0][3] / "result.json").read_text(encoding="utf-8"))["record"]).read_text(encoding="utf-8"))
    assert retry_record["retry_of"] == original_record["run_id"]
    assert retry_record["attempt_no"] == 2
    assert original_record["retry_run_id"] == retry_record["run_id"]
    assert original_record["failure_class"] == "protocol"


def test_runner_no_submit_is_terminal_and_pre_read_hang_has_finite_deadline(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys, time\n"
        "if '--version' in sys.argv:\n"
        "    print('codex-cli 0.160.0')\n"
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
        ("hang", "infrastructure"),
        ("usage", "infrastructure"),
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
            assert "classified as infrastructure" in record["failure_reason"]
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
            assert "only failed or interrupted infrastructure/protocol attempts" in retry.stderr
