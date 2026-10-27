---
id: issue-113-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 113 Server side of frozen-scope local knowledge retrieval with retrieval receipts
last-verified: 2026-10-27
verified-against: orch/issue-113-frozen-retrieval based on 6874d17e (#112 candidate); the candidate is the branch tip of the same tree this evidence was produced from
---

# Issue 113 Server acceptance

The Server candidate is the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-113-frozen-retrieval`, starting at 6874d17e (the #112 candidate).
The Desktop repo carries the same branch name and starts at 81b0a0d; its
companion report is `docs/acceptance/issue-113/report.md` in that repository.
No issue closure and no PR are claimed by this report.

Implemented Server surface (#113):

- `POST /api/resources/{resource_id}/knowledge-revisions/{revision_id}/activate-local`
  (`backend/app/gateway/routers/resources.py` ->
  `KnowledgeFacade.activate_local_revision` ->
  `KnowledgeLocalImportService.activate_local_revision`,
  `backend/app/agentplatform/knowledge/local_import.py`) anchors a
  device-local KB on one registered local import. Activation is a LIVE
  pointer move only: no provider dataset, no platform content, audit event
  `knowledge_local_revision_activated`.
- Closure resolution
  (`backend/app/agentplatform/resources/service.py`,
  `_resolve_published_revision`) accepts an anchored local-import revision
  (status stays `draft`): LIVE resolves through the active pointer, PINNED
  through the explicit revision anchor. Without an anchor the run refuses —
  draft/current content is never impersonated.
- Frozen scope binding (`build_frozen_knowledge_bindings` in
  `backend/app/gateway/canonical_agent_run_preparation.py`): a local-import
  revision binds to the stable dataset token `local:<revision_id>` only when
  the run caller owns the KB and the manifest names exactly one importing
  device; anything else stays out of the Effective Knowledge Scope and is
  therefore invisible to the model. Provider-backed LIVE/PINNED behavior is
  unchanged.
- Device dispatch (`backend/app/gateway/local_knowledge.py` + the
  `search_local_knowledge` closure): retrieval goes through the device broker
  as operation `local.knowledge.search` to the one owning device, carrying
  frozen identity fields only (query, revision id, manifest hash, per-document
  id/filename/content-hash). Results outside the frozen manifest are dropped;
  unreported documents are recorded missing. Device execution receipts enter
  the run evidence ledger via `record_local_execution_receipt` (Tool Receipt
  tied to the Run and tool call), and retrieval results flow through the
  existing `KnowledgeRuntimeAdapter` pipeline so every search produces a
  Retrieval Receipt (`run_id`, KB/revision/manifest identity, bounded items)
  archived into the run record by the existing archiver.
- Extension seam
  (`backend/packages/agentplatform-extension/.../knowledge/runtime_adapter.py`,
  `scope.py`): `local:<...>` datasets never reach a knowledge provider — they
  are dispatched to the injected `local_search` callable, and without one the
  search is denied with a recorded `access_denied` receipt.

Environment: WSL Ubuntu, Python 3.12 venv (fastapi 0.136.1), pytest via the
focused runner `dev-log/issue-112/test.sh`, ruff (miniconda). No model
credentials were configured in this environment; real-LLM portions of the
scenarios below are unexecuted on that stated dependency.

| Scenario | Overall status | Current evidence and remaining required work |
| --- | --- | --- |
| T113-01 | incomplete (automated passed; live run unexecuted) | Automated: LIVE/PINNED closure resolution freezes the local-import revision at run start (14-test suite: activated revision resolves into the run snapshot with revision no/hash and `provider_dataset_id` NULL; activation of R2 after run A freezes moves only run B; a PIN on R1 stays fixed across activation of R2; un-activated KB refuses the run). Mid-run publication of R2 with a live installed Desktop + running Run is the unexecuted portion (needs real devices + Server). |
| T113-02 | incomplete (automated passed; real-data QA unexecuted) | Automated: local dataset retrieval dispatches to the owning device and produces a Retrieval Receipt carrying `run_id`, `knowledge_base_id`, `revision_id`, `revision_no`, `manifest_hash`, per-item logical document id/display name/content hash/position, while the model-facing result carries only citation handles (document/dataset/chunk ids stripped). Question answering over real local material with a real model is unexecuted on model credentials. |
| T113-03 | incomplete (automated passed; UI comparison unexecuted) | Automated: another caller's local KB binds nothing (invisible, not an error leak); a manifest without one device binding stays invisible; unknown manifest or manifest-hash mismatch is refused by the device (`KNOWLEDGE_SEARCH_REVISION_UNKNOWN`); result chunks outside the frozen manifest are dropped server-side. The original file never appears as a platform attachment (no upload path exists in the change). Original-file vs platform-attachment UI comparison is unexecuted. |
| T113-04 | incomplete (automated passed; live failures unexecuted) | Automated: device-offline/unauthorized-device paths raise fixed `KNOWLEDGE_DEVICE_UNAVAILABLE` before any task is sent; non-completed broker tasks surface the device error code as a tool failure; denied searches record an `access_denied` retrieval receipt (never an empty success); device-side drift/missing documents are structured `missing` entries, never current content. Live offline/mid-disconnect injection against a paired device and any real-model unavailability paths are unexecuted. |

Win7 is the only explicitly deferred platform verification for this stage: it
stays unexecuted and is owned by the closing ticket #131 together with the
Win7 compatibility patches listed there. Modern Windows passes above must not
be read as Win7 passes.

## Commands and results

All commands ran inside the server worktree with the focused runner; each is
reproducible and exited 0.

- `cd dev-log/issue-112 && ./test.sh backend/tests/unit/knowledge/test_local_knowledge_retrieval.py -q`
  -> 14 passed (11.75s). Red first: the same file failed collection before
  `build_frozen_knowledge_bindings` existed and failed 3/11 after the first
  implementation slice (activation 404 semantics, device-less manifests,
  model-facing projection) before turning green.
- `./test.sh backend/tests/unit/knowledge/test_local_knowledge_retrieval.py backend/tests/unit/knowledge/test_run_knowledge_freeze.py backend/tests/unit/knowledge/test_pinned_revision_run.py backend/tests/unit/knowledge/test_effective_knowledge_scope.py backend/tests/unit/knowledge/test_retrieval_receipts.py -q`
  -> 54 passed (22.23s).
- `./test.sh backend/tests/unit/gateway/test_canonical_agent_run.py backend/tests/unit/gateway/test_canonical_prep_single_pass.py backend/tests/unit/gateway/test_first_token_timing.py backend/tests/unit/gateway/test_resources_api_knowledge_local_imports.py backend/tests/unit/knowledge/test_local_knowledge_retrieval.py -q`
  -> 26 passed (22.72s).
- `./test.sh backend/tests/unit/gateway/test_resources_api_knowledge_local_imports.py backend/tests/unit/gateway/test_resources_api_knowledge_revisions.py backend/tests/unit/gateway/test_tool_receipt.py backend/tests/unit/gateway/test_receipt_verification.py backend/tests/unit/knowledge -q`
  -> 334 passed, 3 skipped (167.89s).
- `$HOME/miniconda3/bin/python -m ruff check backend` -> All checks passed, exit 0.
- Full baseline scope: `./test.sh backend/tests/integration/api -q --ignore-glob "*_e2e*.py" --ignore-glob "*live*.py" -o faulthandler_timeout=60`
  -> 1212 passed, 31 skipped (205.41s), exit 0 — identical to the
  orchestrator-recorded pre-change baseline.

## Dependencies still required (staged portions)

- Installed Desktop package and a real authenticated Server pair (account A,
  device D1; K2 not accessible to A) for the live cross-repo scenarios; the
  Desktop-side automated evidence is in the Desktop repository report.
- Model credentials for any real-model question answering; those scenario
  portions are recorded unexecuted (staged on model credentials).
- `npm.cmd run dist:win` on the Desktop candidate remains a pending packaging
  step; the installer SHA-256 will bind this report's counterpart after
  packaging.

## Baseline relation

Pre-change baseline for the same integration scope was 1212 passed, 31
skipped (orchestrator-recorded run at the #112 candidate) and is reproduced
exactly. The knowledge/receipt unit suites above were green before the
change; only the new 14-test file was created red and turned green by the
implementation.

## Freeze semantics relative to the #112 revision registry

#112 made local-import revisions append-only, draft-only, and
pointer-free ("never touches the KnowledgeBase pointer"). #113 adds exactly
one controlled pointer move — `activate_local_revision` — that only ever
anchors a *registered local import* revision (refusing provider revisions,
409 otherwise) and creates no provider dataset. Publication/prepare of local
revisions remain refused (409), the manifest hash remains the version
identity, and every Run still freezes its revision through the unchanged
closure resolution, so a Run never observes content that was not frozen into
its snapshot: activation between Runs moves new Runs only, and a device-side
hash mismatch yields a structured `missing` entry instead of current content.
