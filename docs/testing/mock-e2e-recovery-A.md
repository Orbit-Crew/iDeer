---
id: docs-testing-mock-e2e-recovery-a
kind: evidence
status: archived
owner: test maintainers
scope: repair record for mock e2e recovery ticket 03-A (cases #10-14, #20-26, #40-41) — resource gallery product fix and capability-center, integrations, and skill-export spec repairs; all 14 cases pass five production-mode repeats
archived-reason: candidate-scoped repair record from the recovery batch (candidate based on c166617ba); the batch merged into develop at e33a103f1 — group results are the batch candidates' results, not current verification
---

# Mock E2E recovery — ticket 03-A

## Result

Ticket 03-A covers cases #10–14, #20–26, and #40–41 (14 tests). All 14 now pass in production mode with one worker, zero retries, and five repetitions (70/70, 214.87 seconds). The complete three-spec run also passed (14/14, 39.14 seconds). The test candidate was based on `c166617ba2ce8cfcb4b98688126b4d2488295fb9`. At implementation handoff, the product/test diff fingerprint is `d87e6b35f0fca8b178f409a370f3b102fa869275e503bd5b07422f5201150e77`, produced by `git diff --binary -- frontend/src/components/workspace/resources/resource-gallery.tsx frontend/tests/e2e/capability-center.spec.ts frontend/tests/e2e/integrations.spec.ts frontend/tests/e2e/skill-export.spec.ts frontend/tests/unit/components/workspace/resources/resource-gallery.test.tsx | sha256sum`. The production build reused for browser verification reported BUILD_ID `828sMqM_WSDUWYDUdQGJ7`.

The same product/test signature was verified before and after both standard-config attempts. The first attempt is not a valid product failure because the reused server was no longer listening on port 3000. Root restarted the same production build with the correct auth-disabled environment; the original standard-config command then passed. Both attempts are described below with their matching logs and JSON summaries.

## Candidate and environment binding

Implementation/review base: `c166617ba2ce8cfcb4b98688126b4d2488295fb9`. `dev-log/environment.json` snapshots `af4254571b791906485c53022b4ad572ce3047ee`; the intervening commit is docs-only, and these configuration inputs remained unchanged at the implementation base. Hashes: `backend/uv.lock` `c4f73e16090624966e694447a5bb916658c1bb2986e886d0326eeee950a11d3c`; `frontend/pnpm-lock.yaml` `849a445b1984f4eea0a68ca3ce210885f595ed36c8892447d001d5a4bb42a866`; `frontend/playwright.config.ts` `ac28d626b212577e6f674ca7d5c67a14ddfe531c07f60c4575363d809dc3a182`; `scripts/run-test-lane.sh` `f94e6449f559736ae3c423946f670a003fd7c99c36947035eaa039ccd24e59cb`. `config.yaml` and `frontend/.env` are hashed in that snapshot; their contents are excluded.

Runtime used: Python 3.13.2, Node v22.23.2, pnpm 10.26.2, Playwright 1.59.1, Chromium/Chrome for Testing 147.0.7727.15 (Playwright revision 1217). The production frontend server was launched with `DEER_FLOW_AUTH_DISABLED=1 SKIP_ENV_VALIDATION=1 pnpm exec next start --hostname 127.0.0.1`; the startup output is `dev-log/02-next-production-server-auth-disabled.log`. Browser probes used `CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000` against BUILD_ID `828sMqM_WSDUWYDUdQGJ7`. `frontend/playwright.config.ts` sets a 30,000 ms test timeout. Focused, repeat, and three-spec commands overrode workers to 1 and retries to 0. Under `CI=1`, defaults are one worker and two retries; the last standard-config run intentionally leaves those defaults in effect.

The inherited full-lane result (413 collected, 358 passed, 55 failed) remains a separate historical baseline. These focused results do not establish whether any of the original failures were order dependent.

## Evidence and current contracts

The canonical catalog routes are `/workspace/capabilities/agents`, `/workspace/capabilities/skills`, and `/workspace/capabilities/connectors`; the old `/workspace/capabilities?tab=...` URLs redirect to the agents page. The current resource route uses `ResourceGallery`, whose localized heading is `t.resources.title` (Chinese `资源`, English `Resources`). The capability root redirect is implemented in `frontend/src/app/workspace/capabilities/page.tsx`, and localized text is in `frontend/src/core/i18n/locales/zh-CN.ts` and `en-US.ts`.

The resource list contract is canonical-only under [Resource Governance v2](../decisions/2026-08-14-resource-governance-v2.md). Published skill descriptions are projected by `_skill_description` in `backend/app/gateway/routers/resources.py`; `ResourceItem.description` is optional in `frontend/src/core/skills/api.ts`. The catalog test therefore adds a narrow `/api/resources?type=skill` fixture with the published description. It does not change the shared E2E helper, whose impact was CRITICAL / 75 direct callers.

Settings deep links use the current keys `account`, `appearance`, `channels`, `memory`, `subagents`, `notification`, and `about`; tool and skill entries in the settings panel navigate to the connector and skill resource routes. The Lark integrations entry is available when the mocked CLI status is available and absent when the test explicitly returns `cli.available: false`. The default `mockLangGraphAPI` models an available Lark CLI. Accordingly case #10 now waits for the Integrations entry to become visible in that default environment, while case #21 keeps the negative assertion in the unavailable environment.

## Case classification

| Cases       | Classification from production-mode probes                                                                                                                                                                                                                          | Assertion / behavior retained                                                                                                                                                                                                                    |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| #10         | Stale route and heading, stale settings destinations, and an incomplete canonical resource-list fixture. The first standalone failure was the obsolete `能力中心` heading; after migration, a detail assertion exposed the missing description in the test fixture. | Connector route and `资源` heading; catalog cards, search, detail slug and description, community guidance; settings Integrations waits until visible in CLI-available mock, Tools and Skills are clicked and navigate to connectors and skills. |
| #11         | Stale skills URL first. After fixing the URL, the test exposed a real mobile product defect: `ResourceGallery` did not render a sidebar trigger at mobile widths.                                                                                                   | Canonical skills URL and real `Toggle Sidebar` click/navigation remain. Minimal product fix adds the shared `SidebarTrigger` on mobile.                                                                                                          |
| #12         | Stale capability root route.                                                                                                                                                                                                                                        | Canonical connectors page still shows the MCP authorization failure and independently available Lark state.                                                                                                                                      |
| #13         | Stale skills query route.                                                                                                                                                                                                                                           | Canonical skills route retains the 9-card catalog, search feedback, clear behavior, and community import guidance.                                                                                                                               |
| #14         | Stale capability root route; generic alert locator was ambiguous because both the permission message and route announcer use alert semantics.                                                                                                                       | Canonical connector route, refetch failure, filter state, and a text-qualified Admin privileges alert.                                                                                                                                           |
| #20, #22–26 | Stale `?tab=plugins` deep link; the plugins tab was removed with the old capability center.                                                                                                                                                                         | Canonical connector URL retains Lark dialog opening, clipboard fallback, close-before-settings flow, skill-pack installation, credential switching, and selected-permission registration assertions.                                             |
| #21         | Stale unsupported `settings=integrations` deep link and stale dialog assumption.                                                                                                                                                                                    | Opens Settings through the actual sidebar menu. With `cli.available: false`, asserts Integrations is hidden; case #10 verifies it appears after the available status loads.                                                                      |
| #40–41      | Stale skills query route; case #40 also expected the old “Capability Center” heading.                                                                                                                                                                               | Canonical skills route retains preview refresh/stale-content/download behavior, mobile blockers, and denied download. The modal close heading is now Resources.                                                                                  |

The product correction is separately recorded in the local ignored sub-ticket `.scratch/test-system-first-batch/issues/03-A1-mobile-resource-sidebar.md`. That ticket notes the exact product red on the migrated route before the trigger was added. A focused unit regression in `frontend/tests/unit/components/workspace/resources/resource-gallery.test.tsx` verifies the mobile trigger renders.

No test files were moved or deleted, so this ticket does not add a migration-ledger entry. The case-by-case assertion replacement map above records how the old URLs, heading, and settings assumptions now map to the live routes and behavior.

## Red and green runs

- Preflight command: `python3 scripts/test_preflight.py frontend-mock-e2e`. The restricted attempt failed at Chromium launch and socket bind; the same preflight passed in the allowed environment. Logs: `dev-log/02-preflight-current.log`, `dev-log/02-preflight-allowed.log`.
- Case #10 original production red: `CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 pnpm exec playwright test tests/e2e/capability-center.spec.ts -g 'catalog navigation, search, details, and migrated settings' --workers=1 --retries=0 --reporter=line --trace=retain-on-failure`; 1 failed at the obsolete heading assertion. Log: `dev-log/03-a-case10-red.log`.
- Cases #11–14, #20–26, #40–41 initial production baseline; the selector names all 13 titles explicitly:

  ```sh
  CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 pnpm exec playwright test tests/e2e/capability-center.spec.ts tests/e2e/integrations.spec.ts tests/e2e/skill-export.spec.ts --grep 'the skills catalog fits a mobile viewport|MCP access errors preserve the independently available Lark integration|Community search gives feedback and clearing it restores import guidance|plugin filters remain usable after an MCP refetch fails|opens the Lark plugin from a capability deep link|hides the integrations entry in a deployment without the Lark CLI|falls back when copying a Lark authorization link without the Clipboard API|closes the plugin dialog before opening general settings|can install the Lark integration skill pack from the capability center|can switch the Lark app by entering new credentials|keeps selected permissions when re-registering the Lark app|custom export previews, handles stale content and downloads only after refresh|mobile manifest blockers are readable and cannot download' --workers=1 --retries=0 --reporter=line --trace=retain-on-failure
  ```

  Result: 13 selected, 13 failed, exit 1. The old capability route redirected to agents and the old settings key was ignored. Neither this run's elapsed time nor the standalone #10 red time was recorded; both are unavailable, not inferred. Evidence: `dev-log/03-a-assigned-red.log`, `dev-log/03-a-assigned-red.exit`, `dev-log/03-a-case10-red.log`, `dev-log/03-a-case10-red.exit`.

- After route migration, probes showed #10's missing published description in the fixture, #14's strict generic alert match, and #11's absent mobile trigger. The mobile failure was recorded before the product edit; the route-contract and focused-green logs are `dev-log/03-a-route-contract-green.log` and `dev-log/03-a-focused-product-green.log`.
- First 70-run repeat batch produced 67 passes and 3 failures, all repeat executions of #10. The obsolete assertion expected no Integrations entry, while the default mock models an available Lark CLI. A single pass during initial loading was timing-dependent. This run overlapped the test assertion edit, so it is diagnostic only and not acceptance for any frozen candidate. Log: `dev-log/03-a-all-14-repeat5.log`.
- Final selected batch used this exact command and selector (all 14 exact assigned titles, five executions each):

  ```sh
  CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 pnpm exec playwright test tests/e2e/capability-center.spec.ts tests/e2e/integrations.spec.ts tests/e2e/skill-export.spec.ts --grep 'catalog navigation, search, details, and migrated settings|the skills catalog fits a mobile viewport|MCP access errors preserve the independently available Lark integration|Community search gives feedback and clearing it restores import guidance|plugin filters remain usable after an MCP refetch fails|opens the Lark plugin from a capability deep link|hides the integrations entry in a deployment without the Lark CLI|falls back when copying a Lark authorization link without the Clipboard API|closes the plugin dialog before opening general settings|can install the Lark integration skill pack from the capability center|can switch the Lark app by entering new credentials|keeps selected permissions when re-registering the Lark app|custom export previews, handles stale content and downloads only after refresh|mobile manifest blockers are readable and cannot download' --workers=1 --retries=0 --repeat-each=5 --reporter=line --trace=retain-on-failure
  ```

  Result: 70 selected executions passed, exit 0, 214.87 seconds. Logs: `dev-log/03-a-repeat5-current.log`, `dev-log/03-a-repeat5-current.exit`, and `dev-log/03-a-repeat5-time.log`.

- Final complete three-spec focused run: `CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 pnpm exec playwright test tests/e2e/capability-center.spec.ts tests/e2e/integrations.spec.ts tests/e2e/skill-export.spec.ts --workers=1 --retries=0 --reporter=line --trace=retain-on-failure`; all 14 tests passed, exit 0, Playwright duration 37.9 seconds / wall 39.14 seconds. Logs: `dev-log/03-a-three-specs-full.log`, `dev-log/03-a-three-specs-full.exit`, `dev-log/03-a-three-specs-time.log`.
- Static and focused checks: Prettier passed; ESLint exit 0 with one existing warning at `resource-gallery.test.tsx:122` (`consistent-type-imports`); `pnpm exec tsc --noEmit` passed; focused Vitest passed 1 file / 6 tests.

The service lifecycle matters for reproduction: the auth-disabled Next production service ran on `127.0.0.1:3000` while the selected repeat and three-spec focused batches ran. It was not listening at the time of the first standard-config attempt with `PLAYWRIGHT_SKIP_WEB_SERVER=1`, which failed all 14 at `page.goto` with `net::ERR_CONNECTION_REFUSED` (58.84 seconds, exit 1); see `dev-log/03-a-formal-config.log` and `.json`. The run used the config defaults under `CI=1`: one worker, two retries, 30-second per-test timeout. This environment-induced result is not a source regression.

Root restarted the same build with `DEER_FLOW_AUTH_DISABLED=1 SKIP_ENV_VALIDATION=1 pnpm exec next start --hostname 127.0.0.1` (session 53051, BUILD_ID unchanged). The original default-config three-spec command was then rerun without worker/retry overrides:

```sh
CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 pnpm exec playwright test tests/e2e/capability-center.spec.ts tests/e2e/integrations.spec.ts tests/e2e/skill-export.spec.ts --reporter=line --trace=retain-on-failure
```

Result: all 14 passed, Playwright duration 28.7 seconds / wall 29.82 seconds, exit 0. Effective values from `CI=1` and `frontend/playwright.config.ts`: workers 1, retries 2, test timeout 30 seconds. Source signature before/after was `d87e6b35f0fca8b178f409a370f3b102fa869275e503bd5b07422f5201150e77`, HEAD was `c166617ba2ce8cfcb4b98688126b4d2488295fb9`. Logs: `dev-log/03-a-formal-config-server-ready.log`, `.json`. Root retains the service in session 53051; this agent did not stop or modify it.

## Timed reconstruction of the original A assertions

The initial red logs do not contain elapsed times. To recover measurable diagnostic evidence without inventing those times, root reconstructed the three unchanged test files from ticket-start commit `c166617ba2ce8cfcb4b98688126b4d2488295fb9` as temporary sibling specs. This supplemental run used the current production build `828sMqM_WSDUWYDUdQGJ7`, including the mobile trigger fix. It therefore proves that the original route/assertion failures still reproduce, and does not replace the original pre-product-fix red evidence. The current implementation and acceptance test files were unchanged. The temporary copies were removed after the run.

Reconstruction and test command, from the worktree root:

```sh
git show c166617ba:frontend/tests/e2e/capability-center.spec.ts > frontend/tests/e2e/diagnostic-red-capability-center.spec.ts
git show c166617ba:frontend/tests/e2e/integrations.spec.ts > frontend/tests/e2e/diagnostic-red-integrations.spec.ts
git show c166617ba:frontend/tests/e2e/skill-export.spec.ts > frontend/tests/e2e/diagnostic-red-skill-export.spec.ts
cd frontend
CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 PLAYWRIGHT_JSON_OUTPUT_NAME=../dev-log/03-a-red-timed-results.json pnpm exec playwright test tests/e2e/diagnostic-red-capability-center.spec.ts tests/e2e/diagnostic-red-integrations.spec.ts tests/e2e/diagnostic-red-skill-export.spec.ts --workers=1 --retries=0 --reporter=line,json --trace=retain-on-failure
rm tests/e2e/diagnostic-red-capability-center.spec.ts tests/e2e/diagnostic-red-integrations.spec.ts tests/e2e/diagnostic-red-skill-export.spec.ts
```

Result: 14 collected, 14 failed, zero skipped or retries, exit 1, 199.58 seconds wall / 198.569 seconds Playwright. Effective timeout remained 30 seconds; four cases exhausted that existing timeout at obsolete navigation or dialog steps. Per-case duration below comes directly from each JSON result's `duration` field in milliseconds divided by 1000, not from file timestamps. Logs: `dev-log/03-a-red-timed.log`, `dev-log/03-a-red-timed.json`, `dev-log/03-a-red-timed-results.json`. Environment and dependency/configuration hashes are the same ones recorded above. The reconstructed original failures are separate from the final frozen 70/70 and default-config 14/14 green evidence.

| Case | Observed status | Duration, seconds |
| ---- | --------------- | ----------------- |
| #10  | failed          | 6.540             |
| #11  | failed          | 6.129             |
| #12  | failed          | 6.884             |
| #13  | failed          | 6.400             |
| #14  | failed          | 6.143             |
| #20  | failed          | 6.348             |
| #21  | failed          | 6.798             |
| #22  | timedOut        | 30.262            |
| #23  | failed          | 6.461             |
| #24  | failed          | 6.069             |
| #25  | failed          | 6.094             |
| #26  | timedOut        | 30.132            |
| #40  | timedOut        | 30.106            |
| #41  | timedOut        | 30.081            |
