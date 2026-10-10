---
id: docs-agents-issue-tracker
kind: reference
status: current
owner: repository maintainers
scope: where local specifications and work tickets live, their triage vocabulary, and the GitHub issue/PR command conventions for this repository
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 71ae798fb
---

# Local specifications and work tickets

Specifications for this repo live as Markdown files in `docs/specs/`. Work tickets live as one Markdown file per ticket under `.scratch/<feature-slug>/issues/`, numbered from `01` in dependency order. Each ticket records its blockers and `ready-for-agent` status. `.scratch/` is git-ignored, so local tickets stay in the working directory and are not published to GitHub or included in commits by default. GitHub Issues remain available for separate issue discussions.

Local specifications use a date-prefixed descriptive filename and YAML frontmatter with `triage: ready-for-agent` once they are fully specified. The file itself is the published specification; do not create a GitHub issue merely to publish it. The triage vocabulary is defined in [triage-labels.md](triage-labels.md).

> 本仓库 GitHub issues 归属 **Orbit-Crew/iDeer**。执行 GitHub issue 操作时显式加 `--repo Orbit-Crew/iDeer`，避免工作树的 remote 配置影响目标仓库。

## GitHub issue conventions

- **Create an issue**: `gh issue create --title "..." --body "..." --repo Orbit-Crew/iDeer`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments --repo Orbit-Crew/iDeer`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --repo Orbit-Crew/iDeer --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..." --repo Orbit-Crew/iDeer`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..." --repo Orbit-Crew/iDeer` / `--remove-label "..." --repo Orbit-Crew/iDeer`
- **Close**: `gh issue close <number> --comment "..." --repo Orbit-Crew/iDeer`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone. For this repo prefer `--repo Orbit-Crew/iDeer` as noted above.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments --repo Orbit-Crew/iDeer` and `gh pr diff <number> --repo Orbit-Crew/iDeer` for the diff.
- **List external PRs for triage**: `gh pr list --repo Orbit-Crew/iDeer --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close` (each with `--repo Orbit-Crew/iDeer` for this repo).

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42 --repo Orbit-Crew/iDeer` and fall back to `gh issue view 42 --repo Orbit-Crew/iDeer`.

## When a skill says "publish to the issue tracker"

Write a specification to `docs/specs/` with the appropriate `triage` frontmatter. Write implementation tickets as separate numbered files under `.scratch/<feature-slug>/issues/`, using the status value from [triage-labels.md](triage-labels.md). Do not create GitHub issues solely to publish a specification or work-ticket breakdown.

## When a skill says "fetch the relevant ticket"

For a local work ticket, read its numbered file under `.scratch/<feature-slug>/issues/`. For an existing GitHub issue reference, run `gh issue view <number> --comments --repo Orbit-Crew/iDeer`.

## Wayfinding operations

Legacy GitHub workflow used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets; it does not change the local publication rule above for new work-ticket breakdowns.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map --repo Orbit-Crew/iDeer`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/Orbit-Crew/iDeer/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/Orbit-Crew/iDeer/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --repo Orbit-Crew/iDeer --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me --repo Orbit-Crew/iDeer`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>" --repo Orbit-Crew/iDeer`, then `gh issue close <n> --repo Orbit-Crew/iDeer`, then append a context pointer (gist + link) to the map's Decisions-so-far.
