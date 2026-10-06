---
id: adr-0005-preserve-workbench-experience-when-adopting-deerflow-features
kind: decision
status: current
owner: repository maintainers
scope: placement of adopted DeerFlow capabilities inside the existing workbench pages (Expert, Skill, Connector, and a distinct Scheduled Tasks destination); refines ADR-0001
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 02af2a4e8
---

# Preserve the iDeer workbench experience when adopting DeerFlow features

The pre-DeerFlow iDeer pages keep their navigation positions, visual layout, wording, and common action paths. We adopt DeerFlow capabilities individually: custom Agent management belongs in the existing Expert page; Skill management and MCP connection configuration belong in the existing Skill and Connector pages; Scheduled Tasks gets a distinct destination after the original navigation items. This refines [ADR 0001](0001-workbench-capability-navigation.md), which listed only the original destinations. We chose this over duplicate management pages or placing scheduled conversations inside Workflow because users should find new capabilities without relearning the existing workbench.
