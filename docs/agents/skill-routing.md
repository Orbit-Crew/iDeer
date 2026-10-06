---
id: docs-agents-skill-routing
kind: reference
status: current
owner: repository maintainers
scope: full skill-routing flow for coding agents (precedence over skills, main flow, on-ramps, phase boundaries, communication agreement); root AGENTS.md carries the compact table
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 71ae798fb
---

# Skill Routing

How coding agents route work through the installed ask-matt skill set, adapted to this repository's discipline. Root `AGENTS.md` carries the compact routing table; this document carries the full flow, the low-frequency routes, phase boundaries, and the precedence rules that reconcile the skill flow with this repo's own contracts.

## Precedence

1. **Repository discipline always wins.** The test-lane contract ([test-lane-runbook.md](../testing/test-lane-runbook.md)), the `orchestrate-worktrees` rule for long-span work, the enterprise compatibility rules, and the guidance-sync convention in `AGENTS.md` are not overridden by any skill.
2. **Skills change how work is prepared and reviewed, never what validation is required.** `tdd` and `code-review` complement the lane contract; they never replace a lane run.
3. **If a routed skill is not installed** in the running harness, follow the stated principle in the routing table instead of the skill's mechanics.

## Main flow: idea → ship

1. **Sharpen the idea with `grill-with-docs`** — a stateful interview that reads `CONTEXT.md` and `docs/adr/` first (see [domain.md](domain.md)) and leaves a glossary/ADR paper trail. Small, well-specified changes skip the interview and go straight to the TDD slice discipline in `AGENTS.md`.
2. **Runnable design question** (state model, UI feel, business logic you must see run) — `/handoff` out to a fresh session, `/prototype` the answer as throwaway code on a `prototype/<name>` branch out of main, then `/handoff` back what was learned. The prototype stays as a primary source, pointed at from the implementation issue.
3. **Multi-session build** — `/to-spec` writes the spec to `docs/specs/` with `triage:` frontmatter, then `/to-tickets` splits it into tracer-bullet tickets under `.scratch/<feature-slug>/issues/`, each declaring its blocking edges (see [issue-tracker.md](issue-tracker.md)). Work the tickets through **`orchestrate-worktrees`** — one self-contained subagent per ticket in a dedicated git worktree. This is this repo's rule and replaces `/implement-spec`'s single-integration-branch mode; do not run `/implement-spec` across long-span work here.
4. **Each ticket drives `tdd`** — one red-green slice at a time, focused test per slice, static check per slice, standard lane once at implementation completion. Close the diff with **`code-review`** (Standards + Spec axes) before handing off, and shape the PR body per the root Commit & Pull Request guidelines.
5. **`retro` closes the loop.** After a completed build — especially one that went sideways — propose a retro and run it when accepted. It looks back over the session and proposes changes to the agent's environment: automated checks, coding standards, steering docs, navigation pointers. Land accepted proposals through the guidance-maintenance convention (edit `AGENTS.md` as sole source, sync the mirror).

## On-ramps

- **Bugs and requests piling up → `triage`.** For raw incoming issues you did not create (already-agent-ready tickets from `/to-tickets` are not re-triaged). Use the canonical labels in [triage-labels.md](triage-labels.md); publish specifications to `docs/specs/` and tickets to `.scratch/`, not GitHub issues.
- **Something's broken and resists a first glance → `diagnosing-bugs`.** Refuse to theorize until there is a tight feedback loop: one command that already goes red on this bug. Fix behind a regression test. When the real finding is that no seam exists to lock the bug down, hand off to `improve-codebase-architecture`.
- **Huge, foggy effort → `wayfinder`.** For greenfield or too-big-for-one-session efforts where the way is not visible yet: chart a shared map of decision tickets (GitHub map + child issues per [issue-tracker.md](issue-tracker.md) "Wayfinding operations") and resolve them one at a time — decisions, not deliverables. When the map clears, merge into `/to-spec`; do not loop the map straight into implementation.

## Codebase health and vocabulary

- **`improve-codebase-architecture`** surveys deepening opportunities during spare moments; a chosen candidate generates an idea that enters the main flow at `grill-with-docs`.
- **`codebase-design`** is the deep-module vocabulary (module, interface, depth, seam, adapter, leverage, locality) for designing a module's shape. `tdd` and `improve-codebase-architecture` both speak it.
- **`domain-modeling`** keeps `CONTEXT.md` and `docs/adr/` clean: challenge fuzzy terms, resolve overloaded words, record hard-to-reverse decisions as ADRs. Use the glossary's vocabulary in outputs and treat its `_Avoid_` terms as forbidden ([domain.md](domain.md)).

## Standalone routes

- **`prototype`** — a throwaway program that answers one design question; the answer folds into real code, the prototype is kept on its branch as a primary source.
- **`research`** — delegate reading legwork to a background agent that investigates against primary sources and leaves a cited Markdown file; feed the file into `grill-with-docs`.
- **`to-questionnaire`** — when the missing information lives in someone else's head; writes a questionnaire whose answers feed `grill-with-docs` or `/to-spec`.
- **`wizard`** — steps only a human can take: provisioning, credentials, CI secrets, third-party dashboards, one-off migrations. Generates an interactive script; if the agent could do it itself, it should.
- **`wait-what`** — the corrective when a message did not land: re-pitch the last explanation in plain English using the glossary vocabulary, mid-conversation, inside any other skill.
- **`teach`** — learn a concept over multiple sessions, using the current directory as a stateful workspace.

## Phase boundaries

A phase is a chunk of work inside a session (grilling, implementation, review). At a boundary choose one of five options:

- **Continue** — stay put; the default within a phase, and the first option to rule out only when cost demands it.
- **`clear`** — empty the window when nothing here matters to what is next; natural between tickets, and `orchestrate-worktrees` subagents start fresh anyway.
- **`handoff`** — write a portable markdown file; only for a new harness, a new directory, a colleague, or forking a side task mid-phase.
- **Subagent** — send a tightly-scoped task to its own window and get a report back; this repo's orchestration pattern for long-span work.
- **`compact`** — compress context and seed a fresh session with it; prefer doing this at a phase boundary when approaching the smart zone. Keep grilling → spec → tickets in one unbroken window when practical so they build on the same thinking.

## Communication agreement

- **Explain before doing.** State the approach and its assumptions before executing, and keep the user current at phase boundaries.
- **Facts are the agent's job; decisions are the user's.** Gather evidence from the code and reports yourself; when a choice changes the outcome, present the options with a recommendation and let the user decide.
- **Surface suggestions explicitly.** Adjacent defects, cheaper designs, and reusable utilities are reported as suggestions, never silently applied or silently ignored.
- **Re-pitch when it did not land.** If the user is confused by an explanation, restate it in plain language grounded in the glossary instead of repeating the same framing.
