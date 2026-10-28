---
id: issue-114-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 114 Server/Web side of hybrid device retrieval with partial-failure semantics
last-verified: 2026-10-27
verified-against: orch/issue-114-web-device-retrieval working tree on top of 4811ab74 (#115 candidate); adoption of an interrupted in-session partial, re-verified from the tree (see Provenance)
---

# Issue 114 Server acceptance

The Server/Web candidate lives in the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-114-web-device-retrieval`, stacked on 4811ab74 (#115). The Desktop
repo carries the same branch name at b8005dd with no Desktop code change for
this ticket (the Desktop entry is the #113 retrieval surface; see the Desktop
companion report). No issue closure and no PR are claimed.

## Provenance

The implementing session was interrupted by a provider quota limit after the
work was written but before commit. The uncommitted tree was inventoried
(`git diff` = 12 modified files + 6 untracked, archived at
`dev-log/issue-114/partial.patch`), reviewed change-by-change against the
ticket, and re-verified from the tree: every acceptance command below was run
by the adopting session against the working tree exactly as committed.

## Implemented surface

- `backend/app/gateway/hybrid_knowledge.py` (new): engine labels
  (`local_device` / `server_provider`), frozen-identity source attribution,
  `requires_local_material`, structured `source_unavailable` and
  `paused_local_required` results, and the caller-authorized
  `knowledge_scope_view` behind the Web selector. Attribution projects only
  frozen run metadata; scores are never compared across engines.
- `canonical_agent_run_preparation.py`: a failed local leg returns the
  structured source failure instead of raising a tool error, so it can never
  impersonate "no material"; local-only runs pause. Also fixes a latent #113
  defect: dispatch specs were filtered by logical KB id against dataset-token
  keys, which silently dropped every local dispatch; membership now runs on
  `set(knowledge_scope.values())`.
- `routers/resources.py`: `GET /api/resources/{id}/knowledge-scope` — the
  selection surface reads exactly what a Run would bind; selection only
  narrows via `runtime_knowledge_scope`.
- `routers/devices.py`: `local.knowledge.search` joins `local.files.write` as
  device-gated consent — a Web caller (owner or admin) receives 403
  `LOCAL_APPROVAL_REQUIRED` and may only wait; the originating Desktop decides.
- `retrieval_receipts.py`: `source_unavailable` / `paused_local_required`
  receipt statuses plus model-facing text; a failure is never an `empty_hit`.
- Web: `KnowledgeScopeSelector` on the chat page (per-chat narrowing),
  `useAgentKnowledgeScope`, retrieval-receipt card renders the new statuses,
  zh-CN/en-US i18n.

## Commands and results

Focused runner: `dev-log/issue-112/test.sh` (PYTHONPATH backend:tests:harness
:agentplatform-extension:extension-api; Python 3.12.3 venv,
fastapi 0.136.1) — all repo-root-relative.

| Suite | Result |
| --- | --- |
| `tests/unit/knowledge/test_hybrid_knowledge_retrieval.py` (new, 14) | 14 passed |
| `tests/unit/gateway/test_resources_api_knowledge_scope.py` (new, 4) | 4 passed |
| `tests/integration/api/test_local_knowledge_consent_gate.py` (new, 4 parametrized) | 4 passed |
| Adjacent: `test_local_knowledge_retrieval.py`, `test_canonical_prep_single_pass.py`, `test_canonical_agent_run.py` | 18 passed |
| Full `tests/integration/api` (e2e/live excluded, `-o faulthandler_timeout=60`) | 1216 passed, 31 skipped, exit 0 (202 s; baseline 1212 + 4 new) |
| `ruff check backend` | All checks passed, exit 0 |
| Web focused: `knowledge-scope-selector.test.tsx` + `retrieval-receipt-card.test.tsx` | 11 passed |
| Web `pnpm check` (eslint + tsc) | exit 0 (0 errors; warnings pre-existing) |
| Desktop full vitest + runtime pytest | not rerun: Desktop tree is byte-identical to the b8005dd state whose 24 files / 98 tests and 429 passed / 11 skipped run is recorded in the #115 report |

Key test-to-AC bindings: `test_receipts_name_the_engine_and_kb_revision_source`
and `test_closure_dispatches_to_device_and_delivers_validated_chunks` (AC1/AC4);
`test_raw_scores_are_never_merged_across_engines`,
`test_source_attribution_projects_frozen_identity` (AC2);
`test_unavailable_local_source_is_recorded_as_source_failure_never_empty_hit`,
`test_local_required_failure_pauses_instead_of_answering`,
`test_device_unavailable_in_hybrid_scope_reports_incomplete_source`,
`test_mid_disconnect_failure_is_structured_not_raised`,
`test_local_only_run_pauses_when_the_device_is_unavailable` (AC3);
`test_remote_consent_cannot_approve_device_gated_operations` (AC1);
`test_another_users_local_kb_binds_nothing_for_a_teammate`,
`test_runtime_restriction_cannot_add_unknown_knowledge_bases` (AC1/AC4).

## Scenario records

| Scenario | Status | Evidence |
| --- | --- | --- |
| T114-01 (two entries, one scope; LIVE/PINNED frozen) | passed (automated) | One canonical chain serves both entries; scope view + closure dispatch + narrowing-only selection; freeze semantics carried from #113 unchanged (`test_closure_dispatches_to_device_and_delivers_validated_chunks`, scope-view API tests). Installed dual-UI walk-through staged on the modern-Windows installed acceptance run. |
| T114-02 (unauthorized KB invisible) | passed (automated) | `test_another_users_local_kb_binds_nothing_for_a_teammate`, `test_unanchored_local_kb_stays_out_of_the_view`, `test_runtime_restriction_cannot_add_unknown_knowledge_bases`. Live cross-account probe staged on deployment. |
| T114-03 (offline/disconnect/partial) | passed (automated) | `test_device_unavailable_in_hybrid_scope_reports_incomplete_source`, `test_mid_disconnect_failure_is_structured_not_raised`, `test_local_only_run_pauses_when_the_device_is_unavailable`, consent gate 403. Real-device fault injection staged on the installed run. |
| T114-04 (receipts consistent, no scope widening) | passed (automated) | `test_receipts_name_the_engine_and_kb_revision_source`, receipt statuses (`source_unavailable` / `paused_local_required` never `empty_hit`), no raw cross-engine score merge. Human readability of receipts in the installed UI staged. |

Real model conditions (LLM-backed answers over hybrid sources): unexecuted,
staged on model credentials; per the ticket this does not block the
automated contract evidence above. Win7: unexecuted, owned by #131.
`dist:win` packaging of the eventual combined candidate: pending, recorded
in the closing acceptance pass.
