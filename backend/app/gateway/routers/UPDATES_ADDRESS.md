---
id: controlled-desktop-updates-address
kind: reference
status: current
owner: Neowyh
scope: Reviewed Desktop release publication and signed compatibility admission
last-verified: 2026-10-25
verified-against: codex/complete-issues-105-110
---

# Controlled update publication

The formal Gateway and both bundled Nginx entries publish the read-only
/updates/ prefix. The publication directory UPDATES_CONTROLLED_DIR contains
operations-reviewed manifest.json and manifest.sig under desktop/, and
compatibility.json plus compatibility.sig at its root.

A Desktop patch asset is desktop/files/resources/... with the corresponding
installation-relative path, SHA-256 and length listed in the signed manifest.
The full installer is desktop/installer.exe and requires the manifest installer
entry with path installer.exe, sha256 and bytes. Gateway denies unlisted files,
corrupt content, traversal and symlinks escaping the controlled directory.
Missing publication returns DOCUMENT_NOT_PUBLISHED with status 404.

Desktop verifies the detached signature with its packaged public key before
preparing an update; checking/download/import never authorizes installation.
Signing private keys stay outside source, images, logs and clients.
Gateway does not claim that an old correctly signed release is fresh solely
because its signature verifies. Operations must review candidate identities,
baselines and deployment order.

For new-task compatibility admission, deploy the matching trusted Ed25519 public
key at UPDATES_TRUSTED_PUBLIC_KEY_FILE and set SERVER_RELEASE_VERSION to the
actual Server release identity. Persist UPDATES_STATE_DIR across restarts.
Each signed device HELLO reports desktop_version, runtime_python and
protocol_version; every dispatch verifies that exact combination against
candidateCombo or supportedCombos, including minProtocol and per-capability
restrictions. Original clients without the new version fields require an
explicit legacyHello mapping in the reviewed combination, cross-checked with
their signed Runtime version and registered device metadata; ambiguous
mappings never grant admission. Existing unknown execution evidence and signed receipts survive
core blocking. See backend/docs/development-reference.md for the complete
publication, first-deployment fallback and authorization contracts.
