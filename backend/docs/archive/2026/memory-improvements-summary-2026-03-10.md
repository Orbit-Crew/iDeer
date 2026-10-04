---
id: backend-docs-archive-2026-memory-improvements-summary
kind: snapshot
status: archived
owner: repository maintainers
scope: summary of memory prompt-injection implementation status as of 2026-03-10 on main, companion to memory-improvements-2026-03-10
archived-reason: point-in-time status snapshot; the format_memory_for_injection API it describes has since been replaced by the MemoryManager flow in backend/packages/harness/deerflow/agents/memory/manager.py
---

# Memory System Improvements - Summary

> status: archived; current memory implementation: `backend/packages/harness/deerflow/agents/memory/manager.py` (MemoryManager; the API shape below is historical)
> source date: 2026-03-10
> canonical-path: `backend/docs/archive/2026/memory-improvements-summary-2026-03-10.md`

## Sync Note (2026-03-10)

This summary is synchronized with the `main` branch implementation.
TF-IDF/context-aware retrieval is **planned**, not merged yet.

## Implemented

- Accurate token counting with `tiktoken` in memory injection.
- Facts are injected into `<memory>` prompt content.
- Facts are ordered by confidence and bounded by `max_injection_tokens`.

## Planned (Not Yet Merged)

- TF-IDF cosine similarity recall based on recent conversation context.
- `current_context` parameter for `format_memory_for_injection`.
- Weighted ranking (`similarity` + `confidence`).
- Runtime extraction/injection flow for context-aware fact selection.

## Why This Sync Was Needed

Earlier docs described TF-IDF behavior as already implemented, which did not match code in `main`.
This mismatch is tracked in issue `#1059`.

## Current API Shape

```python
def format_memory_for_injection(memory_data: dict[str, Any], max_tokens: int = 2000) -> str:
```

No `current_context` argument is currently available in `main`.

## Verification Pointers

> Historical paths as of 2026-03-10; the current memory implementation is `backend/packages/harness/deerflow/agents/memory/manager.py`.

- Implementation: `packages/harness/ideer/agents/memory/prompt.py`
- Prompt assembly: `packages/harness/ideer/agents/lead_agent/prompt.py`
- Regression tests: `backend/tests/test_memory_prompt_injection.py`
