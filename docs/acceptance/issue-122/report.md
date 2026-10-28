---
id: issue-122-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 122 Server side of Skill execution environment declaration and content-bound script authorization — the per-Skill declaration contract, the SERVER-leg gated executor, the owner-scoped grant store, and the device-gated/basis-validated receipt contract
last-verified: 2026-10-27
verified-against: orch/issue-122-skill-exec-env working tree on top of a015b08b (#121 candidate); every acceptance command below was run against this tree
---

# Issue 122 Server acceptance

The Server candidate lives in the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-122-skill-exec-env`, stacked on a015b08b (#121). The Desktop repo
carries the same branch on top of 4d61488; its companion report is
`docs/acceptance/issue-122/report.md` in that repository. No issue closure,
no PR, and no installer are claimed by this report; `dist:win` stays a
recorded-pending step.

## Recorded existing rules (expected constants, read before implementing)

- R1 — **The frozen version bytes are the only identity**: a published Skill
  version directory re-hashes through `ResourceStorage.inspect_directory`;
  `create_run_skill_view` refuses any drift. The declaration therefore
  travels inside SKILL.md, never in a mutable side table.
- R2 — **The platform's only sanctioned server execution surface is
  `Sandbox.execute_command`** (local provider = fresh `subprocess.run`
  without a shell); the SERVER leg reuses exactly that and adds no new
  interpreter, no shell, no arbitrary command surface.
- R3 — **Package identity (#120)**: canonical package hash (sorted relative
  POSIX paths, length-prefixed); preview/confirm bind it. The declaration and
  its fingerprint extend the preview projection without changing the hash.
- R4 — **Device-gated consent (#114)**: `local.files.write`,
  `local.knowledge.search`, `local.knowledge.material` are decided on the
  originating Desktop only; #122 adds `local.skill.script` to that set.
- R5 — **Receipt archive field allowlist**: unknown receipt fields are
  refused (`RECEIPT_INVALID`); the device's new skill receipt fields are
  added to both sides of the contract in the same change.

## Implemented surface

- `backend/app/agentplatform/resources/skill_environment.py` (new): the
  bounded declaration contract — `execution-environment` front-matter with
  required `target ∈ {server, user_device}`, the five declared-need
  dimensions (`os`/`dependencies`/`software`/`tools`/`data`, ≤16 entries of
  ≤128 chars each), `requirements_fingerprint` (canonical-JSON SHA-256), the
  scripts-path normalizer, `os_matches`, and the pure content-bound grant
  matching (`evaluate_grant` → `SCRIPT_APPROVAL_REQUIRED` /
  `SCRIPT_REAUTHORIZATION_REQUIRED` / `SCRIPT_AUTHORIZATION_REVOKED` /
  `granted`). The Desktop mirrors this file verbatim (frozen cross-repo
  contract, same fingerprint bytes).
- `backend/app/agentplatform/resources/skill_validation.py`: the front-matter
  key set accepts `execution-environment` and validates its shape at
  draft/import surface; a malformed declaration is a rejected skill.
- `backend/app/agentplatform/resources/skill_package.py`: `build_preview`
  projects `execution_environment` and `requirements_hash` so a confirming
  user sees exactly what the scripts declare (#120 flow unchanged otherwise).
- `backend/app/agentplatform/resources/skill_script_execution.py` (new): the
  SERVER-leg gate and executor — package hash re-derivation
  (`SKILL_PACKAGE_CORRUPTED`), declaration presence
  (`SKILL_ENVIRONMENT_UNDECLARED`) and target match
  (`SKILL_ENVIRONMENT_MISMATCH`, never a downgrade), exact script digest,
  grant evaluation, then one `python3 <frozen script>` through the platform
  sandbox with a bounded timeout; the receipt binds version, package hash,
  script digest, requirements hash, and the authorization basis
  (`skill_script_authorization:<grant id>`).
- `backend/app/gateway/skill_script.py` (new): the owner-scoped
  `SkillScriptAuthorizationRepository` over `SkillScriptAuthorizationRow`;
  a grant's identity hashes (user, target, device, skill, script path,
  script digest, requirements hash); re-granting changed content/scope
  replaces the binding's row; revocation tombstones it.
- `backend/app/agentplatform/resource_models.py`: `SkillScriptAuthorizationRow`
  (`skill_script_authorizations` table; CHECK on target; unique per
  user+target+device+skill+script path; FKs to users_ext/resources).
- `backend/app/gateway/routers/resources.py`: `POST
  /{resource_id}/scripts/authorize` (verifies the confirmed script digest;
  a `user_device` skill refuses — its approvals live on the device),
  `GET /{resource_id}/scripts/authorizations`,
  `DELETE /{resource_id}/scripts/authorizations/{id}` (revoke), and `POST
  /{resource_id}/scripts/execute` (fixed refusal codes → 403/404/409 with
  nothing executed on refusal; success returns the bound receipt). The
  sandbox resolves through the platform provider
  (`_skill_script_sandbox`, injectable in tests); audits
  `skill_script_authorized` / `skill_script_executed` /
  `skill_script_authorization_revoked`.
- `backend/app/gateway/routers/devices.py`: `local.skill.script` joins the
  device-gated consent operations — a Web caller can never approve a device
  script execution.
- `backend/app/device_control/receipt_archive.py` + `protocol.py`: the
  receipt field allowlist accepts the four skill fields
  (`skill_id`, `skill_version`, `skill_content_hash`,
  `authorization_basis`), and a completed `local.skill.script` receipt
  without a valid basis (`approved` or `skill_script_grant:<64 hex>`) is
  refused as `RECEIPT_TASK_MISMATCH`.

## Scenario evidence

| Scenario | Status | Command / evidence |
| --- | --- | --- |
| T122-01 (per-skill declaration + representative SERVER execution) | passed (declaration leg + SERVER execution leg) | `./dev-log/issue-112/test.sh backend/tests/unit/gateway/test_skill_script_authorization.py -q` → 17 passed; `test_preview_projects_declared_environment`, `test_frontmatter_validation_accepts_and_rejects_declaration`, `test_executor_runs_representative_skill_and_binds_receipt` (real `python3` run, fixed output `weekly-report-fixed-ok`), `test_authorize_execute_revoke_roundtrip`. Per-skill environment lists for every migrated catalog skill: staged (needs the real catalog inventory; the contract and preview projection are in place). |
| T122-02 (default off; authorize; offline / dependency mismatch) | passed (default-off + authorize + dependency-mismatch legs) | `test_executor_default_off_without_grant` (sandbox untouched), `test_authorize_execute_revoke_roundtrip` (403 `SCRIPT_APPROVAL_REQUIRED` before any grant), `test_executor_refuses_cross_environment_and_corruption` (undeclared / `user_device` on Server), `test_device_declared_skill_refuses_server_authorization`. Device-offline retry: staged (needs a real offline device; the broker's existing `DEVICE_OFFLINE` path is unchanged and no downgrade path exists). |
| T122-03 (content / scope change vs prose-only change) | passed | `test_executor_reauthorizes_on_content_or_scope_change` (changed bytes → `SCRIPT_REAUTHORIZATION_REQUIRED`; changed declared dependency → re-authorization; prose-only version bump with same bytes+declaration → executes on the old grant), `test_regrant_after_content_change_replaces_binding`. |
| T122-04 (identity matrix; revoke; no exemption) | passed (SERVER legs) | `test_grants_do_not_cross_accounts_or_devices`, `test_other_account_needs_its_own_grant` (public/shared visibility never substitutes for the caller's own grant), revoke round-trip in `test_authorize_execute_revoke_roundtrip` (revoked → 403 `SCRIPT_AUTHORIZATION_REVOKED`, sandbox never touched). |
| T122-05 (corrupted package; interrupted receipt upload + recovery) | passed (corruption leg + basis validation); restart-recovery leg staged | `test_executor_refuses_cross_environment_and_corruption` (drifted bytes → `SKILL_PACKAGE_CORRUPTED` even with a valid grant); receipt-basis validation in `backend/tests/unit/device_control` (114 passed with the receipt archive suite). The interrupted-upload restart-recovery leg rides the existing durable outbox (device side, see the Desktop report) — a dedicated Server-restart exercise is staged. |

## Gates

- New/touched tests: `./dev-log/issue-112/test.sh
  backend/tests/unit/gateway/test_skill_script_authorization.py -q` →
  **17 passed, exit 0**.
- Neighbor drift: `test_resources_api_skill_import.py` +
  `test_skill_trigger_preferences.py` + the new file → **48 passed**;
  `backend/tests/unit/device_control` + new file → **114 passed**;
  `backend/tests/integration/persistence` + unit/persistence → **234
  passed, 10 skipped** (includes the migration-chain head pins bumped to
  `20261027_skill_script_auth` in this ticket).
- Full `backend/tests/integration` (e2e glob excluded, `-m "not live"`,
  `faulthandler_timeout=60`): **2295 passed, 91 skipped, 3 deselected,
  exit 0** — no failure left behind; the two pre-existing migration-head
  pins now name this ticket's head.
- Ruff on every touched file: **All checks passed**.

## Migration

`backend/app/agentplatform/persistence/migrations/versions/20261027_skill_script_authorizations.py`
(id `20261027_skill_script_auth`, down_revision
`20261027_skill_trigger_pref`) creates the grant table with its CHECK,
unique binding constraint, and owner/skill indexes; guarded by an
inspect-first existence check like the #121 migration.

## Pending

- Per-skill environment lists for the full migrated catalog (T122-01
  inventory leg) — staged; needs the real catalog inventory pass.
- Device-offline retry against a real offline device (T122-02) — staged.
- Server-restart receipt-recovery exercise for skill-script receipts
  (T122-05) — staged; the durable outbox and archive contracts are covered.
- Real-LLM / manual UI legs — staged as usual.
- Win7 compatibility verification — explicitly deferred to #131; modern
  Windows results above must not be read as Win7 results.
- `dist:win` packaging — recorded pending; not run in this ticket.
