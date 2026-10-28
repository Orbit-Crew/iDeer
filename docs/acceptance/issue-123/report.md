---
id: issue-123-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 123 Server side of the optional local Connector component install loop — the owner-scoped canonical connector identity (table, migration, and fixed-key registration API), the invisible-404 owner isolation, the frozen version↔manifest-hash binding, and the secrets-never-reach-the-Server request allowlist
last-verified: 2026-10-27
verified-against: orch/issue-123-connector-install working tree on top of b3c93587 (#122 candidate); every acceptance command below was run against this tree
---

# Issue 123 Server acceptance

The Server candidate lives in the isolated worktree
`/home/neowyh/orch-worktrees/issue-112-server`, branch
`orch/issue-123-connector-install`, stacked on b3c93587 (#122). The Desktop
repo carries the same branch on top of 9b35acb; its companion report is
`docs/acceptance/issue-123/report.md` in that repository. No issue closure,
no PR, and no installer are claimed by this report; `dist:win` stays a
recorded-pending step.

## Recorded existing rules (expected constants, read before implementing)

- R1 — **The platform's MCP surfaces are split by resource class**: the
  pre-existing `/api/mcp/config` router (`routers/mcp.py`) is the
  admin-gated configuration of the Server's OWN MCP tools
  (`ExtensionsConfig.McpServerConfig`); device-side connector components
  had no platform representation at all. #123 adds a separate, owner-scoped
  identity class instead of touching the admin config — no parallel MCP
  execution framework is introduced, and the device continues to run
  everything through the existing `local.mcp.*` machinery.
- R2 — **Owner-scoped by construction**: like every platform resource the
  row is keyed by `owner_id`; there is no visibility column and no share,
  publish, or sync endpoint, so another account cannot see, list, or run
  another user's connector (an unknown or foreign id is the same 404).
- R3 — **Frozen binding**: one `(owner, slug, version)` binds exactly one
  manifest hash; re-registering the same version with different content is
  `409 CONNECTOR_IDENTITY_CONFLICT`, a genuine upgrade declares a new
  version, and the same identity again is an idempotent confirmation.
- R4 — **Secrets never reach the Server**: the registration body is a
  fixed four-key allowlist (`extra="forbid"`), so command lines, entry
  paths, environments, and credentials are unrepresentable in the API
  contract itself.

## Implemented surface

- `backend/app/agentplatform/resource_models.py`:
  `ConnectorIdentityRow` (`connectors` table) — the platform-traceable
  identity of a component the user installed on their own device: `id`,
  `owner_id` (FK `users_ext`, CASCADE), `slug`, `display_name`, `version`,
  `manifest_hash`, timestamps; unique per `(owner_id, slug)`. It
  deliberately has no visibility column, no device binding, no runnable
  binding, and no credential column — the command line, environment and
  secrets stay on the installing device (AC2).
- `backend/app/agentplatform/persistence/migrations/versions/20261027_connectors.py`
  (id `20261027_connectors`, down_revision `20261027_skill_script_auth`):
  creates the table with its unique owner+slug constraint and owner index,
  guarded by an inspect-first existence check like the #121/#122
  migrations; the unified-chain head pins move to this revision.
- `backend/app/gateway/routers/connectors.py` (new, mounted in
  `app.py`/`routers/__init__.py`): the canonical identity API —
  - `POST /api/connectors`: fixed-key `ConnectorRegisterRequest`
    (`extra="forbid"`; slug grammar, semver grammar, SHA-256 manifest
    hash) → create or idempotently re-confirm the identity; the frozen
    binding conflict is `409 CONNECTOR_IDENTITY_CONFLICT`; logs carry the
    slug only, never request bodies or values;
  - `GET /api/connectors` / `GET /api/connectors/{id}`: the caller's own
    bounded projection (`connectorId`, `slug`, `displayName`, `version`,
    `manifestHash`) — nobody else's rows ever appear; a foreign or unknown
    id is 404, not 403;
  - `DELETE /api/connectors/{id}`: owner-gated removal (the device calls
    this only after its confirmed local removal).
- `backend/tests/integration/api/test_connectors_router.py` (new): the
  contract suite over an in-memory engine.

## Scenario evidence

| Scenario | Status | Command / evidence |
| --- | --- | --- |
| T123-01 (install loop evidence on the Desktop; Server-side identity traceability) | passed (identity leg) | `./dev-log/issue-112/test.sh backend/tests/integration/api/test_connectors_router.py -q` → 10 passed, exit 0: `test_register_creates_owner_scoped_canonical_identity` (identity registered, listed), `test_register_is_idempotent_for_same_frozen_identity`, `test_version_upgrade_updates_the_identity_row`. The install→execute loop itself is Desktop evidence (`local-runtime/tests/test_connector_install.py`, 15 passed — see the Desktop report). |
| T123-02 (failure categories actionable) | passed (Server legs: frozen-binding conflict + registration validation) | `test_same_version_with_different_content_is_a_conflict` (409 `CONNECTOR_IDENTITY_CONFLICT` — the device surfaces it as its own actionable category), `test_registration_validates_identity_fields` (bad slug/version/hash/display name → 422, list stays empty). Component/dependency/connection-failure injection legs are Desktop evidence (fixed `CONNECTOR_*` categories); the UI fault-injection session is staged. |
| T123-03 (platform resource + share state; B/D2 cannot use D1's binding; config not synced; sanitized logs) | passed (automated) | `test_other_account_cannot_see_or_list_foreign_connectors` (another account's list is empty; foreign id get/delete are 404 — invisible, never forbidden), `test_registration_rejects_credential_shaped_keys` (`command`/`env`/`token`/`entry`/`args`/`secrets` keys → 422; the runnable binding is unrepresentable), `test_registration_does_not_leak_payload_into_logs` (secret-bearing display name never appears in application logs), `test_registration_requires_authentication`. "Config not synced": the identity row has no runnable-binding column at all (schema above), so no second device can receive a runnable configuration; a second device of the same owner learns at most the identity. Real B/D2/D1 three-device exercise: staged. |
| T123-04 (privilege regressions; secrets never to Server/model) | passed (Server legs) | The same owner-isolation and allowlist tests above; deletion of a foreign identity is 404 (`test_other_account_cannot_see_or_list_foreign_connectors`, `test_owner_can_remove_the_identity`). The local DENY / directory-boundary / approval-no-exemption legs are Desktop evidence (policy-before-execution over the shared `local.mcp.*` dispatch). |

## Gates

- New/touched tests: `./dev-log/issue-112/test.sh
  backend/tests/integration/api/test_connectors_router.py -q` →
  **10 passed, exit 0**.
- Persistence + migration chain:
  `./dev-log/issue-112/test.sh backend/tests/integration/persistence -q` →
  **224 passed, 10 skipped, exit 0** (includes the migration-chain head
  pins moved to `20261027_connectors` in this ticket:
  `test_migration_schema.py`, `test_migration_0025_repair_run_change_seq.py`,
  `test_receipt_migration.py`).
- Full `backend/tests/integration` (e2e glob excluded, `-m "not live"`,
  `faulthandler_timeout=60`): **2305 passed, 91 skipped, 3 deselected,
  exit 0** — baseline 2295 + the 10 new connector tests; reconciles
  exactly, no failure left behind.
- Unit gateway+agentplatform: `./dev-log/issue-112/test.sh
  backend/tests/unit/gateway backend/tests/unit/agentplatform -q` →
  **6366 passed, 22 skipped, exit 0** (unchanged from the #122 baseline).
- Ruff on `backend`: **All checks passed**.

## Migration

`backend/app/agentplatform/persistence/migrations/versions/20261027_connectors.py`
(id `20261027_connectors`, down_revision `20261027_skill_script_auth`)
creates the owner-scoped identity table; guarded by an inspect-first
existence check like the prior migrations. The chain head is
single-parented on the #122 revision; all three head-pin tests name this
ticket's head.

## Pending

- Real A/B/D1/D2 three-device exercise (T123-03 cross-device legs) —
  staged; needs the isolated device fleet.
- Real-LLM leg (a Server-run task invoking an installed connector through
  the broker end to end) — staged as usual.
- Win7 compatibility verification — explicitly deferred to #131; modern
  Windows results (Desktop report) must not be read as Win7 results.
- `dist:win` packaging — recorded pending; not run in this ticket.
