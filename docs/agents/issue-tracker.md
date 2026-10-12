---
id: docs-agents-issue-tracker
kind: reference
status: current
owner: repository maintainers
scope: where specifications and work tickets are published (GitHub issues mirrored to Gitea), their triage vocabulary, and the GitHub/Gitea issue and PR command conventions for this repository
last-verified: 2026-10-11
verified-against: maintainer decision 2026-10-11 — specs and tickets publish to GitHub (Orbit-Crew/iDeer), mirrored to Gitea (TechCode/iDeer)
---

# Specifications and work tickets

Specifications and work tickets for this repo are published on **GitHub Issues (`Orbit-Crew/iDeer`)**, each mirrored to **Gitea (`TechCode/iDeer`)** per the [Gitea sync](#gitea-sync) rules. `/to-spec` publishes one specification issue; `/to-tickets` publishes one issue per ticket in dependency order (blockers first), with blocking edges as GitHub native dependencies. The triage vocabulary is defined in [triage-labels.md](triage-labels.md).

Existing files under `docs/specs/` remain as archive; new specifications are not written there. `.scratch/` stays available as a git-ignored scratchpad for drafting, but it is not the tracker: a draft that has not been published as an issue is not a ticket.

> 本仓库 GitHub issues 归属 **Orbit-Crew/iDeer**。执行 GitHub issue 操作时显式加 `--repo Orbit-Crew/iDeer`，避免工作树的 remote 配置影响目标仓库。

## GitHub issue conventions

- **Create an issue**: `gh issue create --title "..." --body "..." --repo Orbit-Crew/iDeer`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments --repo Orbit-Crew/iDeer`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --repo Orbit-Crew/iDeer --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..." --repo Orbit-Crew/iDeer`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..." --repo Orbit-Crew/iDeer` / `--remove-label "..." --repo Orbit-Crew/iDeer`
- **Close**: `gh issue close <number> --comment "..." --repo Orbit-Crew/iDeer`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone. For this repo prefer `--repo Orbit-Crew/iDeer` as noted above.

## Gitea sync

Every issue created on GitHub gets a matching issue on Gitea (`TechCode/iDeer`, intranet) with identical content:

- Tool: `tea` (the default login is already `gitea.com` / Neowyh). Create: `tea issues create --repo TechCode/iDeer --title "..." --description-file <file> --labels "enhancement,needs-triage" --assignees <user>`; verify: `tea issues list --repo TechCode/iDeer --fields "index,title,state,assignees,labels"`.
- Use the Gitea `feature-request.yml` template: the preflight link points at `https://gitea.com/TechCode/iDeer/issues`; all other fields are verbatim copies of the GitHub body.
- Redaction: frame-format document names, sample `.dat` files, and anything else sensitive never appear on either platform; implementers fetch them on the intranet.
- Keep labels and assignee consistent with the GitHub side (default `enhancement` + `needs-triage` + assign to a person).

This applies to specification and ticket issues published by `/to-spec` and `/to-tickets` too: mirror each one immediately after creating it on GitHub. GitHub native dependencies remain the canonical blocking representation; the Gitea mirror carries the dependency state in the body's `Blocked by` line, so keep that line identical on both sides.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments --repo Orbit-Crew/iDeer` and `gh pr diff <number> --repo Orbit-Crew/iDeer` for the diff.
- **List external PRs for triage**: `gh pr list --repo Orbit-Crew/iDeer --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close` (each with `--repo Orbit-Crew/iDeer` for this repo).

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42 --repo Orbit-Crew/iDeer` and fall back to `gh issue view 42 --repo Orbit-Crew/iDeer`.

## When a skill says "publish to the issue tracker"

Publish to GitHub Issues (`Orbit-Crew/iDeer`), then mirror each created issue to Gitea per the [Gitea sync](#gitea-sync) rules.

- **`/to-spec`** creates one specification issue from its spec template. Labels: the category role (`enhancement` or `bug`), the affected `area:*` labels, and `ready-for-agent` from [triage-labels.md](triage-labels.md).
- **`/to-tickets`** creates one issue per ticket from its issue template, in dependency order (blockers first), each labelled like the specification issue. Each ticket body carries a `## Parent` reference to the specification issue (or the triaged source issue), and blocking edges use the GitHub native dependencies documented in [Wayfinding operations](#wayfinding-operations). Title tickets with the category prefix and sequence, e.g. `[feat] 01: <title>`.

Every AI-authored issue — specification, ticket, wayfinder map, or manual — carries the category title prefix (`[bug] ` or `[feat] `) and, wherever the affected areas are known, the matching `area:*` labels. API-created issues get no form-template titles or labels automatically, so these are always applied explicitly. Before creating any AI-authored issue, run a real dedup search (`gh issue list --search ... --repo Orbit-Crew/iDeer`, open and closed) and note the result in the body; do not just tick a preflight box.

**Publish-time self-check — every issue must pass every item below before `gh issue create`:**

- [ ] Parent / Blocked-by references resolve to real issue numbers
- [ ] At least two independently verifiable acceptance criteria
- [ ] No file paths and no line numbers in the body (they go stale; describe behavioral contracts instead)
- [ ] An explicit out-of-scope list

## When a skill says "fetch the relevant ticket"

For a work ticket or any existing issue reference, run `gh issue view <number> --comments --repo Orbit-Crew/iDeer`. Files under `.scratch/` are drafts only; the published ticket is the issue.

## Wayfinding operations

GitHub workflow used by `/wayfinder`; the same sub-issue and native dependency mechanics below are how `/to-tickets` wires its ticket blocking edges. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map --repo Orbit-Crew/iDeer`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/Orbit-Crew/iDeer/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/Orbit-Crew/iDeer/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --repo Orbit-Crew/iDeer --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me --repo Orbit-Crew/iDeer`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>" --repo Orbit-Crew/iDeer`, then `gh issue close <n> --repo Orbit-Crew/iDeer`, then append a context pointer (gist + link) to the map's Decisions-so-far.
