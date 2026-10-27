---
id: issue-115-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 115 Server/Web side of explicit server-side publication of local knowledge
last-verified: 2026-10-27
verified-against: orch/issue-115-server-publish based on b379de04 (#113 candidate); the candidate is the branch tip of the same tree this evidence was produced from
---

# Issue 115 Server acceptance

The Server/Web candidate is the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-115-server-publish`, starting at b379de04 (the #113 candidate).
The Desktop repo carries the same branch name and starts at 25870be; its
companion report is `docs/acceptance/issue-115/report.md` in that repository.
No issue closure and no PR are claimed by this report.

Implemented Server surface (#115):

- `GET /api/resources/{id}/knowledge-revisions/{revision_id}/local-publication/preview`
  (`backend/app/gateway/routers/resources.py` ->
  `KnowledgeFacade.preview_local_publication` ->
  `KnowledgeLocalPublishService.preview_publication`,
  `backend/app/agentplatform/knowledge/local_publish.py`) is a read-only
  preview: it returns the frozen document identities plus the destination
  (a to-be-created independent private server copy, deterministic slug and
  display name, `visibility_application_required` governance note). It
  performs no write, no upload, and creates no copy.
- `POST .../local-publication` with `LocalPublicationConfirmRequest` is the
  explicit confirmation gate. `confirmed=false` is refused with the fixed
  category `LOCAL_PUBLISH_CONFIRMATION_REQUIRED` (409) and creates nothing;
  `confirmed=true` idempotently creates (or reuses) the private server copy
  through the standard `ResourceService.create_resource`. The device KB's
  visibility, revisions, and LIVE pointer are never touched.
- Content travels only through the platform's own document upload endpoint
  (`POST /api/resources/{copy_id}/documents`); `POST
  .../local-publication/complete` then re-verifies every uploaded hash
  against the frozen manifest (refusing `LOCAL_PUBLISH_CONTENT_INCOMPLETE`
  and `LOCAL_PUBLISH_CONTENT_DRIFTED`), freezes the copy's revision through
  the standard `KnowledgeRevisionService.create_revision`, injects the
  managed-origin provenance (`origin=local_publication`, `published_from`
  naming source KB id, source revision id, source manifest hash) into the
  immutable manifest entries, and publishes via the standard
  `publish_revision` -> `execute_publish` build (integrity, eval policy,
  build verification, then the copy's own LIVE pointer move).
- `GET .../local-publication` derives the publication state on every read
  from the copy resource, its documents, and its revision
  (`none | awaiting_content | ready_to_complete | publishing | published |
  failed`), so interrupted uploads, failed builds, and the copy's current
  visibility (permission state) are always current without a status table.
  Audit events: `knowledge_local_publication_confirmed`,
  `knowledge_local_publication_completed`.
- Governance reuse: the copy qualifies for the existing visibility flow
  (`ResourceService.request_visibility` requires a published revision, which
  only the copy can ever have), while the device KB — holding draft-only
  local-import revisions — can never expand its visibility ("Only a
  published resource may expand visibility"). Non-owner calls on the
  publication surface are refused by the unified resource entry (403/404).

Environment: WSL Ubuntu, Python 3.12 (focused pytest runner
`dev-log/issue-112/test.sh` against the #112/#113 venv), ruff via miniconda.
No model credentials and no provider deployment are configured in this
environment; live provider builds are exercised through the controllable
fake provider from the existing publish-test suite.

| Scenario | Overall status | Current evidence and remaining required work |
| --- | --- | --- |
| T115-01 | incomplete (automated passed; installed-UI walk-through unexecuted) | Automated: the read-only preview states destination and document identities with zero side effects (`test_preview_and_unconfirmed_confirm_upload_nothing`: resource set before/after identical, status stays `none`); an unconfirmed confirm call is refused 409 `LOCAL_PUBLISH_CONFIRMATION_REQUIRED` and never fabricates a published state. Desktop-side preview evidence (upload-nothing on the wire) is in the Desktop repository report. The installed-UI preview/cancel walk-through needs the packaged Desktop (`npm.cmd run dist:win` not yet run) and is staged on that packaging step. |
| T115-02 | incomplete (automated passed; real-approval + live B retrieval unexecuted) | Automated: explicit confirm creates an independent private copy; uploads hash-matched against the frozen marker bytes; complete builds the provider dataset through the standard publish machinery; the copy's manifest entries carry `published_from` provenance; A submits the visibility application on the copy, a super-admin approves it, the copy turns `department/public`; a teammate caller's frozen bindings resolve the copy through its `provider_dataset_id` (server-side retrieval, never the device), while the same caller's bindings for the device-local revision stay empty (no dispatch). Real governance approval by a human reviewer and a real B-account retrieval with the installed UI are staged on a deployed Server with a configured provider and the packaged Desktop. |
| T115-03 | incomplete (automated passed; two-account live probe unexecuted) | Automated: the device KB cannot widen visibility even by its owner (draft-only revisions -> "Only a published resource may expand visibility"); a non-owner caller binds nothing for a device-local revision so no local search can ever dispatch to the device; non-owner publication/confirm/status calls are 403/404; the copy's visibility application by a non-owner is refused. Live two-account probes against a real deployment are staged on the same deployment dependency as T115-02. |
| T115-04 | incomplete (automated passed; mid-transfer network injection unexecuted) | Automated: partial upload -> 409 `LOCAL_PUBLISH_CONTENT_INCOMPLETE` with status `awaiting_content` and an explicit missing list; extra/drifted content -> 409 `LOCAL_PUBLISH_CONTENT_DRIFTED`; a failing provider build leaves the copy revision `failed` with `failure_code=parse_failed` visible in the status endpoint; retry completes on the same copy (deterministic slug reuse) and republishes; a later device import leaves the existing copy untouched and shows `none` for the new revision (no two-way sync); the source KB's active pointer and draft revision survive publication unchanged (no silent replacement of a running frozen revision). Real mid-transfer network failure injection (client disconnect during multipart upload) is unexecuted and staged on a deployed pair. |

Win7 is the only explicitly deferred platform verification for this stage:
it stays unexecuted and is owned by the closing ticket #131 together with
the Win7 compatibility patches listed there. Modern Windows passes above
must not be read as Win7 passes. `dist:win` on the Desktop candidate remains
a pending packaging step and is not part of this repository's evidence.

## Commands and results

All commands ran inside the server worktree with the focused runner; each is
reproducible and exited 0 unless stated.

- `dev-log/issue-112/test.sh backend/tests/unit/gateway/test_resources_api_knowledge_local_publication.py -q`
  -> 4 passed (7.9s). The file maps 1:1 onto T115-01..04 and was written
  against the frozen contract before the implementation slices turned it
  green (first red runs: sync/async execute misuse, content-freeze boundary,
  provider-injection mismatch).
- `dev-log/issue-112/test.sh backend/tests/unit/gateway/test_resources_api_knowledge_local_publication.py backend/tests/unit/gateway/test_resources_api_knowledge_local_imports.py backend/tests/unit/knowledge/test_knowledge_revision_publish.py backend/tests/unit/knowledge/test_local_knowledge_retrieval.py -q`
  -> 44 passed (41.6s) — #112/#113 local-knowledge contracts still hold.
- `dev-log/issue-112/test.sh backend/tests/unit/gateway -q -o faulthandler_timeout=60`
  -> 6015 passed, 22 skipped (297.1s) — full gateway unit scope including
  resources API, receipts, and canonical run preparation.
- `dev-log/issue-112/test.sh backend/tests/unit/knowledge -q -o faulthandler_timeout=60`
  -> 288 passed, 3 skipped (185.2s).
- `dev-log/issue-112/test.sh backend/tests/integration/api -q --ignore-glob "*_e2e*.py" --ignore-glob "*live*.py" -o faulthandler_timeout=60`
  -> 1212 passed, 31 skipped (194.3s), exit 0 — identical to the
  orchestrator-recorded pre-change baseline.
- `$HOME/miniconda3/bin/python -m ruff check backend` -> All checks passed,
  exit 0.
- Web (same repository): `pnpm vitest run --pool=forks --maxWorkers=2
  --testTimeout=5000 --hookTimeout=5000` -> 355 files / 10584 tests passed;
  `pnpm rstest run` -> 167 files / 1270 tests passed; `pnpm check`
  (eslint + tsc) -> 0 errors. The Web surface is publication status,
  permission, and failure visibility: `useLocalPublication` +
  `getLocalPublication` (`frontend/src/core/library/{api,hooks,index}.ts`),
  the `LocalPublicationPanel` in
  `frontend/src/components/workspace/library/revision-list.tsx` (states
  `none/awaiting_content/ready_to_complete/publishing/published/failed`,
  missing-document lists, copy visibility and failure codes; polling only
  while building), i18n strings in `en-US.ts`/`zh-CN.ts`, and 5 new cases in
  `frontend/tests/unit/components/workspace/library/revision-list.test.tsx`
  (16/16 in that file).

## Dependencies still required (staged portions)

- A deployed Server with a configured knowledge provider and a packaged
  Desktop (`npm.cmd run dist:win` pending) for the installed-UI and live
  two-account scenarios T115-01..03.
- Human visibility approver for the real governance approval leg of
  T115-02.
- Controlled network failure injection for the mid-transfer leg of T115-04.

## Baseline relation

The orchestrator-recorded pre-change baseline at the #113 candidate is
1212 passed, 31 skipped for the integration/api scope, and the unit suites
above were green before the change; only the new 4-test gateway file and the
5 new Web cases were created and turned green by the implementation. The
background-baseline comparison run is recorded in the commands section.

## Coexistence with #112 immutability and #113 freeze semantics

#112 made local-import revisions append-only, draft-only, and publishable by
nobody (`publish_revision`/`prepare_revision` still 409 on them — unchanged
code). #115 does not mutate any existing revision: publication reads the
frozen manifest, then creates an independent copy whose OWN first revision
carries the provenance block inside its immutable manifest, so the managed
origin is frozen with the same hash governance as every other revision. The
only LIVE pointer moves remain #113's owner-only `activate-local` on device
KBs and the standard publish on the copy; publication never re-points the
source KB, so a Run frozen on the device-local revision (or any revision)
keeps its original bindings, and later publications never retroactively
touch running Runs or existing copies (each source revision publishes to its
own deterministic copy; retries reuse the same copy by construction, never
duplicate it).
