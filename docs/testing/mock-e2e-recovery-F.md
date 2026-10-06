---
id: docs-testing-mock-e2e-recovery-f
kind: evidence
status: archived
owner: test maintainers
scope: repair record for mock e2e recovery ticket 03-F (cases #1 and #38) — a mobile sidebar synchronization failure and a removed static suggestion row, both classified with no product source change needed
archived-reason: candidate-scoped repair record from the recovery batch (ticket start a50dd8de0); the batch merged into develop at e33a103f1 — group results are the batch candidates' results, not current verification
---

# Mock E2E recovery: mobile and sidebar cases

Ticket 03-F investigated cases #1 and #38 from the production-mode mock E2E
baseline. Both are classified. Case #1 was an intermittent test synchronization
failure while measuring a visible mobile sidebar trigger. Case #38 expected a
static suggestion row that the approved current experience removes. No product
source change was needed.

## Candidate and environment

- Ticket-start HEAD: `a50dd8de0ea151be5d62e329d4fc43e936e4bfd2`.
- Production server: root-owned `http://127.0.0.1:3001`, HTTP 200, BUILD_ID
  `6DI8-1eZOmDvXs54ejEIR`.
- The required `python3 scripts/test_preflight.py frontend-mock-e2e` first
  failed in the restricted environment because Chromium could not launch and
  local socket bind returned `Operation not permitted` (exit 1). The same
  command passed in the permitted environment: Chromium launch and local socket
  bind both succeeded (exit 0). Captured output is in ignored
  `dev-log/03-F-preflight-allowed.log` and `.exit`.
- Fresh GitNexus status was `up-to-date`, indexed/current commit matched the
  ticket-start HEAD, runner identity was current, and incomplete reasons were
  empty. Exact impact on `File:frontend/tests/e2e/agent-chat.spec.ts` and
  `File:frontend/tests/e2e/sidebar.spec.ts`, upstream with tests included, was
  `risk: UNKNOWN`, zero callers, zero affected processes/modules. Exact test
  titles were not graph symbols. Text search confirmed these existing tests
  are discovered by Playwright's `testDir`; no production symbol was changed.

## Case classifications

**Case #1, mobile agent welcome keeps the sidebar trigger clickable.** The
current test first waited for visibility and then sampled `boundingBox()` once.
In the diagnostic five-repeat run, four executions completed the pointer hit
test, performed a real `page.mouse.click`, and opened the mobile drawer. One
execution got `null` from the one-shot geometry read before attempting the
click. Its Playwright snapshot still showed the visible “Toggle Sidebar”
button. No evidence showed that the trigger was covered or that its click
failed. The confirmed classification is an intermittent test synchronization
failure at geometry sampling; the specific render transition that produces a
null box was not established. The test now retries a positive, nonzero geometry
assertion, then checks the pointer target, clicks with Playwright's mouse, and
asserts the drawer is visible. It passed 5/5 after the change. This does not
establish order dependence.

**Case #38, mobile welcome layout and desktop sidebar entries.** The baseline
asserted that `[data-slot='suggestions-list']` was visible. The approved
frontend experience removes the static suggestion row while keeping scenario
and Expert quick entries. The failure snapshot showed the welcome title,
scenario tabs, quick entries, composer, and disclaimer, with no suggestion
row. The test now selects the “日常办公” scenario and the “办公文档” Expert
entry, then checks that task entries appear. It also checks the composer and
scenario tabs fit the mobile viewport, checks for document-level horizontal
overflow after the interaction, and verifies the desktop navigation links and
absence of the redirect-only `/workspace/agents` link. The test passed 5/5.

## Shared Mock fixture conclusion

The completed groups do not establish a common shared-Mock defect. Case #1 is
a local geometry-sampling race in its test, case #38 is an obsolete UX
expectation, and D's #39/#47 remain unreproduced without a common fixture or
request-state cause. Ticket 03-F0 closes without a shared fixture edit.

## Validation

The first current-candidate diagnostic used the root-owned production server:

```text
CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 pnpm exec playwright test tests/e2e/agent-chat.spec.ts tests/e2e/sidebar.spec.ts -g 'mobile agent welcome keeps the sidebar trigger clickable|mobile welcome layout stays within viewport and desktop sidebar shows the entries' --workers=1 --retries=0 --reporter=line --trace=retain-on-failure
```

It selected 2 tests, exited 1, and took 20.49 seconds. Case #1 passed. Case #38
failed at the absent static suggestion locator, before its overflow and desktop
assertions. A diagnostic run of both cases with `--repeat-each=5` selected 10
tests and exited 1: case #1 passed 4/5 and case #38 failed 5/5 at that same
locator. The shell wall time was not captured; Playwright reported 1.5 minutes.
Raw output is `dev-log/03-F-baseline-repeat5.log` with exit code in the adjacent
`.exit` file.

The first test-only correction added an explicit geometry-retry timeout. The
Standards review caught that this violated ticket 03-F's no-new-timeout rule.
The explicit option was removed, the focused case was rerun, and all acceptance
results below use the timeout-free candidate. Earlier five-repeat results on
the explicit-timeout candidate are superseded.

After removing the explicit timeout, focused #1 passed 1/1 (Playwright 2.2
seconds, command wall time 2.83 seconds). Prettier and ESLint checks passed:

```text
pnpm exec prettier --check tests/e2e/agent-chat.spec.ts tests/e2e/sidebar.spec.ts
pnpm exec eslint tests/e2e/agent-chat.spec.ts tests/e2e/sidebar.spec.ts
```

Their captured output is in `dev-log/03-F-final-no-timeout-prettier.log` and
`dev-log/03-F-final-no-timeout-eslint.log` (both exit 0).

The five-repeat assigned-case command was:

```text
CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 pnpm exec playwright test tests/e2e/agent-chat.spec.ts tests/e2e/sidebar.spec.ts -g 'mobile agent welcome keeps the sidebar trigger clickable|mobile welcome layout stays within viewport and desktop sidebar shows the entries' --workers=1 --retries=0 --repeat-each=5 --reporter=line
```

The final timeout-free run exited 0 in 18.55 seconds (Playwright 17.9 seconds):
10/10 passed, with zero retries. The full related specs ran in CI formal
configuration:

```text
CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 pnpm exec playwright test tests/e2e/agent-chat.spec.ts tests/e2e/sidebar.spec.ts --reporter=line
```

It exited 0 in 25.11 seconds (Playwright 24.4 seconds): 23/23 passed with one
worker and no retry executions. Final logs and exits are under ignored
`dev-log/03-F-final-no-timeout-repeat5.*` and
`dev-log/03-F-final-no-timeout-related-specs.*`.

The changed test-file SHA-256 fingerprints at the frozen run were:

- `frontend/tests/e2e/agent-chat.spec.ts`:
  `a5223d7a4062bb352fd2992e7049e3a3032ebba5551665b51f052dd4ce4c103f`
- `frontend/tests/e2e/sidebar.spec.ts`:
  `131ce3967d772db78ed47df917bcdf9372170682a4325d8444a4a12c2565b304`

The frozen test diff SHA-256 was
`e701ad69be71f42b805b3490242f6b2a6cfb8c52ffab2a7bf6ba8fa72d4d57ac`.
Both cases preserve actual user-visible behavior checks. Independent review,
the complete graph-change gate, and root-owned broader lanes remain pending.
