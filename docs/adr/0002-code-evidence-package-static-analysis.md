---
id: adr-0002-code-evidence-package-static-analysis
kind: decision
status: current
owner: repository maintainers
scope: fault-zeroing code evidence intake as a thread-private read-only ZIP package analyzed by a fixed scanner set in isolation; no build or execution of submitted programs
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 02af2a4e8
---

# Code evidence packages use static analysis

Fault-zeroing accepts a read-only ZIP Code Evidence Package through a dedicated endpoint and UI rather than a live project directory, generic attachment, or Agent archive. It is retained with its authorized Thread until explicitly deleted, preserving source and fault evidence for a single Run; build metadata is optional and raises analysis confidence. The platform may inspect it and run preinstalled approved static analyzers in an isolated sandbox, but must not build or execute the submitted program. Static-analysis alerts are high-risk candidates until corroborated by other evidence. The first rule profile is general C safety and reliability; MISRA, CERT C, and organization-specific profiles remain later opt-in work.
