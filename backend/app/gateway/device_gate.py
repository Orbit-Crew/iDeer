"""Device control-plane credential gate shared by the security middlewares.

The device endpoints authenticate with device credentials — the pairing code
and claim token on the bootstrap endpoints, the ``X-Device-Session`` token
after registration — enforced inside the devices router and
``DeviceControlService``, not with the browser session cookie. Both security
middlewares consult this predicate so the auth gate and the CSRF gate agree
on exactly which routes are device-credentialed:

- ``AuthMiddleware`` lets them past the user-session gate (a device has no
  browser session). Fail-closed is preserved: without a valid device
  credential the route layer answers 401 instead of the middleware.
- ``CSRFMiddleware`` skips the double-submit cookie check: these routes never
  trust ambient cookie credentials, so a cross-site request has nothing to
  ride (same rationale as the bearer-token fast path).

The predicate is deliberately narrow — POST on exactly the four
device-credentialed endpoints. Every other ``/api/devices`` route (pairing
create/confirm, listing, revocation, tasks, artifact grants) keeps the normal
browser-session gates.
"""

from __future__ import annotations

import re

_BOOTSTRAP_PATHS = frozenset({"/api/devices/register", "/api/devices/register/complete", "/api/devices/login/start"})
_LOGIN_COMPLETE_PATH = re.compile(r"^/api/devices/login/[A-Za-z0-9-]{1,64}/complete$")
_SESSION_PATH = re.compile(r"^/api/devices/[^/]+/(?:heartbeat|disconnect)$")


def is_device_credential_route(method: str, path: str) -> bool:
    """True for the device-credentialed control-plane endpoints.

    Matching uses the same root-path-adjusted request path the route table
    matches, rstripped of a trailing slash.
    """
    if method != "POST":
        return False
    stripped = path.rstrip("/")
    if stripped in _BOOTSTRAP_PATHS:
        return True
    return _SESSION_PATH.match(stripped) is not None or _LOGIN_COMPLETE_PATH.fullmatch(stripped) is not None
