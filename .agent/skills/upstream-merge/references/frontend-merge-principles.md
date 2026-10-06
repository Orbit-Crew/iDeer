# Frontend merge principles (P1-P6) and the entry-parity gate

Origin: distilled from the deerflow-main 0f7d8709 round, where three classes of silent frontend loss were found after "successful" merges — routes present but the entry invisible, frontend calls with no mounted backend router, and upstream brand strings left in components. Read this file whenever the upstream range touches `frontend/` (or the equivalent UI tree). A prior round's archive may carry the original (`FRONTEND_MERGE_PRINCIPLES.md`); prefer the repo's version when it exists.

## The six principles

- **P1 Superset.** Merged result = local entries ∪ upstream entries − entries both sides agreed to remove. No entry disappears without a record; every deletion is registered (a nav-removal allow-list or an explicit exclusion row in the adoption matrix).
- **P2 Entry triple.** An "entry" = route file + visible navigation link + i18n label. Any one missing means the entry is lost. Checking routes alone is not enough, and neither is checking links alone (a link whose backend route is never mounted is a 404).
- **P3 API contract closure.** Every `/api` call the frontend makes must resolve to a mounted backend router. Upstream routers that newly shipped frontend pages depend on are mounted together with the pages; excluded routers (canonical-source decisions) are registered, never silently skipped.
- **P4 Fix placement.** Local and upstream navigation items coexist as a union, local ordering first and upstream additions appended. When an upstream page replaces a local page with the same function, the local entry path survives as a redirect. Heavy panels enter shared bundles only through dynamic imports, pinned by bundle-boundary tests.
- **P5 Brand pass-through.** Upstream UI copy enters the product only through the i18n locale files (single mapping point); upstream brand strings never stay hardcoded in components. After each round, scan the UI tree for upstream brand strings.
- **P6 Test pinning.** Every entry class has an automated guard that fails the build after a loss instead of relying on manual comparison: nav-set test, the entry-parity script, bundle-boundary test, router lifecycle tests.

## The four-layer entry-parity gate

Run after conflict resolution and before committing the round (adapt names to the repo's script when present, e.g. `scripts/check-frontend-entry-parity.sh <baseline> HEAD`):

| Layer | Check | Failure class it catches |
| --- | --- | --- |
| 1 Route files | every baseline page route exists at HEAD | deleted pages |
| 2 Visible nav | every baseline sidebar link still resolves (+ registered removal allow-list) | route present, entry invisible |
| 3 i18n labels | sidebar keys survived | label loss, brand residue |
| 4 API orphans | frontend calls resolve to routes actually mounted by the backend app | calls with no mounted router |

Pass condition: all four layers clean, with every removal or orphan explicitly registered. Invalidate any route-dump cache the script uses before trusting a pass (see the cache rule in the audits reference).

## Terminology mapping precedent

When a round includes an upstream vocabulary rename (components, routes, display words), record the full mapping table in the round's merge playbook, apply it in one atomic convergence (complete the rename this round or revert it whole), and sweep tests/specs to the new paths so future upstream files merge without per-line rewriting. Display language may keep localized words (e.g. Chinese) while code and English copy unify on the upstream term.
