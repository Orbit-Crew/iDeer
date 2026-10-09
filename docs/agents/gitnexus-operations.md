---
id: gitnexus-operations
kind: reference
status: current
owner: repository maintainers
scope: GitNexus worktree analysis and root guidance maintenance
last-verified: 2026-10-09
verified-against: docs/disclosure-branch-root @ f10b0c525eb1438d043951a30d19a99986761286
---

# GitNexus operations

## Operations

### Before editing

Use the upstream impact operation in the current worktree. MCP:

```text
impact({target: "symbolName", direction: "upstream"})
```

CLI fallback:

```sh
node .gitnexus/run.cjs impact "symbolName" --direction upstream --repo .
```

Record callers, affected processes, and risk. HIGH or CRITICAL requires a user warning before edits. UNKNOWN stays unresolved. Search source callers when graph resolution is empty or uncertain; plain-object access, dynamic dispatch, and cross-language calls may be missing from the graph. Search adds evidence and never replaces impact.

For unfamiliar code, query execution flows:

```text
query({search_query: "concept"})
node .gitnexus/run.cjs query "concept" --repo .
```

For a symbol's callers, callees, and processes, use `context({name: "symbolName"})` or `node .gitnexus/run.cjs context "symbolName" --repo .`.

### Before committing

Analyze all graph changes:

```text
detect_changes({scope: "all"})
node .gitnexus/run.cjs detect-changes --scope all --repo .
```

Partial or truncated output is incomplete. Rerun it and retain the full result. A zero means the graph did not map a change; it does not establish that nothing was affected. Use compare mode for regression review:

```text
detect_changes({scope: "compare", base_ref: "product/offline-1.x"})
node .gitnexus/run.cjs detect-changes --scope compare --base-ref "product/offline-1.x" --repo .
```

The sole partial exception is a commit where every changed path ends in `.md`. Record the partial result in the commit message; no re-index is required for that Markdown-only candidate. A script, test, configuration, workflow, or other non-Markdown path requires complete analysis.

### Worktree and index

If `.gitnexus/run.cjs` is missing in a fresh checkout, bootstrap GitNexus with a package runner and inspect its local help before indexing:

```sh
bunx gitnexus@latest --help
bunx gitnexus@latest analyze --index-only
```

Use `pnpm dlx gitnexus@latest` for the same help and analyze commands when Bun is unavailable. Avoid `npx` with npm 11 because that path is known to crash (#1939). Once the runner exists, continue with the worktree status and index identity checks below.

Run status from the worktree being changed. Confirm its repository path, branch, indexed commit, `status`, and `incompleteReasons`; an index from another checkout is not evidence for this tree. For routine indexing, run `node .gitnexus/run.cjs analyze --index-only`. This mode does not inject generated guidance or skills. Use the supported CLI help for current options. Do not use `--skip-git` for normal worktree indexing.

An index is usable for impact only when it identifies the current worktree and has no incomplete reasons. If status is stale, rebuild it in that worktree. Keep the full command output when the analyzer reports omissions, warnings, or truncation. A missing process or caller in incomplete output remains unresolved.

### Rename and security review

Use the graph-aware `rename` operation when renaming symbols. Read `.claude/skills/gitnexus-refactoring/SKILL.md` when that skill is installed. For security review, `explain({target: "fileOrSymbol"})` lists taint flows; first build the control-flow/PDG layer with `analyze --pdg`. Read `.claude/skills/gitnexus-taint-analysis/SKILL.md` when changing that subsystem.

### Resources

MCP resources:

- `gitnexus://repo/AgentPlatform/context` for the repository overview and index freshness.
- `gitnexus://repo/AgentPlatform/clusters` for functional areas.
- `gitnexus://repo/AgentPlatform/processes` for execution flows.
- `gitnexus://repo/AgentPlatform/process/{name}` for one process trace.

Read `.claude/skills/gitnexus-guide/SKILL.md` for tool and resource details, `.claude/skills/gitnexus-exploring/SKILL.md` for architecture searches, or `.claude/skills/gitnexus-impact-analysis/SKILL.md` for blast-radius review. Each skill owns its full procedure when installed.

## Guidance maintenance

The local analyzer can regenerate the managed root block but has no supported compact-template setting. After generation, normalize the recognized block, then sync and check mirrors:

```sh
node .gitnexus/run.cjs analyze --skip-skills --no-stats
python3 scripts/maintain_gitnexus_guidance.py --normalize
python3 scripts/sync_agent_guidance.py --write
python3 scripts/maintain_gitnexus_guidance.py --check
python3 scripts/sync_agent_guidance.py --check
```

The normalizer changes only the root managed block. It accepts the known generated template or its compact form; unknown templates, missing markers, or duplicate markers fail before writing. The checker is read-only and reports byte budgets, missing rules, broken reference anchors, or mirror drift. Use `--check-exemption --base-ref BASE --head-ref HEAD` to verify that every changed path in a candidate has the `.md` suffix.
