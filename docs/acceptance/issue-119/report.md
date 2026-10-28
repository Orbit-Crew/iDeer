---
id: issue-119-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 119 Server side of the wiki index with links, backlinks, and the association graph over one frozen revision
last-verified: 2026-10-27
verified-against: orch/issue-119-wiki-index working tree on top of b63c408e (#118 candidate); every acceptance command below was run against the tree exactly as committed
---

# Issue 119 Server acceptance

The Server/Web candidate lives in the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-119-wiki-index`, stacked on b63c408e (#118). The Desktop repo
carries the same branch name at 5b9f306; its companion report is
`docs/acceptance/issue-119/report.md` in that repository. No issue closure
and no PR are claimed by this report.

## Implemented surface

- `backend/app/agentplatform/knowledge/wiki_navigation.py` (new): the
  read-only navigation projection. No engine, no model call, no new device
  operation — the index derives deterministically from artifacts that
  already exist for exactly one frozen revision:
  - `extract_wiki_links` is one deterministic grammar over the stored page
    bodies: `[[target]]` wiki links and `[text](target)` Markdown links.
    External URLs (`http/https/mailto/ftp`), bare anchors, empty and
    oversized targets (255 chars, `\x00`) are ignored rather than guessed
    at; duplicates collapse to their first occurrence; a page carries at
    most 100 links so one pathological body cannot flood the index.
  - `KnowledgeWikiNavigationService.index` reads only this revision's
    frozen manifest, its own stored #118 wiki pages, and its own stored
    #116 graph artifacts. A link resolves only by the frozen document id,
    the frozen filename, or a completed page title of exactly this
    revision (title resolution is the lexicographically first canonical
    document id); anything else is an explicit `missing_links` entry with
    its bounded text — never a fabricated accessible page. A self
    reference is neither a link nor a gap. Backlinks invert exactly the
    resolved links and name the source's own title and honest status. A
    resolved target names its page status, so a link into a skipped or
    failed page never looks readable. Page rows never carry bodies — those
    stay behind the #118 per-page read.
  - `_associations` reuses the stored #116 graph rows with their frozen
    document binding (document_id, filename, content_hash); failed or
    ungenerated documents appear as honest coverage rows and contribute
    no entities or relations. Aggregate statuses are the existing
    `aggregate_wiki_status` / `aggregate_status`, so the index cannot
    claim a better state than its rows.
- `KnowledgeFacade.wiki_navigation`: the intent behind the HTTP surface,
  riding the same session/actor seams as the #118 read paths.
- `routers/resources.py` (gateway): `GET
  /api/resources/{id}/knowledge-revisions/{rid}/wiki/navigation` —
  read-parity with the #118 page list: the exact `get_visible` guard, so
  a hidden or foreign KnowledgeBase reads as 404 and no other revision's
  or account's titles, links, or relations can appear here. A revision id
  from another knowledge base is 404, never a cross-KB leak.

## Commands and results

Focused runner: `dev-log/issue-112/test.sh` (repo-root-relative; shared
Python 3.12 venv). All commands run 2026-10-27 against the committed tree.

| Suite | Result |
| --- | --- |
| `backend/tests/unit/knowledge/test_wiki_navigation.py` (new, 14) | 14 passed |
| `backend/tests/integration/api/test_knowledge_wiki_navigation_router.py` (new, 5) | 5 passed |
| `backend/tests/unit/knowledge` (full dir) | 391 passed, 3 skipped, exit 0 (7 min 12 s; recorded #118 baseline 377 / 3 → +14 new) |
| Full `backend/tests/integration/api` (e2e/live excluded, `-o faulthandler_timeout=60`) | 1415 passed, 43 skipped, exit 0 (7 min 42 s; #118 tip measured 1410 / 43 → +5 new, deltas reconcile exactly) |
| `ruff check backend` | All checks passed, exit 0 |

Integration baseline reconciliation: the recorded #118 baseline is
1410 passed / 43 skipped in the same shared venv
(`/home/neowyh/code/AgentPlatform/backend/.venv`); today's run measures
1415 / 43 — exactly the 5 new navigation router tests, no drift.

## Scenario records (T119-01..04)

| Scenario | Ticket ACs | Automated evidence (passed) | Staged / unexecuted remainder |
| --- | --- | --- | --- |
| T119-01 (索引 → P → 链接 → Q → 反链 → 关联图 → 返回来源闭环) | 1, 3, 4 | router `test_owner_navigates_links_backlinks_and_associations`: both link shapes (`[[policy.txt]]` + `[[检修手册]]`) dedupe into one resolved link, the closed link loop gives each page the other as its backlink with the source's title/status, the association graph reuses the #116 rows with frozen digests, and the final act reads the linked target through the unchanged #118 per-page endpoint — the closure walks index → link → read. Unit `test_extract_wiki_links_is_deterministic_and_internal_only` (external/anchor excluded), `test_index_resolves_links_by_filename_and_title_and_reports_missing`, `test_index_resolves_links_by_frozen_document_id`, `test_index_page_rows_never_carry_bodies`. Desktop companionship (runtime + UI): companion report T119-01. | Manual reading pass on the real three-end UI + screenshots: **unexecuted** (staged with real model credentials, same staging as #118's T118-01/T118-02 legs). |
| T119-02 (B / 收紧范围越权不可见，权限矩阵) | 1, 4 | router `test_navigation_permission_matrix`: stranger reads 404 on view/navigation/page/generate; a department member of a department-visible KB navigates the same frozen rows and relations while generation still rides the KB's modify boundary (403); another revision id is 404. Unit `test_index_visibility_is_the_kb_parity_guard`, `test_index_refuses_a_revision_from_another_knowledge_base`. | None beyond the shared real-model staging. |
| T119-03 (Q 缺失 / 部分生成 / 来源不可用明确状态) | 2, 4 | router `test_missing_target_and_skipped_page_are_explicit`: a drifted policy.txt generates `partial`; the filename link resolves but names `status: skipped` with an empty title, the title-shaped link degrades to an explicit missing entry (a skipped page has no title, so nothing pretends it resolves), the ghost target stays missing, backlinks stay completed-only, and the association graph reports `not_generated` with per-source `not_generated` coverage rows instead of inventing relations. Unit `test_index_reports_skipped_target_status_instead_of_a_readable_page`, `test_index_backlink_never_points_at_a_missing_target`, `test_index_associations_report_not_generated_without_artifacts`, `test_index_before_any_generation_reports_not_generated`, `test_extract_wiki_links_is_capped_per_page`. | Manual UI fault-injection pass + screenshots: **unexecuted** (staged with real model credentials). |
| T119-04 (新版本发布后旧 Wiki 版本归属不漂移) | 1, 3 | router `test_navigation_is_revision_bound_and_never_leaks_other_versions`: two revisions over the same KB; each index lists exactly its own manifest and pages, the second revision never shows the first's titles/links/backlinks (its title-shaped reference stays an explicit missing entry), and the first revision's association graph is untouched (`属于` still there, second's graph `not_generated`). Unit `test_index_is_scoped_to_exactly_one_revision`, `test_stored_rows_are_queryable_by_revision`. | Manual reopen-the-old-session check on the real UI: **unexecuted** (staged with the real-model environment). |

## Pending / risks

- Real-LLM and real-three-end manual passes: **unexecuted on model
  credentials**; the contracts above are pinned by the automated suites.
- Real Win7: **unexecuted**, owned by [#131](https://github.com/Orbit-Crew/iDeer/issues/131);
  modern-Windows results are not Win7 results.
- The index is a projection: link quality inherits whatever the #118
  model wrote into page bodies (out of scope per the ticket — no new
  extraction engine; the deterministic grammar is capped and never
  guesses).
- `dev-log/` remains an untracked local working directory in this repo
  (ticket copy at `dev-log/ticket-119.md`), exactly as at baseline.
