---
id: docs-local-runtime-browser-login
kind: reference
status: current
owner: repository maintainers
scope: Browser approval, Desktop completion exchange, and public device WebSocket entry
last-verified: 2026-10-18
verified-against: issue-98 working candidate
---

# Browser login and Desktop pairing

Desktop opens `/desktop-login?login_id=...` in the system browser. The page uses
the existing platform login/SSO and shows the signed-in account, device name and
12-hex-character device-key verification code. The user must check that code
against Desktop and explicitly confirm that this is their own device. Browser
authentication alone never creates a Desktop business session.

Runtime starts a 300-second request with its random initiator secret and Ed25519
public key. Server stores only the secret's SHA-256 digest. Browser confirmation
binds the existing authentication/RBAC user and current token version. Runtime
polls completion with its initiating secret and public key. Wrong binding returns
`401 LOGIN_BINDING_INVALID`; a different confirmed owner gets
`403 LOGIN_OWNER_MISMATCH`; expiry returns `410 LOGIN_EXPIRED`; replay returns
`409 LOGIN_ALREADY_USED`. A database compare-and-swap allows one completion
across workers. Failure after consumption cannot reuse the exchange.

Successful completion calls the existing pairing create/register/confirm/complete
transitions. It returns separate one-hour platform user and device credentials,
with the pinned broker key, only in the Runtime HTTPS response. The browser gets
no credentials. Desktop Runtime writes private key/business/device credentials
to separate OS secure-store entries, and settings contain references only. A
failed secure write is explicit, cleans partial writes and never falls back to
a plaintext file. Desktop renderer receives bounded identity/status fields.

The public entry exposes `/api/devices/ws` with WebSocket Upgrade in local,
Docker and Helm nginx configurations. Device credentials remain inside the
signed HELLO frame, not the URL. Runtime opens the connection outward and verifies
the pinned broker key before reporting connected. A browser-login profile with
expired/unvalidated business credentials does not start an executable device
connection. Device-only Desktop profiles remain offline until business login.
An existing device can reauthenticate only after the same owner confirms and
Runtime proves possession of the stored key by signing the login ID and initiating
secret. It keeps its device ID; old sessions and broker connections are invalidated.
No inbound device listener or alternative agent is introduced.

Server routes are owned by `backend/app/gateway/routers/devices.py`;
`DesktopLoginService` owns the approval lifecycle and delegates device lifecycle
to `DeviceControlService`. Schema revision `20261018_desktop_login` is an additive
child of `20261001_rejoin_upstream_line`. No user database is added. See the
[acceptance report](../acceptance/issue-98/report.md) for execution status.
