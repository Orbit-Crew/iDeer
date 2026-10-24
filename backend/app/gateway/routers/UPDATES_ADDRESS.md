# Controlled update address (issue 107)

The Desktop derives its controlled address from the paired Server origin and
reads exactly four documents:

| Path | Consumed by | Purpose |
| --- | --- | --- |
| `/updates/desktop/manifest.json` | issue 107 online check | the signed update manifest |
| `/updates/desktop/manifest.sig` | issue 107 online check | detached Ed25519 signature |
| `/updates/compatibility.json` | issue 110 gate | the signed compatibility declaration |
| `/updates/compatibility.sig` | issue 110 gate | detached signature |

Operations workflow:

1. Build the manifest with the Desktop repo's
   `scripts/release/issue-107/make-update.cjs` (signs with a key kept outside
   every repository).
2. Review the signed pair, then place **exactly those file names** into the
   directory configured by `UPDATES_CONTROLLED_DIR` (deployment config; no
   default is published). The Gateway serves them read-only with
   `Cache-Control: no-store`; anything else under that directory stays private.
3. Until a document exists, the endpoint answers 404
   (`DOCUMENT_NOT_PUBLISHED`) and the Desktop reports the absence honestly —
   checking never installs or gates anything by itself.

The Desktop verifies every signature against its pinned public key, so
placing stale or unreviewed documents can only fail verification, never
install or restrict by itself.
