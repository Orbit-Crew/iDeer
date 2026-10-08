---
id: disclosure-dual-track-ticket10-final-verdict
kind: evidence
status: archived
owner: repository maintainers
scope: Final four-state verdict, comparability limits, independent archive restoration, and candidate-gate handoff for disclosure dual-track tickets 07–10
---
# Disclosure dual-track ticket 10 final verdict

## Four states

| Track | State | Evidence |
| --- | --- | --- |
| Engineering execution | Delivered. Ticket 07's collector/runner recovery and ticket 08's six isolated practical sessions completed. The focused checks and independent implementation reviews recorded for the six sessions passed. No exercise patch entered the product tree. | [Ticket 07 results](disclosure-dual-track-ticket07-results-2026-10-08.md), [ticket 08 results](disclosure-dual-track-ticket08-results-2026-10-09.md) |
| Documentation and audit | Delivered in this candidate. The ticket 07 disagreement count and dispatch-run explanation are corrected below and in its result record. The stale pure-documentation comparison statement is corrected in the specification. Document policy registration, mirrors, protected fingerprints, and document checks are part of this candidate's pre-gate validation. | This report and the linked records; final checks are recorded in the ignored ticket 10 handoff. |
| New acceptance gate | **Incomplete and not passed.** The frozen denominator remains 16 per candidate. Baseline has 13/16 confirmed correct. After has 14/16 confirmed correct and one unresolved conditional answer at slot 25. Slots 31 and 32 are excluded for collector fingerprint drift; slots 26 and 27 ended on quota. The routine-task Markdown unique-byte median fell from 99,857.5 to 88,068.5 bytes, an 11.8058% reduction against the 30% threshold. | Ticket 07 frozen queue, v2 score input/report, physical cost input/report, and ticket 08 results. |
| Legacy acceptance gate | **Not executed.** Ticket 09's prerequisite was not met because the new gate did not pass. No legacy session was started, and no prior legacy score or threshold was changed. | [Ticket 08 results, ticket 09 decision](disclosure-dual-track-ticket08-results-2026-10-09.md#ticket-09-conditional-decision); ignored issue record: `.scratch/disclosure-dual-track/issues/09-legacy-readings.md`. |

The engineering and practical work is delivered while the measured reading outcome remains incomplete and below its frozen cost threshold. These states answer different questions. Passing implementation checks does not turn the new acceptance gate into a pass, and the legacy gate has no result to score.

## Samples, costs, and comparability

Ticket 07 used the frozen 32-slot queue, task prompts, candidate snapshots, model alias `gpt-6.1-sol`, Codex CLI 0.161.0, medium reasoning, and interleaved scheduling. Its raw cost input retains 97 physical reader-session records, including 30 submissions and 67 failures. The recomputation tool groups these into 94 terminal operational groups. Those groups include zero-read failures, diagnostic and retry records, and other extra physical dispatches. **The formal experiment has 32 frozen slots; 94 is not a formal sample count.** The 97 physical records remain in the cost calculation.

An independent median recomputation from the restored physical cost report groups retry-linked rows by `logical_id`, selects the submitted terminal attempt, and sums the five Markdown categories for the ten routine slots per candidate (UI, Chat, Knowledge, Permissions, and Tests, two replicates each). It returns 99,857.5 bytes for baseline and 88,068.5 for after, an 11.8058233% reduction. The other task classes and all failed/extra physical attempts remain in the all-physical report but do not enter this ten-slot median.

The frozen ticket 07 candidate manifests and the commit comparison `5687f8b90b96de73887e91e3984ad74d0772a01b..fe65d5b98ca699bfc7c4694a19d7476949b68062` agree on 25 changed paths: 19 Markdown and six non-Markdown. The non-Markdown paths are two collector/cost tests, three reader/evaluation scripts, and the document policy JSON. Product feature source stayed the same. Evaluator-only materials were excluded from coder-readable inputs, and the external reader tool fingerprint was held fixed. This comparison does not establish that the complete Git candidate changed only in documentation. It reports the result for the frozen candidates as they were measured.

Ticket 08 used one shared 4,927-path non-Markdown product/test/tool tree for its six parentless exercise inputs, with the after side receiving the readable Markdown projection. Evaluator materials were excluded. Blinding was instructional: shared Git objects did not form a physical access boundary. The first four sessions have only a 549.23-second freeze-to-final-observation batch upper bound; the last two have outer bounds of 62 and 69 seconds. Coder intervals were 60, 45, 48, 50, 37, and 26 seconds. These records support completion inside the 30-minute criterion but do not prove hard timeout enforcement or exact per-session outer duration for the first four. The UI after reviewer noted that a numeric `0` ReactNode action is omitted by truthiness rendering. This is non-blocking for the frozen task.

The task set is the frozen queue's eight task classes and two candidates with two replicates. Ticket 08 selected concrete UI settings action, Chat pending-duplicate submission, and Permissions visibility-before-pagination tasks. Its six practical results show that both sides could complete the same fault-injection tasks with the frozen tests. They do not establish a general speed or documentation-quality gain. The reader sample is small, the model provider's resolved revision is unknown, and results do not generalize to other model revisions, providers, task mixes, or hard-timeout guarantees.

## Scoring correction and run identity

The two independent ticket 07 reviews have **six** anchor disagreements: four `UP-C1` conditions in slots 13, 14, 17, and 18, plus `RUN-C1` and `RUN-AUX` in slot 25. The third reviewer marked the four `UP-C1` conditions and `RUN-AUX` not applicable. `RUN-C1` remains unresolved. The frozen score remains baseline 13/16, after 14/16 confirmed plus one unresolved, zero adjudicated incorrect, and zero critical errors or historical-authority misuse findings.

The read-only diagnostic resume trace (`dispatch-report-readonly-attempts.json`, `resumed_after_slot: 1`) and formal queue trace (`dispatch-report.json`, quota stop after slot 27 with slots 28–32 pending) are separate runs and physical attempts. They are not contradictory snapshots of one dispatch. The diagnostic run is not proof of the formal run's quota-stop behavior. Slot 1's frozen queue maps after/UI/replicate 2 while retry metadata says replicate 1; its linked answer remains in slot 1 and the mismatch remains an audit warning. No new formal reader was dispatched after collector fingerprint drift was found. Slots 31 and 32 remain invalid for semantic scoring; neither was redrawn.

## Independent archive restoration

Ticket 07's external archive SHA-256 is `45b3bee34c082b700d00263f6d69e665129b2fb4da449ac299cf95fec5141d88`. Its restored candidate snapshots were extracted under `/tmp/dual-ticket10-audit07/`. The archived score input was passed to the current `score_reviews(queue, records, anchor_specs)` implementation; its parsed JSON result equals the archived score report. The archived physical cost input was rebound to the restored baseline/after snapshots and passed through `scripts/report_disclosure_costs.py`. The tool verified snapshot manifest digests and returned 97 physical records and 94 operational groups. The independent report is `/tmp/dual-ticket10-audit07/cost-independent.json`; the archived inputs and expected output are under `/tmp/dual-ticket10-audit07/formal/`.

Ticket 08's external archive SHA-256 is `9ba23c1e51c7b075be4823c04ad573843997c525851f40e76e75e1ecf81616b0`. Its package manifest verified all 135 entries by byte count and SHA-256. I also fetched the archived Git bundle into a fresh repository under `/tmp/ticket10-restore08/repo`, created six detached worktrees from the parentless input commits, checked all 33,571 input manifest entries against actual file lengths and SHA-256 digests, applied each archived patch, and verified the one-file changed-path boundary and resulting source digest. All six restores passed. The independently generated record is `/tmp/ticket10-restore08/recomputed.json`; focused restored test/static outputs from the original archive are in `/tmp/dual-ticket10-audit08/restore-tests/`. These copies are outside the worktree but remain on this machine. They are not a persistent off-host backup. The ignored `dev-log/` archives and source records remain in place.

## Final candidate gate

The only repository-level acceptance lane for ticket 10 is one complete `pr-standard` run after all tracked documentation, policy, status, review, and mirror changes are finished. The run is still pending in this candidate. After it finishes, the root handoff will record the result and each sub-lane summary in the ignored `dev-log/disclosure-dual-track/ticket10-pr-standard-final.json`, with linked runner logs. That result will name the exact pre-run candidate SHA. No tracked candidate file is to be edited after the lane starts. The handoff will also record `.github/scripts/should-run-real-e2e.sh` selection for the final changed paths.

## Retrospective observations

The source evidence points to a small set of deterministic checks for future experiments:

- Have the orchestration script verify the actual child PID or process-group marker before classifying a sandbox `ps` observation. The ticket 07 timeout test initially confused a scheduling delay with missing cleanup.
- Require every patch and test command to record `git -C <candidate-root> rev-parse --show-toplevel`, the changed path list, and before/after blob hashes. Ticket 08 preserved wrong-working-directory diffs as superseded evidence after discovering them during packaging.
- Validate archive manifests against the files actually packaged, and verify ignored-path rules before moving or deleting worktrees. Ticket 08's restore audit caught a packaging mismatch; the ticket 07 handoff also records the need to preserve ignored raw evidence.
- Capture both child execution time and outer dispatch-to-final-observation time at session start. Ticket 08 had only a batch upper bound for the first four sessions and cannot support exact per-session outer timing or a hard-timeout claim.
- Pin and verify the collector fingerprint on every submitted sample. Slots 31 and 32 show why a changed evaluator tool must invalidate affected records without silently redrawing them.
- Recompute summaries and archive digests from source files, then compare them before writing prose. The ticket 07 disagreement total and distinct diagnostic/formal dispatch runs were both recoverable from original evidence and needed wording corrections.

These are recommendations for experiment tooling and handoff checks. They do not call for another reader run, a change to frozen evidence, or a new permanent root guidance rule.
