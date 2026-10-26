---
id: branch-baseline
kind: evidence
status: current
owner: Neowyh
scope: Repository branch baseline record
last-verified: 2026-10-26
verified-against: AGENTS.md on develop (d37d9723)
---

# Branch baseline record

This record corrects and supersedes the earlier version merged in PR #146:
that version described a main/develop "sync" as a pending follow-up task.
The repository's documented policy makes that framing wrong; this version
aligns the record with the policy.

## Documented policy

- `AGENTS.md` / `CLAUDE.md` (repo root, sole rule source): "Team rules
  belong on `develop`/product branches; pure upstream `main` gets
  fast-forward mirrors."
- `.agent/skills/upstream-merge/SKILL.md` together with
  `UPSTREAM_PATCH_LEDGER.md` define the fork governance: upstream releases
  converge into `develop` through recorded merge rounds archived under
  `docs/upgrades/`, while `main` exists to track the upstream project and
  only ever receives fast-forward mirrors.

## Consequences

- `develop` is where all product work lands, and product branches are cut
  from it. Every issue 105-111 deliverable lives on `develop` (Server PRs
  #142-#146) — exactly where this policy says it belongs.
- `main` tracking only the upstream project is the designed state, not a
  divergence to repair. Its lack of the issue 105-111 work is correct;
  there is no main-sync task, and `develop` must not be merged into `main`.
- Deployment, release and acceptance evidence for this project therefore
  references `develop` or product branches cut from it, never `main`.
