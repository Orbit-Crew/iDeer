---
id: disclosure-reading-collector-2026-10-07
kind: reference
status: current
owner: repository maintainers
scope: reader-isolated document inspection, six-field submission, and preserved attempt records
last-verified: 2026-10-07
verified-against: worktree docs/disclosure-readability-recovery
---

# Disclosure reading collector

This collector runs one candidate-pinned reading session. It records reads,
search output, timing, model and tool configuration, and the submitted answer.
It validates answer structure only. Semantic scoring is a separate process and
is not available to the reader session.

## Prepare a candidate and session

Create a full manifest before the session, then launch the Codex runner with a
frozen candidate root, task prompt, and an output directory outside the
candidate:

```sh
python3 scripts/disclosure_reading_collector.py manifest \
  --root /path/to/candidate --out /path/to/session/candidate.manifest.json
python3 scripts/run_disclosure_reading_session.py \
  --root /path/to/candidate \
  --manifest /path/to/session/candidate.manifest.json \
  --candidate after --task runtime \
  --prompt-file /path/to/session/task.txt \
  --out-dir /path/to/session/records
```

The runner pins the available model and reasoning setting, records the Codex
CLI build and collector hash, saves a copy and digest of the task prompt, and
writes the effective command and comparable configuration fingerprint. The
sidecar keeps invocation-specific paths and the full command separately from
the comparable identity so linked retries and baseline/after candidates can
match. Codex JSONL identifies the requested model alias and CLI build but does
not expose the resolved backend model revision; the sidecar records this limit
instead of claiming a pinned revision. This blocks claims of strict model
comparability. A result may report this as a limitation, but accepting the
limitation does not establish strict comparability or permit a strict pass.
Its default is
`gpt-6.1-sol` with medium reasoning. Change the model only when a registered
experiment explicitly requires it; baseline and after sessions must use the
same value.

Before timing starts, the reader receives the complete MCP tool schemas and
this six-field contract: `entry`, `constraints`, `authorities`, `relevant_decisions`,
`validation`, and `unknowns` must each be a non-empty string. The runner
allowlists these four MCP tools:

- `read_candidate` reads a candidate-relative UTF-8 line range. Its first
  successful call must read every line of the candidate root `AGENTS.md`.
- `search_candidate` performs a literal text search. Returned lines count as
  read content; empty queries are rejected.
- `submit_answer` persists exactly the six fields and stops the timer at the
  first submission. Wrong but structurally valid answers are saved unchanged.
- `report_session_event` records external help or contamination.

The collector validates the entire candidate tree against its full manifest
before each read or search. Direct reads of metadata, specifications, benchmark
cases, evaluator instructions, scoring files, and scoring tests fail. Searches
skip the same material. The manifest retains the full candidate file hashes,
the exclusion list, and an exclusion digest. The timed model does not receive
the manifest itself.

The session record contains every successful read and search range, returned
UTF-8 content bytes, unique bytes after range union, collector output bytes,
MCP tool output bytes, the monotonic start and submission times, answer, model
configuration, manifest digest, and exclusion digest. The adjacent JSONL trace
preserves the actual Codex tool calls and results. Keep the record, trace,
prompt copy, and configuration sidecar together in the session artifact
directory.

## Isolation and retries

The runner starts Codex with user configuration ignored and automatic review
enabled. It disables shell execution, unified execution, delegation, sleep,
web search, browser, computer use, image generation, image viewing, permission
requests, apps, plugins, and memory.
The only enabled MCP server is the required collector, allowlisted to the four
tools above. `project_doc_max_bytes=0` prevents automatic loading of project
`AGENTS.md`; the reader must get that content through the timed collector.
The comparable configuration fixes the first-read startup deadline at 60
seconds and the task timeout at 300 seconds. Startup expiration is retained as
a retryable infrastructure failure; task timeout is terminal and cannot be
redrawn. Both values are recorded with the session and included in the config
fingerprint. A completed run that exits without a persisted submission is a
terminal task failure; only nonzero exits with explicit transport/config
evidence are eligible protocol retries.
Codex config supports these feature and MCP allowlist controls in its
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

Each attempt has a unique ID and its original record is retained. Only an
infrastructure or protocol failure can have one linked retry, with an explicit
reason and identical candidate, task, model, and tool configuration. A timeout
or submitted answer cannot be retried. Mark externally provided help or other
contamination before submission with the audit tool. The reader cannot mark an
answer correct or change the failure status.

The runner defaults to the `non-scored` stage. Its `--stage formal` option uses
a separate formal-session label; the selected stage is recorded in the tool
configuration and included in its fingerprint. Ticket 08 must freeze the
complete prompt and stage configuration before formal use; no formal
experiment is frozen yet.

The non-scored synthetic dry run for ticket 02 used Codex CLI 0.160.0, model
`gpt-6.1-sol`, and medium reasoning. Its local trace and record are in the
ignored `dev-log/disclosure-readability-recovery/ticket02/` directory. This is
tooling evidence only; it is not part of a formal sample or a semantic grade.
The same-provider trace records the collector calls and a harmless attempt to
read `../external-canary.txt`; the collector rejected it with
`ERROR: read requires a safe, candidate-relative path` and persisted the same
denial in `tool_errors`. No canary content was returned or read. The reader
then submitted the six-field answer. The prior trace by itself did not establish
the native tool boundary; the audit now combines this negative proof with the
exact-version Codex registration source and the effective runner config.

The runner requests disabling `shell_tool` and `unified_exec`, but Codex 0.160.0
reports `unified_exec` as stable and the selected model metadata has
`shell_type=unified_exec`. The source shows the shell registration first exits
when `Feature::ShellTool` is disabled (or no execution environment exists, or
the model shell type is disabled), before checking `UnifiedExec`. Thus the
`unified_exec` feature readout does not register shell execution in this run;
the runner's `shell_tool` feature gate is the outer control. Native
`ApplyPatchHandler` has a separate model metadata gate; the runner now passes
an ephemeral catalog with `apply_patch_tool_type=null`, preserving the model
alias and all other selected metadata. The runner also explicitly disables
the configuration-gated `update_plan` and ordinary `request_user_input`
handlers. The public runner CLI test checks that the effective catalog and
these configuration settings reach the subprocess and that the temporary file
is removed after exit.

The selected model metadata also enables `send_user_message_async` and
`clock`. Codex 0.160.0 registers the legacy `request_user_input_async` alias,
`send_message_to_user_async`, and `current_time` for those entries. These are
human-interaction/time utilities, not candidate or scoring-file readers. No
such calls appear in the fresh trace. A future request for outside help must be
recorded through `report_session_event` and treated as contamination. The
`exec` and `wait` tools are CodeMode V8 orchestration wrappers; they dispatch
only enabled nested handlers and have no Node filesystem or fetch/network
global, with module imports rejected. The MCP registry additionally registers
`list_mcp_resources`, `list_mcp_resource_templates`, and `read_mcp_resource`.
The single collector server advertises only tool capability and responds
`-32601 method not found` to all three resource protocol methods, so it exposes
no candidate or scoring resources. The runner config now records these three
handlers and all three model-metadata handlers rather than labeling the four
collector tools as the entire Codex registry. The normal plan and synchronous
user-input handlers are explicitly disabled in the run configuration. The
metadata-enabled asynchronous human-help handlers remain available and are
listed rather than mislabeled as absent.

The source audit is pinned to the installed CLI build `codex-cli 0.160.0` and
upstream tag `rust-v0.160.0` at commit
`a956835d020762cb2b570053af06f643a11c0ecc`. The reviewed `spec_plan.rs`
snapshot has SHA-256
`849ef21d4e5c83febdc31eacd7609911d43e3f69a35168fe02ae899273b5ef3e`; its
`add_shell_tools` gate is at lines 1083–1117. The complete versioned source,
config, protocol probe, and per-session canary evidence are summarized in the
ignored audit file
`dev-log/disclosure-readability-recovery/ticket02/final-isolation-audit/tool-registration-audit.md`.
Earlier usage-limit failures and loopback requests with empty `tools` arrays
remain preserved as inconclusive historical diagnostics; they are not used as
absence evidence. The CLI still does not expose the resolved backend model
revision. Report that limitation, and do not claim strict model comparability
or a strict pass. The runner defaults to `non-scored`; its `--stage formal`
option selects the distinct formal-session label and fingerprints that stage.
Ticket 08 must freeze the prompt and stage configuration before formal use;
formal sessions must report any outside-help request as contamination.
