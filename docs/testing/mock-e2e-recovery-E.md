---
id: docs-testing-mock-e2e-recovery-e
kind: evidence
status: archived
owner: test maintainers
scope: repair record for mock e2e recovery ticket 03-E (cases #7-9 and #52) — artifacts route contract findings, the artifact conflict-indicator sub-ticket evidence restated inline, and browser acceptance of the table-preview and visualization specs
archived-reason: candidate-scoped repair record from the recovery batch (ticket start 943ec105d); the batch merged into develop at e33a103f1 — group results are the batch candidates' results, not current verification
---

# Mock E2E recovery E: artifacts

**Ticket:** 03-E, cases #7–9 and #52
**Ticket start HEAD:** 943ec105d04f4fe93e449cfdd48796fed9564b04
**Status:** implementation and browser acceptance complete; pending root review and parent gates.

## Contract and case findings

The current frontend contract keeps normal chat at full width until a user opens a side panel. File changes and browser frames prompt rather than opening a panel automatically; the original artifact preview entry and panel remain available. See the [frontend experience spec](../specs/2026-09-25-deerflow-frontend-experience-spec.md), user stories 24–26 and 30–31, and implementation/testing decisions at lines 81–83 and 97–100. The recovery spec assigns cases #7–9 and #52 to this ticket and requires stream assembly, refresh recovery, draft conflict, graph preview, and code fallback to remain covered.

| Case                                     | Production evidence and classification                                                                                                                                                                                                                                                  | Assertion retained or replacement                                                                                                                                                                                                                                 |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #7 streamed write_file arguments         | The stream renders /artifact-fixtures/batched-report.md, but leaves #artifacts closed. This matches the current no-auto-open contract.                                                                                                                                                  | Assert the panel starts closed, click the streamed write-file step, then keep the basename and reconstructed Hello world content assertions. The path and content still prove that split argument chunks were assembled.                                          |
| #8 refresh and selection                 | After reload the artifact trigger is present and the panel is closed. Clicking the trigger shows Presented Report, confirming that the selected file survived refresh. This matches the current normal-chat layout contract.                                                            | Assert closed state after reload, explicitly click the existing trigger, then keep the selected-file title assertion.                                                                                                                                             |
| #9 save conflict                         | The conflict state and draft survive a 412 response. At 1280×720 the panel was open, but the conflict indicator had a zero-width bounding box (display:block, visibility:visible, opacity:1, width:0, height:16.19), so users could not see Changed remotely. Confirmed product defect. | After the save attempt, explicitly open the artifact panel and retain visible conflict text, disabled Save, and the draft cell assertions. ArtifactFileDetail now gives the conflict/status span shrink-0, preserving its status text in the constrained toolbar. |
| #52 fault-tree graph and source fallback | The graph content assertions and artifact request succeeded. The test then timed out looking for a radio named Code, while the rendered control's accessible name is View source. Confirmed stale accessible-name expectation.                                                          | Use the current View source radio name and retain the top_event source-content assertion, along with graph node, section, and request assertions.                                                                                                                 |

GitNexus impact for ArtifactFileDetail was run against the fresh ticket-start worktree index. It returned LOW risk, two impacted symbols (one direct and one at depth two), zero execution processes, and one Artifacts module. The root agent approved this narrow edit before it was made. Test-title impact queries returned UNKNOWN because Playwright callbacks are not indexed; source-location and text searches confirmed the exact test sites. No shared mock helper changed.

## Validation

The restricted preflight failed Chromium launch and local socket bind. The same required preflight passed in the permitted environment: python3 scripts/test_preflight.py frontend-mock-e2e. The root-owned production server was healthy at 127.0.0.1:3001; baseline BUILD_ID was Ptsx_FuuVZ9wjAmw_uT-c, and the fixed candidate BUILD_ID was 6DI8-1eZOmDvXs54ejEIR.

The original production diagnostics used CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001, one worker, zero retries, and retained-on-failure traces. The first command selected cases #7, #9, and #52 and failed all three. Its attempted #8 path had an incorrect workflows/ prefix; the separate correct command for tests/e2e/artifact-preview.spec.ts:389 failed at the missing Presented Report content after refresh. Raw outputs are dev-log/03-e-production-baseline.log and dev-log/03-e-case8-production-baseline.log. #9's exact pre-fix DOM measurement is preserved in dev-log/03-e-case9-dom-probe.log.

The exact case #7/#9/#52 baseline command was:

    CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 pnpm exec playwright test tests/e2e/artifact-batched-stream.spec.ts:150 tests/e2e/artifact-table-preview.spec.ts:192 tests/e2e/workflows/artifact-visualization.spec.ts:76 --workers=1 --retries=0 --trace=retain-on-failure

The exact #8 baseline command was:

    CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 pnpm exec playwright test tests/e2e/artifact-preview.spec.ts:389 --workers=1 --retries=0 --trace=retain-on-failure

Playwright cleaned the original baseline trace ZIPs before they were copied into dev-log. The complete original failure outputs remain in the baseline logs, and the pre-fix #9 DOM measurement remains in dev-log/03-e-case9-dom-probe.log. A later supplementary diagnostic on the fixed production build temporarily restored the old assertions; its command was CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 pnpm exec playwright test tests/e2e/artifact-batched-stream.spec.ts:150 tests/e2e/artifact-preview.spec.ts:389 tests/e2e/artifact-table-preview.spec.ts:192 tests/e2e/workflows/artifact-visualization.spec.ts:76 --workers=1 --retries=0 --trace=retain-on-failure --output=../dev-log/03-e-baseline-repro-traces. It selected four tests and reported #7, #8, and #52 failing, #9 passing, in 50 seconds. This supplementary run produced trace ZIPs and error contexts for #7, #8, and #52 under dev-log/03-e-baseline-repro-traces/; those traces are not the original pre-fix captures. The old assertions were restored immediately afterward, and the accepted source/test fingerprint returned to its recorded value.

The focused #9 regression passed on BUILD_ID 6DI8-1eZOmDvXs54ejEIR: 1 passed in 4.1 seconds, shell elapsed 5 seconds. The accepted assigned-case command was:

    CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 pnpm exec playwright test tests/e2e/artifact-batched-stream.spec.ts:150 tests/e2e/artifact-preview.spec.ts:389 tests/e2e/artifact-table-preview.spec.ts:192 tests/e2e/workflows/artifact-visualization.spec.ts:76 --workers=1 --retries=0 --repeat-each=5 --trace=retain-on-failure

It passed 20/20 (five executions per case) in 55.5 seconds of Playwright time and 60 seconds wall time, with zero retries. Complete containing specs collected 18 tests under CI project defaults (one worker, up to two retries); all 18 passed in 33.0 seconds of Playwright time and 36 seconds wall time, with zero retries consumed:

    CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 pnpm exec playwright test tests/e2e/artifact-batched-stream.spec.ts tests/e2e/artifact-preview.spec.ts tests/e2e/artifact-table-preview.spec.ts tests/e2e/workflows/artifact-visualization.spec.ts

Narrow ESLint, TypeScript (tsc --noEmit), and Prettier checks passed. Accepted run outputs and exit markers are in dev-log/03-e-assigned-repeat5-attempt2.log / .exit, dev-log/03-e-related-specs-formal.log / .exit, and dev-log/03-e-case9-green.log / .exit; static-check outputs are in dev-log/03-e-eslint.log and dev-log/03-e-tsc.log. The source/test diff fingerprint recorded before the accepted repeats, after the repeats, and after restoring the temporary diagnostic is 76b84e1e9a70139aa0aa66aecef68a297b0d7dc61d7758caeecd0bd7da636fff. Playwright test files and product source were unchanged during the accepted repeat and formal runs. Documentation was updated afterward.

## Changed paths

- frontend/src/components/workspace/artifacts/artifact-file-detail.tsx
- frontend/tests/e2e/artifact-batched-stream.spec.ts
- frontend/tests/e2e/artifact-preview.spec.ts
- frontend/tests/e2e/artifact-table-preview.spec.ts
- frontend/tests/e2e/workflows/artifact-visualization.spec.ts
- docs/testing/mock-e2e-recovery-E.md
- docs/testing/mock-e2e-recovery-diagnosis.md

The E1 sub-ticket lives only in the ignored local scratch area
(`.scratch/test-system-first-batch/issues/03-E1-artifact-conflict-indicator.md`)
and is not part of this commit; its evidence is restated in the #9 row above.
