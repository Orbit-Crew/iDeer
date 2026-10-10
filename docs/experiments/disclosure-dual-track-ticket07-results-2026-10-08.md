---
id: disclosure-dual-track-ticket07-formal-results
kind: evidence
status: archived
owner: repository maintainers
scope: Formal results, scoring, cost audit, and validation evidence for disclosure dual-track ticket 07
---
# Disclosure dual-track ticket 07 formal results

**Protocol:** `disclosure-reading-v2`
**Frozen queue:** SHA-256 `592943c1e87ecec69a89a5548f870f13927a61ba2503e7ed3c4209af67f35d4c`
**Candidate manifests:** baseline `353d2227cce748a94203bb17e9ea5a1d58486e8ac12312ae38bc688198652432`; after `7914b2481c1a4e0a694c0ab9a6c2cad97e483114474827f7b73531d84eb364a7`.

## Outcome

Ticket 07 is **incomplete and does not pass the v2 gate**. The frozen queue kept its 32 slots and ordering. There are 28 valid submitted logical answers (slots 1–25 and 28–30); the fixed denominator remains 16 per candidate. Baseline has 13/16 correct (81.25%); after has 14/16 confirmed correct (87.5%), zero adjudicated incorrect, and one unresolved answer. Slot 25 meets the scored anchors but has one unresolved conditional harness-patch applicability; its per-answer `correct` value is unresolved, not false. Slots 26 and 27 are quota failures. Slots 31 and 32 are excluded from semantic scoring because their submitted answers used a changed collector fingerprint. All four unavailable or invalid slots remain in the denominator.

Each of the 28 valid answers has two independent, evidence-backed v2 reviews. A/B had six anchor disagreements: four upstream harness-patch conditions (slots 13, 14, 17, and 18), plus runtime slot 25's `RUN-C1` conditional and `RUN-AUX` auxiliary. The independent adjudicator marked the four `UP-C1` conditions and `RUN-AUX` not applicable. `RUN-C1` remains unresolved. There are zero critical errors and zero historical-authority misuse findings among the scored answers. No sample was dropped to improve the result.

The ten valid routine-task answers per candidate were used for the Markdown unique-byte median. Baseline median was 99,857.5 bytes; after median was 88,068.5 bytes, an 11.8058% reduction. This is below the frozen 30% threshold.

## Execution and cost

The cost recomputation covers 97 physical reader-session records: 30 submitted and 67 failed. Of the failures, 63 had zero read events, two had reads before quota exhaustion, and two had reads before infrastructure failure. Two of the 30 physical submissions are the collector-drifted runtime answers in slots 31–32; they are retained in all-physical cost and excluded from v2 semantic scoring. The cost tool groups retry-linked and additional diagnostic/failed dispatch records into 94 terminal logical operational groups; the 94 groups include zero-read and extra dispatch records. **94 is not the formal sample count. The formal queue has 32 frozen slots.**

The original `attempts/quota-exhausted.json` remains untouched. No further readers were dispatched after the tool-fingerprint drift was discovered. Slot 1's frozen queue mapping is after/UI/replicate 2, while its successful retry dispatch metadata says replicate 1; the linked answer is retained under slot 1 and this mismatch is an audit warning.

The read-only diagnostic run `dispatch-report-readonly-attempts.json` records all 32 diagnostic attempts as started with no stop reason (`resumed_after_slot: 1`). The separate formal queue run `dispatch-report.json` stopped on quota after slot 27 and left slots 28–32 pending. These are different runs and physical attempts, not conflicting snapshots of one dispatch. The diagnostic run does not establish that the formal queue stopped correctly. The formal answers and exclusions above are based on raw records and fingerprints; the new queue runner's public quota behavior is covered by its focused tests.

## Audit artifacts

Ignored raw records, independent grades, adjudication, cost input, and recomputable reports are under `dev-log/disclosure-dual-track/ticket07-formal/`. The A/B v2 grade files are `grades/a-v2.json` and `grades/b-v2.json`; third-party decisions are in `grades/up-c1-adjudication.json`; normalized scoring input and output are `grades/v2-score-input.json` and `grades/v2-score-report.json`. The v2 score input SHA-256 is `0b84e0af38cb4951fe64fe913afbedb75a179608776c7a827ef9269ebeaf729d`; score output is `096ea1acb71c03ed74e7ec109c984321afad4a4b3a0fadae259b6d4492cebb59`. Physical cost input and output are `cost-input-all-physical.json` and `cost-report-all-physical.json`, with SHA-256 `3c711257774922b51b62d8d24c36a96cfc265bf16fb0af350b08e356cd056354` and `6193a2d72a30c3d105e6b68bb9dc23c4ed9e3be3b7668121fb4a8e20b7279f50`. The earlier legacy-rubric judgments are invalid for v2 and are retained only as `invalid_legacy_rubric` diagnostics; they do not contribute to these scores.

The frozen model alias and CLI were `gpt-6.1-sol` and Codex CLI 0.161.0 with medium reasoning. The provider's resolved model revision was not exposed by the CLI. Formal results are not generalized to other model revisions.

## Reproduction and validation

The portable clean-restore archive is `dev-log/disclosure-dual-track/ticket07-clean-restore-20261008.tar.gz`, SHA-256 `45b3bee34c082b700d00263f6d69e665129b2fb4da449ac299cf95fec5141d88`; an identical copy is at `/tmp/ticket07-clean-restore-20261008.tar.gz`. It contains the raw records, reviews, adjudication, scoring/cost inputs and outputs, recomputation scripts, and the pinned baseline/after candidate snapshots. An independent restore into `/tmp/dual-ticket10-audit07/` rebound each cost record to the extracted candidate snapshot and ran the archived `report_disclosure_costs.py` with the current candidate's implementation. It validated the snapshot manifests and digests and returned 97 physical records and 94 terminal logical operational groups. The output is in `/tmp/dual-ticket10-audit07/cost-independent.json`; comparison with the archived output is recorded in the ticket 10 handoff. The score tool's `score_reviews(queue, records, anchor_specs)` rerun on archived `v2-score-input.json` was structurally equal to the archived score report. The extracted snapshots passed the cost tool's manifest and digest checks.

The first `backend-standard` lane completed in 1,072 seconds with 29,477 passed, 236 skipped, and one failed test: `test_runner_timeout_cleans_only_its_child_process_group`. Its 0.1-second startup timeout could expire before the fake Codex process spawned the child, so the child-PID assertion did not prove group cleanup. The lane log is `logs/test-lanes/backend-standard-20261008T155237Z-959009/run.log`; the exact assertion was at line 399 of the test and the failure summary is at lines 59441–59507. A focused rerun passed in 4.79 seconds, confirming the timing sensitivity.

The test now starts the runner asynchronously and waits for a child-PID readiness handshake before checking timeout cleanup. This aligns the assertions with the spawned-child phase and reduces the timing race; it cannot guarantee behavior under arbitrary scheduler stalls. The fake CLI and unrelated sibling remain alive beyond the timeout and communicate window, while the child marker is scheduled beyond the startup deadline. The test asserts that the child does not run and the unrelated sibling survives. The focused test passed after the handshake change in 9.57 seconds. No production code changed. A final `backend-standard` rerun is required after this test change; its result will be captured with the committed candidate evidence.
