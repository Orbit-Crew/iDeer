---
id: disclosure-branch-root-engineering-delivery-2026-10-10
kind: evidence
status: current
owner: repository maintainers
scope: implementation delivery and deferred measurement status for NAV and ROOT disclosure work
---

# Disclosure branch and ROOT engineering delivery

## Decision and scope

On 2026-10-10, the user chose to stop further ROOT formal model reading, close out the engineering work, and proceed toward delivery. This report records implementation separately from measured effectiveness. It does not change the frozen experiments, claim an effectiveness gate passed, or attribute score differences to the documentation edits.

## Engineering delivery

The task-branch navigation and compact ROOT guidance implementations are present in this candidate. ROOT guidance is 7,256 UTF-8 bytes, down from the recorded 10,226 bytes (29.0436%); its managed GitNexus block is 1,164 bytes, down from 4,134 bytes. The GitNexus force-generation and normalization path was exercised, including the safety and mirror checks documented in the local ignored handoff. These structural and engineering checks do not measure reading effectiveness.

The local handoff records 28 focused checks and 15 G3 regressions, alongside documentation hygiene, mirror synchronization, protected-fingerprint, and guidance-budget checks. A final integration `pr-standard` remains pending. Its sub-lane outcomes and parent duration must be recorded after it runs on the final candidate.

## NAV measurement status

The frozen NAV queue remains 32 slots. Final adjudicated scoring is baseline 13/16 and after 11/16. Slots 11–13 are permanent quota failures under the protocol; they were not retried, replaced, or removed from the denominator. Formal correctness therefore remains incomplete. The required after routine Markdown cost sample has 9 valid answers out of 10, so the cost gate is also incomplete.

Fifteen non-scored branch pilots and eight second-action probes reached their expected checks. They support reachability only. The wording for item 05 changed, so these observations cannot establish that NAV caused a measured outcome. The formal report and its archived evidence remain the source for scoring, cost, and custody details: [NAV acceptance](disclosure-branch-navigation-acceptance-2026-10-09.md).

## ROOT measurement status

The 32-session ROOT formal queue was not started. One pilot attempt failed before a process launched; two later startup attempts were rejected by automatic review before process launch. No reader submission, task answer, or ROOT effectiveness score resulted. The user then directed that ROOT model reading stop. No finding about reader behavior or formal gate status can be inferred from those startup events.

The earlier dual-track ticket 07 and ticket 08 records remain unchanged. Their findings are not replaced by this delivery note. The NAV and ROOT specifications record implementation completion and deferred or incomplete measurement independently.

## Evidence and next gate

Detailed experiment records and command logs remain in the ignored `dev-log/branch-root/` and `dev-log/disclosure-branch-root/` directories, as identified in `dev-log/branch-root/current-handoff.md`. This report is a reviewer-facing index and summary, not a replacement for raw records. The final integration `pr-standard` is still required for delivery readiness; no test result is recorded here before that run.
