---
id: disclosure-branch-navigation-acceptance-2026-10-09
kind: evidence
status: archived
owner: repository maintainers
scope: Frozen ticket 05 NAV candidate comparison, branch pilots, formal grading, cost, and evidence custody
last-verified: 2026-10-09
verified-against: baseline 73a2a168fa08cf1854d60d1ceff41c4b572f63a6; after f10b0c525eb1438d043951a30d19a99986761286
---
# Ticket 05 navigation acceptance report

> This report records the frozen NAV candidate pair and its pilot and formal evidence. The implementation and branch-reachability pilot are delivered. Formal correctness and reading-cost gates remain incomplete.

## Current status

The navigation documentation is delivered on the frozen after candidate, and the non-scored branch pilot supports matrix reachability. The formal correctness gate and the routine reading-cost gate are **incomplete**. The corrected formal score contains both correct and incorrect submitted answers, but three quota-failed slots remain in the fixed denominator. This evidence does not establish a measured navigation-effectiveness pass or completion of the two-specification feature.

The fixed formal queue has 32 logical slots, 16 per candidate. Slots 11–13 ended in permanent quota failures under the frozen protocol and will not be retried. The other 29 slots submitted answers. Corrected, calibrated A/B reviews cover every submitted answer, and C completed one-to-one adjudication of all 18 disagreements. Missing answers remain in the denominator.

| Dimension | Evidence now available | State |
| --- | --- | --- |
| Navigation documentation | Four NAV route files differ between the frozen pair; the task-routing index and all five measured route pages remain within their byte limits. | Delivered |
| Non-scored branch reachability | Fifteen fixed pilots cover 13 named branches, a mixed task, and an ambiguous task. All submitted once; all required reachability checks passed. | Pilot passed; diagnostic only |
| Formal correctness | 29 submitted answers received corrected independent A/B reviews after six-example calibration. C adjudicated all 18 disagreements. The fixed denominator includes three quota failures. | Incomplete |
| Formal reading cost | The fixed 10 routine after samples include only 9 valid answers. Their median is descriptive and cannot replace the 10-slot gate. | Incomplete |
| Cost recomputation | The frozen cost CLI, run from an independent restored copy with bytecode writing disabled, reproduced the original cost JSON exactly. | Recalculation passed |
| Evidence durability | The original raw archive and corrected-grading supplement have verified worktree-external copies and independent restores. | Verified local copies; no remote retention |
| Broader feature | The independent root GitNexus-guidance specification and integrated final gate are outside this ticket report. | Not complete here |

## Candidate and implementation

The immutable NAV comparison uses baseline commit `73a2a168fa08cf1854d60d1ceff41c4b572f63a6` and after commit `f10b0c525eb1438d043951a30d19a99986761286`. The candidate audit records exactly four changed paths: `docs/agents/routes/chat.md`, `docs/agents/routes/knowledge.md`, `docs/agents/routes/permissions.md`, and `docs/agents/routes/tests.md`. Both manifests contain 5,742 paths. The freeze audit records 5,190 `reader_accessible_text_counts` for each projection and validates the 13-path reviewer/evaluator exclusion ledger. Root guidance, product source, tests, prompts, and evaluator tools are identical across this candidate pair. The canonical manifest hashes are baseline `306b64816b961f990b1a8ea856fc65019e01bdc7385f3e444685054d684b62e6` and after `1a5e27eb833b9aa3fb71cd55b1bbbd6ba272247ae0a9c795cf4fc9ebd89295fc`.

The route pages separate task branches within the existing nine-domain routing structure. They identify branch triggers, applicable current-contract sections, invariant owners, source starting points, conditional decisions, and first validation steps. The changes do not create a new global router or change product behavior. The formal comparison used Codex CLI 0.161.0, requested model alias `gpt-6.1-sol`, and medium reasoning. The resolved backend model revision was unavailable, so this report makes no strict backend-revision identity claim.

This acceptance report, its reviewer-only index entry, and the specification status record were written after the formal sessions. They are reporting artifacts outside the frozen snapshots and were not presented to readers.

The recorded engineering checks include `bash scripts/check_doc_hygiene.sh` passing document checks, 28 guidance mirror pairs, and 67 protected fingerprints, plus `check_agent_guidance.py` reporting zero errors and warnings. The task-routing index is 2,328 UTF-8 bytes. Chat, Permissions, KnowledgeBase, and Tests route pages are 3,673, 3,853, 3,596, and 2,680 bytes, respectively, below the 4 KiB index and 6 KiB route limits. These are documentation-delivery checks; they do not establish the formal reading gates.

## Non-scored branch pilots

The fixed pilot matrix has 15 prompts: 13 named branches, one mixed task, and one ambiguous task. The reviewer-only matrix and all 15 session records are retained with the pilot artifacts. All required branch checks were reachable. The mixed case returned both SDK assembly and Gateway recovery obligations while keeping their invariants separate. The ambiguous case kept possible duplicate-handling layers open and requested narrow source verification or clarification. Pilots exposed source/contract discrepancies as unresolved items instead of silently choosing a side.

The frozen pilot queue SHA-256 is `f1bed945e27f0968daac33c4862098a19ed13c62d6b54fe58f23b03f30387ca3`; the reviewer matrix SHA-256 is `dd324e7e1f0b5ef59b6cd3857120ac585da69eddd186d22f9f61ed24c3c05437`. The sessions produced 2,124,163 returned bytes and 2,044,596 unique bytes over 404 read/search events. Those values describe pilots only. They are not part of the formal cost gate. The pilots used an earlier reader manifest than the final formal freeze. A later audit verified that NAV route bytes, prompts, and effective tool configuration were unchanged, and that no pilot read, listed, or received search results from the 13 excluded reviewer/evaluator paths. This supports using the pilots as reachability evidence, not as formal score or cost evidence.

## Formal comparison

The formal queue has 32 fixed slots, 16 for each candidate. Its candidate commits and corrected reader projections match the freeze record. Twenty-nine slots submitted answers. Slots 11, 12, and 13 ended as quota failures; the frozen protocol forbids their retry, replacement, or denominator adjustment.

The frozen NAV queue SHA-256 is `39b057ccc5f35e4aa51fd6a0043970fff98797a4403562d0cf10e3c9a1421b6e`; the freeze record SHA-256 is `4e26b3aa206aff0aa4def7fa318a46540d4142fbfea18a9e2db5aa2a74ad9960`. The formal tool configuration SHA-256 is `561c95e6cb147a6dfa84ff27c4c8064ef25c24fcc5a2e1990e638706f5b11955`. The exact prompt hashes, role map, model catalog, scoring protocol, queue order, and reader exclusions are recorded in the frozen inputs and archive.

The first A/B scoring set was preserved but is superseded for correctness interpretation. An audit found that the two initial graders' mapped anchor decisions did not consistently follow the frozen v2 semantics, including decisions on anchors where the graders agreed. The evidence does not establish that a specific earlier rubric was used, and the report must not claim that it was. No record proves that the initial formal reviews had a completed independent calibration before scoring.

Two graders then completed six independent calibration examples. The calibration review approved the examples for corrected grading only and records that no historical pre-formal calibration was evidenced. After calibration, A and B independently reviewed all 29 submitted answers against the frozen v2 protocol. Each output covers 176 anchors with canonical coverage, exact answer excerpts, and provenance validation. C completed six calibration examples and adjudicated all 18 disagreements one to one. Root verified each decision against the recorded answer excerpts. The candidate snapshots used for grading each contain 5,742 files, with paths and bytes matching their source snapshots.

The frozen v2 scorer, after C's adjudication, reports an incomplete result. Baseline has 13 correct, two incorrect, and zero unresolved among 15 submitted answers. After has 11 correct, three incorrect, and zero unresolved among 14 submitted answers. The score records zero critical errors and zero historical-authority misuse, with four auxiliary-anchor misses. The incorrect answers are baseline Runtime slots 1 and 32, after Runtime slots 2 and 31, and after History slot 7. The four Runtime answers missed triggered `RUN-C1` validation at the harness cancellation/recovery seam, including checks with customization disabled and enabled. The History answer missed `HIST-C1` because it failed to retain the cited report's per-model 3/3 frozen counts. These are formal answer findings, not evidence that NAV caused the difference between candidates. The three quota-failed slots remain in the 32-slot denominator, and the frozen correctness gate status remains incomplete.

The formal result must remain separate from the pilot matrix. A pilot showing that a branch can be found does not prove that every formal answer contains its applicable anchors. Because submissions are missing and the correctness gate is incomplete, the candidate score difference does not establish a navigation effect or causal attribution.

## Reading cost and independent recomputation

The frozen cost input contains all 32 physical records. Across both candidates, it records 5,011,096 returned bytes, 4,828,453 unique bytes, and 182,643 repeated-return bytes, with no unknown role paths. The source/test/config category totals 1,603,310 bytes. Baseline accounts for 925,093 and after for 678,217. The all-physical Markdown category totals are 3,214,453 bytes; the remaining 10,690 unique bytes are in the `other` category.

| Task | Baseline submitted / slots | Baseline Markdown unique median | Baseline source/test/config bytes, all slots | Baseline repeated bytes, all slots | After submitted / slots | After Markdown unique median | After source/test/config bytes, all slots | After repeated bytes, all slots |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| UI | 2 / 2 | 40,494.5 | 112,802 | 13,478 | 2 / 2 | 57,891.5 | 95,303 | 16,925 |
| Chat | 2 / 2 | 81,966 | 85,637 | 3,407 | 2 / 2 | 87,818 | 83,859 | 6,077 |
| Knowledge | 2 / 2 | 82,777.5 | 326,264 | 30,566 | 1 / 2 | 75,706 | 23,674 | 1,196 |
| Permissions | 2 / 2 | 87,407.5 | 145,921 | 32,930 | 2 / 2 | 83,214.5 | 231,252 | 25,235 |
| Tests | 2 / 2 | 130,769 | 20,820 | 3,469 | 2 / 2 | 125,500.5 | 17,042 | 3,916 |
| Runtime | 2 / 2 | 127,125.5 | 139,375 | 10,557 | 2 / 2 | 230,762 | 162,322 | 11,968 |
| Upstream | 1 / 2 | 140,088 | 78,339 | 4,987 | 1 / 2 | 79,593 | 54,412 | 7,719 |
| History | 2 / 2 | 136,703 | 15,935 | 2,992 | 2 / 2 | 158,969.5 | 10,353 | 7,221 |

The Markdown values in this table sum `root_guidance`, `descendant_guidance`, `route`, `current_documentation`, and `historical_material` for submitted attempts, then report their median per task. Source/test/config and repeated-return totals include all frozen slots for that task, including failed slots. The formal routine Markdown median uses the ten UI, Chat, Knowledge, Permissions, and Tests slots per candidate: baseline is 85,699.5 bytes over 10/10 valid answers; after has 9/10 valid answers and a descriptive nine-answer median of 82,966 bytes. Do not calculate or report a gate reduction from that incomplete after sample. The required 10-slot comparison is unavailable, so the 30% cost gate is incomplete.

The original frozen cost report was independently recomputed from the restored candidate copy. The first attempt imported the collector and created a `__pycache__` file in the candidate, causing candidate snapshot drift. That generated bytecode was moved outside the candidate; the same original CLI then ran with `PYTHONDONTWRITEBYTECODE=1`. It exited successfully, and the original and recomputed report JSON files were identical. The collector, scorer, cost reporter, and frozen manifests were not changed. The bytecode incident is retained as a failed first attempt, not erased from the audit trail.

## Evidence custody and limits

The original 23,685-file raw archive is `dev-log/branch-root/archive/ticket05-navigation-formal-20261009.tar.gz`, SHA-256 `5284b97a5c47f587a4cd9e2d30fa7ebd2bef54d9994d3ac8cda450e5ad692037`, manifest SHA-256 `b1b27521a8812bc0cb2ab36cdd3a2afb20f013fda75f4f3bc908514b2ed452ab`. Its file-by-file restore at `/tmp/ticket05-navigation-formal-restore-final2-20261009/experiment` and worktree-external copy verification passed. The cost CLI's independent recomputation report matched the original report exactly.

The corrected-grading supplement is `dev-log/branch-root/archive/ticket05-corrected-grading-20261009.tar.gz`, SHA-256 `73822f0445dc403b49d3ac783292f02bf437e093f9c498c25f844c7c7f44c888`, manifest SHA-256 `b3da4f36806c6a2c2f1e2e579582ec2a533dba4d0c56f2c5be6ba9f3e7d58553`, 11,536 files. The copy at `/tmp/ticket05-corrected-grading-20261009.tar.gz` has the same SHA-256. Restoring it to `/tmp/ticket05-corrected-grading-independent-restore-20261009/experiment` and running its archived scorer `score_reviews` produced a parsed JSON result identical to `corrected-score-final.json`. The verifier record is `dev-log/branch-root/nav-corrected-archive-verification.json`; the archived scorer SHA-256 is `90cc892fec166822f2ce1894fa0f9be4583b53064c1c871e630eec66cc66dde1`.

The archives have verified worktree-external copies and independent restores. They remain local to this machine; no remote or long-term retention system is claimed.

Current ignored evidence pointers:

- Raw formal records and frozen cost input/report: `dev-log/disclosure-branch-root/ticket05-navigation/formal/`.
- Corrected grading, A/B and C calibration, grader validation, final adjudication, and final score: `dev-log/disclosure-branch-root/ticket05-navigation/formal/continuation-20261009/corrected-grading/`.
- Pilot sessions, dispatcher records, and matrix review: `dev-log/disclosure-branch-root/ticket05-navigation/pilots/`.
- Independent restored cost recomputation: `/tmp/ticket05-navigation-independent-cost-recompute-20261009/verification.json` and `dev-log/branch-root/nav-resume-20261009/verification.json`.
- Original and corrected archive verification: `dev-log/branch-root/nav-corrected-archive-verification.json`, plus the original archive check and restore records under `dev-log/branch-root/nav-resume-20261009/`.

These archives and worktree pointers are local experiment evidence, not repository-tracked copies. Archive hashes identify byte sequences but do not establish long-term retention. The supplement contains two blinded source snapshots with exact source matches, A/B/C calibration and reviews, adjudications, and validation records. The grading process withheld the reviewer-to-candidate mapping; final scoring records retain audit linkage. The archives are reviewer-only audit evidence, not reader inputs or payloads approved for wholesale transmission. Input exclusions and the access audit are recorded in the frozen evidence.

## Decision

The current evidence supports that the NAV documentation was delivered and that all 15 non-scored branch pilots reached their expected branch checks. C's adjudication resolved all 18 anchor disagreements. Formal correctness is **incomplete** because three quota-failed slots remain in the denominator. Formal reading cost is **incomplete** because one of ten after routine slots has no valid answer. Independent cost-report recomputation passed, which verifies the calculation against the retained raw records but does not complete the cost gate.

This report does not declare the NAV measured-effectiveness gate passed or formally failed, does not change the previous ticket 07 result, and does not mark the broader two-specification feature complete. The separate navigation specification remains draft while the requested measured-effectiveness gates are incomplete.
