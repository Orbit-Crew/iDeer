---
id: issue-121-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 121 Server side of unified Skill trigger preferences — per-user preference CRUD, Server-side matching bound to the existing run-snapshot seam, and the rejection/no-drift/no-privilege contracts
last-verified: 2026-10-27
verified-against: orch/issue-121-skill-trigger working tree on top of 7422b14c (#120 candidate); every acceptance command below was run against the tree exactly as committed
---

# Issue 121 Server acceptance

The Server candidate lives in the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-121-skill-trigger`, stacked on 7422b14c (#120). The Desktop repo
carries the same branch on top of 7d9e5a5; its companion report is
`docs/acceptance/issue-121/report.md` in that repository. No issue closure,
no PR, and no installer are claimed by this report.

## Recorded existing rules (expected constants, read before implementing)

#121 reuses and binds the platform's existing selection rules; it does not
invent matching semantics. These were recorded from the #120-tip code before
any implementation output existed:

- R1 — **One preferred Skill per Run**: `ResourceService.create_run_snapshot`
  carries exactly one `selected_resource_id`; `RunResourceSnapshot.selection_role`
  is CHECK-constrained to `root`/`resolved`/`preferred`. Preference matching
  therefore injects at most ONE Skill (`MAX_TRIGGERED_SKILLS_PER_RUN = 1`).
- R2 — **The closure is the only candidate set**: `resolve_dependency_closure`
  enforces caller visibility (`get_visible` parity), published availability
  (`latest_version >= 1`, else 409), cycles (409), and invisible required
  dependencies (404). A preference-selected Skill passes through the exact
  same walk.
- R3 — **Explicit selection hard-fails**: the request-context
  `skill_resource_id`/`skill_name` outside the closure raises 409
  `skill_outside_agent_closure` with the `run_preparation_rejected` audit
  (existing behavior, unchanged).
- R4 — **Agent skill whitelist**: `config.skills: None` injects all closure
  Skills, a list only the named ones, an unresolved name is a 409; the runtime
  `available_skills` set is the same whitelist.
- R5 — **Discovery search cap**: the Skill catalog search returns at most
  `MAX_RESULTS = 5` results (name-only index until explicitly activated).

## Implemented surface

- `backend/app/gateway/skill_trigger.py` (new): the fixed protocol bounds
  (`MAX_KEYWORDS = 16`, `KEYWORD_MAX_CHARS = 64`, `MAX_APPLICABLE_AGENTS = 32`,
  `PRIORITY_MIN/MAX = -1000/1000`, `MAX_PREFERENCES_PER_USER = 200`,
  `PREFERENCE_MESSAGE_LIMIT = 4000`), the documented matching rule
  (`preference_matches`: enabled gate; applicable-agent allowlist where empty
  means every Agent; `always_inject` matches every message, empty keywords
  always inject — the preserved rule — otherwise any NFKC-casefolded keyword
  hit), `select_preference` (highest `priority` wins, ties break on the
  lexicographically smaller skill id, at most one result),
  `message_text_from_input` (only this run request's user messages, bounded),
  `validate_preference_document`, and the owner-scoped
  `SkillTriggerPreferenceRepository` keyed `(user_id, skill_resource_id)`.
- `backend/app/agentplatform/resource_models.py`: `SkillTriggerPreferenceRow`
  (`skill_trigger_preferences` table; composite PK user+skill, FKs to
  `users_ext`/`resources` with CASCADE, priority CHECK).
- `backend/app/agentplatform/persistence/migrations/versions/20261027_skill_trigger_preferences.py`
  (new): chained on the #119 head `20261027_knowledge_wiki_pages`; creates the
  table on databases that predate `create_all`.
- `backend/app/gateway/routers/resources.py`: three owner-gated endpoints —
  `GET /api/resources/skill-trigger-preferences` (the caller's own rows only,
  identity+availability projection, never content), `PUT
  /api/resources/skills/{id}/trigger-preference` (visibility-checked via
  `resolve_for_use`, skill-typed, bounds-validated, 200-cap, audited
  `skill_trigger_preference_updated`), `DELETE .../trigger-preference`
  (idempotent, audited on removal). Configuring a preference grants no rights.
- `backend/app/gateway/canonical_agent_run_preparation.py`: `preferred_skill_origin`
  kwarg. `"explicit"` keeps the existing hard 409; `"preference"` runs the SAME
  closure validation but a miss is audited
  (`skill_trigger_preference_skipped`, user message text never persisted) and
  the Run proceeds without the Skill; a hit is audited
  (`skill_trigger_preference_applied`) with the frozen version/hash after the
  snapshot commit (the audit writes on its own connection and must not
  contend with the snapshot transaction's write lock).
- `backend/app/gateway/run_preparation.py`: matching happens Server-side once
  per Run, only when the request carries no explicit Skill (explicit always
  wins), against this run request's user message; the matched skill is written
  into `body_context["skill_resource_id"]` so `selection_snapshot` records the
  actual selection; a preference-store hiccup degrades to "no trigger".
- `backend/tests/integration/persistence/test_migration_schema.py` +
  `test_migration_0025_repair_run_change_seq.py` + `test_receipt_migration.py`:
  the chain-head pins were stale at the #120 tip (still asserting
  `20261024_task_history` after #119 landed two migrations) — 8 failures exist
  there at the baseline commit with no local changes; this candidate updates
  the pins to the new head `20261027_skill_trigger_pref` and its parent
  `20261027_knowledge_wiki_pages`, turning those suites green again.
- No changes to drafts, publication, the closure walk, `create_run_snapshot`,
  or the run-skill-view: #121 reuses them unchanged.

## Commands and results

Focused runner: `dev-log/issue-112/test.sh` (repo-root-relative; shared
Python 3.12 venv at `/home/neowyh/code/AgentPlatform/backend/.venv`). All
commands run 2026-10-27 against the working tree at this candidate.

| Suite | Result |
| --- | --- |
| `backend/tests/unit/gateway/test_skill_trigger_preferences.py` (new, 17) | 17 passed (first commit-able run; the red run against the unimplemented endpoints failed on the missing module/fields, then the suite went green with the implementation) |
| Neighbors: `test_canonical_agent_run.py`, `test_resources_api_skill_import.py`, `test_memory_preload.py`, `test_services_behavior.py`, `test_openapi_operation_ids.py`, `test_first_token_timing.py`, `test_gateway_imports.py` | 76 passed |
| Full `backend/tests/integration/api` + `integration/skills` + `integration/persistence` (`-o faulthandler_timeout=60`) | 1781 passed, 53 skipped, exit 0 |
| Full `backend/tests/integration/api` alone (baseline reconcile) | 1415 passed, 43 skipped, exit 0 — identical to the recorded #120-tip baseline (1415 / 43): zero drift |
| `ruff check backend` | All checks passed, exit 0 |

Integration baseline reconciliation: the recorded #120-tip baseline is
integration/api 1415 passed / 43 skipped in the same shared venv; this
candidate measures 1415 / 43 — exactly the baseline, no drift. The trio run
above adds the integration/skills and integration/persistence suites, whose
only changes are the stale chain-head pins described above (8 of those tests
fail at the #120 tip with no local changes; they pass here).

## Scenario records (T121-01..04)

| Scenario | Ticket ACs | Automated evidence (passed) | Staged / unexecuted remainder |
| --- | --- | --- | --- |
| T121-01 (Desktop 配置明确选择/关键词/空关键词始终注入/适用 Agent/优先级/启用 → Server 固定消息匹配) | 1, 4 | `test_matching_semantics_bind_documented_rules` + `test_selection_returns_the_single_highest_priority_match` (enabled gate, agent applicability, empty-keyword always-inject, priority order, cap 1, no false injection) + `test_prepare_run_applies_the_preference_match_without_explicit_skill` (a fixed matching message selects the preferred Skill with origin `preference`; a non-matching message injects nothing) + `test_prepare_run_explicit_selection_wins_and_store_failure_degrades`. The Desktop configuration surface: companion report T121-01. | Real-platform session with a real model Run: **unexecuted**, staged on credentials. |
| T121-02 (手动选择/触发校验可见性+已发布+依赖闭包，不可用技能拒绝) | 2, 4 | `test_put_validates_visibility_type_and_unavailable_targets` (invisible → 404, unknown → 404, non-Skill → 409), `test_preference_origin_skips_skill_outside_closure_without_failing_the_run` (trigger entry: out-of-closure skill skipped + audited, Run proceeds), `test_run_still_refuses_when_a_required_closure_dependency_becomes_invisible` (existing visibility rule intact, nothing activated), `test_unpublished_dependency_cannot_be_activated_by_any_entry` (unpublished closure member refused by the existing closure rule for both entries), `test_explicit_selection_keeps_the_hard_closure_failure` (manual entry hard-fails 409 unchanged). | Real cross-repo rejection matrix against a live Server session: **unexecuted**, staged. |
| T121-03 (偏好不越权编辑/执行；进行中 Run 不漂移；A/B 隔离) | 1, 3 | `test_preference_grants_no_content_or_script_rights` (preference in place, `assert_modify` and `save_skill_draft` still 403; projection carries no content), `test_put_creates_updates_and_lists_only_the_caller_rows` (user isolation), `test_new_versions_and_preference_changes_never_drift_a_frozen_run` (frozen Run keeps V1 after preference rewrite + V2 publication; new Run resolves V2 / no preferred Skill under the disabled preference), `test_per_user_preference_cap_and_availability_projection`. The B-account UI leg: companion report T121-03. | Real two-account session with live Runs: **unexecuted**, staged. |
| T121-04 (Run 开始后修改偏好并发布新版本，旧 Run 冻结、新 Run 按新选择) | 3, 4 | `test_new_versions_and_preference_changes_never_drift_a_frozen_run` covers the automated core: run 1 freezes V1 (`selection_role="preferred"`), the preference is disabled and V2 published, run 1's snapshots still carry V1, a new explicit run freezes V2, a new preference-less run carries no preferred Skill; `test_preference_origin_selects_closure_skill_and_audits_frozen_identity` pins the applied audit to the frozen version/hash. | Real cross-repo Run execution (actual continuing session): **unexecuted**, staged with the real-model Run environment. |

## Pending / risks

- Real-platform legs (real accounts A/B, real Runs, real model): **unexecuted**,
  staged on credentials; the contracts above are pinned by automated suites
  over real persistence, real storage layout, and the real run-preparation seam.
- Real Win7: **unexecuted**, owned by
  [#131](https://github.com/Orbit-Crew/iDeer/issues/131); modern-Windows
  results are not Win7 results.
- The persistence chain-head pins (`CURRENT_HEAD` and the head's parent) are
  maintained by hand in `test_migration_schema.py`; #119 missed them. This
  candidate realigns them; future migrations must keep updating the pins.
- Matching reads only THIS run request's user messages; clients that rely on
  server-side history re-send context explicitly. This is the documented,
  tested behavior (`message_text_from_input`).
- `dev-log/` remains an untracked local working directory in this repo
  (ticket copy at `dev-log/ticket-121.md`), exactly as at baseline.

## Installed combination acceptance, 2026-10-29 (modern Windows)

The staged installed-combination portion was executed on the paired Desktop
side and recorded in that repository:
`iDeer-Desktop/docs/acceptance/issue-121/installed-20261029.md` with sanitized
evidence under `docs/acceptance/issue-121/evidence/installed-20261029/`.
T121-01/03/04 passed with the real model: the hit run injected the frozen V1
identity (archived selection snapshot + `skill_trigger_preference_applied`
audit pin the exact run), the endpoint rejection matrix held with unchanged
stored rows, out-of-closure matches hard-refuse (409
`skill_outside_agent_closure`) and skip-audit per run, and a preference
rewrite plus V2 publication during a running run never drifted it. T121-02
is incomplete only on the visibility-reduction dependency. The three
UI-interaction legs are staged on the projection-refresh re-mount race with
the server-side contracts asserted. Bindings identical to the #112 section.
Win7 remains with #131.
