#!/usr/bin/env python3
"""Run one isolated Codex reading session through the disclosure collector MCP tools."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from disclosure_reading_collector import MAX_SESSION_SECONDS, digest, mcp_tool_schemas


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


def classify_runner_failure(trace_path):
    infrastructure_indicators = (
        "connection refused",
        "rate limit",
        "try again at",
        "usage limit",
    )
    protocol_indicators = (
        "approval policy",
        "failed to initialize",
        "mcp server",
        "unexpected argument",
        "transport",
    )
    for line in trace_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            if line.lstrip().casefold().startswith(("error:", "fatal:")):
                message = line.casefold()
                if any(word in message for word in infrastructure_indicators):
                    return "infrastructure"
                if any(word in message for word in protocol_indicators):
                    return "protocol"
            continue
        if event.get("type") in {"error", "turn.failed"}:
            message = json.dumps(event).casefold()
            if any(word in message for word in infrastructure_indicators):
                return "infrastructure"
            if any(word in message for word in protocol_indicators):
                return "protocol"
        item = event.get("item", {})
        if item.get("type") == "error":
            return "protocol"
        error = event.get("error") or item.get("error")
        if error:
            message = json.dumps(error).casefold()
            if any(word in message for word in infrastructure_indicators):
                return "infrastructure"
            if any(word in message for word in protocol_indicators):
                return "protocol"
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
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument(
        "--reasoning",
        choices=("low", "medium", "high", "xhigh", "max", "ultra"),
        default="medium",
    )
    parser.add_argument(
        "--startup-timeout-seconds", type=float, default=STARTUP_TIMEOUT_SECONDS
    )
    parser.add_argument("--retry-of", type=Path)
    parser.add_argument("--retry-reason", default="")
    args = parser.parse_args()

    codex = shutil.which("codex")
    if not codex:
        parser.error("codex CLI is not available on PATH")
    args.collector = (
        Path(__file__).with_name("disclosure_reading_collector.py").resolve()
    )
    root = args.root.resolve(strict=True)
    manifest = args.manifest.resolve(strict=True)
    prompt = args.prompt_file.read_text(encoding="utf-8")
    if not prompt.strip():
        parser.error("prompt file must contain a non-empty task")
    if args.startup_timeout_seconds <= 0:
        parser.error("startup timeout must be a positive number of seconds")
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{args.candidate}-{args.task}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{time.monotonic_ns()}"
    record = args.out_dir / f"{run_id}.json"
    trace = args.out_dir / f"{run_id}.jsonl"
    prompt_copy = args.out_dir / f"{run_id}.prompt.txt"
    config_path = args.out_dir / f"{run_id}.config.json"
    prompt_copy.write_text(prompt, encoding="utf-8")

    tool_config = {
        "codex_cli": subprocess.run(
            [codex, "--version"], text=True, capture_output=True, check=True
        ).stdout.strip(),
        "model": args.model,
        "reasoning": args.reasoning,
        "resolved_model_version": None,
        "model_version_limit": "codex exec --json exposes the requested model alias and CLI build, not the resolved backend model revision",
        "task_timeout_seconds": MAX_SESSION_SECONDS,
        "startup_timeout_seconds": args.startup_timeout_seconds,
        "sandbox": "workspace-write via --approve-for-me (candidate-only cwd; no execution tools)",
        "user_config": "ignored",
        "project_doc_max_bytes": 0,
        "mcp_server": "single required disclosure collector stdio server",
        "mcp_tools": MCP_TOOLS,
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
        "approval_policy": "automatic review; no execution tools enabled",
    }
    tool_config["collector_sha256"] = hashlib.sha256(
        args.collector.read_bytes()
    ).hexdigest()
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
        config_values[
            f"mcp_servers.disclosure_collector.tools.{tool}.approval_mode"
        ] = '"auto"'
    for key, value in config_values.items():
        command.extend(["-c", f"{key}={value}"])
    task_prompt = (
        "Complete one independent, non-scored reading session. Use the available collector tools only. "
        "First read the complete candidate-root AGENTS.md, then inspect the candidate as needed. "
        "Submit exactly six non-empty strings with keys entry, constraints, authorities, relevant_decisions, validation, unknowns. "
        "The collector checks structure only; answer from the candidate and do not infer content you have not read.\n\n"
        "Task:\n" + prompt
    )
    command.extend(["--json", task_prompt])
    tool_config_sha256 = digest(
        json.dumps(
            tool_config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
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

    with trace.open("w", encoding="utf-8") as log:
        process_started = time.monotonic()
        process = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, text=True
        )
        timed_out = False
        startup_timed_out = False
        while process.poll() is None:
            current = json.loads(record.read_text(encoding="utf-8"))
            started = current.get("started_monotonic")
            if (
                started is None
                and time.monotonic() - process_started > args.startup_timeout_seconds
            ):
                process.kill()
                process.wait()
                call_collector(
                    args,
                    "failed",
                    "--record",
                    record,
                    "--reason",
                    f"no successful first read within {args.startup_timeout_seconds} seconds of runner launch",
                    "--failure-class",
                    "infrastructure",
                )
                startup_timed_out = True
                break
            if started is not None and time.monotonic() - started > MAX_SESSION_SECONDS:
                process.kill()
                process.wait()
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
    current = json.loads(record.read_text(encoding="utf-8"))
    if current["status"] == "started":
        evidence_class = (
            classify_runner_failure(trace) if process.returncode != 0 else None
        )
        failure_class = evidence_class or "task"
        reason = (
            f"Codex exited with status {process.returncode} without a persisted six-field submit; "
            f"classified as {failure_class}"
        )
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
            }
        )
    )
    if timed_out or startup_timed_out:
        return 124
    return (
        2
        if current["status"] == "failed" and process.returncode == 0
        else process.returncode
    )


if __name__ == "__main__":
    raise SystemExit(main())
