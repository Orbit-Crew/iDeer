---
id: issue-112-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 112 Server side of local knowledge import to platform Revision registration
last-verified: 2026-10-27
verified-against: orch/issue-112-knowledge-import based on d37d9723 (merge of #146); candidate is the branch tip of the same tree this evidence was produced from
---

# Issue 112 Server acceptance

The Server candidate is the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-112-knowledge-import`, base d37d9723. The Desktop repo carries the
same branch name and starts at 78731f0; its companion report is
`docs/acceptance/issue-112/report.md` in that repository. No issue closure and
no PR are claimed by this report.

Implemented Server surface: `POST
/api/resources/{resource_id}/knowledge-revisions/local-imports`
(`backend/app/gateway/routers/resources.py`, `LocalImportRequest`) registers
one explicit Desktop local import as a draft `KnowledgeRevision` whose manifest
entries carry `origin=local_import` plus the device id
(`backend/app/agentplatform/knowledge/local_import.py`). The manifest hash is
the canonical hash of the frozen identity entries; document identities are
derived deterministically from filename+content hash so an identical re-import
reproduces the same manifest identity. Publish and prepare refuse local-import
revisions with 409 (`backend/app/agentplatform/knowledge/revisions.py`). No
document content, no provider dataset, and no KnowledgeBase pointer change are
involved; the unified resource entry (`ResourceService.get_visible` /
`assert_modify`) supplies owner/visibility governance and audit
(`knowledge_local_import_registered`).

Environment: WSL Ubuntu, Python 3.12.3 venv (fastapi 0.136.1), pytest via the
focused runner `dev-log/issue-112/test.sh`, ruff 0.16.5 via miniconda.

| Scenario | Overall status | Current evidence and remaining required work |
| --- | --- | --- |
| T112-01 | incomplete | Governance-identity registration passes: platform KB UUID, owner private visibility, manifest/hash identity, audit event, identity-only request (5-test suite). Original files and the device index never reach the Server. Real three-end run with installed Desktop, live Server and UI requires the named dependencies below; that portion is unexecuted. |
| T112-02 | incomplete | Invalid manifests (path traversal names, unsupported type, oversize, duplicate content) are rejected with fixed categories and leave zero revision rows; a hidden KB reads as 404 for another account; wrong resource type 404. Real junction/link probes and failure injection against a live paired device are covered on the Desktop side (see its report); the live UI portion is unexecuted. |
| T112-03 | incomplete | Re-import after content change appends R2 with a different manifest hash; R1 keeps its own frozen manifest and hash (never R2 content); identical replay appends R3 with the same manifest identity; publish/prepare of local-import revisions are explicitly refused 409. Live retrieval attempts against a published KB are unexecuted because local-import revisions are draft-only by design. |
| T112-04 | incomplete | A fresh session (restart view) reads the same frozen revision identities; another account gets 404 on revision read and list. Cross-account/device live restart verification with the installed Desktop remains unexecuted. |

Win7 is the only explicitly deferred platform verification for this stage: it
stays unexecuted and is owned by the closing ticket #131 together with the
Win7 compatibility patches listed there. Modern Windows passes above must not
be read as Win7 passes.

## Commands and results

All commands ran inside the server worktree with the focused runner; each is
reproducible and exited 0.

- `cd dev-log/issue-112 && ./test.sh backend/tests/unit/gateway/test_resources_api_knowledge_local_imports.py -q`
  -> 5 passed (8.3s). Red first: the same file failed 5/5 before the router
  endpoint existed (AttributeError on `resources.LocalImportRequest`).
- `./test.sh backend/tests/unit/gateway/test_resources_api_knowledge_revisions.py backend/tests/unit/gateway/test_admin_knowledge_api.py backend/tests/unit/gateway/test_knowledge_tests_api.py backend/tests/unit/gateway/test_resources_api_knowledge_local_imports.py -q`
  -> 22 passed (24.0s).
- `./test.sh backend/tests/unit/knowledge/test_knowledge_revisions.py backend/tests/unit/knowledge/test_knowledge_revision_publish.py backend/tests/unit/knowledge/test_knowledge_facade.py backend/tests/unit/knowledge/test_knowledge_base_service.py -q`
  -> 44 passed (44.7s).
- `$HOME/miniconda3/bin/python -m ruff check backend` -> All checks passed, exit 0.
- Full baseline scope: `./test.sh backend/tests/integration/api -q --ignore-glob "*_e2e*.py" --ignore-glob "*live*.py" -o faulthandler_timeout=60`
  -> 1212 passed, 31 skipped (201.96s), exit 0 — identical to the
  orchestrator-recorded pre-change baseline.

## Dependencies still required (staged portions)

- Installed Desktop package and a real authenticated Server pair (account A/B,
  devices D1/D2) for the true cross-repo scenarios; Desktop-side automated
  evidence is in the Desktop repository report.
- `npm.cmd run dist:win` installer verification on the Desktop candidate; the
  installer SHA-256 binds this report's counterpart after packaging.

## Baseline relation

Pre-change baseline for the same integration scope was 1212 passed, 31 skipped
(orchestrator-recorded run). The unit suites above were green before the change
except the new 5-test file, which was created red and turned green by the
router implementation.
