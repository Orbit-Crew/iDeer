---
id: adr-0003-fault-zeroing-evidence-modes
kind: decision
status: superseded
owner: repository maintainers
scope: historical design for per-run selectable document/code/hybrid evidence modes; replaced by hybrid intake before the 2026-09-29 ADR-0004 implementation revision
superseded-by: docs/adr/0004-fault-zeroing-hybrid-intake-and-shared-execution.md
---

# Fault-zeroing uses explicit evidence modes

> Superseded by [ADR-0004](0004-fault-zeroing-hybrid-intake-and-shared-execution.md): new Runs no longer declare an evidence mode; historical content below is preserved as-is.

Each fault-zeroing Run declares document, code, or hybrid evidence mode. Mode-specific branches extract and validate evidence, then feed one shared fault-tree, root-cause, verification, and reporting flow; the platform does not infer a mode from filenames or maintain separate end-to-end workflows.
