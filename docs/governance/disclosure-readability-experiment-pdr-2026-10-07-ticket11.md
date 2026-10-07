---
id: disclosure-readability-ticket11-pdr-2026-10-07-16cc740f
kind: evidence
status: current
owner: repository maintainers
scope: integrated verdict for the frozen 32-slot progressive-disclosure reading experiment
last-verified: 2026-10-08
verified-against: baseline candidate 867f6709642854721f209a15e362d79a96b3b489; after candidate 16cc740f839876b7b7581a7cbbaf9a318d4c14ac
---

# 票11：正式阅读实验汇总与验收裁决

## Verdict

**Formal acceptance: FAIL.** This report evaluates exactly 32 frozen logical slots (16 per candidate), not the 39 actual attempts. The after candidate has 14/16 correct answers; slot 03 is incorrect and slot 18 has no submitted answer. Critical errors and historical-authority misuse are both 0. The correctness gate requires all 16/16 after answers correct, so it fails. The routine-task pooled unique-byte median increased 16.12% against baseline, failing the required reduction of at least 30%. The routine-task time gate is **incomplete**: slot 18 has no answer-submission duration, so the required ten-session median cannot be calculated without substituting a different interval or dropping a failed slot. The available nine after submission durations have a descriptive median of 92.327 seconds; this is not the gate result. The missing answer, unavailable backend model revision, and locally ignored raw archive remain material limitations. No sample was redrawn, no threshold was changed, and no old score was overwritten.

The reporting implementation and audit are delivered. The separate PR `pr-standard` validation checkbox remains pending until the integration owner records its actual result; this document does not imply that gate passed.

## Frozen inputs and reproducibility

- Experiment: `pdr-2026-10-07-16cc740f`.
- Frozen manifest file `dev-log/disclosure-readability-recovery/ticket08/archive/manifests/frozen-experiment-pdr-2026-10-07-16cc740f.json`, SHA-256 `0cc825816c9f134ccfbd9ea47d5f1722eb7c0ba1c0b91024b1e69f6c995570b1`.
- Frozen queue `dev-log/disclosure-readability-recovery/ticket08/archive/manifests/frozen-queue-pdr-2026-10-07-16cc740f.csv`, SHA-256 `54458c060c267c2272b69cd2ec5330e95d5cb83c13d200d8c746f6a1c3dba1fe`.
- Baseline candidate: commit `867f6709642854721f209a15e362d79a96b3b489`, tree `f2309f2e6c2fb7b64bfe59c5ace9523b6c742838`, canonical manifest SHA-256 `ea6d866455937115b99f9bcb9d688923f37bd20cac967e34f8d79030bbcb924a`.
- After candidate: commit `16cc740f839876b7b7581a7cbbaf9a318d4c14ac`, tree `6f1c4e340758b92ec8e8d3c165185a98a832253f`, canonical manifest SHA-256 `45e45e0e61b15f812a767978e8354b17ce49bb509c28ffbb703d79811d01303b`.
- Both ticket reports verified the candidate manifest, prompts, catalog and formal tool configuration against the frozen records. All actual sessions used Codex CLI `0.160.0`, requested model alias `gpt-6.1-sol`, medium reasoning; source catalog file SHA-256 `9ce669a7c68b7b64004832d0479fa78563f008d4d2b8cc4e26bfc09346d0f33d`, effective catalog canonical SHA-256 `430739c8d3b67555f5c09c7285892249c3efd922f2ebe67430478df7b8f51cf8`, formal tool-config SHA-256 `da55cd757919611c8577414c449a548e3c3ec52b3c4f8955596e15d4ab2cd078`.
- The resolved backend model revision is unavailable. This prevents a strict model-comparability claim and is not treated as a pass.

The raw answers, traces, per-attempt configs, audit inputs and grading records are retained under the local ignored `dev-log/disclosure-readability-recovery/` archive. They have no external durable copy. Hashes establish identity only; a clean checkout cannot reproduce the original read events or independently recompute their interval unions. The tracked reports and this summary preserve findings and recomputation instructions, not a substitute raw archive.

## Completeness, isolation, retries and grading audit

All 32 frozen logical slots were dispatched once. There are 30 terminal submissions and two terminal failures: after Chat slot 18 and baseline Upstream slot 24. Across both tickets there were 39 actual attempts: ticket09 had 23 (19 submitted, 4 failed) and ticket10 had 16 (11 submitted, 5 failed). Seven associated retries were started within the frozen per-slot retry limit. Slot 18 and slot 24 each ended after their allowed retry failed. A typo/preflight failure before a model session in ticket09 and a rejected retry launch while a prior record remained `started` in ticket10 did not start sessions and are not attempts; their traces remain retained. Wrong answers were never redrawn.

Every submitted answer received independent A/B grading. Nine slots had real initial disagreements and received third adjudication: ticket09 slots 01, 03, 05, 12, 16, 17 and 20; ticket10 slots 25 and 28. All nine were resolved; unresolved disagreements are zero. Initial grades, evidence, and third decisions remain in the local archive. In particular, the two History disagreements were resolved by accepting the baseline's equivalent `Task documentation map` plus decision index as a valid route; the after-only filename `task-routing.md` was not required. The failed slots have no semantic answer grade.

The sessions first read the full root `AGENTS.md` and used only the pinned candidate read/search/submit tools. Audits found no external help or contamination and zero collector-forbidden evaluation-material returns. “Forbidden evaluation material” means rubric, scorer, and grading fixtures. The 67 governance fingerprint documents are ordinary candidate-readable documentation and are not collector-forbidden. Reader overlap was limited to three concurrent sessions, with retry and reader-process checks retained. The ticket10 dispatch ledger is partly retrospective: it records run IDs, queue slots, runner execution handles and file-time evidence, but no host OS PID was exposed. The ticket09 initial slot 01 ledger row was reconstructed from retained runner output and run-id timestamp; the evidence and limitation are disclosed in its report.

The frozen runner has a known failure mode: it can read a collector JSON file while the collector is writing it, causing truncated-JSON/`JSONDecodeError` failures. The observed failures appear as workspace-load failure in ticket09 and protocol/Broken pipe failures in ticket10. Frozen code was not changed during collection. Repair and a fresh, separately frozen experiment belong to next work; this audit did not add retries beyond the cap.

## Per-slot final verdict

The values below describe each logical slot's terminal attempt. `failure clock` is elapsed from the collector's first successful content read through failed protocol close, not answer-submission time. A failed slot has no answer, correctness grade, or formal submission duration.

| Slot | Candidate / task / rep | Final status | Correct | Critical / history misuse | Seconds | Unique UTF-8 bytes |
| ---: | --- | --- | --- | --- | ---: | ---: |
| 01 | baseline / UI / 1 | submitted | no | 0 / 0 | 41.777 | 74,517 |
| 02 | after / UI / 1 | submitted | yes | 0 / 0 | 39.118 | 60,083 |
| 03 | after / Chat / 1 | submitted | no | 0 / 0 | 94.812 | 177,533 |
| 04 | baseline / Chat / 1 | submitted | no | 1 / 0 | 81.511 | 143,446 |
| 05 | baseline / Knowledge / 1 | submitted | no | 0 / 0 | 95.089 | 95,279 |
| 06 | after / Knowledge / 1 | submitted | yes | 0 / 0 | 111.798 | 228,878 |
| 07 | after / Permissions / 1 | submitted | yes | 0 / 0 | 92.327 | 211,683 |
| 08 | baseline / Permissions / 1 | submitted | yes | 0 / 0 | 84.893 | 226,736 |
| 09 | baseline / Tests / 1 | submitted | no | 0 / 0 | 56.521 | 171,516 |
| 10 | after / Tests / 1 | submitted | yes | 0 / 0 | 79.561 | 176,759 |
| 11 | after / Tests / 2 | submitted | yes | 0 / 0 | 72.157 | 175,432 |
| 12 | baseline / Tests / 2 | submitted | no | 0 / 0 | 75.249 | 240,308 |
| 13 | baseline / Permissions / 2 | submitted | yes | 0 / 0 | 65.316 | 159,848 |
| 14 | after / Permissions / 2 | submitted | yes | 0 / 0 | 105.091 | 209,148 |
| 15 | after / Knowledge / 2 | submitted | yes | 0 / 0 | 94.350 | 155,592 |
| 16 | baseline / Knowledge / 2 | submitted | no | 0 / 0 | 78.350 | 116,863 |
| 17 | baseline / Chat / 2 | submitted | yes | 0 / 0 | 72.656 | 181,696 |
| 18 | after / Chat / 2 | failed; no answer | unscorable | 0 / 0 | 4.705 failure clock | 36,727 |
| 19 | after / UI / 2 | submitted | yes | 0 / 0 | 56.524 | 88,186 |
| 20 | baseline / UI / 2 | submitted | no | 0 / 0 | 52.465 | 81,638 |
| 21 | baseline / Runtime / 1 | submitted | yes | 0 / 0 | 115.301 | 225,497 |
| 22 | after / Runtime / 1 | submitted | yes | 0 / 0 | 105.809 | 247,914 |
| 23 | after / Upstream / 1 | submitted after retry | yes | 0 / 0 | 144.562 | 139,912 |
| 24 | baseline / Upstream / 1 | failed; no answer | unscorable | 0 / 0 | 154.802 failure clock | 77,008 |
| 25 | baseline / History / 1 | submitted | no | 0 / 0 | 132.395 | 119,892 |
| 26 | after / History / 1 | submitted after retry | yes | 0 / 0 | 120.056 | 142,992 |
| 27 | after / History / 2 | submitted | yes | 0 / 0 | 89.770 | 122,412 |
| 28 | baseline / History / 2 | submitted after retry | no | 0 / 0 | 89.981 | 112,911 |
| 29 | baseline / Upstream / 2 | submitted | yes | 0 / 0 | 63.624 | 108,670 |
| 30 | after / Upstream / 2 | submitted | yes | 0 / 0 | 130.115 | 121,918 |
| 31 | after / Runtime / 2 | submitted | yes | 0 / 0 | 82.838 | 184,688 |
| 32 | baseline / Runtime / 2 | submitted | yes | 0 / 0 | 99.044 | 268,707 |

The two failed clocks above are recomputed from the final raw collector records as `closed_monotonic - started_monotonic`. Slot 18: `249745.192073124 - 249740.486971534 = 4.705` seconds. Slot 24 is its second and final attempt: `264935.031377499 - 264780.229202070 = 154.802` seconds. Slot 24's first attempt took 99.841 seconds, but it is not the terminal logical-slot reading and is excluded from the table. No failed record was assigned a fabricated answer, submission time, or semantic grade.

## Eight task metrics

Each pair below reports correct submitted answers / two logical slots, then the median seconds and median unique bytes for the two slots. A failed slot remains in the fixed two-slot denominator and its actual failed-read bytes are included. A failed slot's displayed timing is its failure clock, from first successful content read to protocol close; this descriptive interval is not a submission duration. Special-task elapsed/byte figures are descriptive and are not included in the routine efficiency gate.

| Task | Baseline correct / 2; median seconds; median bytes | After correct / 2; median seconds; median bytes |
| --- | --- | --- |
| UI | 0/2; 47.121 s; 78,078 B | 2/2; 47.821 s; 74,135 B |
| Chat | 1/2; 77.084 s; 162,571 B | 0/2; 49.759 s; 107,130 B |
| Knowledge | 0/2; 86.720 s; 106,071 B | 2/2; 103.074 s; 192,235 B |
| Permissions | 2/2; 75.105 s; 193,292 B | 2/2; 98.709 s; 210,416 B |
| Tests | 0/2; 65.885 s; 205,912 B | 2/2; 75.859 s; 176,096 B |
| Runtime | 2/2; 107.173 s; 247,102 B | 2/2; 94.324 s; 216,301 B |
| Upstream | 1/2; 109.213 s; 92,839 B | 2/2; 137.339 s; 130,915 B |
| History | 0/2; 111.188 s; 116,402 B | 2/2; 104.908 s; 132,702 B |

Task medians are descriptive only. They are not averaged to produce the gate result.

## Acceptance calculations

- Correctness: after candidate `14/16`, so the required `16/16` fails. It has 15 submitted answers (14 correct and one incorrect at slot 03) plus failed slot 18; all 16 logical slots remain in the denominator. Baseline is `6/16` correct (9 incorrect, 1 failed). Across both candidates there are 20 correct submitted answers, 10 incorrect submitted answers and 2 failed slots.
- Critical errors: after `0`, pass. Historical-authority misuse: after `0`, pass. Unresolved grading disputes: `0`, pass. Completeness: 32/32 logical slots have terminal records and all 39 actual attempts are accounted for, but the correctness gate treats missing answers as non-passing; semantic completeness does not turn failed slots into answers.
- Routine elapsed time: the specification defines time from first successful content read to answer submission and requires the median of all ten routine sessions per candidate. Baseline has ten submitted elapsed times, median `73.9525 s`. After has only nine submitted elapsed times; their descriptive median is `92.327 s`, but slot 18 has no submission duration. Its 4.705-second failure clock ends at protocol close, not answer submission, so it cannot fill the tenth value. The full-record scorer's mechanical output is `85.944 s` because its input schema requires a finite elapsed value and the derived failed record carries this labeled failure clock. That output is not the specification's submission-time metric. The after time gate is therefore **incomplete/unmeasurable**, not passed. Do not drop slot 18 or substitute its failure clock.
- Routine unique bytes: pool the same ten logical slots for each candidate and take the median; failed slot 18 contributes its observed 36,727 unique bytes. Baseline median `151,647 B`; after median `176,095.5 B`. Reduction is `1 - 176095.5 / 151647 = -0.1612198065`, a 16.12% increase, so the required reduction of at least 30% fails. This is one pooled median calculation, not a median of per-task medians; failures are retained.
- Overall formal acceptance fails on correctness and routine unique-byte reduction; the routine elapsed-time gate is incomplete. The reading-effect status is **not passed**. No task-specific 30% threshold applies.

## Reading-cost categories and failure causes

The ticket09 audit category `root` includes root and descendant AGENTS/CLAUDE files. Its report label is corrected below to “all-level guidance”; byte values are unchanged. Reclassification from all 32 final raw path ranges now separates root `AGENTS.md` from descendant AGENTS/CLAUDE guidance and includes failed slot24's final retry. The totals below include exactly one terminal attempt for each logical slot; each category sum was checked against that slot's unique interval-union byte count.

| Candidate | Root AGENTS.md | Other guidance | Task route | Current-contract/document paths* | Historical decision/upgrade paths** | Source/code | Other | Repeated UTF-8 bytes | Protected reads / collector-forbidden bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 261,808 | 522,694 | 0 | 1,017,832 | 176,842 | 380,617 | 44,739 | 242,460 | 0 / 0 |
| after | 258,576 | 271,216 | 277,920 | 980,569 | 136,785 | 553,001 | 1,790 | 243,017 | 0 / 0 |

Root guidance means only the candidate-root `AGENTS.md`; other guidance means every remaining `AGENTS.md` or `CLAUDE.md` path, including a root-level `CLAUDE.md` mirror if read. The requested semantic split between current-contract reads and historical-material reads is **unavailable** from the frozen audit categories: the recorded `contract` path family includes governance/spec documents, while its `history` family includes current ADR and decision files. The raw event paths are exact, but neither the frozen category schema nor a predeclared document-to-semantic mapping distinguishes those two concepts. The table therefore reports the reproducible path-family proxy and does not present it as a semantic current/history total. Future cost collection should freeze that mapping before sessions begin. Repeated bytes are returned UTF-8 content minus each slot's unique path/line union, summed over exactly 32 terminal attempts. Protected-read count and collector-forbidden bytes are separate; the 67 protected governance fingerprints are readable candidate documentation, while forbidden rubric/scorer/fixture reads were zero. The ticket10 published report omits final failed slot24 from its submitted-answer cost table; this integrated table includes its final retry. The category rules match the independent full-record path audit; per-slot and per-path totals are retained in local ignored `ticket11/archive/audits/cost-categories-32-final.json` with input/provenance/report files under `ticket11/archive/scorer/`.

Failure causes were operational, not semantic: ticket09's frozen runner raced collector JSON writes, and ticket10 recorded protocol/Broken pipe failures in the same concurrent-write failure context. A pre-session typo and a refused retry launch are retained but excluded from attempt totals. Failed reads remain included in observed unique bytes; a missing formal submission duration remains explicitly limited. The known runner race is next work, not a reason to mutate the frozen results or recast failed slots as passes.

## Recompute procedure and next work

To reproduce the acceptance arithmetic where the ignored local archive is available:

1. Verify the manifest, queue, baseline/after candidate manifests, prompt hashes, model catalog and tool-config hashes listed above against the retained frozen files.
2. Read ticket09 and ticket10 session reconciliation JSON; select exactly one final attempt for each frozen logical slot, retaining failed statuses and retry lineage. Confirm 32 unique slots and 39 actual attempt records. Recompute each final event's path/line union against the candidate root and check that its category sum matches the audited unique-byte count.
3. Run `scripts/score_disclosure_readability.py` against the retained final-slot input, with two failed records represented as status `failed`, empty reviews, actual unique bytes, and the explicitly labeled read-to-protocol-close failure clock required by the scorer schema. The local `ticket11/archive/scorer/` input, output and provenance preserve each input's raw-record hash and derivation. The scorer correctly counts failures as incorrect in its formal denominator; that is a gate failure, not a semantic answer grade. Its elapsed median includes a failure clock and must not be cited as the specification's answer-submission time gate. Confirm 9 adjudicated disagreements and zero unresolved.
4. For routine classes only, pool all 10 logical slots per candidate. Calculate the pooled unique-byte median over all ten, including observed failed-attempt bytes; do not remove failures or compute task-median-of-medians. For elapsed time, use only the protocol-defined first-successful-read to answer-submission interval. If any required logical slot has no submission duration, mark that candidate's time gate incomplete; a separately labeled failure clock may be reported descriptively but cannot replace submission time. The scorer's elapsed median that includes a failure clock is therefore not the formal time gate. Compute byte reduction as `1 - after_median / baseline_median`.
5. Compare against fixed thresholds: after 16/16 correct, zero critical errors, zero historical-authority misuse, routine median <=300 seconds and pooled routine unique-byte median reduction >=30%. Report each gate separately.

Hashes do not restore the raw records in a clean checkout. Preserve the ignored archive and its complete contents with the experiment owner; any later experiment must repair the runner race, establish durable raw evidence, resolve model identity/comparability, freeze a new candidate and queue, and follow the original thresholds. The current formal reading gate remains failed until new, separately frozen evidence satisfies every gate. No automatic repeated run is authorized by this report.
