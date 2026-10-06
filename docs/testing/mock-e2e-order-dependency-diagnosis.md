---
id: docs-testing-mock-e2e-order-dependency-diagnosis
kind: evidence
status: archived
owner: test maintainers
scope: T2 order-dependency diagnosis for the mock e2e lane (first batch ticket 03) — single, predecessor, and reduced-prefix probes over the registered historical candidates found no stable order-only failure; T2 incomplete and T3 blocked
archived-reason: candidate-scoped diagnosis record from worktree test-system-first-batch; the recovery batch closed its follow-up with per-case classification and no order-dependency claim survives — see mock-e2e-recovery-diagnosis.md
---

# Mock E2E order-dependency diagnosis (T2)

## Outcome

T2 is **incomplete** and T3 remains **blocked**. The initial active-delete target fails without a preceding test, so it cannot demonstrate order dependence. The registered historical candidates were probed in their existing order: settings model sync, settings sync, sidebar, skill export, thread archive, thread delete, then thread history. Every selected historically failing candidate failed alone. The one candidate that passed alone (thread-history message ordering) also passed after its immediate history predecessor and after the reduced historical prefix. No stable order-only failure, minimal causal prefix, or contamination source was established. No test, product behavior, mock reset API, or formal configuration was changed.

## Environment and method

- Worktree: `/home/neowyh/code/AgentPlatform/.worktrees/test-system-first-batch`; branch `fix/test-system-first-batch`; ticket start and review baseline `0f509e95c1d159436b103a928ccbe6a47bff7301`; batch branch start `a1bb73afee6a0e3b1683deb1b326276fe3dda37f`.
- `python3 scripts/test_preflight.py frontend-mock-e2e`: restricted environment exit 1 (Chromium launch and local socket denied); same command in the permitted local environment exit 0 (Chromium and socket ready). Browser probes below ran in the permitted environment.
- Locked dependencies were already installed: Node `v22.23.2`, pnpm `10.26.2`. Formal `config.yaml`, `frontend/.env`, lockfile, Playwright config, workers and retry settings were not modified. Configuration hashes from the environment record: `config.yaml` `89516072f7ee914e7caafcf50fe96e41c128d1f1d7f6d1664288248721dc2098`; `frontend/.env` `b0dae7d39a2134a6459986bbadb9801b3d307fe354547a58577457e67fb36184`; `pnpm-lock.yaml` `849a445b1984f4eea0a68ca3ce210885f595ed36c8892447d001d5a4bb42a866`.
- Each probe used a fresh Playwright-managed Next dev server, Chromium, `--workers=1 --retries=0 --trace=retain-on-failure`; no backend gateway was running, so the dev server logged proxy `ECONNREFUSED 127.0.0.1:8001`. This matches the recorded offline placeholder environment. Next dev appended its generated agent-rules block to `frontend/AGENTS.md`; after the server stopped that exact generated block was removed, retaining the pre-existing guidance.
- Failed standalone probes did not retain whole-command elapsed measurements in the command wrapper; their completed Playwright summaries, exact exits and selected test counts are captured below. The two passing history probes reported `17.5s` and `34.7s`; the reduced historical-prefix batch reported `4.3m`. None of these runs hung or ended without a summary.

## Probe results

Entries 1–10 below were run from `frontend/`; each includes its complete command. Elapsed time is listed as unrecorded when the shell wrapper and failed Playwright summary did not expose it.

| Order | Exact command | Result and elapsed | Observed failure or consequence |
| --- | --- | --- | --- |
| 1 | `CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/thread-delete-confirm.spec.ts -g 'cleanup failure keeps active chat deletion retryable after the row disappears' --workers=1 --retries=0 --repeat-each=5 --trace=retain-on-failure` | exit 1; 5/5 failed; elapsed unrecorded | One navigation hit the 30s test timeout; remaining repeats failed expected navigation to `/workspace/chats/new` (landed on chat `...902`); one also hit a strict locator collision with the Next dev overlay. This solo failure cannot establish order dependence. The first invocation used `tee` and masked its shell exit; the same command was repeated without `tee` and confirmed exit 1. |
| 2 | `CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/settings-model-sync.spec.ts -g 'automatic model fallback cannot overwrite a slowly loaded account preference' --workers=1 --retries=0 --trace=retain-on-failure` | exit 1; 1 failed; elapsed unrecorded | Expected visible `Model A` button was absent. |
| 3 | `CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/settings-sync.spec.ts -g 'account notification setting survives clearing browser storage' --workers=1 --retries=0 --trace=retain-on-failure` | exit 1; 1 failed; elapsed unrecorded | Expected `x-expected-user-id=00000000-0000-0000-0000-000000000025`, received `e2e-user`; subsequent interaction saw a closed page. |
| 4 | `CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/sidebar.spec.ts -g 'mobile welcome layout stays within viewport and desktop sidebar shows the entries' --workers=1 --retries=0 --trace=retain-on-failure` | exit 1; 1 failed; elapsed unrecorded | `[data-slot='suggestions-list']` was absent. |
| 5 | `CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/skill-export.spec.ts -g 'custom export previews, handles stale content and downloads only after refresh' --workers=1 --retries=0 --trace=retain-on-failure` | exit 1; 1 failed; elapsed unrecorded | `View details public-demo` button did not appear before the 30s test timeout. |
| 6 | `CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/thread-archive.spec.ts -g 'archive keeps the open conversation, supports undo and restores from the archive' --workers=1 --retries=0 --trace=retain-on-failure` | exit 1; 1 failed; elapsed unrecorded | Archived chat remained in the sidebar (expected count 0, observed 1). |
| 7 | `CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/thread-history.spec.ts -g 'keeps rendered messages ordered when the latest history page advances' --workers=1 --retries=0 --trace=retain-on-failure` | exit 0; 1 passed; **17.5s** | Only standalone selected candidate that passed. |
| 8 | `CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/thread-history.spec.ts -g 'retrying deletion of the active newly created chat returns to the new chat screen' --workers=1 --retries=0 --trace=retain-on-failure` | exit 1; 1 failed; elapsed unrecorded | Expected `Failed to delete conversation` notification did not appear. |
| 9 | `CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/thread-archive.spec.ts -g 'active list includes legacy chats beyond a full page of archived chats' --workers=1 --retries=0 --trace=retain-on-failure` | exit 1; 1 failed; elapsed unrecorded | `Legacy chat` row was absent. |
| 10 | `CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/thread-history.spec.ts -g 'keeps a thousand-turn history DOM bounded while preserving navigation|keeps rendered messages ordered when the latest history page advances' --workers=1 --retries=0 --trace=retain-on-failure` | exit 0; 2 passed; **34.7s** | Historical immediate predecessor plus target both passed in registered order; this did not reproduce after the nearest same-file predecessor. |

The exact command for the initial target was:

```bash
CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/thread-delete-confirm.spec.ts -g 'cleanup failure keeps active chat deletion retryable after the row disappears' --workers=1 --retries=0 --repeat-each=5 --trace=retain-on-failure
```

The exact reduced historical-prefix command, in actual registered historical order, was:

```bash
CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test tests/e2e/settings-model-sync.spec.ts tests/e2e/settings-sync.spec.ts tests/e2e/sidebar.spec.ts tests/e2e/skill-export.spec.ts tests/e2e/thread-archive.spec.ts tests/e2e/thread-delete-confirm.spec.ts tests/e2e/thread-history.spec.ts -g 'normal thread effort selection preserves the account model|normal thread mode selection preserves the account model|agent thread effort selection preserves the account model|agent thread mode selection preserves the account model|custom agent automatic default does not become an account preference|automatic model fallback cannot overwrite a slowly loaded account preference|account notification setting survives clearing browser storage|mobile welcome layout stays within viewport and desktop sidebar shows the entries|custom export previews, handles stale content and downloads only after refresh|archive keeps the open conversation, supports undo and restores from the archive|active list includes legacy chats beyond a full page of archived chats|opening and dismissing deletion never sends a delete request|confirmation waits for deletion, prevents dismissal, and permits retry after failure|cleanup failure keeps active chat deletion retryable after the row disappears|keeps rendered messages ordered when the latest history page advances' --workers=1 --retries=0 --trace=retain-on-failure
```

That batch selected and started **15 tests using one worker**; the runner's numbered failure output lists actual execution order for the 12 failures: six settings-model-sync cases, settings-sync, sidebar, skill-export, two thread-archive cases, and the active-delete target. Three selected cases passed (the opening/dismissal and confirmation/retry deletion tests preceding the target, plus the final history-order target). It exited 1 with **12 failed and 3 passed in 4.3m**. The final history-order target passed despite the preceding selected historical candidates; all solo-failing representatives remained failed. It therefore produced no target that passes alone and fails after the prefix. Exact Playwright output was kept in the ignored session file `dev-log/t2-historical-prefix-to-thread-history.log` while preparing this versioned report; the report contains the durable outcome and relevant assertions, without credentials or auth headers.

## Historical basis and next work

Candidate order and historical failure references came from `dev-log/2026-10-02-mock-e2e-followup-ledger.md` and its referenced `/tmp/mock-e2e-final.log` and `/tmp/mock-e2e-noagent.log`. Those records called the bucket “suspected order dependency”; their aggregate runs do not prove causation. Current standalone results reclassify selected failures as independently failing candidates on this checkout. The order-history target remaining green under the reduced prefix is negative evidence against that prefix, not proof that every Mock E2E test is isolated.

Do not use the active-delete failure as a dependent target or add a prefix to it. T2 can resume when a registered candidate is shown to pass alone in this environment; then test its actual historical preceding sequence and reduce the prefix while preserving the target pass-to-fail transition. Until a stable repro and causal state/request evidence exist, keep T2 incomplete and T3 blocked. If a future diagnosis points to product behavior, propose that separately from this ticket.

## T3 prerequisite audit

Reviewed for ticket 03 on 2026-10-03 at worktree HEAD `4a2b2c2e40f0a78a03cc3f2838ed8adf76694af0`; the ticket review base is this implementation-start HEAD. The batch branch began at `a1bb73afee6a0e3b1683deb1b326276fe3dda37f`. T1 is complete: [the result-consistency record](test-lane-result-consistency.md) documents the red/green subprocess regressions, focused runner and evidence-writer passes, Ruff, shell syntax, and inventory checks. T2 is not complete: its probe table shows the proposed active-delete target failed 5/5 alone, and the only standalone-green historical candidate passed both after its immediate predecessor and after the reduced prefix. The report contains no stable pass-alone/fail-after-prefix transition or causal state/request evidence.

Decision: the T1 prerequisite is accepted, but the required T2 reproduction and confirmed root cause are absent. Ticket 03 remains blocked. No implementation test, source edit, or browser rerun is warranted on this candidate; any failure fix would be speculative. Resume only after T2 supplies a current-candidate stable reproduction and causal evidence.
