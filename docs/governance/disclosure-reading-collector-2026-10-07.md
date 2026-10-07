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

The runner's prompt currently labels sessions as non-scored. Ticket 08 must
freeze the prompt and stage label for formal use; later formal-stage runners
must not inherit this pilot label implicitly.

The non-scored synthetic dry run for ticket 02 used Codex CLI 0.160.0, model
`gpt-6.1-sol`, and medium reasoning. Its local trace and record are in the
ignored `dev-log/disclosure-readability-recovery/ticket02/` directory. This is
tooling evidence only; it is not part of a formal sample or a semantic grade.
Its trace records only collector calls; it does not prove native file, image,
editing, or permission tools were absent from the model context. The runner
now explicitly disables Codex's `view_image` and
`request_permissions_tool` features. A real-provider inventory probe was
blocked before the model turn by a Codex usage limit. Two later loopback mock
provider requests reached `/v1/responses` but advertised an empty `tools`
array, so they did not establish whether MCP initialization succeeded or which
native tools were available. These diagnostic attempts used a different local
provider and are not formal-model evidence. The usage-limit attempts and
loopback requests, traces, configs, manifests, and synthetic candidate are
preserved under
`dev-log/disclosure-readability-recovery/ticket02/tool-inventory-probe/` and
`dev-log/disclosure-readability-recovery/ticket02/tool-schema-probe-loopback/`.
Verified absence of native file, image, editing, and permission tools remains
a formal-run readiness blocker. Do not claim an MCP-only context until an
actual inventory and harmless negative-access probe establish that boundary.
