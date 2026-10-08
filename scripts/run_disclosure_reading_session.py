#!/usr/bin/env python3
"""Run one isolated Codex reading session through the disclosure collector MCP tools."""

import argparse
import atexit
import hashlib
import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from disclosure_reading_collector import (
    MAX_SESSION_SECONDS,
    digest,
    mcp_tool_schemas,
    write_record,
)

MCP_TOOLS = [
    "read_candidate",
    "search_candidate",
    "submit_answer",
    "report_session_event",
]
DISABLED_FEATURES = [
    "shell_tool",
    "unified_exec",
    "multi_agent",
    "sleep_tool",
    "browser_use",
    "browser_use_external",
    "computer_use",
    "image_generation",
    "view_image",
    "request_permissions_tool",
    "apps",
    "plugins",
    "memories",
]
STARTUP_TIMEOUT_SECONDS = 60


def isolation_model_catalog(catalog, model):
    """Keep the selected catalog entry intact except for native file patch access."""
    matches = [entry for entry in catalog.get("models", []) if entry.get("slug") == model]
    if len(matches) != 1:
        raise ValueError(f"expected one model catalog entry for {model!r}")
    isolated = dict(matches[0])
    isolated["apply_patch_tool_type"] = None
    return {"models": [isolated]}


def load_isolation_model_catalog(codex, model, catalog_file=None):
    catalog_source_sha256 = None
    if catalog_file is not None:
        catalog_bytes = catalog_file.read_bytes()
        try:
            catalog = json.loads(catalog_bytes)
        except json.JSONDecodeError as exc:
            raise ValueError("pinned model catalog is not valid JSON") from exc
        entries = catalog.get("models") if isinstance(catalog, dict) else None
        if not isinstance(entries, list) or len(entries) != 1:
            raise ValueError("pinned model catalog must contain exactly one model")
        if not isinstance(entries[0], dict) or entries[0].get("slug") != model:
            raise ValueError("pinned model catalog must contain the selected model")
        catalog_source_sha256 = hashlib.sha256(catalog_bytes).hexdigest()
        isolated = isolation_model_catalog(catalog, model)
        return isolated, entries[0], catalog_source_sha256

    result = subprocess.run(
        [codex, "debug", "models"],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError("Codex could not load the current model catalog")
    try:
        catalog = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Codex model catalog output was not JSON") from exc
    isolated = isolation_model_catalog(catalog, model)
    original = next(entry for entry in catalog["models"] if entry.get("slug") == model)
    return isolated, original, catalog_source_sha256


def classify_runner_failure(trace_path):
    quota_indicators = ("usage limit", "quota exhausted", "quota exceeded", "hit your limit")
    workspace_indicators = (
        "workspace requirements",
        "failed to load workspace",
        "workspace load failed",
        "could not load workspace",
    )
    infrastructure_indicators = (
        "connection refused",
        "rate limit",
        "try again at",
    )
    protocol_indicators = (
        "approval policy",
        "failed to initialize",
        "mcp server",
        "unexpected argument",
        "transport",
    )

    def classify_message(message):
        message = message.casefold()
        if any(word in message for word in quota_indicators):
            return "quota_exhausted"
        if any(word in message for word in workspace_indicators):
            return "workspace_load"
        if any(word in message for word in protocol_indicators):
            return "protocol"
        if any(word in message for word in infrastructure_indicators):
            return "infrastructure"
        return None

    for line in trace_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            if line.lstrip().casefold().startswith(("error:", "fatal:")):
                if classification := classify_message(line):
                    return classification
            continue
        if event.get("type") in {"error", "turn.failed"}:
            if classification := classify_message(json.dumps(event)):
                return classification
        item = event.get("item", {})
        error = event.get("error") or item.get("error")
        if error:
            if classification := classify_message(json.dumps(error)):
                return classification
        if item.get("type") == "error":
            return "protocol"
    return None


def find_quota_exhaustion(out_dir, marker_path):
    if marker_path.exists():
        return json.loads(marker_path.read_text(encoding="utf-8"))
    for record_path in sorted(out_dir.glob("*.json")):
        if record_path == marker_path:
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("failure_class") == "quota_exhausted":
            marker = {
                "run_id": record.get("run_id"),
                "record": str(record_path),
                "trace": str(out_dir / f"{record_path.stem}.jsonl"),
            }
            write_record(marker_path, marker)
            return marker
    for trace_path in sorted(out_dir.glob("*.jsonl")):
        try:
            if classify_runner_failure(trace_path) == "quota_exhausted":
                marker = {
                    "run_id": trace_path.stem,
                    "record": str(out_dir / f"{trace_path.stem}.json"),
                    "trace": str(trace_path),
                }
                write_record(marker_path, marker)
                return marker
        except OSError:
            continue
    return None


def call_collector(args, *command):
    result = subprocess.run(
        [sys.executable, str(args.collector), *map(str, command)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def terminate_process_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


class RunnerCancelled(Exception):
    def __init__(self, signum):
        self.signum = signum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate", choices=("baseline", "after"), required=True)
    parser.add_argument(
        "--task",
        choices=(
            "ui",
            "chat",
            "knowledge",
            "permissions",
            "tests",
            "runtime",
            "upstream",
            "history",
        ),
        required=True,
    )
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=("non-scored", "formal"), default="non-scored")
    parser.add_argument("--model-catalog-file", type=Path)
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument(
        "--reasoning",
        choices=("low", "medium", "high", "xhigh", "max", "ultra"),
        default="medium",
    )
    parser.add_argument("--startup-timeout-seconds", type=float, default=STARTUP_TIMEOUT_SECONDS)
    parser.add_argument("--retry-of", type=Path)
    parser.add_argument("--retry-reason", default="")
    args = parser.parse_args()

    codex = shutil.which("codex")
    if not codex:
        parser.error("codex CLI is not available on PATH")
    args.collector = Path(__file__).with_name("disclosure_reading_collector.py").resolve()
    root = args.root.resolve(strict=True)
    manifest = args.manifest.resolve(strict=True)
    prompt = args.prompt_file.read_text(encoding="utf-8")
    if not prompt.strip():
        parser.error("prompt file must contain a non-empty task")
    if args.startup_timeout_seconds <= 0:
        parser.error("startup timeout must be a positive number of seconds")
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    quota_marker = args.out_dir / "quota-exhausted.json"
    if marker := find_quota_exhaustion(args.out_dir, quota_marker):
        print(
            json.dumps(
                {
                    "status": "dispatch_stopped",
                    "failure_class": "quota_exhausted",
                    "blocked_by_run_id": marker.get("run_id"),
                }
            )
        )
        return 75
    try:
        isolation_catalog, original_model, model_catalog_source_sha256 = load_isolation_model_catalog(codex, args.model, args.model_catalog_file)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(f"could not prepare the isolated model tool catalog: {exc}")
    catalog_json = json.dumps(isolation_catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    catalog_sha256 = hashlib.sha256(catalog_json.encode("utf-8")).hexdigest()
    catalog_model = isolation_catalog["models"][0]
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="disclosure-model-catalog-",
        delete=False,
    ) as catalog_file:
        catalog_file.write(catalog_json)
        catalog_path = Path(catalog_file.name)
    atexit.register(catalog_path.unlink, missing_ok=True)
    run_id = f"{args.candidate}-{args.task}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{time.monotonic_ns()}"
    record = args.out_dir / f"{run_id}.json"
    trace = args.out_dir / f"{run_id}.jsonl"
    prompt_copy = args.out_dir / f"{run_id}.prompt.txt"
    config_path = args.out_dir / f"{run_id}.config.json"
    prompt_copy.write_text(prompt, encoding="utf-8")

    tool_config = {
        "codex_cli": subprocess.run([codex, "--version"], text=True, capture_output=True, check=True).stdout.strip(),
        "stage": args.stage,
        "model": args.model,
        "reasoning": args.reasoning,
        "resolved_model_version": None,
        "model_version_limit": "codex exec --json exposes the requested model alias and CLI build, not the resolved backend model revision",
        "model_catalog_source": "pinned-file" if args.model_catalog_file else "codex-debug-models",
        "model_catalog_source_sha256": model_catalog_source_sha256,
        "model_catalog_sha256": catalog_sha256,
        "model_tool_metadata_original": {
            "tool_mode": original_model.get("tool_mode"),
            "shell_type": original_model.get("shell_type"),
            "apply_patch_tool_type": original_model.get("apply_patch_tool_type"),
            "experimental_supported_tools": original_model.get("experimental_supported_tools", []),
        },
        "model_tool_metadata_effective": {
            "tool_mode": catalog_model.get("tool_mode"),
            "shell_type": catalog_model.get("shell_type"),
            "apply_patch_tool_type": catalog_model.get("apply_patch_tool_type"),
            "experimental_supported_tools": catalog_model.get("experimental_supported_tools", []),
        },
        "task_timeout_seconds": MAX_SESSION_SECONDS,
        "startup_timeout_seconds": args.startup_timeout_seconds,
        "sandbox": "workspace-write via --approve-for-me with candidate-only cwd; native tools are gated by shell feature/model metadata and disabled-feature settings",
        "user_config": "ignored",
        "project_doc_max_bytes": 0,
        "mcp_server": "single required disclosure collector stdio server; Codex also registers three generic resource handlers with this server",
        "mcp_tools": MCP_TOOLS,
        "mcp_resource_handlers": [
            "list_mcp_resources",
            "list_mcp_resource_templates",
            "read_mcp_resource",
        ],
        "mcp_resource_access": "collector advertises tools only and returns method-not-found for all resource methods; see resource-protocol-probe-summary.json",
        "model_metadata_tools": {
            "send_user_message_async": [
                "request_user_input_async (legacy alias)",
                "send_message_to_user_async",
            ],
            "clock": ["current_time"],
        },
        "core_utility_tools_disabled": [
            "update_plan",
            "request_user_input",
        ],
        "mcp_tool_schema_sha256": digest(
            json.dumps(
                mcp_tool_schemas(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ),
        "mcp_approval": "auto for the four explicitly allowlisted collector tools",
        "web_search": "disabled",
        "disabled_features": DISABLED_FEATURES,
        "approval_policy": "automatic review; shell feature disabled and apply_patch metadata removed; code-mode wrappers may expose only enabled nested handlers",
    }
    tool_config["collector_sha256"] = hashlib.sha256(args.collector.read_bytes()).hexdigest()
    manifest_info = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_sha256 = manifest_info["manifest_sha256"]
    exclusion_sha256 = manifest_info["exclusion_sha256"]
    command = [
        codex,
        "--no-daemon",
        "exec",
        "--approve-for-me",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--strict-config",
        "-C",
        str(root),
        "--model",
        args.model,
        "-c",
        f"model_reasoning_effort={json.dumps(args.reasoning)}",
        "-c",
        "project_doc_max_bytes=0",
        "-c",
        f"model_catalog_json={json.dumps(str(catalog_path))}",
        "-c",
        "tools.update_plan.enabled=false",
        "-c",
        "tools.experimental_request_user_input.enabled=false",
    ]
    for feature in DISABLED_FEATURES:
        command.extend(["--disable", feature])
    command.extend(["-c", 'web_search="disabled"'])
    server_args = [
        str(args.collector),
        "mcp",
        "--manifest",
        str(manifest),
        "--record",
        str(record),
    ]
    config_values = {
        "mcp_servers.disclosure_collector.command": json.dumps(sys.executable),
        "mcp_servers.disclosure_collector.args": json.dumps(server_args),
        "mcp_servers.disclosure_collector.enabled": "true",
        "mcp_servers.disclosure_collector.required": "true",
        "mcp_servers.disclosure_collector.enabled_tools": json.dumps(MCP_TOOLS),
        "mcp_servers.disclosure_collector.default_tools_approval_mode": '"auto"',
    }
    for tool in MCP_TOOLS:
        config_values[f"mcp_servers.disclosure_collector.tools.{tool}.approval_mode"] = '"auto"'
    for key, value in config_values.items():
        command.extend(["-c", f"{key}={value}"])
    stage_instruction = {
        "formal": "Complete one independent formal reading session.",
        "non-scored": "Complete one independent, non-scored reading session.",
    }[args.stage]
    task_prompt = (
        f"{stage_instruction} Use the available collector tools only. "
        "First read the complete candidate-root AGENTS.md, then inspect the candidate as needed. "
        "Submit exactly six non-empty strings with keys entry, constraints, authorities, relevant_decisions, validation, unknowns. "
        "The collector checks structure only; answer from the candidate and do not infer content you have not read.\n\n"
        "Task:\n" + prompt
    )
    command.extend(["--json", task_prompt])
    tool_config_sha256 = digest(json.dumps(tool_config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    start_args = [
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
        args.candidate,
        "--task",
        args.task,
        "--task-hash",
        hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "--model-config",
        f"{args.model}; reasoning={args.reasoning}; {tool_config['codex_cli']}",
        "--tool-config-sha256",
        tool_config_sha256,
        "--startup-timeout-seconds",
        args.startup_timeout_seconds,
    ]
    if args.retry_of:
        start_args += [
            "--retry-of",
            args.retry_of.resolve(strict=True),
            "--retry-reason",
            args.retry_reason,
        ]
    call_collector(args, *start_args)
    config_path.write_text(
        json.dumps(
            {
                "config": tool_config,
                "tool_config_sha256": tool_config_sha256,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "manifest_sha256": manifest_sha256,
                "exclusion_sha256": exclusion_sha256,
                "candidate_root": str(root),
                "manifest_path": str(manifest),
                "record_path": str(record),
                "effective_command": command[:-1],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    process = None
    cancelled_signal = None
    previous_handlers = {}

    def handle_cancellation(signum, _frame):
        raise RunnerCancelled(signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, handle_cancellation)
    try:
        with trace.open("w", encoding="utf-8") as log:
            process_started = time.monotonic()
            process = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            timed_out = False
            startup_timed_out = False
            while process.poll() is None:
                current = json.loads(record.read_text(encoding="utf-8"))
                if current.get("status") != "started":
                    terminate_process_group(process)
                    break
                started = current.get("started_monotonic")
                if started is None and time.monotonic() - process_started > args.startup_timeout_seconds:
                    terminate_process_group(process)
                    call_collector(
                        args,
                        "failed",
                        "--record",
                        record,
                        "--reason",
                        f"no successful first read within {args.startup_timeout_seconds} seconds of runner launch",
                        "--failure-class",
                        "workspace_load",
                    )
                    startup_timed_out = True
                    break
                if started is not None and time.monotonic() - started > MAX_SESSION_SECONDS:
                    terminate_process_group(process)
                    call_collector(
                        args,
                        "timeout",
                        "--record",
                        record,
                        "--reason",
                        f"task exceeded {MAX_SESSION_SECONDS} seconds after first successful read",
                    )
                    timed_out = True
                    break
                time.sleep(0.2)
    except RunnerCancelled as cancellation:
        cancelled_signal = cancellation.signum
    finally:
        if process is not None:
            terminate_process_group(process)
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        catalog_path.unlink(missing_ok=True)
    current = json.loads(record.read_text(encoding="utf-8"))
    if cancelled_signal is not None and current["status"] == "started":
        call_collector(
            args,
            "interrupted",
            "--record",
            record,
            "--reason",
            f"runner received {signal.Signals(cancelled_signal).name} after cleaning its child process group",
            "--failure-class",
            "infrastructure",
        )
        current = json.loads(record.read_text(encoding="utf-8"))
    if current["status"] == "started":
        evidence_class = classify_runner_failure(trace) if process.returncode != 0 else None
        failure_class = evidence_class or "task"
        if failure_class == "quota_exhausted":
            write_record(
                quota_marker,
                {"run_id": run_id, "record": str(record), "trace": str(trace)},
            )
        reason = f"Codex exited with status {process.returncode} without a persisted six-field submit; classified as {failure_class}"
        call_collector(
            args,
            "failed",
            "--record",
            record,
            "--reason",
            reason,
            "--failure-class",
            failure_class,
        )
    current = json.loads(record.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": current["status"],
                "record": str(record),
                "trace": str(trace),
                "config": str(config_path),
                "timed_out": timed_out,
                "startup_timed_out": startup_timed_out,
                "interrupted": cancelled_signal is not None,
            }
        )
    )
    if cancelled_signal is not None:
        return 128 + cancelled_signal
    if timed_out or startup_timed_out:
        return 124
    return 2 if current["status"] == "failed" and process.returncode == 0 else process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
