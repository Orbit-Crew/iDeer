"""Default-deny network policy for enterprise runs."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    """Allow only explicitly listed internal hosts unless opted in."""

    allowed_hosts: tuple[str, ...] = ()
    allow_public: bool = False

    def allows(self, target: str) -> bool:
        parsed = urlparse(target if "://" in target else f"https://{target}")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            return False
        if host in {item.lower().rstrip(".") for item in self.allowed_hosts}:
            return True
        if self.allow_public and not self._is_private_or_local(host):
            return True
        return False

    @staticmethod
    def _is_private_or_local(host: str) -> bool:
        if host == "localhost" or host.endswith(".local"):
            return True
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # Non-IP hostnames are not resolved here; wiring this policy into
            # an egress path requires adding DNS-resolution checks (decision
            # 2026-10-15 product-semantics package, item 04-M1).
            return False
        # Mirror the harness proxy's address_is_public bar: global scope only,
        # so RFC1918 (incl. 172.16/12), link-local/cloud metadata (169.254/16),
        # loopback, ULA fc00::/7, CGNAT and benchmarking ranges stay private.
        return not (address.is_global and not address.is_multicast and not getattr(address, "is_site_local", False))
