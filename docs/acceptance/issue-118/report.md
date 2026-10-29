---
id: issue-118-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 118 Server side of server-orchestrated wiki generation with a permission-bound reading surface
last-verified: 2026-10-27
verified-against: orch/issue-118-auto-wiki working tree on top of 06ec0c23 (#117 candidate); every acceptance command below was run against the tree exactly as committed
---

# Issue 118 Server acceptance

The Server/Web candidate lives in the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-118-auto-wiki`, stacked on 06ec0c23 (#117). The Desktop
repo carries the same branch name at 4d4e224; its companion report is
`docs/acceptance/issue-118/report.md` in that repository. No issue closure
and no PR are claimed by this report.

## Implemented surface

- `backend/app/agentplatform/knowledge/wiki_generation.py` (new): the
  controlled wiki generation service, mirroring the #116 graph stack. The
  Server orchestrates every model call (`generate_document_wiki` via the
  platform's own `run_oneshot_llm` configuration; an injectable writer
  stands in for tests). Device-local material rides the existing
  `local.knowledge.material` dispatch through the shared
  `RevisionMaterialSource` — one frozen document at a time, frozen identity
  fields only, owner-scoped connection, capability-checked, so no device
  ever bulk-uploads its library and **no new device operation was needed**.
  `RevisionMaterialSource` gains an optional `label` (default
  `knowledge-graph`) so a wiki dispatch records `knowledge-wiki:{revision}`
  in its task identity; the execution chain and its SHA-256 re-verification
  are unchanged. Model output is normalized and bounded
  (`normalize_model_wiki`: bounded non-empty title/body, overlong bodies
  refused rather than silently truncated, malformed output is a fixed
  `WIKI_MODEL_OUTPUT_INVALID` page failure).
- `KnowledgeWikiPage` model + migration `20261027_knowledge_wiki_pages`
  (head of the AgentPlatform chain): one row per (frozen revision,
  document) with the document-source binding (document_id, filename,
  content_hash, revision_no, manifest_hash) and either the generated page
  (title + Markdown body) or the fixed category of the skip/failure. Rows
  are keyed by revision, so two revisions' wikis stay isolated;
  regeneration replaces the previous row and never modifies the frozen
  revision itself.
- Fixed statuses and categories: per page `completed` / `skipped`
  (material unavailable at its frozen digest — `GRAPH_CONTENT_DRIFTED`,
  `GRAPH_DEVICE_UNAVAILABLE`, `GRAPH_MATERIAL_REJECTED`,
  `GRAPH_DOCUMENT_NOT_TEXT`, …, the shared chain's categories) / `failed`
  (`WIKI_MODEL_OUTPUT_INVALID`, `WIKI_MODEL_UNAVAILABLE`) / `not_generated`
  (never attempted); aggregate `completed` / `partial` / `failed`.
- `KnowledgeFacade.generate_wiki` / `wiki_view` / `wiki_page`: the three
  intents behind the HTTP surface, with the seam's commit discipline and a
  `knowledge_wiki_generated` audit record.
- `routers/resources.py` (gateway): `POST
  /api/resources/{id}/knowledge-revisions/{rid}/wiki` (generation rides the
  KB's modify boundary, owner-only), `GET …/wiki` (page list + progress +
  sources, visibility-guarded), `GET
  …/wiki/pages/{document_id}` (one page body; the document id must be
  frozen in this revision — anything else reads 404, so an out-of-scope
  page never leaks a title or a body).

## Commands and results

Focused runner: `dev-log/issue-112/test.sh` (repo-root-relative; shared
Python 3.12 venv). All commands run 2026-10-27 against the committed tree.

| Suite | Result |
| --- | --- |
| `backend/tests/unit/knowledge/test_wiki_generation.py` (new, 36) | 36 passed |
| `backend/tests/integration/api/test_knowledge_wiki_router.py` (new, 7) | 7 passed |
| Adjacent unchanged: `test_local_knowledge_consent_gate.py` + `test_knowledge_graph_router.py` + `test_knowledge_graph_query_router.py` + `unit/knowledge/test_knowledge_facade.py` | 29 passed |
| `backend/tests/unit/knowledge` (full dir) | 377 passed, 3 skipped, exit 0 (recorded #117 baseline 341 / 3 → +36 new) |
| Full `backend/tests/integration/api` (e2e/live excluded, `-o faulthandler_timeout=60`) | 1410 passed, 43 skipped, exit 0 (327 s) |
| `ruff check backend` | All checks passed, exit 0 |

Integration baseline reconciliation (the brief's recorded number was
1224 passed / 31 skipped at #116): in today's shared venv the exact #116
tip (f60ce1c9, probed in a throwaway worktree, removed afterwards) measures
**1397 passed / 43 skipped**, and the #117 tip (06ec0c23) collects **1446**
(≈ 1403 passed / 43 skipped). The chain reconciles exactly:
1397 + 6 (#117 query-router tests) + 7 (this issue's wiki router tests)
= 1410. The historical 1224/31 therefore reflects shared-environment drift
(the venv lives in the main checkout and moved since #116's run), not any
change on this branch; this tree adds exactly 7 integration tests to the
#117 tip and nothing else moved.

Key test-to-AC bindings (unit tests in `test_wiki_generation.py` unless
noted): `test_generation_is_server_orchestrated_and_requests_one_document_at_a_time`
(dispatch carries frozen identity only, exactly one document per task,
`knowledge-wiki:` task identity) and
`test_provider_material_comes_from_platform_storage_without_device_dispatch`
(AC1); `test_view_projects_pages_and_sources_with_frozen_bindings`,
`test_page_read…` body/source assertions inside it, and the router's
`test_owner_generates_reads_page_list_and_one_page` — page list carries
titles, digests, and progress but never bodies (AC2/AC4);
`test_view_before_generation_reports_not_generated`,
`test_device_material_drift_is_a_skipped_page…`
(`test_device_material_drift_is_skipped_and_successes_survive`),
`test_device_offline_is_a_skipped_page`,
`test_all_skipped_reports_failed_not_completed`,
`test_model_failure_is_a_failed_page`, and the router's
`test_partial_skip_is_visible_and_retry_completes_without_mixing` —
progress, skips, and partial failures are honest per-page records (AC2);
`test_retry_never_overrides_the_frozen_basis_and_completes_skipped_pages`
(the revision's `manifest_hash`/manifest are byte-identical after a
retry), `test_retry_keeps_each_revision_its_own_sources`,
`test_wikis_are_isolated_between_revisions`, and the router's
`test_wiki_pages_are_isolated_between_revisions` (AC3);
`test_other_account_cannot_view_or_generate`,
`test_department_visibility_can_read_but_not_generate`,
`test_unknown_or_out_of_revision_document_page_is_invisible`,
`test_revision_of_another_kb_is_invisible`, plus the router's
`test_other_account_cannot_see_or_generate`,
`test_department_member_reads_but_cannot_generate`,
`test_page_read_is_404_outside_the_frozen_manifest`,
`test_unknown_revision_is_404` (AC3/AC4 visibility matrix);
`test_returned_material_must_match_the_frozen_digest`,
`test_non_text_material_names_a_fixed_category`,
`test_empty_revision_is_refused` (AC4).

## Scenario records (T118-01..04)

| Scenario | Ticket ACs | Automated evidence (passed) | Staged / unexecuted remainder |
| --- | --- | --- | --- |
| T118-01 (A generates against an approved Revision; Server orchestration and device material/upload scope) | 1, 4 | `test_generation_is_server_orchestrated_and_requests_one_document_at_a_time` — the Server drives the model stand-in, dispatches one frozen document at a time with identity fields only (`revision_id`, `manifest_hash`, `documents`), never a library; `test_provider_material_comes_from_platform_storage_without_device_dispatch` — provider legs never touch the broker; every result binds to KB/Revision (`revision_no`, `manifest_hash` on generate and view). Device consent + transport legs are inherited unchanged from `test_knowledge_material.py` (the same `local.knowledge.material` op, consent before any text). Desktop companionship: `test_generate_posts_then_reads_the_list` posts once to `POST …/wiki` and re-reads the list (see Desktop companion report). | Real cross-repo run with real model credentials (真实三端和模型, material manifest + upload summary capture): **unexecuted** — no model credentials in this environment. Staged: the suites above plus one live generation against a paired Desktop. |
| T118-02 (Desktop page list → page body → source; progress/skips/partial honest) | 2, 4 | `test_view_projects_pages_and_sources_with_frozen_bindings` (list + per-page read with body and frozen digest), `test_device_material_drift_is_skipped_and_successes_survive` (partial: the completed page stays readable, the skipped one names `GRAPH_CONTENT_DRIFTED` with no body), `test_all_skipped_reports_failed_not_completed`; router `test_owner_generates_reads_page_list_and_one_page` and `test_partial_skip_is_visible_and_retry_completes_without_mixing` assert the same over HTTP. Desktop reading surface: `test/wiki.test.tsx` (page list with progress, frozen digest per page, body only from the per-page read, skip visible with its category) and `test_platform_wiki.py` (bounded projection; skipped page projects its category, never text). | Manual reading pass on the real three-end UI with model-generated pages + screenshots: **unexecuted** (depends on T118-01's real-model staging). |
| T118-03 (retry after partial failure; new Revision mid-flight; reopen old wiki/history) | 3, 4 | `test_retry_never_overrides_the_frozen_basis_and_completes_skipped_pages` — retry re-reads every source at its frozen digest, completes the skipped page, and the revision's `manifest_hash` + manifest stay byte-identical; `test_retry_keeps_each_revision_its_own_sources` — a retry of R1 after R2 exists keeps R1 bindings; `test_wikis_are_isolated_between_revisions` and router `test_wiki_pages_are_isolated_between_revisions` — R1 wiki ≠ R2 wiki, per-revision digests and titles; Desktop `runWiki` resets the page list and any open page on view/generate so an older revision's body can never render beside a newer list. | Manual reopen-the-old-session check on the real UI: **unexecuted** (staged with the real-model environment); the stored-artifact contract it would observe is pinned by the router isolation tests. |
| T118-04 (B / narrowed permission requests pages and sources directly; out-of-scope generation refused) | 1, 3 | Visibility matrix fully automated: stranger 404 on view/read/generate, department member reads but generation is 403 (owner-only modify boundary), page reads outside the frozen manifest 404 with no title/body leak, other-KB revisions invisible (`test_other_account_cannot_view_or_generate`, `test_department_visibility_can_read_but_not_generate`, `test_unknown_or_out_of_revision_document_page_is_invisible`, `test_revision_of_another_kb_is_invisible`; router `test_other_account_cannot_see_or_generate`, `test_department_member_reads_but_cannot_generate`, `test_page_read_is_404_outside_the_frozen_manifest`, `test_unknown_revision_is_404`). Desktop pre-validation (`KNOWLEDGE_WIKI_*` fixed categories before the Runtime is touched) pins the client side; authorization itself is never filtered locally. | None — the automated matrix covers the scenario's operations; a manual matrix re-check on the live deployment folds into T118-02's staged pass. |

## Pending / risks

- Real-LLM condition scenarios (T118-01 live leg, T118-02/T118-03 manual
  passes) are **unexecuted on model credentials**; the orchestration,
  binding, isolation, retry, and failure contracts they depend on are
  pinned by the automated suites above with a fixed writer, so only the
  model-facing wording quality is unverified (per AC4 the body need not be
  verbatim).
- dist:win packaging is a pending packaging step (not run in this worktree;
  recorded in the Desktop companion report).
- Real Win7 remains the only explicitly deferred platform validation:
  **unexecuted**, owned by [#131](https://github.com/Orbit-Crew/iDeer/issues/131)
  together with its dependency/compatibility patches. Modern-Windows results
  above are not Win7 results.
- The wiki stack reuses the existing controlled-knowledge idioms (#113
  frozen-identity dispatch, #114 fixed failure categories, #115/#116
  owner-gated mutation boundaries, #116 `RevisionMaterialSource` with only a
  task-label addition); no new device operation, engine, or algorithm tuning
  was introduced, per the ticket's out-of-scope rule.

## Installed combination acceptance, 2026-10-29 (modern Windows)

The staged installed-combination portion was executed on the paired Desktop
side and recorded in that repository:
`iDeer-Desktop/docs/acceptance/issue-118/installed-20261029.md` with sanitized
evidence under `docs/acceptance/issue-118/evidence/installed-20261029/`.
The honest view-before-generation state, per-page frozen digests, skipped-page
presentation, revision isolation and bad-command refusal legs passed; T118-03
and T118-04 passed fully. The live model-written page stays staged on the
material-consent approval-surface and provider dependencies, with the SSE
defect [#37](https://github.com/Orbit-Crew/iDeer-Desktop/issues/37)
observation recorded. Bindings identical to the #112 section. Win7 remains
with #131.
