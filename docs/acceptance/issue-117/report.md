---
id: issue-117-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 117 Server side of scoped graph QA and relation retrieval inside one frozen revision
last-verified: 2026-10-27
verified-against: orch/issue-117-graph-qa working tree on top of f60ce1c9 (#116 candidate); every acceptance command below was run against the tree exactly as committed
---

# Issue 117 Server acceptance

The Server/Web candidate lives in the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-117-graph-qa`, stacked on f60ce1c9 (#116). The Desktop repo
carries the same branch at 6f496dd; its companion report is
`docs/acceptance/issue-117/report.md` in that repository. No issue closure
and no PR are claimed by this report. `dist:win` packaging was not run in
this environment and stays a recorded-pending packaging step (see the
Desktop companion report); no real-LLM leg was executed (no model
credentials here).

## Implemented surface

- `backend/app/agentplatform/knowledge/graph_query.py` (new): the scoped
  graph QA and relation-retrieval service.
  - Authorization is read parity with knowledge retrieval: the KB is
    resolved through `ResourceService.get_visible` only — the same guard
    retrieval rides — so a hidden KB reads as not-found no matter what
    labels or tags a caller sends, and a granted department member reads
    the same frozen scope. Nothing filters authorization by tags.
  - The selected `document_ids` are validated against the revision's
    frozen manifest (`_scoped_entries`): a non-empty subset of at most 50
    frozen documents; anything outside the revision — including a real
    document frozen into another revision of the same KB — is a
    `ResourceConflict` (409), never a silently widened query.
  - `query` reads only the stored `KnowledgeGraphArtifact` rows of exactly
    this revision and the selected documents. Every entity/relation row
    carries `document_id`, `filename`, and the frozen `content_hash`; the
    `scope` array echoes the selected documents with per-document status
    (`completed` / `failed` + fixed category / `not_generated`). A
    full-text filter over entity names/types and relation endpoints is
    deterministic (casefolded substring); an empty query lists the whole
    selected scope.
  - `ask` acquires the selected documents' material through
    `RevisionMaterialSource.document_text` — the exact execution chain
    #116 generation uses (provider originals from platform storage,
    device-local documents via the owner-scoped frozen-identity broker
    dispatch, digest re-checked on both ends). If any selected document's
    material fails, the ask refuses: `answer` is null,
    `answer_available` is false, the gaps are listed per document with
    their fixed categories, and the model is never invoked over a gapped
    scope. The model call (`answer_scoped_question` via the platform's own
    `run_oneshot_llm`; injectable answerer for tests) is instructed to
    answer only from the provided documents and to name the filenames it
    used; empty or oversized answers (>8000 chars) are structured
    `GRAPH_MODEL_OUTPUT_INVALID` refusals, never truncated text.
- `graph_generation.py` refactor (no behavior change): the material
  acquisition moved into `RevisionMaterialSource`, shared by generation
  and scoped QA so there is one execution chain; `manifest_entries` /
  `aggregate_status` became the module's public helpers.
- `KnowledgeFacade.graph_query` / `graph_ask` (+ `graph_answerer` seam):
  the two intents behind the HTTP surface with the seam's commit
  discipline and `knowledge_graph_scoped_query` /
  `knowledge_graph_scoped_ask` audit records.
- `routers/resources.py`: `POST
  /api/resources/{id}/knowledge-revisions/{revision_id}/graph/query` and
  `.../graph/ask` beside the #116 graph endpoints. Pydantic bounds: query
  ≤512 chars (optional), question 1..4000 chars, `document_ids` 1..50
  platform-UUID strings (422 on violation). Membership is re-checked
  inside the service.

## Commands and results

Focused runner: `dev-log/issue-112/test.sh` (repo-root-relative; Python
3.12 venv). All commands run 2026-10-27 on Windows host (win32
10.0.26300 x64) driving WSL Ubuntu for Python, against the committed tree.

| Suite | Result |
| --- | --- |
| `backend/tests/unit/knowledge/test_graph_query.py` (new, 15) | 15 passed |
| `backend/tests/integration/api/test_knowledge_graph_query_router.py` (new, 6) | 6 passed |
| `backend/tests/integration/api/test_knowledge_graph_router.py test_local_knowledge_consent_gate.py test_knowledge_facade.py` (adjacent, unchanged) | 23 passed |
| `backend/tests/integration/api/` graph + consent files together | 18 passed, exit 0 |
| `backend/tests/unit/knowledge` (full dir) | 341 passed, 3 skipped, exit 0 (249 s; recorded baseline 326 / 3 → +15 new) |
| `ruff check backend` | All checks passed, exit 0 |
| Desktop focused: `test_platform_knowledge_graph.py` 11 (5 new) + vitest `test/knowledge-graph.test.tsx` 10 (5 new) + typecheck | green (see Desktop companion report) |

## Scenario records (T117-01..04)

| Scenario | Ticket ACs | Automated evidence (passed) | Staged / unexecuted remainder |
| --- | --- | --- | --- |
| T117-01 (select X, query/ask inside X, widen to X/Y) | 1, 2, 4 | `test_query_narrows_to_the_selected_documents_and_expands_with_the_scope` — guide.txt-only query returns only guide's entities/relations, widening adds policy's; `test_query_results_and_scope_carry_frozen_document_sources` — rows carry filename + frozen SHA-256; `test_ask_answers_from_exactly_the_selected_material_with_sources` — the model saw exactly the selected document (`calls` assertion) and the answer travels with its scope; router `test_scoped_query_and_ask_contract_over_http` pins the same over HTTP. Desktop legs: `test_search_posts_the_selected_scope_and_projects_sourced_rows`, `test_ask_posts_the_question_and_projects_answer_with_scope`, vitest `selectedScope` narrowing assertions (companion report). | Real-model scoped Q&A wording quality: **unexecuted** (no model credentials). Staged: same suites against a live model + paired Desktop. |
| T117-02 (bypass UI: unselected document / unauthorized KB; model-call ownership) | 1, 3, 4 | `test_invisible_kb_reads_as_not_found_for_query_and_ask`, `test_documents_outside_the_frozen_revision_are_refused` (including a document frozen into another revision), router `test_unauthorized_kb_is_404_while_visible_department_reads` (stranger 404 on both endpoints; granted member reads query/ask but still cannot generate — parity with retrieval, not tag filtering), `test_document_outside_the_frozen_revision_is_refused`, `test_invalid_scoped_request_bodies_are_422`. Desktop chain: runtime `KNOWLEDGE_GRAPH_SCOPE_INVALID` / `KNOWLEDGE_GRAPH_QUERY_INVALID` validation (vitest), device `CHAT_COMMAND_INVALID` before any HTTP (`test_scoped_actions_require_a_bounded_scope_and_query`); the only model invocation is the Server's own `run_oneshot_llm` — no desktop model path exists. | None beyond the shared real-model staging of T117-01. |
| T117-03 (missing material / hidden source / partial failure must not answer) | 2, 4 | `test_ask_refuses_to_answer_when_selected_material_is_partially_missing` — drift fails the document with `GRAPH_CONTENT_DRIFTED`, answer null, and the recorded model calls are empty (a gapped scope never reaches the model); `test_ask_reports_a_fully_unavailable_device_as_a_structured_failure` (`GRAPH_DEVICE_UNAVAILABLE`); `test_ask_model_failures_are_structured_instead_of_fabricated` (`GRAPH_MODEL_OUTPUT_INVALID` / `GRAPH_MODEL_UNAVAILABLE`); `test_ask_overlong_answer_is_rejected_rather_than_truncated`; `test_query_before_generation_reports_not_generated_without_rows`; `test_query_over_a_partial_graph_skips_failed_documents`. Router `test_partial_material_failure_refuses_to_answer` pins the HTTP contract. Desktop `test_ask_refusal_is_projected_without_an_answer` + vitest refusal rendering show the refusal instead of an answer. | Live-device fault injection on a real paired Desktop: **unexecuted** (staged with T117-01's real-model environment); the deterministic injections above cover the same fixed categories. |
| T117-04 (new Revision published after the Run; original sources must not move) | 1, 2, 4 | `test_queries_stay_bound_to_the_frozen_revision_after_a_new_version` — query results are byte-identical before/after registering and generating a newer revision (`before == after`), `manifest_hash` stays the original's, and the new revision's documents are refused in the old scope; router `test_version_change_never_replaces_the_original_revision_sources` — query and ask responses are identical pre/post publication and the newer document id is a 409 in the original revision's scope. | Manual "reopen the original session" UI pass on the real three ends: **unexecuted** (staged with the real-model environment); the server-side contract it would observe is fully pinned above. |

## Pending / risks

- Real-LLM legs (scoped Q&A answer quality, manual UI passes) are
  **unexecuted on model credentials**; every authorization, scope,
  sourcing, refusal, and version-binding contract they depend on is pinned
  by the automated suites with fixed generators/answerers.
- dist:win packaging: pending (recorded in the Desktop companion report;
  this report claims no installer).
- Real Win7 remains the only explicitly deferred platform validation:
  **unexecuted**, owned by [#131](https://github.com/Orbit-Crew/iDeer/issues/131).
  Modern-Windows results above are not Win7 results.
- The scoped ask answers from document text, not from graph triples; the
  graph artifacts serve retrieval (`query`) and source display. No general
  cross-library graph governance was introduced (ticket out-of-scope rule).
- Department members can query/ask over a visible department KB, but
  device-local material for an ask is owner-scoped (the broker dispatch
  requires the caller's own device connection), so a member's ask over an
  owner-local document reports the unavailable material instead of
  answering — covered by `test_department_member_with_visibility_reads_like_retrieval`.

## Installed combination acceptance, 2026-10-29 (modern Windows)

The staged installed-combination portion was executed on the paired Desktop
side and recorded in that repository:
`iDeer-Desktop/docs/acceptance/issue-117/installed-20261029.md` with sanitized
evidence under `docs/acceptance/issue-117/evidence/installed-20261029/`.
T117-01/02/04 passed fully and four of T117-03's cases passed with the real
model (`agnes-3.0-flash`). Staged: the structured per-document refusal
display (the #116 material-consent approval surface is unreachable in the
installed app), the gapped-generation per-document category (generation
parked on the material gap), and the deterministic `GRAPH_CONTENT_DRIFTED`
presentation (drift injection needs device-approvable material). Bindings
identical to the #112 section. Win7 remains with #131.
