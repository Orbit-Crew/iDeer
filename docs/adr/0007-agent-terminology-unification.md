---
id: adr-0007-agent-terminology-unification
kind: decision
status: current
owner: repository maintainers
scope: code-level and route vocabulary unifies on "agent" with permanent redirects for pre-unification expert paths; the display word 专家 stays only in zh-CN locale strings; the data source does not move
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 02af2a4e8
---

# Code-level vocabulary unifies on "agent"; 专家 survives only as a display word

Upstream deer-flow names the conversational-expert concept "agent" everywhere: `/workspace/agents` routes, `agent-card` / `agent-settings-dialog` / `agent-welcome` components, the `/api/agents` router, and every test and mock. iDeer renamed the user-facing surface to "experts" — `/workspace/capabilities/experts/*` routes, `ExpertList`, expert edit and chat pages — while the backend domain object stayed "agent" (resource type `agent`, agent metadata reconciliation, frozen agent inputs). The rename is skin-deep: routes and component names only.

Each upstream convergence round pays the same tax for this split. Upstream tests hard-code agents paths and get rewritten to experts paths by hand (the v2.1.0 round rewrote `agent-chat.spec.ts` end to end). Upstream improvements to management components we deleted (`agent-welcome`, `agent-settings-dialog`) land as delete/modify conflicts needing manual transplant triage. Every conflict classifier must re-derive the mapping "agents(上游) = experts(本地) = resource type `agent`" before touching a hunk, and a mistake in that mapping is silent breakage, not a test failure.

## Decision

Code and route vocabulary unifies on "agent". Expert-named routes move to agent-named paths (the merged tree keeps `/workspace/agents` reachable through redirects in both directions during transition), components named for the same concept drop the expert prefix, and tests stop rewriting upstream paths. The display word 专家 is a presentation concern: it lives in the `zh-CN` locale strings and nowhere else; the `en-US` locale shows "Agent". The data source does not move — `/api/agents` stays unmounted and `/api/resources` stays the canonical source; this decision renames surfaces, it does not re-open the data-source question settled by Resource Governance V2 (2026-08-14).

## Trade-offs

The unification is a one-time migration of roughly 30-60 files (expert routes, components, unit tests, e2e) plus permanent redirects so existing bookmarks and chat history links keep working, and it concedes the differentiated word in code — 专家 remains visible to users but greps for it stop finding routes. Keeping the split was the alternative: it would preserve today's naming and instead tax every future convergence with rewrites, transplants, and a human-maintained terminology map (CONTEXT.md glossary entry plus a merge-playbook check). That map is still recorded as the transition-period safety net, but the mapping it documents should stop growing once the rename lands.

## Implementation status (2026-10-04)

在历史工作树 `docs/agent-doc-disclosure @ 02af2a4e8` 的抽查中，`/workspace/agents` 路由和 `agent-*` 组件已成为 canonical（恢复了 `agent-card`、`agent-settings-dialog` helpers），迁移前的 `/workspace/capabilities/experts/*` 路径已永久重定向，`frontend/src` 中不再有 `ExpertList` 或 expert 前缀组件，专家一词只出现在 `zh-CN` locale 文案中。这些事实只描述该历史工作树，不证明当前候选的实现或验证状态；当前候选状态见 [项目状态页](../project-state.md)。

## Re-evaluation triggers

Revisit this decision when any of the following becomes true:

- Product packaging requires "experts" as a marketed, versioned concept (for example an 专家市场 storefront) strong enough to justify a brand word in code, not only in copy.
- Upstream renames the concept itself, which would reset the mapping cost and warrant a fresh comparison.
- The rename migration stalls past half-done (some routes renamed, some not): a partially applied vocabulary is worse than either consistent form, so the unfinished remainder either completes or reverts within the same convergence round it started in.
