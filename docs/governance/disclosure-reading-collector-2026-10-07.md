---
id: disclosure-reading-collector-2026-10-07
kind: reference
status: current
owner: repository maintainers
scope: reader-isolated document inspection, six-field submission, dispatch stopping, and preserved attempt lifecycle
last-verified: 2026-10-08
verified-against: worktree docs/disclosure-dual-track, ticket 02 recovery changes
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
a retryable workspace-load failure; task timeout is terminal and cannot be
redrawn. Both values are recorded with the session and included in the config
fingerprint. A completed run that exits without a persisted submission is a
terminal task failure; explicit collector transport/config evidence is a
protocol failure.
Codex config supports these feature and MCP allowlist controls in its
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

Each attempt has a unique ID and its original record is retained. An
infrastructure, workspace-load, or protocol failure can have one linked retry,
with an explicit reason and identical candidate, task, model, and tool
configuration. Quota exhaustion is terminal for dispatch: the runner records a
quota marker before closing the attempt, and later invocations in the same
output directory recover the stop from that marker, a quota-classified record,
or a retained trace, then return `dispatch_stopped` with exit code 75. Each
runner invocation accepts one task and does not own the caller's queue; the
caller must stop launching tasks and leave unstarted entries in their existing
order. A task timeout or submitted answer is not retryable; a
wrong answer remains a submitted answer for the scorer to grade. The runner
handles SIGINT and SIGTERM by killing and waiting for only its Codex process
group, then records an open attempt as interrupted/infrastructure. If an
answer was already persisted, cancellation preserves the submitted status.
Mark externally provided help or other contamination before submission with
the audit tool. The reader cannot mark an answer correct or change the failure
status.

Session records are updated under a per-record process lock. Each update is
flushed to a same-directory temporary file and atomically replaced, so runner
polling sees a complete JSON snapshot and concurrent collector commands do not
discard each other's events. A terminal submission cannot be overwritten by a
later failure close. The final record and JSONL trace remain together even for
failed, timed-out, or interrupted attempts; failure-close time is not an answer
submission duration.

The runner defaults to the `non-scored` stage. Its `--stage formal` option uses
a separate formal-session label; the selected stage is recorded in the tool
configuration and included in its fingerprint. Ticket 08 froze experiment
`pdr-2026-10-07-16cc740f` after pilot review. Its immutable queue and candidate
manifests are recorded in the coordinator handoff below; no formal session has
started yet.

For a frozen batch, supply the same single-model catalog with
`--model-catalog-file` to every session. The runner records the source-file
digest and the effective catalog digest after native patch metadata is
removed. Do not rely on a fresh live catalog lookup for each attempt.

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
Ticket 08 has frozen the prompt and stage configuration; formal sessions must
report any outside-help request as contamination. Use the same single-model
catalog file for every attempt so source and effective catalog digests stay
fixed within the experiment.

## Ticket 08 formal experiment handoff

The frozen experiment uses baseline commit
`867f6709642854721f209a15e362d79a96b3b489` (tree
`f2309f2e6c2fb7b64bfe59c5ace9523b6c742838`) and after commit
`16cc740f839876b7b7581a7cbbaf9a318d4c14ac` (tree
`6f1c4e340758b92ec8e8d3c165185a98a832253f`). The frozen manifest digests are
`ea6d866455937115b99f9bcb9d688923f37bd20cac967e34f8d79030bbcb924a` and
`45e45e0e61b15f812a767978e8354b17ce49bb509c28ffbb703d79811d01303b`. The
32-slot queue is `dev-log/disclosure-readability-recovery/ticket08/archive/manifests/frozen-queue-pdr-2026-10-07-16cc740f.csv`
(SHA-256 `54458c060c267c2272b69cd2ec5330e95d5cb83c13d200d8c746f6a1c3dba1fe`);
the complete machine-readable freeze record is
`dev-log/disclosure-readability-recovery/ticket08/archive/manifests/frozen-experiment-pdr-2026-10-07-16cc740f.json`.
Ticket 09 occupies the first 20 routine slots and ticket 10 the final 12
special slots. The queue reverses task order between replicates and alternates
candidate-first order within each task.

Use `--stage formal`, the pinned source catalog
`dev-log/disclosure-readability-recovery/ticket08/archive/model-catalog/gpt-6.1-sol-source.json`
(SHA-256 `9ce669a7c68b7b64004832d0479fa78563f008d4d2b8cc4e26bfc09346d0f33d`),
model alias `gpt-6.1-sol`, and medium reasoning for every slot. The offline
formal tool-configuration fingerprint is
`da55cd757919611c8577414c449a548e3c3ec52b3c4f8955596e15d4ab2cd078`; check
the first session sidecar and require every later sidecar to match it and both
catalog digests before accepting a record. The archived effective JSON is
retained for audit and is not supplied as `--model-catalog-file`; the runner
derives the effective catalog and passes a temporary copy to Codex. The
scoring rubric is fixed at SHA-256
`bb40af129e64da013885c4b74cb51169bf047ae5139f4f3deee16af0cb9fc171`.

Each session has a 60-second startup limit and 300-second task limit, with no
more than three readers at once. Only an infrastructure or protocol failure
allows one linked retry; retain the first attempt and retry unchanged task,
candidate, manifest, prompt, catalog, and formal config. A wrong answer or task
timeout remains a failed logical slot and cannot be replaced. An interrupted
attempt can be retried only when it is explicitly classified as infrastructure
or protocol; a task-class interruption remains failed and is not replaced.
The scorer input contains exactly 32 logical slots; keep every raw retry
attempt in its audit archive rather than adding it as another logical record.
Reader access remains limited to candidate material through the four collector
tools; scorer, rubric, specifications, and this handoff remain excluded.

Codex CLI 0.160.0 reports the requested alias but not the resolved backend
model revision; this is a documented strict-comparability limitation, not a
freeze blocker. Provider identifier and endpoint host are not available from
the local catalog. Raw records and audit files remain in the ignored local
`dev-log` archive; no external durable archive is configured, so a clean
checkout cannot reproduce raw reads or answers.
