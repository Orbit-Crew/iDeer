---
id: docs-testing-mock-e2e-recovery-d
kind: evidence
status: archived
owner: test maintainers
scope: repair record for mock e2e recovery ticket 03-D (cases #15-19, #39, #42-49) — fourteen cases passing five production repeats after the formatted candidate, with #39/#47 non-reproduction recorded without causal claims
archived-reason: candidate-scoped repair record from the recovery batch (base 3ad6359af); the batch merged into develop at e33a103f1 — group results are the batch candidates' results, not current verification
---

# Mock E2E recovery — ticket 03-D

## Result

Ticket 03-D covers cases #15–19, #39, and #42–49 (14 cases). The formatted candidate passed all 14 five times with one worker and zero retries (70/70; elapsed 181.57 seconds) and passed the complete six-spec set in CI configuration (76/76; zero skipped, unexpected, or flaky; elapsed 132.63 seconds). From base `3ad6359aff7243a3a391c6a244612c0e2782f5be`, the eight-path product/test diff fingerprint for these final runs was `4e8ab90b14a64544c7dd2c7584b339ec02aedf21a7b3dfcb0db8e9e162281d03`. The first commit-hook attempt applied Prettier to five test files, so its earlier browser results are retained as history only and were rerun on this formatted candidate. The final source/test fingerprint stayed unchanged across both post-format runs.

The initial assigned production run selected 14 cases: 12 failed and two passed (exit 1, 171 seconds). Cases #39 and #47 were among the cases that did not reproduce in the group run; subsequent five-repeat and related-spec runs also passed them. No root cause or order-dependency claim is made for those two cases. The earlier loss of the local service during a separate repeat attempt is an environment interruption and is excluded from the final evidence.

The strict #18 stream assertion initially exposed an asynchronous observation race in the test: the goal write and optimistic GoalStatus were visible while the composer still showed “Working…”, but the follow-up stream request had not yet been captured. The test now polls the observed request count before checking its exact method, path, and identities. The focused case passed five times, and the post-format repeat/formal runs above passed on the corrected candidate. An earlier 69/70 attempt is retained as diagnostic evidence and is not counted as acceptance.

## Candidate and environment

The implementation base was commit `3ad6359aff7243a3a391c6a244612c0e2782f5be` on `fix/test-system-first-batch`, in its isolated worktree. Browser runs used the already built production frontend at `http://127.0.0.1:3001`, started with `DEER_FLOW_AUTH_DISABLED=1`. Its BUILD_ID was `Ptsx_FuuVZ9wjAmw_uT-c`; the root-owned service returned HTTP 200 before both post-format runs. The initial sandboxed `python3 scripts/test_preflight.py frontend-mock-e2e` attempt could not launch Chromium or bind a local socket; the identical command in the permitted local environment passed both checks. No product source changed after this build; the post-format candidate changed only tests and test fixtures. An offline Gateway was not used as a frontend health signal.

The focused run used `CI=1`, `PLAYWRIGHT_SKIP_WEB_SERVER=1`, and `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001`, with this exact selector and execution configuration:

```sh
CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 pnpm exec playwright test \
  tests/e2e/chat.spec.ts \
  tests/e2e/sidecar-chat.spec.ts \
  tests/e2e/thread-history.spec.ts \
  tests/e2e/thread-archive.spec.ts \
  tests/e2e/thread-delete-confirm.spec.ts \
  tests/e2e/thread-ordering.spec.ts \
  --grep 'switching conversations during goal preparation drops the stale continuation|dropping the project scope mid-submission resets the thread identity|edits and reruns only the latest question in a regular chat|goal command assigns the project before saving the goal|blocks unresolved composer template placeholders until replaced|opens restored side chat history without animated scroll|archive keeps the open conversation, supports undo and restores from the archive|active list includes legacy chats beyond a full page of archived chats|archived (default|custom agent) chat can be restored from its mobile header|cleanup failure keeps active chat deletion retryable after the row disappears|keeps rendered messages ordered when the latest history page advances|retrying deletion of the active newly created chat returns to the new chat screen|a live compaction during submit keeps history order and appends the new turn' \
  --workers=1 --retries=0 --repeat-each=5 --reporter=line
```

The initial pre-hook run passed 70 expected, 0 unexpected, 0 flaky, 0 skipped in 162.09 seconds. After the Prettier hook changed five test files, the same frozen repeat command ran again on the final fingerprint above: 70 expected, 0 unexpected, 0 flaky, 0 skipped; exit 0; elapsed 181.57 seconds. The focused #18 exact-request case passed 5/5 with zero retries. The formal command used the same six spec files, `CI=1`, and no worker or retry overrides (the project CI defaults):

```sh
CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 pnpm exec playwright test \
  tests/e2e/chat.spec.ts \
  tests/e2e/sidecar-chat.spec.ts \
  tests/e2e/thread-history.spec.ts \
  tests/e2e/thread-archive.spec.ts \
  tests/e2e/thread-delete-confirm.spec.ts \
  tests/e2e/thread-ordering.spec.ts \
  --reporter=json
```

The earlier formal run collected 76 and passed in 123.02 seconds. On the formatted candidate fingerprint above, Playwright again collected 76 cases across the six files and reported 76 expected, 0 unexpected, 0 flaky, and 0 skipped; exit 0; elapsed 132.63 seconds. Targeted Prettier, ESLint, `pnpm exec tsc --noEmit`, and `git diff --check` passed on the formatted files. No test timeout, retry, or scope was increased to obtain these results. Post-format raw output and exit records are in ignored `dev-log/root-run/d-repeat-post-format/` and `dev-log/root-run/d-formal-post-format/`.

## Case findings and assertion mapping

| Cases | Evidence-based finding and current coverage |
| --- | --- |
| #15–16 | The project-scoped composer did not reliably establish the native project/thread association before continuing, and query-only scope changes could leave an in-flight submission associated with stale identity. The chat route now pre-creates the requested project thread before message/goal work and checks both thread and project identity after awaits. Tests hold the native create request, switch conversation or drop project scope, release the request, and assert there is no stale goal write/run or URL rewrite. |
| #17 | The regular-chat edit/rerun fixture did not model the new run in the persisted message page. The case-local fixture now updates its history projection when the edited stream is delivered. Assertions keep the earlier exchange, show the replacement question and rerun answer exactly once, and prove the original latest question is absent. |
| #18 | The project/goal fixture returned a generic sidecar identity instead of the requested native thread identity, so it could not establish the create → project assignment → goal save → SDK stream contract. The test-local native and SDK routes now echo the requested identity and project. Assertions check project ID, goal body and HTTP 200, event order, one SDK create, and the exact `POST /api/langgraph/threads/{id}/runs/stream` path plus matching path/context identity. The test waits for that observable request before asserting it. |
| #19 | The former “Research” welcome suggestion button is no longer part of the current composer experience. The test now enters the documented template text through the composer and retains its core contract: unresolved placeholders block submission, replacing the placeholder permits the expected send. |
| #39 | The prior side-chat scroll symptom was not reproduced in the 14-case baseline run or final repeated/formal runs. The case itself was unchanged; no causal fix is claimed. Its restored-history and scroll-position assertions remain intact. |
| #42–43 | The shared search fixture did not implement the archive filter and pagination parameters used by the current archive list. A test-local archive-aware search response now filters active/archived metadata, sorts and applies offset/limit. Cases retain archive/undo/restore-after-refresh behavior and prove a legacy active row remains visible after more than one archived page. |
| #44–45 | Archived chat headers lacked the restore/status control on regular and custom-agent routes. `ThreadArchiveStatus` is now mounted in both existing-chat headers. The paired mobile cases click Restore and verify the archived state clears on each route. |
| #46 | The prior assertion expected an active deletion with a neighboring thread to navigate to `/new`, contrary to the established recent-thread-list contract. The test now asserts navigation to the surviving neighbor after retrying cleanup, while keeping the first failure, missing remote row, retry, and cleanup assertions. The no-neighbor `/new` path remains asserted by #48. |
| #47 | The duplicate-text symptom was not reproduced in the assigned run. The updated history fixture captures the submitted ID, streamed values, latest page, cursor page, and run IDs; assertions verify exact prompt/answer IDs and counts, adjacent prompt/answer order, preserved history duration, and the same order after refresh. No hidden duplicate is accepted through a `.first()` locator. |
| #48 | The newly created active chat has no surviving neighbor. Its retry path still asserts successful cleanup returns to `/workspace/chats/new`, removes both streamed messages, and remains fresh after revisiting the deleted route. |
| #49 | The compaction stream is now scoped to the observed `POST /api/langgraph/threads/{threadId}/runs/stream` route. The handler asserts exactly one request with the expected method and thread ID. The emitted checkpoint and persisted page share the submitted human ID; assertions count one human and one answer, retain their order through compaction, pagination, and refresh, and exclude the hidden summary. |

The shared `handleRunStream` test helper now accepts optional streamed messages and a run ID so cases #17 and #47 can model the event and persistence contracts they exercise. Its upstream GitNexus impact is exact MEDIUM: eight direct callers, all included test files. The neighboring `mockLangGraphAPI` setup surface was audited at exact CRITICAL (75 direct, eight indirect) but was not changed. `ChatPage` route-symbol impact was UNKNOWN because GitNexus resolves no callers for the Next route entry; source inspection confirmed it is the `/workspace/chats/[thread_id]` page default export. `ThreadArchiveStatus` impact was exact LOW with one direct caller/process. The compaction handler is test-local and its impact was LOW. The complete mock lane remains required to validate the helper change across its callers.

## GitNexus change gate

On the final staged D candidate, `detect_changes({scope: "all"})` returned 46 changed symbols across 10 files and 12 affected processes at HIGH risk. The complete changed-symbol and process arrays matched their reported counts; neither partial nor truncated was set. The affected flows include both chat routes' persisted-thread-ID clear/resolve behavior and locale context/cookie operations. The route lifecycle risk is why the final full Mock E2E lane remains a parent acceptance gate. This is not evidence of an order-dependent failure; the five-solo/five-prefix causal criterion was not met.

No shared behavior gap spanning D and another group was proven, so this work does not close F0 or justify an order-dependency repair. No test file was added, moved, or deleted; the migration ledger does not need an entry. Independent Standards and Spec re-reviews found no remaining D findings. The full Mock E2E lane and parent gates remain pending after this D commit.
