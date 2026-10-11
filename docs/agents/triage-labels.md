---
id: docs-agents-triage-labels
kind: reference
status: current
owner: repository maintainers
scope: canonical triage vocabulary mapped to label strings for the repo issue tracker (GitHub, mirrored to Gitea)
last-verified: 2026-10-11
verified-against: maintainer decision 2026-10-11 — specs and tickets publish to GitHub (Orbit-Crew/iDeer), mirrored to Gitea (TechCode/iDeer)
---

# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Specifications and work tickets are published as GitHub issues: apply the label string directly on the issue and keep it consistent on the Gitea mirror.

Edit the right-hand column to match whatever vocabulary you actually use.
