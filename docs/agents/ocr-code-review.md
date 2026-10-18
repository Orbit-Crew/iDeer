---
id: docs-agents-ocr-code-review
kind: reference
status: current
owner: repository maintainers
scope: operating notes for the open-code-review (ocr) CLI on this repository — scoping, timeout behavior, resume semantics, and evidence retention learned in the telemetry .dat review cycle (PR #86)
last-verified: 2026-10-17
verified-against: PR #86 review sessions fdc9d8ee / 9d3b2721 / 57510407 / 25a56330
---

# open-code-review (ocr) operating notes

`ocr review` generates AI line-level review comments from a git diff. These notes record the operating behaviors that cost the telemetry review cycle extra runs; they are CLI behaviors, not repo policy.

## Scope per run

Restrict each run to the files that need it with `--exclude '<patterns>'` (comma-separated gitignore-style). A whole-PR run over the three telemetry tool modules (1,100+ new lines) failed its deep pass; the same files scoped alone, or a single fix-commit range (`--commit <sha>` / `--from <ref> --to <ref>`), finished within budget and cost about half the tokens.

## Timeouts

`--timeout` raises ocr's own per-group review budget; it does **not** lift the fixed ~300-second per-request deadline in the CLI's HTTP client (`context deadline exceeded` with `duration_ms` ≈ 300000 in the session log). Requests that outgrow that deadline — large-file planning passes on a reasoning model — fail regardless of `--timeout`. Mitigation is scoping (smaller groups → smaller prompts), not a bigger flag.

## Resume semantics

`ocr review --resume <id>` continues a run that was **killed mid-execution**; it is a no-op for a run that exited normally with partial results ("completed with failure" reports), replaying the cache at zero cost and zero new coverage. For those, start a fresh run with a tighter scope instead. The resume id prints on failure or via `ocr session list`; session JSONL logs live under `~/.opencodereview/sessions/`.

## Evidence retention

Write results to a file with `--output <path>` and keep the file in the session's `dev-log/` (git-ignored) — background task ids and in-memory outputs do not survive session restarts, and the review evidence is part of the handoff record.

## Provider

`--provider` / `--model` override the configured LLM for one run (`ocr llm providers` lists built-ins). HTTP 429 storms from the provider gateway exhaust retries and fail the group; a fresh scoped run after a cooldown is the working recovery.
