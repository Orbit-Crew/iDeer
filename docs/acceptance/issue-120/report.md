---
id: issue-120-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 120 Server side of the complete Skill package preview import — read-only preview, hash-bound confirmed private draft, publication to a version copy, frozen Run versions
last-verified: 2026-10-27
verified-against: orch/issue-120-skill-import working tree on top of 01374778 (#119 candidate); every acceptance command below was run against the tree exactly as committed
---

# Issue 120 Server acceptance

The Server candidate lives in the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-120-skill-import`, stacked on 01374778 (#119). The Desktop repo
carries the same branch on top of 0fc854d; its companion report is
`docs/acceptance/issue-120/report.md` in that repository. No issue closure,
no PR, and no installer are claimed by this report.

## Implemented surface

- `backend/app/agentplatform/resources/skill_package.py` (new): the shared
  package identity helpers. `materialize` lays an uploaded package out as a
  Skill directory without executing anything (Markdown wraps as
  `SKILL.md`; ZIP/directory extract through the canonical member rules —
  traversal, absolute, backslash and symlink members refused, count/size
  caps enforced, members normalized to 0644). `build_preview` is the
  bounded read-only projection: `inspect_directory` applies the canonical
  content bar (`SKILL.md` present, no symlinks, no unscanned executables,
  size/count limits) and computes the canonical package hash (sorted
  relative POSIX paths, length-prefixed — the same hash drafts and
  versions carry), `_validate_skill_frontmatter` applies the enterprise
  front-matter rules, and the projection carries the body (bounded 20000,
  with `body_truncated`), per-file path/role/bytes/SHA-256 (bounded 200),
  counts, and the hyphen-case name. `classify_role` maps members to
  body/script/reference/attachment.
- `backend/app/gateway/routers/resources.py`: two endpoints under the
  existing `/api/resources` router.
  - `POST /import/skill/preview` — read-only preview of exactly what a
    confirmed import would upload (body, scripts, references, per-file
    and package hashes) plus the destination (`resource_type: skill`,
    `visibility: private`, the calling account). It persists nothing: no
    resource, draft, or version row and no stored content, so an
    unconfirmed package never enters the catalog. The upload drains to a
    temporary file under the origin's cap (20 MB markdown / 100 MB
    archive) and is always cleaned up.
  - `POST /import/skill/confirm` (201) — re-materializes and re-validates
    the package, refuses when the computed package hash does not equal
    `expected_package_hash`, refuses a slug the owner already has (409),
    creates the importing account's private filesystem skill, and lands
    the draft through the existing `ResourcePublisher.save_filesystem_draft`
    (its rollback plus the staged-draft discard guarantees nothing partial
    presents as imported). An explicit `skill_import_confirmed` audit
    event records origin/revision/hash. No version is published here —
    publication rides the existing draft/publish flow, and the local
    package never becomes an executable channel: it only ever becomes
    catalog content served to Server-orchestrated Runs.
- No changes to drafts, validation, publication, run snapshots, or the
  run-skill-view: #120 reuses them unchanged (frozen identity, read-parity
  authorization, built-in read-only via `assert_modify`, fork-to-copy).

## Commands and results

Focused runner: `dev-log/issue-112/test.sh` (repo-root-relative; shared
Python 3.12 venv at `/home/neowyh/code/AgentPlatform/backend/.venv`). All
commands run 2026-10-27 against the working tree at this candidate.

| Suite | Result |
| --- | --- |
| `backend/tests/unit/gateway/test_resources_api_skill_import.py` (new, 14) | 14 passed (first commit-able run; initially 13 failed / 1 passed red against the unimplemented endpoints) |
| `backend/tests/unit/gateway/test_resources_api.py` + `backend/tests/unit/resources` (neighbors) | 148 passed (162 total with the new file) |
| `backend/tests/unit/gateway/test_openapi_operation_ids.py` + `test_gateway_imports.py` + `test_resources_api_audit.py` | 13 passed (the two new routes satisfy the OpenAPI contract) |
| Full `backend/tests/integration/api` (`-o faulthandler_timeout=60`) | 1415 passed, 43 skipped, exit 0 — identical to the recorded #119-tip baseline (1415 / 43): the new endpoints add no integration/api tests and drift nothing; e2e/live legs are among the 43 skips |
| `ruff check backend` | All checks passed, exit 0 |

Integration baseline reconciliation: the recorded #119 baseline is
1415 passed / 43 skipped in the same shared venv; today's run measures
1415 / 43 — exactly the baseline, no drift (the new contracts live in
`backend/tests/unit/gateway/`).

## Scenario records (T120-01..04)

| Scenario | Ticket ACs | Automated evidence (passed) | Staged / unexecuted remainder |
| --- | --- | --- | --- |
| T120-01 (三种包型预览 + 取消不上传 + 确认后 private 草稿 + 既有校验/发布) | 1, 4 | `test_preview_reports_upload_scope_and_persists_nothing` — markdown/zip/directory previews carry the name/description/body, per-file roles and SHA-256, the canonical package hash (recomputed in the test from the frozen protocol, never read back), the private destination, and leave Resource/Draft/Version tables empty; `test_confirm_creates_private_draft_without_publishing` — the confirmed import lands `visibility: private`, `owner_id` caller, `latest_version: 0`, draft R1 with the preview hash, the on-disk draft carries body+script+reference, and the `skill_import_confirmed` audit event fires. The Desktop-side preview/cancel/confirm UI: companion report T120-01. | Real-platform upload with a real account: **unexecuted**, staged. |
| T120-02 (内置只读 + 修改产生新草稿/版本 + 本地缓存编辑不能冒充平台 hash) | 2, 3 | `test_builtin_skill_is_read_only_and_changes_need_a_new_copy` — the system-owned skill refuses `save_skill_draft` with 403 before anything is staged, its bytes/version stay frozen, and `fork` starts an independent owned copy with its own V1; `test_confirmed_draft_publishes_through_existing_flow_and_keeps_run_frozen` — publication reuses the existing flow (V1 hash == preview hash) and a SKILL.md-only edit rides a new draft to V2. Device-side local-cache drift: companion report T120-02. | Manual built-in readonly UI pass: **unexecuted**, staged. |
| T120-03 (非法路径/损坏/hash 不符/越权明确失败不执行) | 3, 4 | `test_preview_refuses_illegal_package_content` (traversal `../`, absolute, nested climb, backslash, `.sh` executable — all 400 before anything is stored), `test_preview_refuses_symlink_and_broken_archive` (ZIP symlink entry, non-ZIP bytes, unsupported origin — 400), `test_confirm_refuses_hash_mismatch` (drifted bytes vs the confirmed hash → 400, nothing created), `test_confirm_refuses_duplicate_slug_for_same_owner` (409), `test_private_skill_is_invisible_to_other_account` (another account's `get_visible` → `ResourceNotFound`). Device-side identical-category refusals: companion report T120-03. | Manual fault-injection pass: **unexecuted**, staged. |
| T120-04 (Run 冻结 V1，发布 V2 后原 Run 保持 V1、新 Run 用 V2) | 2, 3, 4 | `test_confirmed_draft_publishes_through_existing_flow_and_keeps_run_frozen` — `create_run_snapshot` freezes resource/version/content_hash at enqueue (V1 == preview hash); after the V2 publication `get_published_content(version=1)` still returns the frozen hash while latest is V2 (versions [1, 2] on disk); `create_run_skill_view` materializes the frozen V1 bytes for the run and raises on a tampered hash (`"f"*64`), so a local cache edit cannot impersonate the platform version. The Desktop publication leg: companion report T120-04. | Real cross-repo Run execution (actual Run continuing on V1 while a new Run picks V2): **unexecuted**, staged with the real-model Run environment. |

## Pending / risks

- Real-platform legs (real accounts A/B, real uploads, real Runs):
  **unexecuted**, staged; the contracts above are pinned by the automated
  suites over real persistence and real storage layout.
- Real Win7: **unexecuted**, owned by [#131](https://github.com/Orbit-Crew/iDeer/issues/131);
  modern-Windows results are not Win7 results.
- The confirm endpoint is not idempotent by design: a repeated confirm of
  the same package refuses with 409 (owned slug), so one import produces
  exactly one private draft; re-importing modified content is a new
  package identity and needs a new slug or a draft edit on the existing
  resource.
- `dev-log/` remains an untracked local working directory in this repo
  (ticket copy at `dev-log/ticket-120.md`), exactly as at baseline.
