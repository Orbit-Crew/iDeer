---
id: issue-116-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 116 Server side of controlled knowledge-graph generation with source visibility
last-verified: 2026-10-27
verified-against: orch/issue-116-controlled-graph working tree on top of d862a1ea (#114 candidate); every acceptance command below was run against the tree exactly as committed
---

# Issue 116 Server acceptance

The Server/Web candidate lives in the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-116-controlled-graph`, stacked on d862a1ea (#114). The Desktop
repo carries the same branch name at 465c02e; its companion report is
`docs/acceptance/issue-116/report.md` in that repository. No issue closure
and no PR are claimed by this report.

## Implemented surface

- `backend/app/agentplatform/knowledge/graph_generation.py` (new): the
  controlled graph generation service. The Server orchestrates every model
  call (`generate_document_graph` via the platform's own `run_oneshot_llm`
  configuration; an injectable generator stands in for tests). Device-local
  material is requested one frozen document at a time through the broker
  (`local.knowledge.material`, frozen identity fields only, owner-scoped
  connection, capability-checked), the returned text is re-verified against
  the frozen SHA-256 on arrival, and provider material is read from the
  platform's own document store with the same digest check — neither end
  can substitute content, and no device ever bulk-uploads its library
  (the device refuses multi-document requests outright). Model output is
  normalized and bounded (`normalize_model_graph`: 200 entities / 200
  relations, dangling relations dropped, malformed output is a fixed
  `GRAPH_MODEL_OUTPUT_INVALID` document failure).
- `KnowledgeGraphArtifact` model + migration
  `20261027_knowledge_graph_artifacts` (head of the AgentPlatform chain):
  one row per (frozen revision, document) with the document-source binding
  (document_id, filename, content_hash, revision_no, manifest_hash) and
  either the extracted graph or the fixed failure category. Rows are keyed
  by revision, so two revisions' graphs stay isolated; regeneration
  replaces the previous row.
- `KnowledgeFacade.generate_graph` / `graph_view`: the two intents behind
  the HTTP surface, with the seam's commit discipline and a
  `knowledge_graph_generated` audit record.
- `routers/resources.py`: `POST/GET
  /api/resources/{id}/knowledge-revisions/{revision_id}/graph`. Generation
  rides the KB's modify boundary (owner-only); viewing rides visibility
  (hidden KB reads 404, department members read the same frozen bindings).
- `routers/devices.py`: `local.knowledge.material` joins
  `local.knowledge.search` and `local.files.write` as a device-gated
  consent decision — a Web caller (owner or admin) receives 403
  `LOCAL_APPROVAL_REQUIRED` and may only wait; the originating Desktop
  decides.

## Commands and results

Focused runner: `dev-log/issue-112/test.sh` (repo-root-relative; Python
3.12 venv). All commands run 2026-10-27 against the committed tree.

| Suite | Result |
| --- | --- |
| `backend/tests/unit/knowledge/test_graph_generation.py` (new, 27) | 27 passed |
| `backend/tests/integration/api/test_knowledge_graph_router.py` (new, 6) | 6 passed |
| `backend/tests/integration/api/test_local_knowledge_consent_gate.py` (+1 operation param ×2 roles) | 6 passed |
| `backend/tests/unit/knowledge` (full dir) | 326 passed, 3 skipped, exit 0 (HEAD pre-existing suite measures 299 / 3; +27 new) |
| `backend/tests/unit/knowledge backend/tests/unit/gateway` (full) | 6345 passed, 25 skipped, exit 0 |
| Full `backend/tests/integration/api` (e2e/live excluded, `-o faulthandler_timeout=60`) | 1224 passed, 31 skipped, exit 0 (201 s; recorded baseline 1216 + 31 skipped → +8 new) |
| `ruff check backend` | All checks passed, exit 0 |
| Desktop focused: `test_knowledge_material.py` (12) + `test_platform_knowledge_graph.py` (6) | 18 passed (see Desktop companion report) |

Key test-to-AC bindings (all in `test_graph_generation.py` unless noted):
`test_generation_is_server_orchestrated_and_requests_one_document_at_a_time`
and `test_provider_material_comes_from_platform_storage_without_device_dispatch`
(AC1); `test_view_projects_entities_relations_and_sources_with_frozen_bindings`,
`test_invalid_model_output_is_a_document_failure` (AC2);
`test_graphs_are_isolated_between_revisions`,
`test_other_account_cannot_view_or_generate`,
`test_department_visibility_can_view_but_not_generate`,
`test_revision_of_another_kb_is_invisible`, plus the router's
`test_other_account_cannot_see_or_generate` and
`test_department_member_reads_but_cannot_generate` (AC2/AC3 visibility
matrix); `test_device_material_drift_is_a_structured_failure_and_successes_survive`,
`test_device_offline_is_a_structured_failure`,
`test_returned_material_must_match_the_frozen_digest`,
`test_all_failures_report_failed_not_completed`, and the router's
`test_partial_failure_is_visible_through_the_router` (AC2/AC4);
`test_signed_material_task_asks_for_local_consent_before_any_text` (Desktop
runtime, AC1 device-authorization leg).

## Scenario records (T116-01..04)

| Scenario | Ticket ACs | Automated evidence (passed) | Staged / unexecuted remainder |
| --- | --- | --- | --- |
| T116-01 | 1, 2, 4 | `test_generation_is_server_orchestrated_and_requests_one_document_at_a_time` — dispatch carries frozen identity only, exactly one document per task, no library upload; `test_provider_material_comes_from_platform_storage_without_device_dispatch` — provider legs never touch the broker; generation status binds to KB/Revision (`revision_no`, `manifest_hash` in every response). Device consent + transport legs: Desktop `test_knowledge_material.py` (consent_required before any text). | Real cross-repo run with real model credentials (真实三端和模型, network upload summary capture): **unexecuted** — no model credentials in this environment. Staged commands: Server suite above + Desktop `test_knowledge_material.py` + a live generation against a paired Desktop. |
| T116-02 | 2, 3, 4 | `test_view_projects_entities_relations_and_sources_with_frozen_bindings` — the representative relation 甲零件—[属于]→乙组件 from the fixed material is returned with its document source binding; router `test_owner_generates_and_reads_graph_with_sources` asserts the same over HTTP. Desktop panel structure: `test/knowledge-graph.test.tsx` renders entity/relation/source facts and the locate action (companion report). | Manual usability pass on the real three-end UI with model-generated graphs + screenshots: **unexecuted** (depends on T116-01's real-model staging). |
| T116-03 | 2, 3 | `test_other_account_cannot_view_or_generate`, `test_department_visibility_can_view_but_not_generate`, `test_graphs_are_isolated_between_revisions`, `test_revision_of_another_kb_is_invisible`; router `test_other_account_cannot_see_or_generate`, `test_department_member_reads_but_cannot_generate`, `test_unknown_revision_is_404`. Visibility matrix (owner / department member / stranger × view / generate) and R1↔R2 source isolation are fully automated and green. | None — the automated matrix covers the scenario's operations; a manual matrix re-check on the live deployment is folded into T116-02's staged pass. |
| T116-04 | 2, 4 | `test_device_material_drift_is_a_structured_failure_and_successes_survive` (partial: the surviving source stays verifiable, the failed one names `GRAPH_CONTENT_DRIFTED`), `test_device_offline_is_a_structured_failure`, `test_returned_material_must_match_the_frozen_digest`, `test_all_failures_report_failed_not_completed`, `test_invalid_model_output_is_a_document_failure`; router `test_partial_failure_is_visible_through_the_router`. Fault injection is deterministic (fixed materials, fake broker), no model wording involved. | Re-open-the-page persistence check on the real UI: **unexecuted** (staged with T116-02); the stored-artifact contract it would observe is pinned by `test_regeneration_replaces_previous_artifacts` and the router view tests. |

## Pending / risks

- Real-LLM condition scenarios (T116-01 live leg, T116-02 manual pass,
  T116-04 page-reopen check) are **unexecuted on model credentials**; the
  orchestration, authorization, binding, isolation, and failure contracts
  they depend on are pinned by the automated suites above with a fixed
  generator, so only the model-facing wording quality is unverified.
- dist:win packaging is a pending packaging step (not run in this worktree;
  recorded in the Desktop companion report).
- Real Win7 remains the only explicitly deferred platform validation:
  **unexecuted**, owned by [#131](https://github.com/Orbit-Crew/iDeer/issues/131)
  together with its dependency/compatibility patches. Modern-Windows results
  above are not Win7 results.
- The graph stack reuses the existing controlled-knowledge idioms
  (#113 frozen-identity dispatch, #114 fixed failure categories, #115
  owner-gated mutation boundaries); no new graph engine or algorithm tuning
  was introduced, per the ticket's out-of-scope rule.

## Installed combination acceptance, 2026-10-29 (modern Windows)

The staged installed-combination portion was executed on the paired Desktop
side and recorded in that repository:
`iDeer-Desktop/docs/acceptance/issue-116/installed-20261029.md` with sanitized
evidence under `docs/acceptance/issue-116/evidence/installed-20261029/`.
Server-orchestrated generation with structured per-source failure, the honest
empty-graph state, locate-inside-workspace, cross-account invisibility and
reopen persistence all passed. A completed real-model graph stays unexecuted
with the recorded observation that the Desktop candidate's
`knowledge_seam.py` constructs KnowledgeFacade without a
`graph_broker_factory`, so the device material dispatch chain never engages;
the consent-card legs have no reachable approval surface. Bindings identical
to the #112 section. Win7 remains with #131.
