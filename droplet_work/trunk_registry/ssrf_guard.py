"""trunk_registry.ssrf_guard — REUSES provider_registry.ssrf_guard verbatim.

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.1 / §8 ("REUSE ... ssrf_guard ... import/share,
do not rewrite") + §6 ("SSRF via user sip_host | REUSE ssrf_guard.py verbatim").

A user/super-admin who registers a trunk supplies a `sip_host` (e.g. a self-hosted GSM gateway
on their LAN, or a SIP provider hostname). Validating that host server-side is the SAME SSRF
surface the provider registry already solved (CVE-2025-59146): a host resolving to
169.254.169.254 / RFC1918 / loopback must be rejected before any connect.

This module is a THIN RE-EXPORT of the LIVE, already-tested provider_registry.ssrf_guard — one
implementation on the box, no drift. `validate_endpoint(host, port, scheme)` and
`revalidate_redirect_location(...)` behave identically (every encoding trick: hex/octal/dword/
IPv6-mapped/DNS-rebind/redirect-deny). If provider_registry is somehow absent, validate FAILS
CLOSED (returns a not-ok Decision) — we never fall open on an SSRF check.
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - the box always ships provider_registry alongside this package.
    from provider_registry.ssrf_guard import (  # type: ignore  # noqa: F401
        Decision,
        validate_endpoint,
        revalidate_redirect_location,
        CONNECT_TIMEOUT_S,
        READ_TIMEOUT_S,
    )
    _SHARED_OK = True
except Exception:  # noqa: BLE001
    _SHARED_OK = False

    class Decision:  # type: ignore[no-redef]
        """Fail-closed stand-in used only if provider_registry is absent (never on the box)."""

        def __init__(self, ok: bool = False, reason: str = "", **kw: Any):
            self.ok = ok
            self.reason = reason
            for k, v in kw.items():
                setattr(self, k, v)

        def __bool__(self) -> bool:
            return self.ok

    CONNECT_TIMEOUT_S = 10
    READ_TIMEOUT_S = 60

    def validate_endpoint(host, port, scheme, **kw) -> "Decision":  # type: ignore[no-redef]
        # FAIL CLOSED — never allow an unvalidated host when the SSRF guard is missing.
        return Decision(ok=False, reason="ssrf_guard_unavailable_fail_closed",
                        host=str(host or ""), port=int(port or 0), scheme=str(scheme or ""))

    def revalidate_redirect_location(location, **kw) -> "Decision":  # type: ignore[no-redef]
        return Decision(ok=False, reason="ssrf_guard_unavailable_fail_closed")
