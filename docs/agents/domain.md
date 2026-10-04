# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root, or
- **`CONTEXT-MAP.md`** at the repo root if it exists: it points at one `CONTEXT.md` per context. Read each one relevant to the topic.
- **`docs/adr/`**: read ADRs that touch the area you're about to work in. In multi-context repos, also check `src/<context>/docs/adr/` for context-scoped decisions.
- **`docs/project-state.md`**: candidate-scoped implementation, integration, and verification status per domain. Read it when you need to know whether a capability is actually implemented, integrated, or verified on the current candidate — an accepted decision alone does not mean shipped, validated behavior.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

> 本仓库的现行决策入口是[决策索引](../decisions/README.md)：编号 ADR 在 `docs/adr/`（如 `0007-agent-terminology-unification.md`），历史 dated decision 保留在 `docs/decisions/`。新 ADR 一律按 `NNNN-topic-name.md` 编号命名，该规则以 `docs/decisions/README.md` 的声明为准。决策状态词为 `current`、`draft`、`superseded`、`archived`；决策被接受只说明"定了什么"，实现/集成/验证状态以[项目状态页](../project-state.md)为准，不得由决策状态推断。

## File structure

Single-context repo (most repos):

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

Multi-context repo (presence of `CONTEXT-MAP.md` at the root):

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

当前仓库为 **single-context**（无 `pnpm-workspace.yaml` / 根 `package.json` workspaces / 根 `packages/*`），使用根 `CONTEXT.md` + `docs/adr/` 布局。

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
