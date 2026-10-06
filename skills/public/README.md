# skills/public — upstream landing zone (not the authoritative skill tree)

This directory only receives original upstream skill packages. Do not make
enterprise adaptations here (governance frontmatter, offline behavior,
rebranding): upstream merges overwrite this tree freely.

The authoritative bundled skill tree is [`resources/skills/`](../../resources/skills/).
Enterprise skill content lives there and ships to the runtime (docker
bind-mount) and intranet packaging. Skill review and the script-level test
loader both target `resources/skills/` only.

To take an upstream change: copy what you need from here into
`resources/skills/<skill>/`, preserving that copy's enterprise SKILL.md
adaptations, and align it with the script-level tests in
`backend/tests/unit/skills/`.

This landing-zone rule is declared in the root `AGENTS.md` (mirrored to
`CLAUDE.md`), which is the surviving authority for repository structure.
