---
name: upstream-merge
description: Merge upstream project releases into a downstream fork without silently losing either side. Encodes the dual-track system (tag-anchored convergence rounds plus a fix track for urgent cherry-picks), the conflict decision table by path ownership, and the two anti-clobber audits (local work preserved, upstream updates absorbed). Use whenever the user mentions merging, syncing, or absorbing an upstream project or a new upstream tag/release, resolving upstream-vs-local file conflicts, maintaining an upstream patch ledger, upgrading a fork, or cherry-picking an upstream fix — including Chinese phrasings like 合并上游、同步上游、收敛、升级上游、把上游新版本合进来、cherry-pick 上游修复 — even if they just say "upstream released a new version, update us".
---

# Upstream merge (dual-track convergence)

Merge upstream releases into a downstream fork so that neither side is silently lost. A merge round ends only when three things are true: the test suite passes, every local difference from upstream is still present or was removed by a recorded decision, and every upstream change in the range is present, adapted, or dispositioned with a written reason.

## Why this process exists

Downstream forks die in one of two ways, and both deaths are quiet:

1. **Local work is overwritten.** The conflict looks mechanical, "ours" feels like the safe default, and a local retry loop or a security gate disappears because it read like leftover cruft. git reports the merge as clean.
2. **Upstream updates are drowned.** Resolving toward "ours" by default stops the fork from receiving fixes while everyone believes it did. A local workaround that predates an upstream fix can suppress it forever, and nobody notices because nothing conflicts.

Both failures survive every textual merge check. Only a registered inventory, deliberate resolution rules, and behavioral audits catch them. Hence everything below.

## Step 0 — Bind to the repo's governance

Read the repo's own records before touching git. In this repository (AgentPlatform) they are:

- Governance plan with the dual-track rules and the decision funnel: `docs/offline-product-line-governance-plan.md`
- The authoritative patch ledger: `UPSTREAM_PATCH_LEDGER.md` (repo root). Read its round-inspection table and per-round reassess conclusions too — they are the precedent base for this round's keep/retire calls, not just the row list.
- The previous round's archive: `docs/upgrades/<upstream-version>/` — at minimum `UPSTREAM_LOCK.md`, `PATH_POLICY.md`, `CONFLICT_LEDGER.md`, `DoD_CHECKLIST.md`, plus whatever principle or matrix files the round accumulated (e.g. `FRONTEND_MERGE_PRINCIPLES.md`, adoption matrices, baseline reports)
- Test lanes: `scripts/run-test-lane.sh` and `docs/testing/test-lane-runbook.md`
- Impact tooling: GitNexus (`.gitnexus/run.cjs`) — run impact analysis before editing conflicted code, `detect-changes --scope all` before committing, and rebuild the index after the merge before running detect-changes again (the index goes stale with the merge itself)
- Merge history from git itself: `git log --merges --oneline develop` shows prior round boundaries, each pairing with a `docs/upgrades/` archive; prior recovery commits (`fix(...): restore ... after merge ...`) are recorded losses — each one is a concrete case the audits in this skill must now prevent

In another repo, look for equivalents (a fork policy doc, a vendored-patch registry, a CI lane list). If none exist, the defaults in this skill ARE the governance: create the records it names, starting with an empty patch ledger at the repo root.

**Prior rounds are history, not validation.** A previous round's passes, reassessments, and lane results describe that round's candidate only. Re-derive this round's evidence from today's tree; reuse a prior result only when the candidate, dependencies, test configuration, and environment are unchanged.

## Step 1 — Route to a track

| Request | Track |
| --- | --- |
| Upstream minor tag released; feature or architecture upgrade; periodic sync | Convergence track |
| Security fix or blocking defect that cannot wait for the next round | Fix track |
| Anything else urgent (a feature, a refactor, a nice-to-have) | Refuse the bypass: it waits for the next convergence round. Say this explicitly. |

The two tracks exist because they trade differently. Convergence rounds are slow, complete, and auditable; the fix track is fast and narrow. Mixing them (pulling a feature in because it rode along with a fix) is how unreviewed dependencies enter the tree.

## Convergence track

### Phase 0 — Freeze and lock

1. Confirm a clean worktree on `develop` (or the repo's main product branch). Record the HEAD SHA.
2. Fetch the upstream remote. Select the target **release tag** (e.g. `v2.2.0`). Never anchor a round on the upstream default branch's commit count; only release tags are anchors.
3. Tag the pre-merge develop HEAD as a snapshot, `deerflow-vX.Y.0` style, and push nothing yet. Warn the user about the naming trap if the repo uses it: the snapshot tag and the upstream tag share a version number and mean opposite things (snapshot = our state before absorbing upstream; upstream tag = their released tree). Rollback uses the snapshot tag only.
4. Read the upstream changelog for the range so you know what is supposed to arrive, not just which files changed.

### Phase 1 — Understand the history, then inventory (Gate A precondition)

Work on a scratch copy or worktree; nothing here edits `develop`.

**Read the history first.** Before classifying anything, run a bounded pass over git history to learn why the tree looks the way it does. Git records intent that no prose doc captures, and a conflict resolved without knowing either side's purpose is a coin flip that happens to pass tests. Keep the pass bounded: the last round or two, and only the files in play.

1. Round boundaries: `git log --merges --format='%h %s' develop`. Each upstream-merge commit pairs with a `docs/upgrades/` archive; read the latest round's lock and conflict records.
2. Recorded losses: search recovery commits (`git log --oneline --grep=restore develop`, or the repo's phrasing). Every "restore X after merge" commit marks a file that already lost local work once — a known fragile spot.
3. Local intent per file: for each file in the local-difference list below, `git log --follow --oneline <baseline>..HEAD -- <file>`, and read the messages of the commits that created the local state. For a function-level question, `git log -L :<functionName>:<file>`.
4. Upstream intent per file: `git log <baseline>..<target-tag> --oneline -- <file>` gives the other side's stated reasoning for the same region.

**Write a short history brief into the round records** (a few lines per local patch family): what the patch does, which commit introduced it, what problem that commit says it solved; known fragile spots; what the upstream commits say they intend in the conflicting regions.

The brief feeds two consumers. For the **user**, it turns each conflict into a decision with evidence: "upstream wants X (commit `abc123`, 'message'); local wants Y (commit `def456`, 'message', ledger row R-n); I propose Z because ...". For the **agent**, it separates load-bearing local code (added to fix a real bug) from incidental drift (a tweak nobody remembers) — exactly the distinction the classification below needs.

**Local side.** List every file where develop differs from the locked baseline (the previous round's upstream tag or its SHA, recorded in the last `UPSTREAM_LOCK.md`; with no lock record — first round — the baseline is the fork point via `git merge-base develop <upstream-default-branch>` or the last absorbed upstream tag):

```
git diff <locked-baseline>..HEAD --name-only
```

Classify every file — per file where a ledger row applies, by path family where an ownership zone covers the family — into exactly one of:

- covered by a patch-ledger row (record which row)
- covered by an ownership zone in the decision table (Step 3)
- an upstream change already absorbed in a previous round
- **unmapped** — stop here. Register it in the patch ledger or ask the user. An unmapped difference is an unprotected difference; carrying it into a merge is how local work dies.

**Upstream side.** List the adoption surface:

```
git diff <locked-baseline>..<target-tag> --name-only
git log --oneline <locked-baseline>..<target-tag>
```

Build the feature/fix list from the changelog and the commit log. This list becomes the Gate B checklist in Phase 4.

**Probe.** Run a trial merge on a scratch branch (`git merge --no-commit --no-ff <target-tag>`, then abort) and census the conflicts by path — skip it if a recent trial-merge census for this same range already exists. The census is a work plan and a scale estimate, not a resolution preview. If the repo keeps a merge plan, attach the census to it.

**Dark conflicts.** The census lists only unmerged paths. Files both sides edited that git auto-merges are invisible to it — and they are the largest silent-loss surface (76 such files in one real round). Enumerate the intersection and give every file in it Gate A's union check even though git reports no conflict:

```bash
comm -12 \
  <(git diff <locked-baseline>..<snapshot-tag> --name-only | sort) \
  <(git diff <locked-baseline>..<target-tag> --name-only | sort)
```

### Phase 2 — Integrate on a throwaway branch

1. Create a dedicated worktree and branch (`integration/upstream-vX.Y.0`, or the repo's existing integration-branch naming convention). The branch is local-only: it exists to be reviewed and tested, then merged with `--no-ff` and deleted. Never work on the integration branch across sessions without a pointer to it in the round's records.
2. Merge the target tag. Resolve conflicts using the decision table below.
3. **Every "ours" resolution must cite its justification** in the conflict ledger: a patch-ledger row, an ownership-zone rule, commit history showing the local change's purpose, or an explicit user decision. An uncited "ours" is reopened by default, because "ours by default" is exactly the drowning failure.
4. **Registry and record files** (patch ledgers, guidance docs, lock files) are union-merged: graft both sides' rows, never rebuild them with positional scripts. Sides may have different column counts; a script keyed to one side's layout silently drops the other side's data. After merging, assert the result has at least as many rows as either input and that no reassessment cell went empty. (A real incident: a ledger-merge script assumed 8 columns, integration rows had 7, and an entire reassessment pass was erased.)
5. **Identical-block dedup hazard.** When a conflicted file contains two similar-looking blocks and one side's resolution deletes one, git may treat it as dedup instead of loss. After resolving such a file, diff your resolution against both parents for that region and confirm each side's logic appears exactly as many times as it should. (A real incident: a heartbeat subscribe loop vanished this way and only the full test suite caught it.)
6. **Spanning renames finish this round or revert entirely.** If an upstream change forces a rename/refactor across many files (routes, vocabulary, module names), either complete the whole convergence in this round or revert it whole. A half-renamed tree is the worst of both sides.

### Step 3 — Conflict decision table

The whole tag is absorbed by default; exclusions are registered, never silent. Resolve per hunk and per path: a global resolution strategy (`git merge -X ours` / `-X theirs`) or wholesale namespace replacement is forbidden — per-path ownership is the only admissible lens.

| Zone | Default | Discipline |
| --- | --- | --- |
| Upstream-owned runtime/harness core (locally patched via ledger rows only) | Take upstream; re-apply the patch rows on top | Each row's removal condition gets re-evaluated this round (Step 4 reassess) |
| Security, authorization, permission gates | Local gate wins | Upstream convenience features must route **through** the local gate. Adapt them; never accept an implementation that bypasses the gate, however tidy it looks. |
| Enterprise delivery/deployment (offline bundles, intranet scripts) | Local wins | Upstream deploy changes are adopted only if the intranet path still works. Capabilities the intranet must not activate are adopted as code, never as configuration: upstream config keys land commented-out, deployment-sensitive defaults are pinned by the intranet overlay (never left at upstream values), outbound-calling extras are dropped with a recorded disposition. |
| Persistence migrations | Forward-only reconciliation | If upstream extended the migration chain linearly past a local branch point, re-join with a new forward-only merge revision. Never rewrite deployed revisions or restamp databases; pin with a single-head `alembic heads`-style assertion and run the migration suites. |
| Application code both sides touch (gateway, config, frontend) | Semantic merge | Reconstruct the superset: both sides' behavior present and reconciled. "Pick a side" is not a resolution here. When both sides edited the same section set, restore the union of sections. Frontend surfaces additionally follow the P1-P6 principles in `references/frontend-merge-principles.md` (entry = route + visible nav + i18n; every `/api` call resolves to a mounted router; lockfiles are regenerated from the merged manifests, never hand-merged). |
| Files only upstream touched | Take theirs, no hesitation | Silence here is correctness |
| Records, ledgers, guidance docs | Union/graft | See Phase 2 rule 4 |

### Phase 3 — Accept (lanes plus two audits)

Run the lanes the repo's runbook prescribes for an upstream-absorption round: the standard lane plus the delivery-level acceptance it names (mock E2E, intranet bundle). Full delivery lanes (`core-full`-class) only on an explicit delivery or release request. Then run the two anti-clobber audits — the recipes live in `references/anti-clobber-audits.md`; read that file before judging Phase 3 complete.

- **Gate A (local preserved):** every file classified in Phase 1 still carries its local logic, or lost it by a recorded decision — including the dark-conflict files the probe could not see.
- **Gate B (upstream absorbed):** every change in the upstream range is present, adapted, or dispositioned with a written reason.
- If the range touched the frontend, run the four-layer entry-parity gate from `references/frontend-merge-principles.md` with no unregistered losses.
- If the repo ships an offline/intranet deliverable, rebuild the bundle, run the intranet check and container smoke, and record anything incomplete as incomplete.
- Before trusting any gate result, delete generated caches (route dumps, build artifacts, lockfiles created by earlier tooling). A cache that predates the change under test has produced both false failures and false passes.
- Bucket every acceptance failure instead of "fixing until green": upstream-new behavior needing local adaptation / pre-existing at the baseline (prove with a baseline rerun) / order-dependent (rerun serially) / genuinely broken (fix the smallest thing). Record the buckets; do not silently absorb them.

### Phase 4 — Land and record

1. Merge `--no-ff` into `develop`. The merge commit is the round's boundary; a fast-forward erases it. Rerun the acceptance lanes on the merge result itself — unless the merge commit's tree is identical to the validated integration tip (`git diff <integration-tip> <merge-commit> --stat` empty), in which case the Phase-3 lane results carry over.
2. Write the round's records under `docs/upgrades/<target-tag>/`:
   - `UPSTREAM_LOCK.md`: develop SHA + snapshot tag, target tag and its SHA, previous baseline SHA, date, remote URL, probe result
   - `PATH_POLICY.md`: carried forward from the previous round; extend it with any new path family or ownership change decided this round
   - `CONFLICT_LEDGER.md`: every resolved path — what each side wanted, the decision, the citation; dark-conflict files audited via the union check
   - Patch-ledger reassess: for every row, is the removal condition met now? Absorb upstream equivalents, retire patches whose seams now exist upstream, keep the rest with today's evidence. Record the comparison command and its scope, then check the scope's siblings: path-scoped comparison commands miss files outside their path (package metadata, docs) — the Phase-1 whole-tree inventory is the authority, and any file it shows unmapped fails the round even when the scoped command is clean
   - Acceptance decomposition: the upstream range grouped by category (features, fixes, refactors, deps, tests), each group's disposition (adopt / keep local / reimplement) with the reason and the validation command
   - Generic fixes worth contributing go back upstream as PRs; register them in the reassess rows as candidates
   - `DoD_CHECKLIST.md` with evidence (commands, numbers, commit SHAs), and PR materials
3. Update the locked-baseline pointer for the next round (it is this round's target tag).
4. Delete the integration branch and worktree (named to the repo's existing convention). Keep the snapshot tag.
5. Deliver the final report (template below) and let the user run the push.

### Final report template

```
# Convergence round <target-tag>
- Locked baseline → target tag: <SHA(s)>
- Snapshot tag: <name> (rollback anchor)
- Merge commit: <SHA>
- Upstream changes absorbed: N — <list: present as-is / adapted how>
- Upstream changes dispositioned: <list + reason, or "none">
- Local patches: kept M / retired K (<which, and the upstream equivalent that replaced them>)
- Unmapped local differences found by the Phase-1 inventory: <list, or "none">
- Acceptance: <lanes run, results; Gate A result; Gate B result>
- History findings: <fragile spots and load-bearing local code the history pass surfaced, or "none">
- Intranet bundle: <result + incomplete items, or "not applicable">
- PATH_POLICY: <updated / unchanged>
- High-risk lane selection: <protected paths touched; Real-E2E note for the PR handoff, or "none">
- Records written: <file list>
- Your step: review the report, then `git push origin <branch>`
```

## Fix track (urgent cherry-pick)

Eligible: security fixes and blocking defects only. Say no to everything else.

1. Create a short-lived branch `fix/upstream-<PR-number>-<slug>` from develop.
2. `git cherry-pick -x <upstream-SHA>` for the single fix commit. If local patches conflict with it, adapt through the local seams (the decision table still applies); do not take the upstream file wholesale.
3. Run the fix's focused test suite plus the narrowest dependent lane. Full lanes are NOT required here; the next convergence round re-runs everything.
4. Register the fix in the patch ledger: source SHA, reason, and the note "will be absorbed naturally by the next convergence round" (git recognizes the same change at merge time, so no second long-lived line is created).
5. Merge `--no-ff` back to develop, delete the branch, and report: what was picked, from where, what was adapted, what was validated.
6. Never cherry-pick a feature, and never let a security cherry-pick drag adjacent commits in.

## Common failure modes (from real rounds)

- **The tolerant wrapper.** An upstream change offers a convenient shortcut that skips a local security gate. It looks like an improvement and passes upstream's tests. Reject it; adapt the feature to route through the gate.
- **The registry script.** Rebuilding a ledger/guidance file with code that assumes one side's schema erases the other side's rows. Graft, then recount.
- **The stale cache.** A gate reads a route dump or build artifact generated before the merge and reports a pre-existing anomaly as new (or hides a new one as pre-existing). Delete caches before trusting gate output.
- **The suppressed failure.** An acceptance failure gets "fixed" by deleting the test's premise. Failures get bucketed and recorded, and the fix goes into the smallest unit that owns the bug.
- **The silent local diff.** A local tweak nobody registered gets merged over and discovered months later. Phase 1's inventory exists precisely to catch these while they are still recoverable.
- **The dark conflict.** Files both sides edited that git auto-merges never appear in the conflict list. They are enumerated and audited in Phase 1, not trusted to the merge machinery.
- **The coin-flip resolution.** A conflict resolved without reading either side's history "works" until the day someone needs that code to do what its commit said it does. Phase 1's history pass exists so every resolution can answer "why" with a commit, a ledger row, or a user decision.

## References

- `references/anti-clobber-audits.md` — Gate A/B recipes, registry merge rules, cache rule, failure bucketing. Read before judging Phase 3 complete.
- `references/frontend-merge-principles.md` — P1-P6 frontend principles and the four-layer entry-parity gate. Read whenever the upstream range touches the UI tree.
