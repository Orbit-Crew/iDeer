---
id: docs-testing-test-migration-ledger
kind: reference
status: current
owner: test maintainers
scope: living ledger and deletion gate for test moves and deletions — per-batch records of removed/kept paths, replacement strength, and validation commands; authority together with coverage-matrix.md for test-coverage-and-migration
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ c55cd37de
---

# Test Migration Ledger

> audience: testers, developers, release maintainers<br>
> status: current<br>
> owner: test maintainers<br>
> last-verified: 2026-10-04<br>
> canonical-path: `docs/testing/test-migration-ledger.md`

This ledger is the deletion and move gate for the test-suite reorganization.
Do not delete an old test file unless this file records an equal or stronger
replacement assertion and the validation command for that batch.

## 迁移方法

1. Locate the test's behavior owner and the destination that matches its layer
   and execution owner; check imports, test configuration, markers, fixtures,
   and path-sensitive behavior before treating another copy as equivalent.
2. Compare the removed assertions with the keeper. Preserve every behavior
   check, or add an equal or stronger replacement before deleting the old test.
3. Run the paired baseline and keeper commands needed to establish equivalence;
   after a move, run `python3 scripts/test_inventory.py` and update the
   inventory when ownership or collection changes.
4. Record the removed and retained paths, assertion mapping, relevant runner
   configuration, validation commands and actual results under a dated batch.
   A deletion without this evidence is not authorized by the ledger.

The batch entries below are historical examples. Use only the entry relevant
to the test being moved; they do not replace validation on the current
candidate.

## Batch 2026-10-13: backend/tests root↔subdir dedup — gateway (batch 2 of 8)

Same protocol as batch 1. Validation: `uv run --no-sync pytest tests/unit/gateway
-q -m "not serial and not requires_llm and not live and not external"` →
3075 passed / 18 skipped; ruff check/format clean.

| Removed root copy | Kept canonical path | Assertion mapping / replacement strength | Validation |
| --- | --- | --- | --- |
| `tests/test_auth.py` (50 identical + 3 drifted + 40 root-only) | `tests/unit/gateway/test_auth.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_auth_middleware.py` (17 identical + 2 drifted + 14 root-only) | `tests/unit/gateway/test_auth_middleware.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_auth_type_system.py` (45 identical + 4 drifted + 21 root-only) | `tests/unit/gateway/test_auth_type_system.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_clarification_middleware.py` (9 identical + 1 drifted + 53 root-only) | `tests/unit/gateway/test_clarification_middleware.py` | root variant wins on drifted names; 1 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_csrf_middleware.py` (3 identical + 12 drifted + 3 root-only) | `tests/unit/gateway/test_csrf_middleware.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_dynamic_context_middleware.py` (7 identical + 5 drifted + 32 root-only) | `tests/unit/gateway/test_dynamic_context_middleware.py` | root variant wins on drifted names; 0 class methods + 2 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_feedback.py` (25 identical + 0 drifted + 5 root-only) | `tests/unit/gateway/test_feedback.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_gateway_config_freshness.py` (4 identical + 1 drifted + 1 root-only) | `tests/unit/gateway/test_gateway_config_freshness.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_gateway_docs_toggle.py` (10 identical + 0 drifted + 1 root-only) | `tests/unit/gateway/test_gateway_docs_toggle.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_gateway_lifespan_shutdown.py` (0 identical + 1 drifted + 12 root-only) | `tests/unit/gateway/test_gateway_lifespan_shutdown.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_gateway_services.py` (29 identical + 7 drifted + 135 root-only) | `tests/unit/gateway/test_gateway_services.py` | root variant wins on drifted names; 0 class methods + 3 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_guardrail_middleware.py` (25 identical + 0 drifted + 24 root-only) | `tests/unit/gateway/test_guardrail_middleware.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_harness_boundary.py` (1 identical + 0 drifted + 0 root-only) | `tests/unit/gateway/test_harness_boundary.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_initialize_admin.py` (6 identical + 6 drifted + 2 root-only) | `tests/unit/gateway/test_initialize_admin.py` | root variant wins on drifted names; 0 class methods + 3 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_internal_auth.py` (0 identical + 2 drifted + 2 root-only) | `tests/unit/gateway/test_internal_auth.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_langgraph_auth.py` (26 identical + 1 drifted + 9 root-only) | `tests/unit/gateway/test_langgraph_auth.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir; `__file__` .parent chain normalized for unit/gateway depth | both copies green on the same candidate pre-merge |
| `tests/test_lead_agent_prompt.py` (7 identical + 8 drifted + 14 root-only) | `tests/unit/gateway/test_lead_agent_prompt.py` | root variant wins on drifted names; 0 class methods + 2 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_llm_error_handling_middleware.py` (9 identical + 5 drifted + 63 root-only) | `tests/unit/gateway/test_llm_error_handling_middleware.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_loop_detection_middleware.py` (59 identical + 4 drifted + 54 root-only) | `tests/unit/gateway/test_loop_detection_middleware.py` | root variant wins on drifted names; 2 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_safety_finish_reason_middleware.py` (31 identical + 1 drifted + 10 root-only) | `tests/unit/gateway/test_safety_finish_reason_middleware.py` | root variant wins on drifted names; 1 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_security_scanner.py` (17 identical + 0 drifted + 10 root-only) | `tests/unit/gateway/test_security_scanner.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_subagent_executor.py` (0 identical + 0 drifted + 147 root-only) | `tests/unit/gateway/test_subagent_executor.py` | root variant wins on drifted names; 0 class methods + 29 module defs carried from subdir; 3 stale-API carried tests dropped (superseded by root TestAgentConstruction evolved equivalents) | both copies green on the same candidate pre-merge |
| `tests/test_subagent_limit_middleware.py` (12 identical + 1 drifted + 12 root-only) | `tests/unit/gateway/test_subagent_limit_middleware.py` | root variant wins on drifted names; 2 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_subagent_prompt_security.py` (3 identical + 3 drifted + 3 root-only) | `tests/unit/gateway/test_subagent_prompt_security.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_subagent_timeout_config.py` (44 identical + 3 drifted + 8 root-only) | `tests/unit/gateway/test_subagent_timeout_config.py` | root variant wins on drifted names; 1 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_subagent_token_collector.py` (12 identical + 0 drifted + 2 root-only) | `tests/unit/gateway/test_subagent_token_collector.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_title_middleware_core_logic.py` (12 identical + 5 drifted + 32 root-only) | `tests/unit/gateway/test_title_middleware_core_logic.py` | root variant wins on drifted names; 1 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_token_usage_middleware.py` (0 identical + 0 drifted + 11 root-only) | `tests/unit/gateway/test_token_usage_middleware.py` | root variant wins on drifted names; 35 class methods + 7 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_uploads_manager.py` (25 identical + 0 drifted + 6 root-only) | `tests/unit/gateway/test_uploads_manager.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_uploads_middleware_core_logic.py` (24 identical + 4 drifted + 24 root-only) | `tests/unit/gateway/test_uploads_middleware_core_logic.py` | root variant wins on drifted names; 10 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_user_context.py` (10 identical + 0 drifted + 16 root-only) | `tests/unit/gateway/test_user_context.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_view_image_middleware.py` (22 identical + 5 drifted + 16 root-only) | `tests/unit/gateway/test_view_image_middleware.py` | root variant wins on drifted names; 2 class methods + 2 module defs carried from subdir | both copies green on the same candidate pre-merge |

## Batch 2026-10-13: backend/tests root↔subdir dedup — runtime (batch 3 of 8)

Same protocol as batch 1. Validation: `uv run --no-sync pytest tests/unit/runtime -q -m "not serial and not requires_llm and not live and not external"` → 1380 passed / 8 skipped; ruff check/format clean.

| Removed root copy | Kept canonical path | Assertion mapping / replacement strength | Validation |
| --- | --- | --- | --- |
| `tests/test_cancel_run_idempotent.py` (4 identical + 3 drifted + 0 root-only) | `tests/unit/runtime/test_cancel_run_idempotent.py` | root variant wins on drifted names; 2 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_checkpointer.py` (19 identical + 7 drifted + 30 root-only) | `tests/unit/runtime/test_checkpointer.py` | root variant wins on drifted names; 1 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_detect_thread_boundaries.py` (4 identical + 2 drifted + 8 root-only) | `tests/unit/runtime/test_detect_thread_boundaries.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_gateway_run_recovery.py` (0 identical + 2 drifted + 4 root-only) | `tests/unit/runtime/test_gateway_run_recovery.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_gateway_runtime_cleanup.py` (5 identical + 1 drifted + 10 root-only) | `tests/unit/runtime/test_gateway_runtime_cleanup.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_run_event_store.py` (46 identical + 0 drifted + 44 root-only) | `tests/unit/runtime/test_run_event_store.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_run_manager.py` (38 identical + 5 drifted + 31 root-only) | `tests/unit/runtime/test_run_manager.py` | root variant wins on drifted names; 0 class methods + 56 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_run_repository.py` (25 identical + 9 drifted + 35 root-only) | `tests/unit/runtime/test_run_repository.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_run_worker_rollback.py` (12 identical + 5 drifted + 91 root-only) | `tests/unit/runtime/test_run_worker_rollback.py` | root variant wins on drifted names; 0 class methods + 5 module defs carried from subdir; carried test id literals adapted to the root helper defaults (ckpt-1) | both copies green on the same candidate pre-merge |
| `tests/test_safety_finish_reason_graph_integration.py` (3 identical + 0 drifted + 2 root-only) | `tests/unit/runtime/test_safety_finish_reason_graph_integration.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_serialization.py` (16 identical + 1 drifted + 9 root-only) | `tests/unit/runtime/test_serialization.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_stream_bridge.py` (10 identical + 1 drifted + 47 root-only) | `tests/unit/runtime/test_stream_bridge.py` | root variant wins on drifted names; 0 class methods + 2 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_thread_data_middleware.py` (4 identical + 0 drifted + 2 root-only) | `tests/unit/runtime/test_thread_data_middleware.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_thread_meta_repo.py` (46 identical + 1 drifted + 20 root-only) | `tests/unit/runtime/test_thread_meta_repo.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_thread_run_messages_pagination.py` (9 identical + 1 drifted + 8 root-only) | `tests/unit/runtime/test_thread_run_messages_pagination.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_thread_state_reducers.py` (10 identical + 2 drifted + 33 root-only) | `tests/unit/runtime/test_thread_state_reducers.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_thread_token_usage.py` (0 identical + 2 drifted + 7 root-only) | `tests/unit/runtime/test_thread_token_usage.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_token_usage.py` (14 identical + 0 drifted + 0 root-only) | `tests/unit/runtime/test_token_usage.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_worker_langfuse_metadata.py` (1 identical + 3 drifted + 2 root-only) | `tests/unit/runtime/test_worker_langfuse_metadata.py` | root variant wins on drifted names; 4 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |

## Batch 2026-10-13: backend/tests root↔subdir dedup — models/persistence (batch 4 of 8)

Same protocol as batch 1. Validation: `uv run --no-sync pytest tests/unit/models tests/unit/persistence -q -m "not serial and not requires_llm and not live and not external"` → 1093 passed / 1 skipped; ruff check/format clean.

| Removed root copy | Kept canonical path | Assertion mapping / replacement strength | Validation |
| --- | --- | --- | --- |
| `tests/test_client.py` (91 identical + 52 drifted + 46 root-only) | `tests/unit/models/test_client.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_client_langfuse_metadata.py` (1 identical + 2 drifted + 5 root-only) | `tests/unit/models/test_client_langfuse_metadata.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_client_live.py` (19 identical + 0 drifted + 0 root-only) | `tests/unit/models/test_client_live.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_codex_provider.py` (21 identical + 0 drifted + 5 root-only) | `tests/unit/models/test_codex_provider.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_infoquest_client.py` (0 identical + 0 drifted + 22 root-only) | `tests/unit/models/test_infoquest_client.py` | root variant wins on drifted names; 11 class methods + 10 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_lead_agent_model_resolution.py` (11 identical + 6 drifted + 31 root-only) | `tests/unit/models/test_lead_agent_model_resolution.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_mindie_provider.py` (41 identical + 0 drifted + 4 root-only) | `tests/unit/models/test_mindie_provider.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_model_config.py` (2 identical + 0 drifted + 2 root-only) | `tests/unit/models/test_model_config.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_model_factory.py` (31 identical + 4 drifted + 34 root-only) | `tests/unit/models/test_model_factory.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_patched_deepseek.py` (9 identical + 1 drifted + 0 root-only) | `tests/unit/models/test_patched_deepseek.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_patched_minimax.py` (1 identical + 3 drifted + 1 root-only) | `tests/unit/models/test_patched_minimax.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_persistence_scaffold.py` (21 identical + 1 drifted + 17 root-only) | `tests/unit/persistence/test_persistence_scaffold.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_vllm_provider.py` (0 identical + 0 drifted + 16 root-only) | `tests/unit/models/test_vllm_provider.py` | root variant wins on drifted names; 0 class methods + 8 module defs carried from subdir | both copies green on the same candidate pre-merge |

## Batch 2026-10-13: backend/tests root↔subdir dedup — tools (batch 5 of 8)

Same protocol as batch 1. Validation: `uv run --no-sync pytest tests/unit/tools -q -m "not serial and not requires_llm and not live and not external"` → 1981 passed / 2 skipped; ruff check/format clean.

| Removed root copy | Kept canonical path | Assertion mapping / replacement strength | Validation |
| --- | --- | --- | --- |
| `tests/test_dangling_tool_call_middleware.py` (24 identical + 2 drifted + 32 root-only) | `tests/unit/tools/test_dangling_tool_call_middleware.py` | root variant wins on drifted names; 1 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_deferred_tool_promotion_real_llm.py` (0 identical + 1 drifted + 0 root-only) | `tests/unit/tools/test_deferred_tool_promotion_real_llm.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_file_conversion.py` (18 identical + 12 drifted + 2 root-only) | `tests/unit/tools/test_file_conversion.py` | root variant wins on drifted names; 5 class methods + 2 module defs carried from subdir; spliced docx/xlsx routing tests re-bound to the legacy app.agentplatform seam via alias import | both copies green on the same candidate pre-merge |
| `tests/test_invoke_acp_agent_tool.py` (7 identical + 9 drifted + 3 root-only) | `tests/unit/tools/test_invoke_acp_agent_tool.py` | root variant wins on drifted names; 0 class methods + 14 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_jina_client.py` (12 identical + 1 drifted + 7 root-only) | `tests/unit/tools/test_jina_client.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_mcp_cache.py` (0 identical + 0 drifted + 19 root-only) | `tests/unit/tools/test_mcp_cache.py` | root variant wins on drifted names; 0 class methods + 6 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_mcp_client_config.py` (7 identical + 1 drifted + 6 root-only) | `tests/unit/tools/test_mcp_client_config.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_mcp_config_secrets.py` (18 identical + 0 drifted + 82 root-only) | `tests/unit/tools/test_mcp_config_secrets.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_mcp_oauth.py` (3 identical + 0 drifted + 9 root-only) | `tests/unit/tools/test_mcp_oauth.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_mcp_session_pool.py` (2 identical + 12 drifted + 46 root-only) | `tests/unit/tools/test_mcp_session_pool.py` | root variant wins on drifted names; 0 class methods + 15 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_mcp_sync_wrapper.py` (5 identical + 1 drifted + 3 root-only) | `tests/unit/tools/test_mcp_sync_wrapper.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_present_file_tool_core_logic.py` (4 identical + 0 drifted + 1 root-only) | `tests/unit/tools/test_present_file_tool_core_logic.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_serper_tools.py` (18 identical + 0 drifted + 78 root-only) | `tests/unit/tools/test_serper_tools.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_setup_agent_tool.py` (0 identical + 2 drifted + 8 root-only) | `tests/unit/tools/test_setup_agent_tool.py` | root variant wins on drifted names; 0 class methods + 8 module defs carried from subdir; sub _call_setup_agent/_make_runtime helpers carried under aliases for the carried user-store class | both copies green on the same candidate pre-merge |
| `tests/test_skill_manage_tool.py` (0 identical + 0 drifted + 10 root-only) | `tests/unit/tools/test_skill_manage_tool.py` | root variant wins on drifted names; 0 class methods + 9 module defs carried from subdir; sub autouse isolation fixture scoped to the carried classes only | both copies green on the same candidate pre-merge |
| `tests/test_task_tool_usage_recorder.py` (8 identical + 0 drifted + 1 root-only) | `tests/unit/tools/test_task_tool_usage_recorder.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_tool_args_schema_no_pydantic_warning.py` (3 identical + 0 drifted + 4 root-only) | `tests/unit/tools/test_tool_args_schema_no_pydantic_warning.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_tool_call_metadata.py` (0 identical + 0 drifted + 14 root-only) | `tests/unit/tools/test_tool_call_metadata.py` | root variant wins on drifted names; 0 class methods + 9 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_tool_deduplication.py` (5 identical + 1 drifted + 1 root-only) | `tests/unit/tools/test_tool_deduplication.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_tool_error_handling_middleware.py` (9 identical + 1 drifted + 30 root-only) | `tests/unit/tools/test_tool_error_handling_middleware.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_tool_output_truncation.py` (36 identical + 0 drifted + 26 root-only) | `tests/unit/tools/test_tool_output_truncation.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_tracing_factory.py` (5 identical + 0 drifted + 0 root-only) | `tests/unit/tools/test_tracing_factory.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_tracing_metadata.py` (9 identical + 0 drifted + 2 root-only) | `tests/unit/tools/test_tracing_metadata.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_update_agent_tool.py` (0 identical + 0 drifted + 27 root-only) | `tests/unit/tools/test_update_agent_tool.py` | root variant wins on drifted names; 0 class methods + 2 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_view_image_tool.py` (6 identical + 1 drifted + 1 root-only) | `tests/unit/tools/test_view_image_tool.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |

## Batch 2026-10-13: backend/tests root↔subdir dedup — sandbox (batch 6 of 8)

Same protocol as batch 1. Validation: `uv run --no-sync pytest tests/unit/sandbox tests/integration/sandbox -q -m "not serial and not requires_llm and not live and not external"` → 2144 passed / 10 skipped; ruff check/format clean.

| Removed root copy | Kept canonical path | Assertion mapping / replacement strength | Validation |
| --- | --- | --- | --- |
| `tests/test_aio_sandbox.py` (13 identical + 3 drifted + 43 root-only) | `tests/integration/sandbox/test_aio_sandbox.py` | root variant wins on drifted names; 1 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_aio_sandbox_local_backend.py` (13 identical + 1 drifted + 82 root-only) | `tests/integration/sandbox/test_aio_sandbox_local_backend.py` | root variant wins on drifted names; 0 class methods + 2 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_aio_sandbox_readiness.py` (0 identical + 3 drifted + 2 root-only) | `tests/integration/sandbox/test_aio_sandbox_readiness.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_docker_sandbox_mode_detection.py` (6 identical + 0 drifted + 20 root-only) | `tests/integration/sandbox/test_docker_sandbox_mode_detection.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_local_sandbox_encoding.py` (5 identical + 3 drifted + 13 root-only) | `tests/unit/sandbox/test_local_sandbox_encoding.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_local_sandbox_provider_mounts.py` (39 identical + 5 drifted + 11 root-only) | `tests/unit/sandbox/test_local_sandbox_provider_mounts.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_local_sandbox_virtual_path_contract.py` (14 identical + 6 drifted + 4 root-only) | `tests/unit/sandbox/test_local_sandbox_virtual_path_contract.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_provisioner_pvc_volumes.py` (2 identical + 4 drifted + 53 root-only) | `tests/integration/sandbox/test_provisioner_pvc_volumes.py` | root variant wins on drifted names; 12 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_remote_sandbox_backend.py` (19 identical + 1 drifted + 14 root-only) | `tests/integration/sandbox/test_remote_sandbox_backend.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_runtime_paths.py` (5 identical + 4 drifted + 3 root-only) | `tests/unit/sandbox/test_runtime_paths.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_sandbox_audit_middleware.py` (47 identical + 0 drifted + 25 root-only) | `tests/unit/sandbox/test_sandbox_audit_middleware.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_sandbox_middleware.py` (2 identical + 4 drifted + 30 root-only) | `tests/unit/sandbox/test_sandbox_middleware.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_sandbox_orphan_reconciliation.py` (11 identical + 14 drifted + 65 root-only) | `tests/integration/sandbox/test_sandbox_orphan_reconciliation.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_sandbox_orphan_reconciliation_e2e.py` (3 identical + 0 drifted + 0 root-only) | `tests/integration/api/test_sandbox_orphan_reconciliation_e2e.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_sandbox_search_tools.py` (15 identical + 4 drifted + 21 root-only) | `tests/unit/sandbox/test_sandbox_search_tools.py` | root variant wins on drifted names; 0 class methods + 5 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_sandbox_tools_security.py` (67 identical + 24 drifted + 28 root-only) | `tests/unit/sandbox/test_sandbox_tools_security.py` | root variant wins on drifted names; 0 class methods + 3 module defs carried from subdir; carried test path literals adapted to the root _THREAD_DATA binding (/tmp/deer-flow) | both copies green on the same candidate pre-merge |

## Batch 2026-10-13: backend/tests root↔subdir dedup — skills/scripts (batch 7 of 8)

Same protocol as batch 1. Validation: `uv run --no-sync pytest tests/unit/skills tests/unit/scripts -q -m "not serial and not requires_llm and not live and not external"` → 1739 passed / 1 skipped; ruff check/format clean.

| Removed root copy | Kept canonical path | Assertion mapping / replacement strength | Validation |
| --- | --- | --- | --- |
| `tests/test_acp_config.py` (13 identical + 1 drifted + 4 root-only) | `tests/unit/scripts/test_acp_config.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_app_config_reload.py` (8 identical + 0 drifted + 27 root-only) | `tests/unit/scripts/test_app_config_reload.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_check_script.py` (0 identical + 3 drifted + 5 root-only) | `tests/unit/scripts/test_check_script.py` | root variant wins on drifted names; 0 class methods + 4 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_config_version.py` (6 identical + 0 drifted + 7 root-only) | `tests/unit/scripts/test_config_version.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_dev_entrypoint.py` (8 identical + 1 drifted + 9 root-only) | `tests/unit/scripts/test_dev_entrypoint.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_doctor.py` (32 identical + 2 drifted + 39 root-only) | `tests/unit/scripts/test_doctor.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_local_skill_storage_write.py` (11 identical + 3 drifted + 7 root-only) | `tests/unit/skills/test_local_skill_storage_write.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_logging_level_from_config.py` (6 identical + 0 drifted + 1 root-only) | `tests/unit/scripts/test_logging_level_from_config.py` | root variant wins on drifted names; 1 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_setup_wizard.py` (29 identical + 0 drifted + 20 root-only) | `tests/unit/scripts/test_setup_wizard.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_skill_creator_quick_validate.py` (0 identical + 0 drifted + 6 root-only) | `tests/unit/skills/test_skill_creator_quick_validate.py` | root variant wins on drifted names; 0 class methods + 6 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_skills_installer.py` (28 identical + 3 drifted + 21 root-only) | `tests/unit/skills/test_skills_installer.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_skills_loader.py` (3 identical + 1 drifted + 4 root-only) | `tests/unit/skills/test_skills_loader.py` | root variant wins on drifted names; 0 class methods + 2 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_skills_validation.py` (19 identical + 1 drifted + 6 root-only) | `tests/unit/skills/test_skills_validation.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir; stale list-only allowed-tools rejection test dropped (superseded by root test_allows_allowed_tools_string) | both copies green on the same candidate pre-merge |
| `tests/test_subagent_skills_config.py` (42 identical + 0 drifted + 0 root-only) | `tests/unit/skills/test_subagent_skills_config.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_tracing_config.py` (7 identical + 0 drifted + 0 root-only) | `tests/unit/scripts/test_tracing_config.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |

## Batch 2026-10-13: backend/tests root↔subdir dedup — channels/memory/workflows (batch 1 of 8)

Ticket #66 under [the dedup decision](../decisions/2026-10-13-backend-test-dedup.md):
for every root ↔ `{unit,integration,contracts}` same-name pair the ROOT copy is
the merge base and is deleted after its content lands at the canonical subdir
path (`__file__` depths normalized); subdir-only tests are carried over
(spliced into same-named classes or appended as module defs). On drifted
same-name tests the root variant wins: both variants were green on the same
candidate before the merge, so no retained assertion is weaker than what the
standard lane ran. Module-global directives (`pytestmark`, `pytest_plugins`)
are not carried from the sub copy. Per-file merge reports (spliced methods,
carried defs, root-wins conflicts, import shadowing) are archived in the
ticket's `dev-log/batch6/merge_report_*.json`.

| Removed root copy | Kept canonical path | Assertion mapping / replacement strength | Validation |
| --- | --- | --- | --- |
| `tests/test_channel_file_attachments.py` (16 identical + 4 drifted + 28 root-only) | `tests/unit/channels/test_channel_file_attachments.py` | root variant wins on drifted names; 18 class methods + 2 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_channels.py` (74 identical + 19 drifted + 259 root-only) | `tests/unit/channels/test_channels.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_dingtalk_channel.py` (66 identical + 12 drifted + 42 root-only) | `tests/unit/channels/test_dingtalk_channel.py` | root variant wins on drifted names; 0 class methods + 37 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_discord_channel.py` (0 identical + 0 drifted + 23 root-only) | `tests/unit/channels/test_discord_channel.py` | root variant wins on drifted names; 0 class methods + 22 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_feishu_parser.py` (5 identical + 1 drifted + 25 root-only) | `tests/unit/workflows/test_feishu_parser.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_memory_prompt_injection.py` (10 identical + 1 drifted + 24 root-only) | `tests/unit/memory/test_memory_prompt_injection.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_memory_queue.py` (0 identical + 10 drifted + 16 root-only) | `tests/unit/memory/test_memory_queue.py` | root variant wins on drifted names; 0 class methods + 2 module defs carried from subdir; appended legacy-API test rewritten against `app.agentplatform.legacy.memory.queue` alias | both copies green on the same candidate pre-merge |
| `tests/test_memory_storage.py` (0 identical + 11 drifted + 5 root-only) | `tests/unit/memory/test_memory_storage.py` | root variant wins on drifted names; 0 class methods + 1 module defs carried from subdir; appended legacy-API tests rewritten against `app.agentplatform.legacy.memory.storage` alias | both copies green on the same candidate pre-merge |
| `tests/test_memory_updater.py` (13 identical + 33 drifted + 36 root-only) | `tests/unit/memory/test_memory_updater.py` | root variant wins on drifted names; 0 class methods + 2 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_memory_upload_filtering.py` (22 identical + 4 drifted + 7 root-only) | `tests/unit/memory/test_memory_upload_filtering.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_skills_parser.py` (13 identical + 3 drifted + 14 root-only) | `tests/unit/workflows/test_skills_parser.py` | root variant wins on drifted names; 0 class methods + 0 module defs carried from subdir | both copies green on the same candidate pre-merge |
| `tests/test_wechat_channel.py` (18 identical + 11 drifted + 12 root-only) | `tests/unit/channels/test_wechat_channel.py` | root variant wins on drifted names; 0 class methods + 85 module defs carried from subdir | both copies green on the same candidate pre-merge |

Validation (this batch):

```bash
cd backend
UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests PYTHONIOENCODING=utf-8 PYTHONUTF8=1 \
  uv run --no-sync pytest tests/unit/channels tests/unit/memory tests/unit/workflows \
  -q -m "not serial and not requires_llm and not live and not external"
# 2560 passed
uv run --no-sync ruff check tests/unit/channels tests/unit/memory tests/unit/workflows
uv run --no-sync ruff format --check tests/unit/channels tests/unit/memory tests/unit/workflows
```

## Batch 2026-10-03: Thread initialization ordering duplicate

Removed `frontend/tests/e2e/workflows/chat-thread-init-ordering.spec.ts` and
retained the upstream-path copy at
`frontend/tests/e2e/chat-thread-init-ordering.spec.ts`. The files contain the
same Playwright test, request event capture, 250 ms stream delay, and assertions
that neither `/history` nor `GET /runs` starts before `POST /runs/stream`. Their
only source differences were equivalent relative imports to the same mock API
module and the issue URL in a comment. Both tests use the same Playwright
configuration, Chromium project, page fixture, mock handlers, and runtime.
There are no markers or path-sensitive behaviors.

GitNexus returned `UNKNOWN` with no resolved callers for the removed path. A
repository text search found no imports or active configuration references;
the remaining path references are the specification's keeper/removal table and
its paired baseline command. Full `detect-changes --scope all` mapped the two
documentation files but did not list the deleted test path; the Git diff has
three changed paths including that deletion. The graph omission is recorded as
an unresolved index limitation, not as evidence of no effect. The T1
result-consistency record confirms its
focused regression and static check passed, so the prerequisite is satisfied.

The paired Chromium baseline first collected exactly two tests, then passed
both tests in 22.7 seconds in the allowed browser/socket environment. After
deletion, the retained-file command passed 1 test. The preflight exited 0 with
Chromium launch and local socket bind ready. The removed test's assertions map
one-to-one to the retained test:

| Removed assertion | Retained assertion |
| --- | --- |
| `POST /runs/stream` is issued during send | Same request assertion |
| No `GET /history` request precedes stream initiation | Same sequence assertion |
| No `GET /runs` request precedes stream initiation | Same sequence assertion |
| Delay stream response by 250 ms to expose early initialization requests | Same delayed route handlers |

Validation used the locked frontend dependencies and unchanged Chromium test
configuration:

```bash
CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test \
  tests/e2e/chat-thread-init-ordering.spec.ts \
  tests/e2e/workflows/chat-thread-init-ordering.spec.ts \
  --project=chromium --retries=0 --list
CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test \
  tests/e2e/chat-thread-init-ordering.spec.ts \
  tests/e2e/workflows/chat-thread-init-ordering.spec.ts \
  --project=chromium --retries=0
CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test \
  tests/e2e/chat-thread-init-ordering.spec.ts \
  --project=chromium --retries=0
```

The collected count changed from 2 to 1. No test was skipped, weakened, or
removed from the formal lane configuration.

## Batch 2026-10-03: Serialization test duplicate

Removed `backend/tests/unit/runtime/test_serialize_message_content.py` and
retained the upstream-path copy at `backend/tests/test_serialize_message_content.py`.
The files have the same 13 pytest cases, fixtures, imports, markers, and execution
semantics. Their only source difference was the GitHub issue URL in the module
docstring. Both run from `backend/` and use the same `backend/tests/conftest.py`
fixture context; neither uses `__file__`, package-relative imports, or path-based
behavior. No marker or other execution option exists in either file. GitNexus
could not resolve upstream callers for the removed test classes (`UNKNOWN`); a
repository text search found no imports or calls to them. The remaining exact
path references outside this ledger are this specification and its historical
paired command.

The 13 removed test cases map one-to-one to the cases retained in the upstream
path:

| Removed case | Retained case | Assertion retained |
| --- | --- | --- |
| `TestSerializeToolMessageContent.test_string_content` | Same case | `"ok"` content and `"tool"` type |
| `test_list_of_blocks_content` | Same case | Extracted text, with no `[` or `{` repr artifacts |
| `test_multiple_text_blocks` | Same case | Text blocks joined with a newline |
| `test_string_chunks_are_joined_without_newlines` | Same case | String chunks joined contiguously |
| `test_mixed_string_chunks_and_blocks` | Same case | String chunks contiguous; text block separated by newline |
| `test_mixed_blocks_with_non_text` | Same case | Text retained while image block is skipped |
| `test_empty_list_content` | Same case | Empty list serializes to empty text |
| `test_plain_string_in_list` | Same case | Bare string in list is retained |
| `test_unknown_content_type_falls_back` | Same case | Integer content falls back to `"42"` |
| `TestExtractText.test_string_passthrough` | Same case | String passes through unchanged |
| `test_list_text_blocks` | Same case | Text block content is extracted |
| `test_empty_list` | Same case | Empty list extracts to empty text |
| `test_fallback_non_iterable` | Same case | Non-iterable integer falls back to `"123"` |

Current-candidate validation used the preconfigured backend Python 3.12
environment, locked dependencies, and `UV_CACHE_DIR=/tmp/deer-flow-uv-cache`.
The test-scope patch fingerprint is
`a9d23fb8bdeb33713871702c2f2e3ab4069e4c9684397565578b6dfc92d2633f`,
computed by `git diff --binary 83eaecb879e28d8f726cc7d114e59f5735e7da3f --
backend/tests/unit/runtime/test_serialize_message_content.py | sha256sum`.
The paired baseline command exited 0 with 26 passed in 7.66s:

```bash
UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests \
  uv run --no-sync pytest tests/test_serialize_message_content.py \
  tests/unit/runtime/test_serialize_message_content.py -q
```

After deletion, the keeper command exited 0 with 13 passed in 8.33s. The narrow
static check, `UV_CACHE_DIR=/tmp/deer-flow-uv-cache uv run --no-sync ruff check
tests/test_serialize_message_content.py`, exited 0 (`All checks passed!`).
`python3 scripts/test_inventory.py --collect --json` exited 0 in 32.28s.
Its JSON reported 13 collected keeper nodes at the upstream path and no
duplicate-path entry. No other root-level test was moved or deleted.

GitNexus impact for both deleted test classes returned `UNKNOWN` with zero
resolved callers. Text search found no imports or calls; outside this ledger,
the exact removed-path references remain only in the specification and its
baseline command. Both
MCP and CLI `detect_changes --scope all` completed without partial or
truncated output and mapped 2 documentation files, 4 symbols, and 0 processes.
The worktree diff contains 3 tracked files, including the removed test path;
GitNexus did not list that deleted path. Its impact therefore remains
`UNKNOWN`, not zero. The paired 26-to-13 run and one-to-one mapping above
provide the behavior evidence for this deletion.

## Batch 2026-10-03: Message merge duplicate

Removed `frontend/tests/unit/core/threads/message-merge-local.test.ts` and
retained `frontend/tests/unit/core/threads/message-merge.test.ts`, the upstream
Rstest path. The nine Vitest cases have one-to-one equivalents in the retained
file. Both exercise the same exported message merge or optimistic visibility
behavior with the same input and expected result. The retained file also covers
protected early messages, history/live ordering, historical run metadata,
pagination, summarization, and replay ordering, including its parameterized
cases.

| Removed Vitest case | Retained Rstest case | Behavior kept |
| --- | --- | --- |
| `mergeMessages removes duplicate messages already present in history` | Same case | Duplicate human and AI messages appear once |
| `mergeMessages lets live thread messages replace overlapping history` | Same case | Live human and AI copies replace older history copies |
| `mergeMessages deduplicates tool messages by tool_call_id` | Same case | Live tool output replaces history with the same tool call ID |
| `getVisibleOptimisticMessages hides optimistic user input after server human arrives` | Same case | Server confirmation hides the optimistic input |
| `mergeMessages shows server human instead of optimistic duplicate after first response` | Same case | The first server human is rendered without an optimistic duplicate |
| `getVisibleOptimisticMessages keeps optimistic user input until server human arrives` | Same case | Pending input remains visible before server confirmation |
| `getVisibleOptimisticMessages keeps non-human optimistic status messages` | Same case | Non-human status messages remain visible |
| `getVisibleOptimisticMessages hides the upload optimistic pair after server human arrives` | Same case | Server confirmation hides the optimistic upload pair |
| `getVisibleOptimisticMessages hides optimistic user input after later server turns` | Same case | A later server turn hides the prior input, while the current pending input remains visible |

The tests use no DOM, setup hook, marker, timer, fixture, or path-dependent
behavior. Vitest runs the removed file in jsdom with `tests/setup.ts`; Rstest
runs the retained file in Node. Both resolve `@` to `frontend/src`, and the
tested functions are pure, so the environment difference does not supply any
unique assertion. The project continues to collect files by framework import.

The paired baseline used the locked frontend dependencies. Vitest passed 9 of
9 tests in 8.53s. Rstest first failed to start in the restricted sandbox with
`listen EPERM` on `127.0.0.1:3000`; the same command passed when rerun with local
socket access, collecting and passing 102 tests (1 file; 754ms total, including
372ms build and 382ms test time). This is an environment denial, not a test
failure. After removal, the same Rstest command passed all 102 collected tests.
`python3 scripts/test_inventory.py --collect --json` exited 0 with 1900
inventory entries. It reported 98 statically discovered test declarations at
the retained Rstest path and no entry for the removed path. The static count
does not expand `test.each`; the Rstest execution report is the actual count of
102 tests. Vitest and Rstest remain separate frameworks; this change only
removes the duplicate Vitest file.

GitNexus did not map the deleted test path and returned `UNKNOWN` for that
target. Impact on the underlying `mergeMessages` implementation reported 13
symbols across 5 processes, and `getVisibleOptimisticMessages` reported 10
symbols across 5 processes, both `CRITICAL`; neither implementation changed.
Repository search found no imports or active configuration references to the
removed file. Its remaining path references are in the migration and conflict
ledgers, the specification, and the ticket's paired-baseline command. The graph
result remains an index limitation, not a zero-impact claim. The full candidate
`detect-changes --scope all` result and exact tracked diff count are recorded in
the ticket execution record.
## Batch 2026-10-06: Bundled-tree harness-validator sweep retires with the skills/public demotion

Ticket `doc-disclosure-followup` issue 17. `backend/tests/test_skills_bundled.py`
swept `skills/public/**/SKILL.md` with the upstream harness validator
(`deerflow.skills.validation`). Issue 17 names `resources/skills` the
authoritative bundled tree and demotes `skills/public` to the upstream landing
zone that enterprise no longer maintains, so the sweep's target tree is retired.
The sweep does not transfer to the resources tree: the harness validator is an
installer-path contract whose upstream key set rejects the enterprise governance
keys the resources tree legitimately carries (`category`, `display_name`,
`display_name_en`, `description_en`, `visibility`, `homepage`, `skill_id`,
`install_method`, `install_source`, `enabled_at`, `name_zh` — 6 of 86 packages
would fail), and the runtime never applies the harness validator to the bundled
tree, only to user-installed packages. Replacement strength: the authoritative
tree's frontmatter is fully swept by the app-side enterprise validator in
`backend/tests/unit/skills/test_public_skill_catalog.py` (349 parametrized
checks including frontmatter validity, required fields, offline readability,
and dangerous-instruction scans); the harness validator keeps its synthetic
unit coverage in `backend/tests/test_skills_validation.py`. The one test with
no tree dependency — the registry's eval-fixture exclusion behavior — is
retained in `test_skills_bundled.py`, rewritten against a synthetic skills
root so no test reads `skills/public` anymore.

| Old path | New path | Core assertions retained | Delete old path | Validation |
| --- | --- | --- | --- | --- |
| `backend/tests/test_skills_bundled.py::test_bundled_skill_frontmatter_is_valid[86 public-tree params]` | `backend/tests/unit/skills/test_public_skill_catalog.py` (authoritative resources tree, app-side validator) | Bundled-tree SKILL.md frontmatter validity, now against the authoritative tree with the matching validator | Yes (drop duplicate sweep; targets retired landing zone) | `cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests .venv/bin/python -m pytest tests/test_skills_bundled.py tests/unit/skills/test_public_skill_catalog.py tests/test_skills_validation.py -q` (all green; catalog 349 passed) |
| `backend/tests/test_skills_bundled.py::test_runtime_registry_excludes_skill_reviewer_eval_fixtures` | Same path, rewritten synthetic (`test_runtime_registry_excludes_eval_fixture_skills`) | Nested `evals/fixtures` SKILL.md files never register as runtime skills | No | Same command as above |

## Batch 2026-10-05: Skill-script tests migrate into the backend unit tree

Ticket `doc-disclosure-followup` issue 02. The root `tests/skills/` files (four
skill-script suites plus the `skill_loader.py` helper) had no lane ownership:
`scripts/test_inventory.py` deliberately scans only the lane-consumed roots
(`backend/tests`, `frontend/tests`, `local-runtime/tests`), so nothing ever ran
them — which is exactly how the podcast suite rotted for a month after the
script it tested changed. Ownership is resolved by migrating the files into
`backend/tests/unit/skills/` (which already owns bundled-skill asset tests such
as `test_public_skill_catalog.py`) instead of widening the inventory scan:
a scan would have listed the files while still leaving "no CI runs them" true,
and honest scan ownership would have required lane-runner changes. After the
move the inventory classifies them as `backend-standard` automatically (no
special markers), so the hermetic backend PR lane now executes them.
`skill_loader.py` gained one line of change: `REPO_ROOT` walks four parents
instead of two to still reach the repository root. Test bodies are otherwise
formatter-only churn from `backend/ruff.toml` (line-length 240); no assertion
changed in this batch.

| Old path | New path | Core assertions retained | Delete old path | Validation |
| --- | --- | --- | --- | --- |
| `tests/skills/test_image_generation.py` | `backend/tests/unit/skills/test_image_generation.py` | Unchanged (36 tests) | Yes | `cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests .venv/bin/python -m pytest tests/unit/skills/test_image_generation.py tests/unit/skills/test_music_generation.py tests/unit/skills/test_podcast_generation.py tests/unit/skills/test_video_generation.py -q` (77 passed) |
| `tests/skills/test_music_generation.py` | `backend/tests/unit/skills/test_music_generation.py` | Unchanged (9 tests) | Yes | Same command as above |
| `tests/skills/test_podcast_generation.py` | `backend/tests/unit/skills/test_podcast_generation.py` | Unchanged from commit `b0486a782` (19 tests; that commit rewrote the assertions to the current Volcengine-only script — the MiniMax/retry coverage it dropped is recoverable from git history pending a diagnosis ticket) | Yes | Same command as above |
| `tests/skills/test_video_generation.py` | `backend/tests/unit/skills/test_video_generation.py` | Unchanged (13 tests) | Yes | Same command as above |
| `tests/skills/skill_loader.py` | `backend/tests/unit/skills/skill_loader.py` | Same `load()`/`FakeResp` contract; `REPO_ROOT` now `parents[4]` | Yes | Same command as above; `python3 scripts/test_inventory.py` lists all four files under lane `backend-standard` |

Follow-up fix, same batch (`1c6497e3c`): the default SourceFileLoader bytecode
cache made `load()` write `skills/public/<skill>/scripts/__pycache__/*.pyc`
into the shipped packages, which the skill review
(`backend/tests/test_skill_review_core.py`) fails as "not NUL-free UTF-8" and
which pr-standard caught on `6282d2b5a`. `skill_loader.py` now suppresses
bytecode writes around `exec_module`; regression test
`backend/tests/unit/skills/test_skill_loader.py` (4 params, red first) pins
that loading writes nothing into the packages.

## Batch 2026-10-05: task_tool core-logic duplicate removed, root copy kept

Ticket `doc-disclosure-followup` issue 02. Two same-basename task_tool files
collected concurrently without shadowing: `backend/tests/__init__.py` makes the
root copy import as `tests.test_task_tool_core_logic` while the unit copy
imports as `test_task_tool_core_logic` (no `__init__.py` under
`backend/tests/unit/`), so one pytest run collected 82 + 39 = 121 tests.
`backend/tests/test_task_tool_core_logic.py` is the current generation (last
touched 2026-09-15, imports the live config systems `SubagentRuntimeConfig`,
`deerflow.sandbox.security`, `SubagentExecutionCapacity`, and the
`status_contract` keys) and is the maintained lineage. The deleted unit copy
was the older fork (last touched 2026-09-07); 27 of its 39 collected test
names duplicate root names, and both copies passed against the same product
code, so the root versions supersede them. The root copy stays in place with
its pre-deletion collection count of 82 intact; three still-unique tests were
ported into it (85 collected after the port).

| Removed/kept path | Superseded or retained coverage | Replacement strength | Validation |
| --- | --- | --- | --- |
| `backend/tests/unit/tools/test_task_tool_core_logic.py` deleted (39 tests, 27 names duplicated in root) | Kept `backend/tests/test_task_tool_core_logic.py` (82 tests) unchanged: cancellation/cleanup/terminal-event/skill-allowlist/tool-groups/bash-gate/polling-timeout coverage of the same names, plus the root-only deferred-cleanup and loop-pinning family | Equal-or-stronger: both copies passed on the same candidate; the kept copy carries seven subsequent feature commits of evolved assertions (status-contract kwargs, tool receipts, loop-bound contracts) that the unit fork lacks | `cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests .venv/bin/python -m pytest tests/test_task_tool_core_logic.py -q` (85 passed) |
| `test_report_subagent_usage_records_from_callback_manager`, `test_report_subagent_usage_does_not_raise_for_unknown_callback_shape`, `test_task_tool_completed_path_reports_usage_from_callback_manager` (unit-only) | Ported into `backend/tests/test_task_tool_core_logic.py` with a `FakeUsageRecorder` helper; the end-to-end variant drops the old `app_config=SimpleNamespace(token_usage=...)` wiring (the registry now resolves `custom_agents` from app_config; the behavior under test — recorder resolution through an `AsyncCallbackManager` — does not need app_config) | Equal: same assertions (records delivered, `usage_reported` flag, unknown-shape no-raise, completed-path delivery) | Same command as above |
| `_find_usage_recorder` shape matrix: `test_find_usage_recorder_accepts_callback_runtime_shapes` (3 params), `test_find_usage_recorder_accepts_langchain_async_callback_manager`, `test_find_usage_recorder_ignores_unknown_callback_shapes` (4 params) — unit-only names | `backend/tests/unit/tools/test_task_tool_usage_recorder.py` already owns this seam (9 tests: plain list, async/sync manager, none/empty/unknown/unwrapped/non-dict-config shapes) and is retained | Equal: same `_find_usage_recorder` contract at a dedicated home | `cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests .venv/bin/python -m pytest tests/unit/tools/test_task_tool_usage_recorder.py -q` (9 passed) |
| `test_poller_failure_propagates_and_defers_cleanup` (unit-only lightweight variant) | Root poller-failure family covers the behavior more deeply: `test_unexpected_poller_error_deferred_cleanup_survives_sync_invocation`, `test_unexpected_error_re_raised_promptly_via_short_grace`, and the broken-status-accessor deferred-cleaner test (re-raise of the original error, cooperative cancel request, deferred cleanup scheduling) | Stronger: the root tests exercise the real persistent-loop/threaded unwind instead of a stubbed isolated loop | Same command as the kept file above |

## Batch 2026-10-03: i18n key parity moves from runtime checks to the compiler

Ticket `architecture-deepening` issue 09 (spec candidate 8, Q12=a). The
`Translations` interface (`frontend/src/core/i18n/locales/types.ts`, 2,047
hand-maintained lines) was replaced by a one-line derivation from the en-US
literal (`export type Translations = typeof enUS`), making en-US the source of
truth and zh-CN a checked adapter. No test file was moved or renamed; one
describe block was deleted because the compiler now owns its assertion.

| Removed/kept path | Superseded or retained coverage | Replacement strength | Validation |
| --- | --- | --- | --- |
| `frontend/tests/unit/core/i18n/keys.test.ts` — `key parity` describe (5 tests: top-level/workspace/sidebar/workflows/breadcrumb key-set equality) | Deleted as compile-time superseded: `zhCN` is annotated with the derived `Translations`, so any missing or extra zh-CN key fails `tsc --noEmit` (verified: deleting `common.favoritesOnly` from zh-CN produces TS2741; adding a key to en-US alone produces TS2741 on zh-CN until translated). The compiler covers every key of every section, not the five sampled ones. | Stronger: exhaustive, build-blocking, zero-maintenance; the former checks could only sample sections and could never fail once the manual interface existed | `cd frontend && ./node_modules/.bin/tsc --noEmit` plus the focused suite below |
| `frontend/tests/unit/core/i18n/keys.test.ts` — new `workbench keys` describe (3 tests) and the rest of the file (admin/workflow/brand value assertions) | Kept and extended: value assertions pin the exact strings, including the former page-hardcoded Chinese now living in `zhCN.workbench` and `zhCN.agents.skilledAt` | Unchanged for existing assertions; additive for the migrated strings | `cd frontend && pnpm vitest run tests/unit/core/i18n/keys.test.ts` |
| `frontend/tests/unit/core/i18n/translations.test.ts` — "every locale has all top-level sections" | Kept as deliberate redundancy: the loop also exercises the `translations` record mapping (`Record<Locale, Translations>`) at runtime, and its section list is a pinned subset rather than pure parity | Compile-time guarantee plus a runtime record smoke | `cd frontend && pnpm vitest run tests/unit/core/i18n/translations.test.ts` |
| `frontend/tests/e2e/smoke/workbuddy-cascade.spec.ts` — "shows the task-first welcome hierarchy" scenario-prompt assertions (2 lines) | Correction found by the integration `pr-standard` run (unit i18n mocks had papered over the locale seam): the migrated prompts now render through i18n, so the assertions pin the en-US strings (`Unclear direction?` / `Clear goal?`) that the smoke suite's locale actually renders | Same elements, same strength; assertion update only, no product change | `bash scripts/run-test-lane.sh frontend-smoke` |
| `backend/tests/unit/scripts/test_fault_zeroing_visual_outputs.py` — SKILL/SOUL verbatim-restatement loops (REQUIRED_OUTPUTS / STAGE_MARKERS / RESPONSIBILITY_PHRASES inside SKILL.md and SOUL.md) | Correction found by the integration `pr-standard` runs (issue 07's focused batch missed this file): under the contract single-home design the skill and soul reference the generated copy by section instead of restating it, so the tests now pin (a) the `/mnt/skills/.../references/result_contract.md` mount path and the section names each file must reference, and (b) the reference target carrying the phrases verbatim — which parity already guards against `contract.py` | Phrases remain pinned (now at the generated reference target); reference-by-section adds the new design's guarantee the old assertions could not express | `cd backend && uv run pytest tests/unit/scripts/test_fault_zeroing_visual_outputs.py -q` |

## Batch 2026-10-03: Skill selection consolidates into the selection module

Ticket `architecture-deepening` issue 08 (spec candidate 7, Q11=a). The
composer's skill selection (offerable gate, "/" matcher, selected-chip state,
`/name ` submission prefix, draft-restore degradation) moved into
`frontend/src/core/skills/selection.ts`. The two same-named matchers were
unified into one whose rule is name-or-description (the "/" typing flow now
also matches descriptions — a spec-declared behavior change; the suggestion
count cap is kept). The matcher tests of both old homes merged at the module
interface. No assertion was weakened; the DOM hydration file was renamed in
place and grew one test.

| Removed/merged path | Replacement coverage | Core contract retained | Validation |
| --- | --- | --- | --- |
| `frontend/tests/unit/components/workspace/input-box-helpers.test.ts` — `filterSkillsForAgent` (3 tests) and `getMatchingSkillSuggestions` (10 tests) describes | `frontend/tests/unit/core/skills/selection.test.ts` (new, 23 tests): `offerableSkills` (4), `matchSkills` (11), selection state + `submitTextFor` (3), `fromDraft` (5) | Inherit vs empty allowlist, name/slug/resource-id case-insensitive admission, enabled filtering, startsWith ranking, reserved-name exclusion (contract set + builtin extras), builtin-after-skill ordering, cap ≤ 6, empty-catalog builtin-only degradation; stronger: unified matcher adds explicit description-match coverage and the gate adds slug/resource-id cases | `cd frontend && pnpm vitest run tests/unit/core/skills/selection.test.ts --pool=forks --maxWorkers=2` |
| `frontend/tests/unit/components/workspace/slash-suggestions.test.ts` — `getMatchingSkillSuggestions` (11 tests) and `RESERVED_SLASH_SKILL_NAMES` (2 tests, local 7-name drift set) describes | Same `matchSkills` describe as above; reserved names now pinned by `tests/unit/core/skills/slash-contract.test.ts` (contract 8-name set, superset including `agent`) plus the matcher's reserved-name loop | Overlay matching by name or description, disabled exclusion, case-insensitivity, reserved exclusion | Same command as above; `cd frontend && pnpm rstest run tests/unit/core/skills/slash-contract.test.ts` |
| `frontend/tests/unit/components/workspace/slash-suggestions.test.ts` — `parseSlashPrefix` describe (10 tests); `frontend/tests/unit/components/workspace/slash-overlay.test.ts` — 2 `parseSlashPrefix` tests | `/name ` grammar stays pinned by `tests/unit/core/skills/slash.test.ts` (`parseSlashSkillReference` over `SLASH_SKILL_RE`) and the cross-stack contract tests (`tests/unit/core/skills/slash-contract.test.ts` + `backend/tests/test_slash_skill_contract.py`); the tested alias of the dead `parseTaskSkillPrefix` parser was removed with it | Leading `/word` grammar and reserved-command refusal | `cd frontend && pnpm rstest run tests/unit/core/skills/slash.test.ts tests/unit/core/skills/slash-contract.test.ts`; backend side below |
| `frontend/tests/unit/core/threads/task-input.test.ts` — 2 `prepareTaskSubmission` tests | Deleted with the test-only function (no production caller); prefix production is `submitTextFor` (asserted in `selection.test.ts`), prefix grammar as row above | Wire prefix bytes unchanged (backend parses syntactically; contract tests green both sides) | Same commands as above |
| `frontend/tests/unit/core/threads/composer-draft.test.ts` — `resolveComposerDraft` degradation test (1 test, 2 assertions) | `selection.test.ts` `fromDraft` describe (5 tests): chip restore, fold-back when not offerable, empty-text fold, no-skill passthrough, disabled-skill degradation | Saved skill restores as chip; unavailable skill folds back to editable `/name text` | Same command as above |
| `frontend/tests/unit/components/workspace/input-box-agent-skill-hydration.dom.test.tsx` (2 tests) | Renamed to `frontend/tests/unit/components/workspace/input-box-skill-hydration.dom.test.tsx` (3 tests) — the deleted `agentSkillNames`/`agentSkillsLoading` props are replaced by `allowedSkillNames` + the `useSkills` loading gate; adds a degradation-through-DOM test | Wait-for-catalog chip restore, inherit semantics without allowlist; stronger: non-offerable saved skill folds into editable text in the real composer | `cd frontend && pnpm rstest run tests/unit/components/workspace/input-box-skill-hydration.dom.test.tsx` |

Cross-stack slash protocol evidence: `contracts/slash_skill_contract.json` is
unchanged; both sides of the contract test pass on this candidate —
`cd frontend && pnpm rstest run tests/unit/core/skills/slash-contract.test.ts`
and `cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache uv run pytest
tests/test_slash_skill_contract.py -q`.

## Batch 2026-10-03: Thread-page hook owns the shared chat-route wiring

Ticket `architecture-deepening` issue 05 (spec candidate 4, Q8=a). No test
file was moved, renamed, or deleted. The shared chat-route wiring (stream
wiring incl. thread adoption and finish notifications, welcome-mode state,
empty-thread redirect, stop/branch/regenerate, view turn-submit controller)
moved from the three chat routes into the new hook
`frontend/src/core/threads/use-thread-page.ts`, and its behavior assertions
moved to the hook interface. The two page test files were rewritten in place
as adapter assertions over the page seam; the routes keep render/layout and
page-increment assertions.

| New owner | Absorbed behavior (previous home) | Replacement strength | Validation |
| --- | --- | --- | --- |
| `frontend/tests/unit/core/threads/use-thread-page.test.tsx` (new, 32 tests) | Welcome-mode init/send-flip/re-sync (`chats/[thread_id]/page.test.tsx` "onSend callback exits welcome mode", agents page "onSend callback sets welcome mode to false", both pages' welcome init via `isNewThread`); thread adoption on `onStart`/`onThreadCreated` with `setThreadId`/`setIsNewThread`/`history.replaceState` (chats page "onStart callback sets threadId and updates URL", agents page "onStart callback updates threadId and replaces URL" + encoded-segments variant); identity gating (`threadId` undefined while new, `displayThreadId` passthrough — chats page "passes displayThreadId so optimistic messages attach to the view"); finish notification policy (12 assertions across both page files: hidden/focused gating, default body, last-message body, 200-char truncation, empty/no-text messages); empty-thread redirect trigger, target and guards (page effects, previously untested at this strength); `handleStop`/`handleRegenerate`/`handleEditAndRegenerate`/`handleBranchTurn` incl. branch toast/navigation/no-op guards (chats + showcase page callbacks, agents page stop/regenerate); turn-submit dispatch and options forwarding (chats page "dispatches submitted messages through the turn-submit controller", "forwards the submit request options..."); fence invalidation on conversation switch (page-internal cleanup effects) | Stronger: each policy is now asserted once at the hook interface with real `turn-submit` wiring (gate/controller/fence interplay is exercised, not mocked), instead of duplicated per page behind a fully mocked stream module | `cd frontend && pnpm vitest run tests/unit/core/threads/use-thread-page.test.tsx --pool=forks --maxWorkers=2` |
| `frontend/tests/unit/app/workspace/chats/[thread_id]/page.test.tsx` (rewritten in place, 1537 → 1117 lines, 46 → 38 tests) | Asserted stream wiring through a fully mocked `useThreadStream` | Adapter assertions over the page seam: the page fixture reaches InputBox/MessageList, the scenario binding flows through the seam's `admit`/`extraContext`/`prepareSubmit`/`threadPath` ports, `branchPending` gates edit/branch, identity forwarding; render/layout/scenario-selection assertions unchanged | `cd frontend && pnpm vitest run 'tests/unit/app/workspace/chats/[thread_id]/page.test.tsx' --pool=forks --maxWorkers=2` |
| `frontend/tests/unit/app/workspace/agents/[agent_name]/chats/[thread_id]/page.test.tsx` (rewritten in place, 867 → 614 lines, 43 → 35 tests) | Same mocked-stream page-plumbing assertions | Adapter assertions: agent-scoped `threadPath` encoding, agent binding context/pre-create ports, controller/stop/regenerate prop identity, welcome/status/disabled rendering; skill-closure, badge, navigation, and clarification assertions unchanged | `cd frontend && pnpm vitest run 'tests/unit/app/workspace/agents/[agent_name]/chats/[thread_id]/page.test.tsx' --pool=forks --maxWorkers=2` |
| `frontend/tests/unit/app/workspace/chats/thread-page.test.tsx` (mock addition only) | — | `pathOfThread` added to the `@/core/threads/utils` mock because the route now resolves its URL policy through the seam; assertions unchanged | Same file run below |

The showcase route component
(`frontend/src/components/workspace/chats/chat-page.tsx`) had no dedicated
test file before or after; its wiring behavior is owned by the hook tests
above.

## Batch 2026-10-03: Turn-submit module owns the message submit chain

Ticket `architecture-deepening` issue 04 (spec candidate 3, Q7=a). No test
file was moved, renamed, or deleted. The submit-chain behaviors (duplicate
fence, draft hold/persist/restore/clear, attachment pre-uploads, lifecycle
ownership) moved from composer/page internals into the new module
`frontend/src/core/threads/turn-submit.ts`, and the behavior assertions moved
to that module interface. Composer and page tests keep wiring smoke only.

| New owner | Absorbed behavior (previous home) | Replacement strength | Validation |
| --- | --- | --- | --- |
| `frontend/tests/unit/core/threads/turn-submit.test.ts` (33 tests) | Duplicate-submission fence (`hooks.test.ts` "does not send when sendInFlight is true", composer `pendingDraftSubmissionKeyRef` rejection); send-failure draft preservation (`ea4e32572` unit/e2e keepers retained); onSent-once/at-dispatch vs onSendCompleted-at-stream-finish (`hooks.test.ts` "completes a sent message only after the stream finishes", both retained unchanged); attachment pre-upload reuse/dedup and lazy-new-thread skip (previously untested composer internals); admission drop and stale-continuation drop (previously untested `submissionEpochRef` internals) | Stronger: the fence exists in exactly one place and the pinned send-failure/terminal-event contracts are now asserted at the module interface in pure unit tests instead of through DOM wiring | `cd frontend && pnpm vitest run tests/unit/core/threads/turn-submit.test.ts tests/unit/core/threads/hooks.test.ts --pool=forks --maxWorkers=2` |
| `frontend/tests/unit/components/workspace/turn-submit-test-stub.ts` (new helper) | — | Framework-agnostic composer wiring double shared by vitest and rstest files | Covered by the suites below |
| `frontend/tests/unit/components/workspace/input-box-project-attachment.dom.test.tsx` (rewritten in place) | Simulated the completion lifecycle by calling `options.onSent`/`options.onSendCompleted` submit-option callbacks | Stronger: the six staged-attachment assertions now run through a real `TurnSubmitController` and its gate (`completeTurn()` settles the dispatched turn exactly as the stream's `onFinish` would) | `cd frontend && pnpm rstest run tests/unit/components/workspace/input-box-project-attachment.dom.test.tsx` |
| `frontend/tests/unit/app/workspace/chats/[thread_id]/page.test.tsx` (2 tests rewritten) | "handleSubmit with files returns send promise" / "handleSubmit without files returns void" / "forwards submit options (onSent)" page-plumbing assertions | The files/void plumbing moved into the module (owned by `turn-submit.test.ts`); the page tests keep wiring smoke: controller dispatch carries the scenario-selection context and forwards submit-request options untouched | `cd frontend && pnpm vitest run 'tests/unit/app/workspace/chats/[thread_id]/page.test.tsx' --pool=forks --maxWorkers=2` |
| `frontend/tests/unit/app/workspace/agents/[agent_name]/chats/[thread_id]/page.test.tsx` (2 tests merged into 1) | "handleSubmit returns promise/undefined" page-plumbing assertions | Same split: plumbing owned by the module; the page test pins that the controller dispatches with the agent binding context | `cd frontend && pnpm vitest run 'tests/unit/app/workspace/agents/[agent_name]/chats/[thread_id]/page.test.tsx' --pool=forks --maxWorkers=2` |
| `frontend/tests/unit/components/workspace/input-box.test.tsx`, `input-box-pending-template.test.tsx`, `input-box-stop-gating.dom.test.tsx`, `input-box-empty-skills.dom.test.tsx`, `input-box-agent-skill-hydration.dom.test.tsx` (rewired in place) | Asserted against the composer's `onSubmit` prop | Same assertions re-pointed to the `turnSubmit` controller stub; no assertion lost | Full suites below |

Kept unchanged and still green on the candidate: `tests/unit/core/threads/hooks.test.ts`
(124 tests, including both `ea4e32572` keepers), `tests/e2e/chat.spec.ts`
draft-preservation scenarios (browser lane), `tests/unit/app/workspace/agents/new/page.test.tsx`
and `tests/unit/app/workspace/chats/thread-page.test.tsx` (unaffected direct senders).

## Batch 2026-10-03: Knowledge endpoints route through the facade seam

Ticket `architecture-deepening` issue 03 (spec candidate 1, Q6=a). No test
file was moved, renamed, or deleted; two gateway route-test files were
rewritten in place from patching route-module globals to injecting the
`KnowledgeFacade` seam, and the facade unit test file gained seam-level
intent tests. Every replaced assertion retains an equal or stronger owner at
the same path.

| Rewritten in place | Replaced patching | Equal-or-stronger replacement at the same path | Validation |
| --- | --- | --- | --- |
| `backend/tests/unit/gateway/test_resources_api_knowledge_revisions.py` | `resources.get_session_factory`, `resources.get_paths`, `resources.record_audit`, `resources.configured_ragflow_provider` | Facade injected per test (`provider_factory` for the 503 case, `BackgroundTasks.add_task` as the build scheduler); audit payloads asserted through the injected sink; governance 403/404 and duplicate-publish 409 assertions retained | `cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests .venv/bin/python -m pytest tests/unit/gateway/test_resources_api_knowledge_revisions.py tests/unit/knowledge/test_knowledge_facade.py -q` |
| `backend/tests/unit/gateway/test_knowledge_tests_api.py` | `resources.get_session_factory`, `knowledge_tests.KnowledgeRetrievalTestService`, `knowledge_tests.record_audit` | Facade injected per test (`search`/`settings_factory` for provider states, facade subclass for the storage-refusal 503); execute/list/replay, provider-error state, 503/422/409/404 distinct safe states retained; adds policy endpoints classifying a non-KB resource as 404 (was 409 via `ResourceConflict`), policy round-trip, evaluation start/list/read/retry-guard, and comparison enqueue/read endpoint coverage that previously had no route-level owner | Same command as above plus `tests/unit/gateway/test_knowledge_tests_api.py` |
| `backend/tests/unit/knowledge/test_knowledge_facade.py` | (additive) | New seam-level tests: revision/retrieval-test/evaluation/policy intents commit and audit exact payloads, `KnowledgeProviderUnavailable` on missing provider, `RetrievalTestStorageUnavailable` on storage refusal, non-KB resources raise `ResourceNotFound` (404) for policy intents | Same command as above |

Two non-knowledge resources test files kept their environment wiring working
after the session-factory helper moved to the shared seam module; their
assertions are unchanged:

| Adjusted wiring only | Change | Validation |
| --- | --- | --- |
| `backend/tests/unit/gateway/test_resources_api_audit.py` | patches `resources._factory` instead of the removed `resources.get_session_factory` import | `cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests .venv/bin/python -m pytest tests/unit/gateway/test_resources_api_audit.py tests/unit/gateway/test_resources_api_canonical_drafts.py -q` |
| `backend/tests/unit/gateway/test_resources_api_canonical_drafts.py` | same patch-target rename (5 sites) | Same command as above |

Behavioral note recorded for reviewers: the two
`ResourceConflict("KnowledgeBase not found")` raises in the evaluation-policy
routes became `ResourceNotFound` via the evaluation service guard, so a
non-KnowledgeBase resource now reads as 404 (unknown == invisible) instead of
409; the comparison evaluation route's 422 detail code unified from
`invalid_evaluation_comparison` to `invalid_evaluation` as part of collapsing
the duplicate error-translation stack into one mapping
(`app/gateway/knowledge_seam.py::translate_resource_errors`). No test or
frontend consumer referenced the removed code.

Validation of the wider blast radius (all green on the candidate revision):

```bash
cd backend
UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests .venv/bin/python -m pytest tests/unit/gateway tests/unit/knowledge tests/unit/resources -q
# 2521 passed, 9 skipped
UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests .venv/bin/python -m pytest tests/contracts/ tests/integration/persistence/ -q
# 456 passed
```

## Batch 2026-10-01: Exact backend test copies at upstream paths

Removed the nested local-migration copy in each row and retained the identical
test file at its original root path from upstream baseline `0f7d8709`. Each
pair was byte-for-byte identical (matching SHA-256, size, and line count), had
the same only applicable fixture file (`backend/tests/conftest.py`), and had
no `__file__`, package-relative import, or path-sensitive behavior. All 26
retained root paths exist in `0f7d8709`; none of the removed nested paths does.
The test bodies have no path-dependent references. Text hits for a few generic
test method names outside these pairs were separate methods in other test
classes, not imports or calls. A repository path search found one documentation
reference to the removed readability path in
`UPSTREAM_PATCH_LEDGER.md`; its two test IDs remain in the retained upstream
path; the root patch ledger now references the retained upstream file.

GitNexus could not resolve these test symbols in the current index (26
`UNKNOWN` results). A repository text search confirmed no caller or active
configuration references to the removed paths. No test was skipped or
weakened.

Each pair was run separately, with both files supplied to pytest:

```bash
cd backend
UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests \
  /home/neowyh/code/AgentPlatform/backend/.venv/bin/python -m pytest \
  <removed-copy> <retained-upstream-file> -q
```

The preconfigured Python 3.12.3 backend environment was used directly because
the new worktree had no dependency environment and network resolution for
`hatchling` was unavailable. All commands exited 0: 390 passed across the
paired runs (195 test executions per copy), with 11 non-failing warnings and
no skips.

| Removed nested copy | Retained upstream path | Paired result |
| --- | --- | ---: |
| `tests/integration/sandbox/test_provisioner_kubeconfig.py` | `tests/test_provisioner_kubeconfig.py` | 10 passed |
| `tests/unit/gateway/test_auth_config.py` | `tests/test_auth_config.py` | 12 passed |
| `tests/unit/gateway/test_auth_errors.py` | `tests/test_auth_errors.py` | 16 passed; 2 warnings |
| `tests/unit/models/test_claude_provider_oauth_billing.py` | `tests/test_claude_provider_oauth_billing.py` | 22 passed |
| `tests/unit/models/test_claude_provider_prompt_caching.py` | `tests/test_claude_provider_prompt_caching.py` | 26 passed |
| `tests/unit/models/test_cli_auth_providers.py` | `tests/test_cli_auth_providers.py` | 24 passed |
| `tests/unit/models/test_client_message_serialization.py` | `tests/test_client_message_serialization.py` | 4 passed |
| `tests/unit/runtime/test_converters.py` | `tests/test_converters.py` | 30 passed |
| `tests/unit/scripts/test_credential_loader.py` | `tests/test_credential_loader.py` | 16 passed |
| `tests/unit/gateway/test_ensure_admin.py` | `tests/test_ensure_admin.py` | 22 passed |
| `tests/unit/tools/test_exa_tools.py` | `tests/test_exa_tools.py` | 24 passed |
| `tests/unit/tools/test_firecrawl_tools.py` | `tests/test_firecrawl_tools.py` | 4 passed |
| `tests/unit/tools/test_local_bash_tool_loading.py` | `tests/test_local_bash_tool_loading.py` | 10 passed |
| `tests/unit/scripts/test_loop_detection_config.py` | `tests/test_loop_detection_config.py` | 16 passed |
| `tests/unit/tools/test_mcp_custom_interceptors.py` | `tests/test_mcp_custom_interceptors.py` | 20 passed |
| `tests/unit/models/test_patched_openai.py` | `tests/test_patched_openai.py` | 16 passed |
| `tests/unit/persistence/test_persistence_timezone.py` | `tests/test_persistence_timezone.py` | 8 passed; 9 warnings |
| `tests/unit/tools/test_readability.py` | `tests/test_readability.py` | 4 passed |
| `tests/unit/tools/test_reflection_resolvers.py` | `tests/test_reflection_resolvers.py` | 6 passed |
| `tests/unit/runtime/test_run_event_store_pagination.py` | `tests/test_run_event_store_pagination.py` | 12 passed |
| `tests/unit/runtime/test_run_naming.py` | `tests/test_run_naming.py` | 14 passed |
| `tests/unit/scripts/test_safety_termination_detectors.py` | `tests/test_safety_termination_detectors.py` | 36 passed |
| `tests/unit/skills/test_skills_archive_root.py` | `tests/test_skills_archive_root.py` | 6 passed |
| `tests/unit/runtime/test_sse_format.py` | `tests/test_sse_format.py` | 6 passed |
| `tests/unit/scripts/test_token_usage_config.py` | `tests/test_token_usage_config.py` | 2 passed |
| `tests/unit/tools/test_utils_time.py` | `tests/test_utils_time.py` | 24 passed |

The actual paired command elapsed 192.1 seconds. After removing these copies,
the backend test-shaped file count is 1,137, down from 1,163. The keeper
assertions remain at the upstream paths; no mechanical migration of other
root-level tests is part of this batch.

## Batch 2026-07-14: Phase 5 final verification

Phase 5 is a non-destructive review phase. No test was deleted, moved, or
added. Every item below was verified against the working tree at commit
`4a2eedbb` plus unstaged Phase 5 review changes.

### Governance artifacts

| Artifact | Status | Verification |
| --- | --- | --- |
| `coverage-matrix.md` | Real lane marked as primary browser-to-persistence proof; mock/auth/visual/a11y disclaimed as non-RBAC evidence. | `cd frontend && pnpm exec playwright test --config=playwright.real.config.ts --list` (5 tests) |
| `test-migration-ledger.md` | Every deleted test has an equal-or-stronger retained primary owner with a repeatable validation command. | See all batches above. |

### CI lane coverage

| Lane | Config | Collect | Verification |
| --- | --- | --- | --- |
| PR backend hermetic | `backend-unit-tests.yml` | `tests/unit tests/integration tests/contracts` (4 shards, `-m "not serial and not requires_llm"`) | `cd backend && make lint` (ruff pass) |
| PR frontend typecheck/lint | `lint-check.yml`, `frontend-unit-tests.yml` | ESLint + `tsc --noEmit` + dep-cruiser + build | `cd frontend && pnpm typecheck` (0 errors) |
| PR mock Chromium | `playwright.config.ts` chromium project | `smoke/` + `workflows/` | `pnpm exec playwright test --list --project=chromium` |
| Merge gate real E2E | `playwright.real.config.ts` / `run-real-e2e.sh` | `real/` (isolated SQLite + seed + teardown) | `pnpm exec playwright test --config=playwright.real.config.ts --list` (5 tests) |
| Nightly visual | `playwright.config.ts` visual project + `playwright.login-visual.config.ts` | 10 baselines (landing 3 + workspace 3 + core 3 + login 1) | `pnpm exec playwright test --list --project=visual` (9) + login-visual config (1) |
| Nightly a11y | `playwright.a11y.config.ts` | 3 public pages (Landing, Login, Setup) | `pnpm exec playwright test --config=playwright.a11y.config.ts --list` (3 tests) |

### Generated artifact cleanup

| Artifact | Action |
| --- | --- |
| Old `*-chromium-linux.png` snapshots (6 files) | Deleted — only `*-visual-linux.png` retained |
| `frontend/playwright-artifacts/` | Empty directory preserved for visual-screenshot.spec.ts output |
| `backend/test-results/.last-run.json`, `test-results/.last-run.json` | Deleted |
| `task_plan.md`, `session-ses_*.md`, `config.yaml.bak-*`, `docs/pr-evidence/*.png` | Deleted |
| Unrelated CN-named docs on permission model redesign and fault-zeroing | Deleted |
| `__pycache__` directories | Not tracked; excluded by `.gitignore` |

### Risk assessment

`git diff --check` reports no conflict markers. GitNexus `detect_changes`
reports 0 changed symbols and 0 affected processes (risk: none). No
production code, skip rule, coverage threshold, or public API was modified
by Phase 5.

## Batch 2026-07-14: Pragmatic lane separation

The external `backend/tests/qa/` suite was removed. It started against a
shared `localhost:8001`, mutated shared accounts, and skipped the whole suite
when its server was absent; it was therefore neither hermetic integration nor
a trustworthy release gate.

| Removed source | Primary owner retained | Contract retained | Validation |
| --- | --- | --- | --- |
| `backend/tests/qa/test_api_qa.py` | Exact API keepers listed below | Auth setup/login, CRUD, and response-body contracts | Exact keeper commands below, then `cd backend && make test` |
| `backend/tests/qa/test_api_qa_multitole.py` | Exact RBAC keepers listed below | Role matrix, department boundaries, and cross-user isolation | Exact keeper commands below, then `cd backend && make test` |
| `backend/tests/qa/test_sse_streaming.py` | Exact SSE keepers listed below | SSE headers, frame/end/error behavior, and persistence lifecycle | Exact keeper commands below, then `cd backend && make test` |
| `frontend/tests/e2e/visual/visual-screenshot.spec.ts` as a PR visual gate | `landing.visual.spec.ts`, `workspace-layout.visual.spec.ts`, `core.visual.spec.ts`, and `login.visual.spec.ts` | Ten stable product baselines; capture-only screenshots remain manual/nightly reference output | `cd frontend && pnpm test:e2e:visual -- --list` |

The isolated `backend/scripts/run-real-e2e.sh` lane remains the only browser
test that owns a temporary backend, database, seed data, and teardown. It is
the merge gate for real authentication and persistence; no mock or QA lane is
presented as an equivalent proof.

### Removed API behavior → exact keeper

| Removed QA behavior | Retained test file | Retained behavior | Verification |
| --- | --- | --- | --- |
| Setup status; local login success/failure; authenticated and unauthenticated `me` | `backend/tests/integration/api/test_auth_router_e2e.py`, `test_auth_router_missing_paths.py`, `test_auth_router_session_and_setup_edges.py` | Setup state, password rejection, session identity and unauthenticated denial | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_auth_router_e2e.py tests/integration/api/test_auth_router_missing_paths.py tests/integration/api/test_auth_router_session_and_setup_edges.py -q` |
| Agent list, CRUD, and name availability | `backend/tests/integration/api/test_agents_router_e2e.py`, `test_agents_router_behavior.py`, `test_agents_router_edge_cases.py` | List/create/update/delete, metadata behavior, conflict and validation responses | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_agents_router_e2e.py tests/integration/api/test_agents_router_behavior.py tests/integration/api/test_agents_router_edge_cases.py -q` |
| Workflow list and CRUD | `backend/tests/integration/api/test_workflows_router_e2e.py`, `test_workflow_router.py` | List/create/update/delete, YAML and conflict/error contracts | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_workflows_router_e2e.py tests/integration/api/test_workflow_router.py -q` |
| Thread search and create | `backend/tests/integration/api/test_threads_router_e2e.py`, `test_threads_router.py` | Search/create request-response contract and ownership boundaries | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_threads_router_e2e.py tests/integration/api/test_threads_router.py -q` |
| Admin statistics, users, and departments | `backend/tests/integration/api/test_admin_router_e2e.py`, `test_admin_router.py`, `test_admin_router_comprehensive.py` | Read/write response bodies, validation, and authorization failures | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_admin_router_e2e.py tests/integration/api/test_admin_router.py tests/integration/api/test_admin_router_comprehensive.py -q` |
| Skills list | `backend/tests/integration/api/test_skills_router_e2e.py`, `test_skills_router_comprehensive.py`, `test_skills_router_edge_cases.py` | Catalog/list contract, visibility and error responses | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_skills_router_e2e.py tests/integration/api/test_skills_router_comprehensive.py tests/integration/api/test_skills_router_edge_cases.py -q` |
| Tools list | `backend/tests/integration/api/test_tools_router_e2e.py`, `test_tools_router.py` | Tool list and tool response contracts | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_tools_router_e2e.py tests/integration/api/test_tools_router.py -q` |
| Memory load and export | `backend/tests/integration/api/test_memory_router_e2e.py`, `test_memory_router.py`, `test_memory_router_edge_cases.py` | Load/update/delete/export response and error contracts | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_memory_router_e2e.py tests/integration/api/test_memory_router.py tests/integration/api/test_memory_router_edge_cases.py -q` |
| Models list | `backend/tests/integration/api/test_models_router_e2e.py`, `test_models_router.py`, `test_models_router_comprehensive.py` | Model listing, provider configuration and errors | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_models_router_e2e.py tests/integration/api/test_models_router.py tests/integration/api/test_models_router_comprehensive.py -q` |
| MCP config read | `backend/tests/integration/api/test_mcp_config_router_e2e.py` | MCP configuration read/write and protected values | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_mcp_config_router_e2e.py -q` |

### Removed RBAC behavior → exact keeper

| Removed QA behavior | Retained test file | Retained behavior | Verification |
| --- | --- | --- | --- |
| Super-admin admin reads/writes and normal user/viewer admin denials | `backend/tests/contracts/test_rbac_matrix.py`, `test_rbac_permission_matrix_extended.py` | Role-by-route allow/deny matrix, including department creation and user listing | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/contracts/test_rbac_matrix.py tests/contracts/test_rbac_permission_matrix_extended.py -q` |
| Department-admin read scope and fail-closed write restrictions | `backend/tests/contracts/test_rbac_matrix.py`, `test_rbac_permission_matrix_extended.py`, `test_permission_model_edge_cases.py` | Department-admin stats/departments/users reads and prohibited mutations | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/contracts/test_rbac_matrix.py tests/contracts/test_rbac_permission_matrix_extended.py tests/contracts/test_permission_model_edge_cases.py -q` |
| User/viewer agent, workflow, skill, tool, thread, and memory access | `backend/tests/contracts/test_authz_rbac.py`, `test_user_isolation.py`, `test_memory_thread_meta_isolation.py` | Authz allow/deny plus cross-user thread/memory isolation | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/contracts/test_authz_rbac.py tests/contracts/test_user_isolation.py tests/contracts/test_memory_thread_meta_isolation.py -q` |
| Unauthenticated setup-status allow and protected-route denial | `backend/tests/integration/api/test_auth_router_missing_paths.py`, `backend/tests/contracts/test_authz_rbac.py` | Setup endpoint public scope and protected endpoint rejection | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_auth_router_missing_paths.py tests/contracts/test_authz_rbac.py -q` |

### Removed SSE behavior → exact keeper

| Removed QA behavior | Retained test file | Retained behavior | Verification |
| --- | --- | --- | --- |
| Stateless and thread-run SSE content type/cache headers | `backend/tests/integration/api/test_runs_stateless_router.py`, `test_threads_router_comprehensive.py` | Streaming response headers and thread-run route contract | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_runs_stateless_router.py tests/integration/api/test_threads_router_comprehensive.py -q` |
| SSE frames and terminal end event | `backend/tests/integration/api/test_runs_lifecycle.py`, `test_runs_stateless_router_e2e.py` | Event stream completion and persisted terminal run state | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_runs_lifecycle.py tests/integration/api/test_runs_stateless_router_e2e.py -q` |
| Invalid assistant and unauthenticated stream errors | `backend/tests/integration/api/test_runs_stateless_router.py`, `backend/tests/contracts/test_authz_rbac.py` | Invalid run request errors and fail-closed unauthenticated access | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_runs_stateless_router.py tests/contracts/test_authz_rbac.py -q` |
| Heartbeat/comment tolerance and disconnect cancellation | `backend/tests/integration/api/test_runs_lifecycle.py` | Consumer disconnect cancellation and stream lifecycle cleanup | `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/api/test_runs_lifecycle.py -q` |

## Batch 2026-07-14: Phase 1 weak assertion hardening

Status-code-only assertions in Agent, Workflow, Auth, Memory, and Admin test
files were strengthened to validate response body fields and error details.
No test was deleted, moved, or renamed. No production code, skip rule, or
coverage threshold changed. Three sub-agents worked in parallel on independent
files, plus a lightweight frontend assertion clean-up.

| File (backend) | Assertions strengthened | Pattern |
| --- | --- | --- |
| `test_agents_router_edge_cases.py` | 17 | Added `resp.json()["detail"]` / `{"code","message"}` body checks to disabled/error/not-found/validation/conflict cases |
| `test_agents_router_comprehensive.py` | ~42 | Same pattern: 403 disabled, 500 error, 404 not-found, 422 validation, 409 conflict |
| `test_workflows_router.py` | ~19 | Not-found, forbidden, conflict, delete-success body, run-accepted run_id/status checks |
| `test_workflows_router_e2e.py` | ~9 | Create/delete/run success body, invalid-yaml detail check |
| `test_auth_router_missing_paths.py` | 6 | Login-failure 401, register 400, admin-exists 409, OAuth 501 detail checks |
| `test_memory_router_e2e.py` | 2 | Delete/update not-found detail checks |
| `test_auth_router_edge_cases.py` | 1 | OAuth 501 detail check |
| `test_admin_router_comprehensive.py` | 14 | 422 validation, 403 RBAC, 500 database body checks |
| `test_admin_router_e2e.py` | 5 | Create/update department body, RBAC 403 detail checks |

| File (frontend) | Assertions strengthened | Pattern |
| --- | --- | --- |
| `admin/departments/page.test.tsx` | 4 | Tightened count + `toHaveTextContent` content check |
| `admin/tools/page.test.tsx` | 2 | Tightened `toBeGreaterThanOrEqual` → `toHaveLength` |
| `agents/new/page.test.tsx` | 3 | Added `toHaveTextContent` content check |
| `workflows/[workflow_name]/page.test.tsx` | 2 | Tightened count assertions |

Validation:

```bash
cd backend
PYTHONPATH=. uv run pytest tests/unit tests/integration tests/contracts -m "not serial and not requires_llm" -q
# → 12741 passed, 12 skipped, 101 deselected

cd ../frontend
pnpm exec vitest run tests/unit/app/workspace/admin/departments tests/unit/app/workspace/admin/tools tests/unit/app/workspace/agents/new/page.test.tsx
# → 5 test files, 324 passed
```

## Batch 2026-07-13: Phase 3 evidence-backed duplicate consolidation

Only test cases with an equal-or-stronger retained owner were deleted. No
production code, skip rule, coverage threshold, or public API changed.

| Deleted source | Retained primary owner | Contract retained | Validation |
| --- | --- | --- | --- |
| `frontend/tests/e2e/workflows/admin-panel.spec.ts`: dashboard access, statistics cards, user navigation, department navigation | `admin-management.spec.ts`: Dashboard plus click-based navigation access control | Dashboard route, exactly six `admin-stat-card` elements, and user/department navigation | Affected workflow collection: 58 tests / 7 files; `pnpm exec playwright test --project=chromium tests/e2e/workflows/admin-management.spec.ts` (12 passed) |
| `agent-chat.spec.ts`: agent gallery load | `agent-management.spec.ts`: gallery agent cards | Gallery load; keeper additionally checks normal and template cards | Same frontend collection |
| `chat-flow.spec.ts`: new-chat load and send/receive | `chat.spec.ts`: input-page and streamed reply contracts | New-chat input and mocked stream response; chat export remains in `chat-flow.spec.ts` | Same frontend collection |
| `settings-management.spec.ts`: Skills tabs and public Skills list | `skill-management.spec.ts`: Settings Page cases | Public/custom tabs and public skill content; non-Skills settings remain in source | Same frontend collection |
| `backend/tests/unit/channels/test_channel_file_attachments.py`: base receive/send/default/outbound checks, all `_make_inbound` cases, and base channel properties | `test_channel_base.py::{TestReceiveFile,TestSendFileDefault,TestOnOutbound,TestMakeInbound,TestInit,TestProperties}` | Base-channel behavior; attachment file retains upload ordering, failure continuation, false return, and send-failure behavior | `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/channels/test_channel_base.py tests/unit/channels/test_channel_file_attachments.py -q` (78 passed; exactly 17 fewer than the 95-test baseline) |
| `backend/tests/contracts/test_visibility_applications_e2e.py`: invalid type, unknown/terminal/stale/self review, unknown/foreign/terminal withdraw, non-admin list, super-admin and regular-user review duplicates | `test_visibility_applications.py` matching router tests | Mock-router error/RBAC boundary; e2e file retains resource-metadata approval, rejection, cross-department rules, withdraw mutation/conflict, and submit-to-approve/withdraw/reject workflows | `PYTHONPATH=. uv run pytest tests/contracts/test_visibility_applications.py tests/contracts/test_visibility_applications_e2e.py -v` (41 passed) |

The isolated real-browser visibility lane remains the primary SQLite-backed UI
proof for approval and rejection. The similarly named backend `*_e2e.py` file
uses mocked sessions; it is not presented as SQLite coverage.

## Batch 2026-07-12: Isolated Real E2E Lane

This is additive coverage; no existing mock, auth, visual, or a11y test was
deleted or moved. The lane uses its own Playwright config and an ephemeral
backend state managed by `backend/scripts/run-real-e2e.sh`.

| New path | Primary responsibility | Persistent-state proof | Validation |
| --- | --- | --- | --- |
| `frontend/tests/e2e/real/role-access-boundaries.spec.ts` | Seeded super-admin, user, viewer, and department-admin access boundaries | Isolated SQLite rows agree with the browser-observed role result. | `cd frontend && E2E_STATE_DIR=/tmp E2E_RUN_ID=collect-only IDEER_INTERNAL_GATEWAY_BASE_URL=http://127.0.0.1:8001 pnpm exec playwright test --config=playwright.real.config.ts --list`; `QA_ISOLATED=1 bash backend/scripts/run-real-e2e.sh` |
| `frontend/tests/e2e/real/memory-persistence.spec.ts` | Create, reload, and delete a user memory fact | The isolated user's memory files agree with the UI. This behavior is deliberately not represented as a SQLite assertion. | `cd frontend && E2E_STATE_DIR=/tmp E2E_RUN_ID=collect-only IDEER_INTERNAL_GATEWAY_BASE_URL=http://127.0.0.1:8001 pnpm exec playwright test --config=playwright.real.config.ts --list`; `QA_ISOLATED=1 bash backend/scripts/run-real-e2e.sh` |
| `frontend/tests/e2e/real/visibility-application-flow.spec.ts` | Owner submission plus independent approval and rejection by a super-admin | UI status, `visibility_applications.status`, and affected resource metadata agree in the isolated SQLite database. | `cd frontend && E2E_STATE_DIR=/tmp E2E_RUN_ID=collect-only IDEER_INTERNAL_GATEWAY_BASE_URL=http://127.0.0.1:8001 pnpm exec playwright test --config=playwright.real.config.ts --list`; `QA_ISOLATED=1 bash backend/scripts/run-real-e2e.sh` |

The separate `Real E2E Tests` workflow runs this lane on pull requests that
change `frontend/**`, `backend/**`, or its own workflow file. It installs the
backend and frontend dependencies plus Chromium, and uploads the isolated-run
logs, report, and traces when the lane fails.

### Phase 2 execution evidence and necessary product repairs

The isolated lane exposed three product-path defects. These repairs are part of
the Phase 2 commit because without them the required browser-to-persistence
contracts cannot be exercised. No public endpoint shape changed.

| Defect | Repair and boundary | Failure and regression evidence |
| --- | --- | --- |
| A successful login wrote the cookie but App Router navigation could race the subsequent SSR request. | `login/page.tsx` uses a full-document navigation after login/register; the admin route is guarded server-side by `workspace/admin/layout.tsx`, with the super-admin-only audit-log subroute guarded separately. Client pages no longer navigate during render. | The real lane previously timed out at login despite successful `/auth/me`; login unit tests cover valid/invalid next paths and `location.assign`, admin-layout unit tests cover allow/deny roles, and the final isolated run passed all seven scenarios. |
| A viewer could not discover a public custom agent owned by another user because `/api/agents` scanned only the requester directory. | `list_agents` discovers metadata-backed accessible agents, loads them from the owner directory, and returns them read-only with the owner's SOUL content. Access remains fail-closed through `check_resource_access`. | The corrected integration test switches the effective user to a distinct viewer and asserts visibility, owner, read-only status, and SOUL. The real viewer scenario failed before this repair and passes in the final lane. GitNexus impact was attempted for `list_agents`; the current index did not contain the symbol, so direct API regression and full real-lane evidence are authoritative. |
| The approval scenario selected reviewed items using CSS/text assumptions instead of the approval page state machine. | It identifies the component card by run-scoped reason, switches to the resulting approved/rejected filter, and asserts the status within that card. | The runner first showed the application correctly moved out of the pending filter; the revised scenario and SQLite terminal-state assertions pass for both approval and rejection. |

Final Phase 2 verification used:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=. uv run pytest tests/scripts/test_real_e2e_scripts.py -q
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=. uv run pytest tests/integration/api/test_agents_router_behavior.py -q

cd ../frontend
pnpm exec vitest run tests/unit/app/workspace/admin
pnpm exec vitest run 'tests/unit/app/(auth)/login/page.test.tsx'
pnpm exec tsc --noEmit

cd ..
UV_CACHE_DIR=/tmp/uv-cache QA_ISOLATED=1 REAL_E2E_ARTIFACTS_DIR=/tmp/real-e2e-artifacts-phase2-final-2 bash backend/scripts/run-real-e2e.sh
```

The final isolated execution passed 7/7 and cleaned its temporary run state.

## Batch 2026-07-09: Frontend E2E Directory Split

| Old path | New path | Core assertions retained | Stronger replacement | Delete old path | Validation |
| --- | --- | --- | --- | --- | --- |
| `frontend/tests/e2e/landing.spec.ts` | `frontend/tests/e2e/smoke/landing.spec.ts` | Landing route smoke assertions | Default Chromium project now collects only `smoke/` and `workflows/` | Yes | `cd frontend && pnpm exec playwright test --list` |
| `frontend/tests/e2e/brand-and-offline.spec.ts` | `frontend/tests/e2e/smoke/brand-and-offline.spec.ts` | Brand/offline smoke assertions | Isolated from workflow specs | Yes | `cd frontend && pnpm exec playwright test --project=chromium tests/e2e/smoke` |
| `frontend/tests/e2e/sidebar.spec.ts` | `frontend/tests/e2e/smoke/sidebar.spec.ts` | Workspace navigation/sidebar assertions | Isolated as smoke navigation | Yes | `cd frontend && pnpm exec playwright test --project=chromium tests/e2e/smoke` |
| `frontend/tests/e2e/qa/smoke-landing.spec.ts` | `frontend/tests/e2e/smoke/smoke-landing.spec.ts` | QA landing smoke assertions | Removed from `qa/` bucket and default duplicate collection | Yes | `cd frontend && pnpm exec playwright test --list` |
| `frontend/tests/e2e/qa/auth-flow.spec.ts` | `frontend/tests/e2e/auth/auth-flow.spec.ts` | Real-auth login/logout/setup assertions | Runs only through `playwright.auth.config.ts` with auth enabled | Yes | `cd frontend && pnpm exec playwright test --config=playwright.auth.config.ts --list` |
| `frontend/tests/e2e/qa/smoke-login.spec.ts` | `frontend/tests/e2e/auth/smoke-login.spec.ts` | Real-auth login smoke assertions | Runs only through `playwright.auth.config.ts` with auth enabled | Yes | `cd frontend && pnpm exec playwright test --config=playwright.auth.config.ts --list` |
| `frontend/tests/e2e/qa/visual-screenshot.spec.ts` | `frontend/tests/e2e/visual/visual-screenshot.spec.ts` | Visual capture entrypoint | Isolated from default Chromium project | Yes | `cd frontend && pnpm exec playwright test --project=visual --list` |
| `frontend/tests/e2e/*.spec.ts` business specs | `frontend/tests/e2e/workflows/*.spec.ts` | Existing user-path assertions | Default Chromium project explicitly matches workflow specs once | Yes | `cd frontend && pnpm exec playwright test --list` |
| `frontend/tests/e2e/qa/*.spec.ts` business specs | `frontend/tests/e2e/workflows/*-qa.spec.ts` where needed | Existing QA workflow assertions | Removed `qa/` bucket from project collection | Yes | `cd frontend && pnpm exec playwright test --list` |

The intermediate `smoke/smoke-landing.spec.ts` and retained `*-qa.spec.ts`
workflow files were later merged into the primary specs in the
2026-07-10 duplicate QA merge batch below.

## Batch 2026-07-09: Backend Script Tests

| Old path | New path | Core assertions retained | Stronger replacement | Delete old path | Validation |
| --- | --- | --- | --- | --- | --- |
| `backend/tests/test_check_script.py` | `backend/tests/unit/scripts/test_check_script.py` | Script command behavior and subprocess handling | Runs under unit/scripts domain | Yes | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/scripts -v` |
| `backend/tests/test_doctor.py` | `backend/tests/unit/scripts/test_doctor.py` | Doctor command and environment checks | Runs under unit/scripts domain | Yes | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/scripts -v` |
| `backend/tests/test_intranet_deploy_scripts.py` | `backend/tests/unit/scripts/test_intranet_deploy_scripts.py` | Intranet deploy script assertions with fakes | Runs under unit/scripts domain | Yes | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/scripts -v` |
| `backend/tests/test_start_local_script.py` | `backend/tests/unit/scripts/test_start_local_script.py` | Local startup script behavior | Runs under unit/scripts domain | Yes | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/scripts -v` |

## Batch 2026-07-09: Backend Root Test Domain Move

All remaining `backend/tests/test_*.py` files were moved without content edits into:

- `backend/tests/unit/{gateway,runtime,memory,sandbox,workflows,skills,channels,models,tools,scripts,persistence}/`
- `backend/tests/integration/{api,persistence,sandbox}/`
- `backend/tests/contracts/`

Core assertions are retained because the test bodies were not changed. The
replacement is stronger at the suite level because `backend/Makefile` now runs
`tests/unit tests/integration tests/contracts` directly and no longer depends on
the root `tests/*.py` transition glob.

Validation:

```bash
cd backend
find tests -maxdepth 1 -type f -name 'test_*.py'
PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit tests/integration tests/contracts -v -m "not serial and not requires_llm"
```

Correction (2026-10-13, ticket #66): this batch's claim was true when recorded
(commit `60f0ef382` moved the root files verbatim, e.g. `test_channels.py` as an
R100 rename), but subsequent batch commits between 2026-07-09 and 2026-09-06
(e.g. `4feb26e0f` "B4b 权限/隔离 + B4c 杂项" and the legacy-harness refactor)
recreated root-level copies without a ledger batch. Both trees then evolved in
parallel — root copies absorbing newer product-contract assertions, subdir
copies evolving independently — so the "no root-level tests left" statement
above no longer described the tree. The duplicates were resolved and this entry
superseded by the 2026-10-13 dedup batches at the top of this ledger, under
[the dedup decision](../decisions/2026-10-13-backend-test-dedup.md).

## Batch 2026-07-09: Stable Contract Entrypoints

| Previous migrated path | Final path | Core assertions retained | Stronger replacement | Delete old path | Validation |
| --- | --- | --- | --- | --- | --- |
| `backend/tests/contracts/test_rbac_permission_matrix.py` | `backend/tests/contracts/test_rbac_matrix.py` | Role, resource, and action permission matrix | Stable platform-level RBAC contract path | Yes | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/contracts/test_rbac_matrix.py -v` |
| `backend/tests/contracts/test_owner_isolation.py` | `backend/tests/contracts/test_user_isolation.py` | Cross-user read/update/delete isolation for thread/run/event/feedback stores | Stable user-isolation contract path alongside memory, path, setup-agent, and update-agent isolation contracts | Yes | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/contracts/test_user_isolation.py tests/contracts/test_memory_*isolation.py tests/contracts/test_paths_user_isolation.py -v` |
| `backend/tests/integration/api/test_runtime_lifecycle_e2e.py` | `backend/tests/integration/api/test_runs_lifecycle.py` | Run creation, SSE stream events, checkpoint writes, run store, thread message state, cancel, rollback recovery | Stable run lifecycle integration entrypoint | Yes | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/integration/api/test_runs_lifecycle.py -v -m "not requires_llm"` |
| `backend/tests/integration/persistence/test_alembic_migrations.py` | `backend/tests/integration/persistence/test_migration_schema.py` | Alembic head schema, ORM table/column checks, downgrade/re-upgrade, merge revision round-trip, stamp-head behavior | Migration workflow now calls this final path | Yes | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/integration/persistence/test_migration_schema.py -v` |
| `backend/tests/unit/skills/test_skills_bundled.py` | `backend/tests/unit/skills/test_public_skill_catalog.py` | Bundled `skills/public/**/SKILL.md` validation | Adds required frontmatter fields, UTF-8/offline readability, and dangerous-instruction scans | Yes | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/skills/test_public_skill_catalog.py -v` |
| Missing | `frontend/tests/e2e/workflows/cross-feature-contracts.spec.ts` | N/A | Shared mock fixture now locks Agent, Workflow, Memory, and Skills API shapes through UI consumption | N/A | `cd frontend && pnpm exec playwright test --project=chromium tests/e2e/workflows/cross-feature-contracts.spec.ts` |

## Batch 2026-07-09: Patch-Name File Cleanup

Files whose names contained `coverage`, `boost`, `gaps`, `full`, or `extra`
were not deleted. They were mechanically renamed in place so the same assertions
remain in their migrated domain bucket:

| Old filename fragment | New filename fragment | Decision | Replacement path rule | Validation |
| --- | --- | --- | --- | --- |
| `coverage_boost` | `behavior` | Rename | Same directory, same test body | `find backend/tests -type f \( -name '*coverage*.py' -o -name '*boost*.py' -o -name '*gaps*.py' -o -name '*full*.py' -o -name '*extra*.py' \)` |
| `coverage` | `edge_cases` | Rename | Same directory, same test body | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit tests/integration tests/contracts -v -m "not serial and not requires_llm"` |
| `boost` | `behavior` | Rename | Same directory, same test body | `cd backend && make test-coverage` |
| `gaps` | `missing_paths` | Rename | Same directory, same test body | `cd backend && make test-coverage` |
| `full` | `comprehensive` | Rename | Same directory, same test body | `cd backend && make test-coverage` |
| `extra` | `additional` | Rename | Same directory, same test body | `cd backend && make test-coverage` |

## Batch 2026-07-10: Residual Patch-Name Cleanup

The first cleanup removed `coverage`, `boost`, `gaps`, `full`, and `extra`
fragments, but a later static gate still found residual `cov3` and `fix`
filenames. These files were renamed without changing assertions:

| Old path | New path | Core assertions retained | Validation |
| --- | --- | --- | --- |
| `backend/tests/integration/api/test_auth_router_cov3.py` | `backend/tests/integration/api/test_auth_router_session_and_setup_edges.py` | Auth password validation, secure session cookie attributes, trusted proxy client IP extraction, and setup-status cache behavior | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/integration/api/test_auth_router_session_and_setup_edges.py -v` |
| `backend/tests/unit/gateway/test_llm_error_middleware_cov3.py` | `backend/tests/unit/gateway/test_llm_error_middleware_circuit_breaker.py` | Circuit-breaker state transitions, fast-fail responses, retry-event fallback, GraphBubbleUp probe reset, and Retry-After parsing | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/gateway/test_llm_error_middleware_circuit_breaker.py -v` |
| `backend/tests/unit/runtime/test_checkpointer_none_fix.py` | `backend/tests/unit/runtime/test_checkpointer_default_memory_saver.py` | Sync and async default checkpointer contexts return usable `InMemorySaver` instances | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/runtime/test_checkpointer_default_memory_saver.py -v` |
| `backend/tests/unit/runtime/test_worker_cov3.py` | `backend/tests/unit/runtime/test_worker_context_and_rollback.py` | Run worker app config/store propagation, multi-mode stream filtering, and rollback checkpoint id injection | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/runtime/test_worker_context_and_rollback.py -v` |
| `backend/tests/unit/scripts/test_network_cov3.py` | `backend/tests/unit/scripts/test_network_port_allocator.py` | Port availability, reservation, release, context manager cleanup, and concurrent allocation behavior | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/scripts/test_network_port_allocator.py -v` |
| `backend/tests/unit/tools/test_image_search_edge_cases_fix.py` | `backend/tests/unit/tools/test_image_search_import_and_filters.py` | Local `ddgs` import handling, filter forwarding, empty results, import errors, and search exceptions | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/tools/test_image_search_import_and_filters.py -v` |
| `backend/tests/unit/workflows/test_parser_cov3.py` | `backend/tests/unit/workflows/test_parser_nested_condition_branches.py` | Nested condition `then`/`else` parsing and recursive step reference validation | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/workflows/test_parser_nested_condition_branches.py -v` |

The residual static gate may still match
`backend/tests/unit/runtime/test_gateway_run_recovery.py` because `recovery`
contains the substring `cov`. That is a false positive: the file name describes
gateway run recovery behavior and is not a patch-name exception.

## Batch 2026-07-11: `feat/improve-tests` Content Audit

`feat/improve-tests` was not merged directly. Its `auth/`, `routers/`,
`sandbox/`, and similar top-level directories conflict with the final
`unit/`, `integration/`, and `contracts/` hierarchy used by this branch.

| Source | Decision | Evidence | Validation |
| --- | --- | --- | --- |
| Backend test-directory reorganization in `9c9956e2` | Not copied | The source test node names are already represented in the final layered suite; copying its aggregated files would duplicate collection under a second taxonomy. | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit tests/integration tests/contracts --collect-only -q` |
| RBAC-only source nodes absent by name | Not copied | They encode superseded department-admin expectations, including denial of department listing. `tests/contracts/test_rbac_matrix.py` is the current contract: department admins can read departments but cannot mutate them. | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/contracts/test_rbac_matrix.py -v` |
| Sandbox async-lock exception node | Not copied | It targets the removed executor-based lock acquisition and expects a `RuntimeError`. The current polling implementation is covered by lock-acquisition and cancellation tests in `tests/integration/sandbox/test_aio_sandbox_provider.py`. | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/integration/sandbox/test_aio_sandbox_provider.py -v` |
| `error_codes.py` change and five frontend test deletions | Excluded | They are non-test changes or deletions without an equal-or-stronger replacement proof. | `git diff --check` and targeted test collection |

The source branch itself has collection errors in its aggregated agents,
workflows, and local-sandbox modules. Those files are audit inputs only; they
are not a valid replacement suite for the current branch.

Final verification collected 12,817 current-suite tests and the default backend
run passed with 12,717 passed, 3 skipped, and 97 deselected. The coverage run
reached 98% but had one order-sensitive failure in
`test_stream_run_executes_real_lead_agent_setup_agent_business_path`: its run
completed, then the status poll received `token_invalid` with a malformed
token. The same test passed alone under coverage and with its immediately
preceding module, so this remains a separate full-suite isolation issue rather
than a reason to import the source branch.

## Batch 2026-07-10: Frontend E2E Duplicate QA Merge

The initial E2E directory split preserved some `qa/` filenames as `*-qa.spec.ts`
so no assertions were lost during migration. These duplicate entrypoints were
then merged into the primary smoke/workflow specs:

| Removed path | Replacement path | Core assertions retained | Validation |
| --- | --- | --- | --- |
| `frontend/tests/e2e/smoke/smoke-landing.spec.ts` | `frontend/tests/e2e/smoke/landing.spec.ts` | Landing page load, title/brand signal, visible workspace entrypoint, and CTA navigation | `cd frontend && pnpm exec playwright test --project=chromium tests/e2e/smoke/landing.spec.ts --list` |
| `frontend/tests/e2e/workflows/agent-management-qa.spec.ts` | `frontend/tests/e2e/workflows/agent-management.spec.ts` | Agent listing, create-page navigation, valid-name setup progression, detail-page rendering, and delete dialog behavior | `cd frontend && pnpm exec playwright test --project=chromium tests/e2e/workflows/agent-management.spec.ts --list` |
| `frontend/tests/e2e/workflows/workflow-management-qa.spec.ts` | `frontend/tests/e2e/workflows/workflow-management.spec.ts` | Workflow listing, create-page navigation, YAML editor input behavior, detail navigation, run dialog, edit page, and delete dialog behavior | `cd frontend && pnpm exec playwright test --project=chromium tests/e2e/workflows/workflow-management.spec.ts --list` |

## Batch 2026-07-11: `offline_feature` Product-Test Intake

| Removed assertion/API | Replacement coverage | Core contract retained | Validation |
| --- | --- | --- | --- |
| `ResourceMetadataStore.soft_delete` timestamp behavior | `test_resource_metadata_store.py` hard-delete execution and failure handling | Metadata is removed atomically and a database failure is reported without restoring tombstones | `cd backend && uv run pytest tests/unit/gateway/test_resource_metadata_store.py tests/integration/api/test_workflow_router.py tests/integration/api/test_workflows_router.py tests/integration/api/test_workflows_router_e2e.py -q` |
| Workflow router mocks of `soft_delete` | Workflow delete tests mock `ResourceMetadataStore.delete` and retain non-fatal metadata-cleanup assertions | A workflow deletion remains successful when metadata cleanup fails, while pending applications are still handled | Same command as above |

The product merge imported five root-level backend tests. They were moved
directly into the existing layered layout; no root collection entrypoint was
restored.

| Source path | Final path | Core assertions retained | Validation |
| --- | --- | --- | --- |
| `backend/tests/test_agents_same_name.py` | `backend/tests/integration/api/test_agents_same_name.py` | Per-owner metadata reads, upserts, favourites, and deletion remain isolated when agent names match. | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/integration/api/test_agents_same_name.py -q` |
| `backend/tests/test_audit_logs.py` | `backend/tests/integration/api/test_audit_logs.py` | Department-admin audit-log list and detail access. | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/integration/api/test_audit_logs.py -q` |
| `backend/tests/test_user_deletion.py` | `backend/tests/integration/api/test_user_deletion.py` | Database commit precedes filesystem cleanup; cleanup failure remains auditable and retryable. | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/integration/api/test_user_deletion.py -q` |
| `backend/tests/test_reconcile_user_state.py` | `backend/tests/unit/scripts/test_reconcile_user_state.py` | Read-only inventory and guarded deletion for stale runtime-user state. | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/scripts/test_reconcile_user_state.py -q` |
| `backend/tests/test_runtime_user_context.py` | `backend/tests/unit/runtime/test_runtime_user_context.py` | Pytest uses a temporary `IDEER_HOME`, distinct from production runtime state. | `cd backend && PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/unit/runtime/test_runtime_user_context.py -q` |

## Batch 2026-10-06: Stale `detect_blocking_io_static` duplicate removal

`60f0ef382` moved `backend/tests/test_detect_blocking_io_static.py` to
`backend/tests/unit/scripts/`; `40c4ec32` (#4200) later re-created the
top-level file with a superset of the tests, orphaning the moved copy. Its
`from support...` import resolves only under the lane environment
(`PYTHONPATH=.:tests`), so bare `pytest tests/unit/scripts` aborted with
`ModuleNotFoundError: No module named 'support'`.

| Removed path | Replacement path | Core assertions retained | Validation |
| --- | --- | --- | --- |
| `backend/tests/unit/scripts/test_detect_blocking_io_static.py` | `backend/tests/test_detect_blocking_io_static.py` | Static blocking-IO detector: direct async blocking calls, sync helpers reachable from async code and via self/cls attribute chains, Path/httpx/os detection, CLI JSON and summary output, parse-error reporting | `cd backend && PYTHONPATH=.:tests PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests/test_detect_blocking_io_static.py -q` |
