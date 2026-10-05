---
id: adr-0001-workbench-capability-navigation
kind: decision
status: current
owner: repository maintainers
scope: persistent workbench navigation destinations and the lifecycle actions each capability page unifies (frontend); ownership, visibility, and administrator permission boundaries are out of scope
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 02af2a4e8
---

# Consolidate capability management in workbench navigation

The persistent workbench navigation is New conversation, Conversation history, Expert-Skill-Connector, Workflow, and Library. Expert-Skill-Connector is one capability center with Expert, Skill, and Connector pages; it replaces the Settings Skill and Tool entries, while Memory remains in Settings and system-tool governance remains in the administrator surface. Each page unifies authorized lifecycle, task-use, import/export, favorite, and visibility-change actions without changing ownership, visibility, or administrator permission boundaries.

## Consequences

New conversation and Conversation history become distinct destinations. Automation and Workflow become one user-facing Workflow destination. Connector is the user-facing name for MCP connection configuration; its task use selects or authorizes the connection for a conversation rather than treating it as a slash-invoked Skill. Legacy Settings launches for Skill and Tool redirect to the corresponding capability page.
