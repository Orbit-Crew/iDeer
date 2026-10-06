# Anti-clobber audits: recipes for Gates A and B

Read this before judging Phase 3 (acceptance) complete. The gates are the two audits the merge process exists for; a lane run alone does not substitute for either.

## Gate A — local work preserved

**Question answered:** did anything the local side owns survive the merge?

1. **Inventory is the checklist.** Phase 1 produced a classification of every file where develop differed from the locked baseline. That list is Gate A's input. For each entry:
   - Ledger-row files: re-run the row's recorded validation (its test command), and confirm the patch's load-bearing code is still present (grep for the row's key symbol, flag, or block). Ledger comparison commands are path-scoped and miss sibling files outside that scope (package metadata like `pyproject.toml`, docs); the Phase-1 whole-tree inventory is the authority — any file it shows unmapped fails the round even when the scoped command is clean.
   - Dark-conflict files (both sides edited, git auto-merged them — enumerated in Phase 1): these get the union check below even though git reported no conflict.
   - Ownership-zone files: confirm the zone's rule still holds in the merged file (the security gate is still on the path, the intranet script still runs, the superset sections are all present).
   - Unmapped files (registered during Phase 1): confirm the newly registered difference survived, and add it to the ledger with this round's evidence.
2. **Union check on semantic-merge-zone and dark-conflict files.** For each file both sides touched — whether git conflicted or auto-merged — compute the diff of the merged result against each parent and verify the result contains the union of both parents' behavioral changes:
   ```
   git diff <baseline>..<merged-result> -- <file>   # combined change
   git diff <baseline>..<target-tag> -- <file>      # upstream's change
   git diff <baseline>..<snapshot-tag> -- <file>    # local's change
   ```
   Every behavioral region present in a parent but absent from the result is a suspected loss until explained.
3. **Identical-block recount.** If a conflict hunk contained two similar blocks (retry loops, subscribe loops, repeated config blocks), count those blocks in both parents and in the result. A count drop that git presented as dedup is a loss.
4. **Tests as the net, not the only net.** The full lane run backs this audit up; it does not replace it, because a lost behavior with no test fails silently at gate time and loudly in production later.

**Pass condition:** every Phase-1 entry accounted for (present, or removed by a recorded decision). Any unexplained absence fails the round.

## Gate B — upstream updates absorbed

**Question answered:** did the fork actually receive what this upstream release shipped?

1. **List the range.** From the changelog and `git log --oneline <baseline>..<target-tag>`, build the table of upstream changes (features, fixes, refactors, dependency bumps).
2. **Disposition every row**, one of exactly three:
   - **present** — merged as upstream wrote it;
   - **adapted** — present with local modifications (renamed to local vocabulary, rerouted through a local gate); record what was changed and why;
   - **dispositioned** — deliberately not taken; record the reason and the revival condition (a later round, an upstream seam, a user decision).
   A row with no disposition is a drowned update. This table goes into the round's DoD checklist.
3. **Fix-pointer audit.** For every upstream fix in the range, locate the fixed symbol or behavior in the merged tree and confirm the fix is reachable (not shadowed by a local override, not behind a permanently false flag). A local workaround that predates the upstream fix and still shadows it is a dispositioned row, not a pass.
4. **The default direction check.** Re-read the conflict ledger. Every "ours" resolution must cite a ledger row, an ownership rule, or a user decision. Uncited "ours" rows reopen Gate B for their files.

**Pass condition:** the adoption table is complete, every row dispositioned, and the count of present/adapted rows matches what the changelog promised.

## Registry merge rules (ledgers, lock files, guidance docs)

- Graft both sides' rows into the result; never regenerate a registry from one side's schema.
- Sides may carry different column counts or section orders. Key rows by their identity (patch ID, entry name), not position.
- After merging: result row count ≥ max(either side's count); every identity from both sides appears; every reassessment/status cell on union rows is non-empty.
- When in doubt, merge by hand. Registries are small; scripts on registries have erased real work.

## Cache invalidation before gates

Delete generated state before trusting any gate: route dumps, build artifacts, ephemeral tooling caches, generated type files — never version-controlled lockfiles. A gate reading a cache that predates the change under test proves nothing about the current candidate. If a gate failure looks impossible, invalidate the cache and rerun before debugging product code — and if the failure was a cache artifact, record that correction wherever the earlier claim was written.

## Acceptance-failure bucketing

Every failure gets exactly one bucket, recorded with evidence:

1. **Upstream-new × local adaptation** — upstream behavior the local mock/fixture/script does not know yet. Fix goes to the adaptation, tracked as follow-up work if large.
2. **Pre-existing at baseline** — prove it by rerunning the failing test at the snapshot tag (or the recorded baseline) and observing the same failure. Record and move on; do not fix inside the merge round.
3. **Order-dependent** — passes alone, fails in the suite (or vice versa). Rerun serially to confirm, record, and treat as bucket 1 or 4 by root cause.
4. **Genuinely broken by the merge** — the smallest unit that owns the bug gets the smallest fix. Never widen the fix to make a lane pass, and never weaken an assertion to go green. When a rejected bypassing implementation leaves tests failing, adapt the test fakes to the production contract (e.g. async acquisition against the real gate) — never fake the gate away or re-route around it.
