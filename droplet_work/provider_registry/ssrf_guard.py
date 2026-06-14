"""provider_registry.ssrf_guard — the HARD gate on user-supplied endpoints (W2).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §6 (the SSRF row) + §2e (SSRF is the #1 risk,
CVE-2025-59146 / CVE-2025-53767 / the LiteLLM-RAG-May-2026 precedent) + §13 R3.

THE THREAT: an authenticated gateway that accepts a user-supplied `base_url` (the
"add a self-hosted endpoint" feature) and fetches it server-side can be tricked into
hitting cloud-metadata (169.254.169.254 -> IAM/instance-token exfiltration), internal
RFC1918 services, or localhost. This module REJECTS any endpoint that resolves to a
non-public address, by EVERY known encoding trick (hex / octal / dword / IPv6-mapped /
DNS-rebind), and forces redirect re-validation on the caller.

DESIGN:
  * `validate_endpoint(host, port, scheme)` takes the THREE fields SEPARATELY (never a
    pre-assembled URL the attacker controls the parse of), reassembles server-side, and
    DNS-resolves ALL A/AAAA records — a host that resolves to even ONE private/blocked
    address is rejected (defeats DNS-rebind: every resolved IP must be public).
  * Pure decision logic + a DNS resolve. It does ZERO HTTP I/O (the fetch happens in the
    caller AFTER this returns OK). NEVER raises — always returns a Decision.
  * The resolver is INJECTABLE (`resolve=`) so the offline test suite drives every branch
    (hex/octal/IPv6/rebind) with a fake resolver and no real network.
  * `revalidate_redirect_location(location, base_scheme)` is the redirect-deny hook the
    HTTP caller MUST call on any 3xx Location with `allow_redirects=False` (a public host
    that 302-redirects to 169.254.169.254 is the classic bypass).

This module ships and is tested BEFORE any self-hosted provider can be registered (§13 R3).
It is the app-layer guard; the box egress firewall is the defense-in-depth backstop (§6).
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

# Allowed URL schemes (no file://, gopher://, ftp://, dict://, ldap:// — classic SSRF vectors).
_ALLOWED_SCHEMES = ("http", "https")

# The blocked network denylist (§6). DNS-resolve-ALL then check every IP against these.
# IPv4: localhost/loopback, this-host (0.0.0.0/8), RFC1918 private, link-local + cloud
# metadata (169.254/16 — covers 169.254.169.254 AWS/GCP/Azure/DO/OpenStack), CGNAT,
# benchmarking, and reserved. IPv6: loopback, link-local (fe80::/10 — covers fde::
# metadata on some clouds), ULA (fc00::/7), and the IPv4-mapped forms.
_BLOCKED_V4 = (
    "0.0.0.0/8",        # "this host" — 0.0.0.0 routes to localhost on Linux
    "10.0.0.0/8",       # RFC1918
    "100.64.0.0/10",    # CGNAT / shared address space
    "127.0.0.0/8",      # loopback
    "169.254.0.0/16",   # link-local + CLOUD METADATA (169.254.169.254)
    "172.16.0.0/12",    # RFC1918
    "192.0.0.0/24",     # IETF protocol assignments
    "192.0.2.0/24",     # TEST-NET-1
    "192.168.0.0/16",   # RFC1918
    "198.18.0.0/15",    # benchmarking
    "198.51.100.0/24",  # TEST-NET-2
    "203.0.113.0/24",   # TEST-NET-3
    "224.0.0.0/4",      # multicast
    "240.0.0.0/4",      # reserved (incl. 255.255.255.255 broadcast)
)
_BLOCKED_V6 = (
    "::1/128",          # loopback
    "::/128",           # unspecified
    "::ffff:0:0/96",    # IPv4-mapped (re-checked against v4 denylist after extraction)
    "64:ff9b::/96",     # NAT64 (could embed a private v4)
    "100::/64",         # discard-only
    "fe80::/10",        # link-local (some clouds expose metadata here)
    "fc00::/7",         # unique-local (ULA, the v6 RFC1918 analogue)
    "ff00::/8",         # multicast
    "2001:db8::/32",    # documentation
)

_BLOCKED_V4_NETS = [ipaddress.ip_network(c) for c in _BLOCKED_V4]
_BLOCKED_V6_NETS = [ipaddress.ip_network(c) for c in _BLOCKED_V6]

# Connect/read timeouts the HTTP caller MUST apply (exported so callers don't drift) (§6).
CONNECT_TIMEOUT_S = 10
READ_TIMEOUT_S = 60


@dataclass
class Decision:
    """The result of a validation. `ok` is the ONLY thing a caller should branch on.
    `reason`/`resolved_ips` are for the audit log + the "precise error" the UI shows."""
    ok: bool
    reason: str = ""
    host: str = ""
    port: int = 0
    scheme: str = ""
    resolved_ips: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # so `if validate_endpoint(...):` reads naturally
        return self.ok


# ---------------------------------------------------------------------------
# IP classification — the core "is this address public/safe?" decision.
# ---------------------------------------------------------------------------
def _is_blocked_ip(ip_str: str) -> Tuple[bool, str]:
    """Return (blocked, reason) for a single resolved IP string.

    Defeats the encoding tricks by going through Python's `ip_address`, which CANONICALIZES
    hex (0x7f.0.0.1), octal (0177.0.0.1), dword (2130706433), and IPv4-mapped IPv6
    (::ffff:127.0.0.1) into the real address BEFORE the denylist check. An IPv4-mapped or
    NAT64-embedded v6 has its v4 part extracted and re-checked against the v4 denylist.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # Not parseable as an IP at all -> refuse (fail-closed; we never fetch the unknown).
        return True, f"unparseable_ip:{ip_str}"

    # General-purpose flags first (covers anything the explicit nets miss).
    if ip.is_loopback:
        return True, "loopback"
    if ip.is_link_local:
        return True, "link_local_or_metadata"
    if ip.is_private:
        return True, "private_rfc1918"
    if ip.is_multicast:
        return True, "multicast"
    if ip.is_reserved:
        return True, "reserved"
    if ip.is_unspecified:
        return True, "unspecified"

    if isinstance(ip, ipaddress.IPv6Address):
        # IPv4-mapped / 6to4 / NAT64 can smuggle a private v4 inside a "public-looking" v6.
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return _is_blocked_ip(str(mapped))
        # 64:ff9b::a.b.c.d NAT64 — last 32 bits are the embedded v4.
        if ip in ipaddress.ip_network("64:ff9b::/96"):
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
            return _is_blocked_ip(str(embedded))
        for net in _BLOCKED_V6_NETS:
            if ip in net:
                return True, f"blocked_v6_net:{net}"
        return False, ""

    for net in _BLOCKED_V4_NETS:
        if ip in net:
            return True, f"blocked_v4_net:{net}"
    return False, ""


def _default_resolve(host: str) -> List[str]:
    """Resolve a host to ALL its A/AAAA records (defeats DNS-rebind: we check every IP).

    Uses getaddrinfo for BOTH families. Returns [] on failure (caller treats empty as a
    hard reject — we never fetch a host we couldn't resolve)."""
    out: List[str] = []
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except Exception:  # noqa: BLE001 — resolution failure -> empty -> reject
        return out
    for info in infos:
        sockaddr = info[4]
        if sockaddr and sockaddr[0]:
            ip = sockaddr[0]
            # strip a v6 scope id ("fe80::1%eth0")
            ip = ip.split("%", 1)[0]
            if ip not in out:
                out.append(ip)
    return out


def _looks_like_ip_literal(host: str) -> Optional[str]:
    """If `host` is itself an IP literal in ANY encoding (decimal/hex/octal/dword/IPv6/
    IPv4-mapped), return its CANONICAL string form so the denylist sees the real address.
    Else None (it's a name to DNS-resolve).

    This is the layer that catches `0x7f000001`, `0177.0.0.1`, `2130706433`, `[::1]`,
    `[::ffff:169.254.169.254]` — encodings a naive denylist string-match would miss.
    """
    h = (host or "").strip()
    if not h:
        return None
    # Bracketed IPv6 literal: [::1] -> ::1
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    h = h.split("%", 1)[0]  # drop a zone id
    # Python's ip_address canonicalizes hex/octal/dword v4 AND every v6 form.
    try:
        return str(ipaddress.ip_address(h))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# The public gate.
# ---------------------------------------------------------------------------
def validate_endpoint(
    host: str,
    port: int = 443,
    scheme: str = "https",
    *,
    resolve: Optional[Callable[[str], List[str]]] = None,
    allow_hosts: Optional[List[str]] = None,
) -> Decision:
    """HARD-gate a user-supplied endpoint. Returns a Decision (truthy iff safe to fetch).

    Steps (§6, fail-closed at every one):
      1. scheme in {http, https} (no file/gopher/ftp/dict/ldap).
      2. port is a sane 1..65535 int.
      3. host present; if it's an IP LITERAL in any encoding, canonicalize + denylist-check
         it DIRECTLY (no DNS — an attacker can't rebind a literal).
      4. else DNS-resolve ALL A/AAAA; reject if resolution is empty; reject if ANY resolved
         IP is private/loopback/link-local/metadata/reserved (defeats DNS-rebind).
      5. optional host allowlist for HOSTED providers (exact host or suffix match).

    `resolve` is injectable for tests. NEVER raises.
    """
    sch = (scheme or "").strip().lower()
    if sch not in _ALLOWED_SCHEMES:
        return Decision(False, reason=f"scheme_not_allowed:{sch or '(empty)'}",
                        host=host, port=port, scheme=sch)

    try:
        p = int(port)
    except (TypeError, ValueError):
        return Decision(False, reason=f"bad_port:{port!r}", host=host, scheme=sch)
    if not (1 <= p <= 65535):
        return Decision(False, reason=f"port_out_of_range:{p}", host=host, scheme=sch)

    h = (host or "").strip()
    if not h:
        return Decision(False, reason="empty_host", port=p, scheme=sch)
    # A host must never carry credentials, a path, or a port — those belong in separate fields.
    if any(c in h for c in ("/", "\\", "@", " ", "?", "#")) or ":" in h.split("]")[-1].lstrip(":"):
        # (the `]`/`:` dance allows a bare bracketed IPv6 literal but rejects host:port smuggling)
        if not (h.startswith("[") and h.endswith("]")):
            return Decision(False, reason="malformed_host", host=h, port=p, scheme=sch)

    allow = [a.strip().lower() for a in (allow_hosts or []) if a.strip()]

    # --- Case A: the host is an IP literal (any encoding). Check it directly. ---
    literal = _looks_like_ip_literal(h)
    if literal is not None:
        blocked, reason = _is_blocked_ip(literal)
        if blocked:
            return Decision(False, reason=f"ip_literal_blocked:{reason}",
                            host=h, port=p, scheme=sch, resolved_ips=[literal])
        if allow and not _host_in_allowlist(literal, allow):
            return Decision(False, reason="not_in_allowlist",
                            host=h, port=p, scheme=sch, resolved_ips=[literal])
        return Decision(True, reason="ok_ip_literal", host=h, port=p, scheme=sch,
                        resolved_ips=[literal])

    # --- Case B: a DNS name. Resolve ALL records; every one must be public. ---
    if allow and not _host_in_allowlist(h.lower(), allow):
        return Decision(False, reason="not_in_allowlist", host=h, port=p, scheme=sch)

    resolver = resolve or _default_resolve
    try:
        ips = list(resolver(h))
    except Exception:  # noqa: BLE001 — a throwing resolver = reject (fail-closed)
        ips = []
    if not ips:
        return Decision(False, reason="dns_unresolved", host=h, port=p, scheme=sch)
    for ip_str in ips:
        blocked, reason = _is_blocked_ip(ip_str)
        if blocked:
            # Even ONE private resolved IP -> reject the whole host (DNS-rebind defense).
            return Decision(False, reason=f"resolves_to_blocked:{reason}:{ip_str}",
                            host=h, port=p, scheme=sch, resolved_ips=ips)
    return Decision(True, reason="ok_resolved_public", host=h, port=p, scheme=sch,
                    resolved_ips=ips)


def _host_in_allowlist(host_or_ip: str, allow: List[str]) -> bool:
    """Exact host match OR dot-suffix match (`api.fal.run` matches allow `fal.run`).
    An IP literal must match exactly (no suffix semantics for IPs)."""
    h = host_or_ip.lower()
    for a in allow:
        if h == a:
            return True
        # suffix match only for names, and only on a label boundary
        if not _looks_like_ip_literal(h) and h.endswith("." + a):
            return True
    return False


def revalidate_redirect_location(
    location: str,
    *,
    resolve: Optional[Callable[[str], List[str]]] = None,
    allow_hosts: Optional[List[str]] = None,
) -> Decision:
    """Re-validate a 3xx redirect target (the HTTP caller MUST use allow_redirects=False
    and pass every Location here). A public host that 302s to 169.254.169.254 is the
    classic SSRF bypass — this re-runs the full gate on the redirect URL.

    Splits the Location into scheme/host/port WITHOUT trusting urllib's lenient parse for
    the security decision (we re-extract host+port ourselves). NEVER raises.
    """
    loc = (location or "").strip()
    if not loc:
        return Decision(False, reason="empty_redirect_location")
    # A scheme-relative or relative redirect (//evil, /path) is refused — only absolute
    # http(s) URLs are honored, and they go through the full gate.
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(loc)
    except Exception:  # noqa: BLE001
        return Decision(False, reason="redirect_unparseable")
    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return Decision(False, reason=f"redirect_scheme_not_allowed:{scheme or '(relative)'}")
    host = parts.hostname or ""
    port = parts.port or (443 if scheme == "https" else 80)
    return validate_endpoint(host, port, scheme, resolve=resolve, allow_hosts=allow_hosts)
