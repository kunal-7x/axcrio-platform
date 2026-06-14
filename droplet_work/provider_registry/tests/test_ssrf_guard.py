"""Offline test suite for provider_registry.ssrf_guard (W2).

Spec acceptance (PROVIDER-FRAMEWORK-PLAN §10.4 / §14 W2): 127.0.0.1, 169.254.169.254, 10.x,
hex/octal/dword, IPv6-mapped, DNS-rebind, redirect-to-private ALL rejected; a public https
host passes. The resolver is INJECTED so there is ZERO real network I/O.

Run standalone:  python -m provider_registry.tests.test_ssrf_guard
(also collectible by pytest). Exit 0 = all PASS.
"""
from __future__ import annotations

import sys

from provider_registry import ssrf_guard as sg


# A fake resolver: a host -> list-of-IPs map. Defeats real DNS; lets us script DNS-rebind.
def _resolver(mapping):
    def _r(host):
        return list(mapping.get(host, []))
    return _r


_PUBLIC = _resolver({
    "api.fal.run": ["151.101.1.140"],
    "evil.example.com": ["8.8.8.8"],
    "rebind.example.com": ["8.8.8.8", "169.254.169.254"],   # one public + one metadata
    "internal.corp": ["10.1.2.3"],
    "v6public.example.com": ["2606:4700:4700::1111"],        # Cloudflare public v6
    "v6mapped.example.com": ["::ffff:127.0.0.1"],            # IPv4-mapped loopback
})


def _expect_block(host, port=443, scheme="https", why=""):
    d = sg.validate_endpoint(host, port, scheme, resolve=_PUBLIC)
    assert not d.ok, f"EXPECTED BLOCK but allowed: {host!r} ({why}) -> {d.reason}"
    return d


def _expect_allow(host, port=443, scheme="https", why="", allow_hosts=None):
    d = sg.validate_endpoint(host, port, scheme, resolve=_PUBLIC, allow_hosts=allow_hosts)
    assert d.ok, f"EXPECTED ALLOW but blocked: {host!r} ({why}) -> {d.reason}"
    return d


def run() -> int:
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, ""))
        except AssertionError as e:
            results.append((name, False, str(e)))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"UNEXPECTED {type(e).__name__}: {e}"))

    # --- localhost / loopback (literal, every v4 encoding) ---
    check("block_127.0.0.1", lambda: _expect_block("127.0.0.1", why="loopback literal"))
    check("block_localhost_dns", lambda: _expect_block("localhost", why="resolves loopback")
          if False else _expect_block_dns("localhost", ["127.0.0.1"]))
    check("block_0.0.0.0", lambda: _expect_block("0.0.0.0", why="this-host"))
    check("block_hex_127", lambda: _expect_block("0x7f000001", why="hex dword loopback"))
    check("block_octal_127", lambda: _expect_block("0177.0.0.1", why="octal loopback"))
    check("block_dword_127", lambda: _expect_block("2130706433", why="dword loopback"))

    # --- cloud metadata (THE #1 risk) ---
    check("block_metadata_169.254.169.254",
          lambda: _expect_block("169.254.169.254", why="cloud metadata"))
    check("block_metadata_hex",
          lambda: _expect_block("0xA9FEA9FE", why="hex metadata"))
    check("block_link_local_169.254.x",
          lambda: _expect_block("169.254.1.1", why="link-local"))

    # --- RFC1918 private (literal + via DNS) ---
    check("block_10.x", lambda: _expect_block("10.0.0.5", why="rfc1918 /8"))
    check("block_172.16.x", lambda: _expect_block("172.16.5.5", why="rfc1918 /12"))
    check("block_192.168.x", lambda: _expect_block("192.168.1.1", why="rfc1918 /16"))
    check("block_internal_dns", lambda: _expect_block("internal.corp", why="DNS->10.x"))
    check("block_cgnat_100.64", lambda: _expect_block("100.64.0.1", why="CGNAT"))

    # --- IPv6 loopback / ULA / IPv4-mapped ---
    check("block_v6_loopback", lambda: _expect_block("[::1]", why="v6 loopback"))
    check("block_v6_ula", lambda: _expect_block("[fc00::1]", why="v6 ULA"))
    check("block_v6_linklocal", lambda: _expect_block("[fe80::1]", why="v6 link-local"))
    check("block_v6_mapped_loopback",
          lambda: _expect_block("[::ffff:127.0.0.1]", why="v4-mapped loopback literal"))
    check("block_v6_mapped_metadata",
          lambda: _expect_block("[::ffff:169.254.169.254]", why="v4-mapped metadata"))
    check("block_v6_mapped_dns",
          lambda: _expect_block("v6mapped.example.com", why="DNS->v4-mapped loopback"))

    # --- DNS-rebind: a host that resolves to one PUBLIC + one PRIVATE must be rejected ---
    check("block_dns_rebind",
          lambda: _expect_block("rebind.example.com", why="rebind: public+metadata"))

    # --- scheme / port / malformed-host gating ---
    check("block_scheme_file", lambda: _expect_block("api.fal.run", scheme="file", why="file://"))
    check("block_scheme_gopher", lambda: _expect_block("api.fal.run", scheme="gopher", why="gopher://"))
    check("block_port_zero", lambda: _expect_block("api.fal.run", port=0, why="port 0"))
    check("block_port_high", lambda: _expect_block("api.fal.run", port=99999, why="port>65535"))
    check("block_empty_host", lambda: _expect_block("", why="empty host"))
    check("block_hostport_smuggle",
          lambda: _expect_block("api.fal.run:22", why="host:port smuggling"))
    check("block_credential_smuggle",
          lambda: _expect_block("user@169.254.169.254", why="userinfo smuggling"))
    check("block_dns_unresolved",
          lambda: _expect_block("nonexistent.invalid", why="empty resolution -> reject"))

    # --- the happy path: public hosts pass ---
    check("allow_public_https", lambda: _expect_allow("api.fal.run", why="public host"))
    check("allow_public_http", lambda: _expect_allow("api.fal.run", port=80, scheme="http",
                                                      why="public http"))
    check("allow_public_v6", lambda: _expect_allow("v6public.example.com", why="public v6"))
    check("allow_public_literal", lambda: _expect_allow("8.8.8.8", why="public IP literal"))

    # --- host allowlist (HOSTED providers) ---
    check("allow_in_allowlist",
          lambda: _expect_allow("api.fal.run", why="suffix allow", allow_hosts=["fal.run"]))
    check("block_not_in_allowlist", lambda: _assert_block_allowlist())

    # --- redirect-deny: a 302 Location to a private target must be re-rejected ---
    check("redirect_to_metadata_blocked", lambda: _assert_redirect_block(
        "http://169.254.169.254/latest/meta-data/", why="redirect to metadata"))
    check("redirect_to_private_dns_blocked", lambda: _assert_redirect_block(
        "https://internal.corp/x", why="redirect to private DNS"))
    check("redirect_relative_blocked", lambda: _assert_redirect_block(
        "//evil/path", why="scheme-relative redirect"))
    check("redirect_to_public_allowed", lambda: _assert_redirect_allow(
        "https://api.fal.run/next", why="redirect to public"))

    return _report("SSRF", results)


# helpers that need a custom resolver/closure
def _expect_block_dns(host, ips):
    d = sg.validate_endpoint(host, 443, "https", resolve=_resolver({host: ips}))
    assert not d.ok, f"EXPECTED BLOCK (dns->{ips}) but allowed: {host} -> {d.reason}"


def _assert_block_allowlist():
    d = sg.validate_endpoint("evil.example.com", 443, "https",
                             resolve=_PUBLIC, allow_hosts=["fal.run"])
    assert not d.ok, f"EXPECTED BLOCK (not in allowlist) but allowed -> {d.reason}"


def _assert_redirect_block(location, why=""):
    d = sg.revalidate_redirect_location(location, resolve=_PUBLIC)
    assert not d.ok, f"EXPECTED redirect BLOCK ({why}) but allowed -> {d.reason}"


def _assert_redirect_allow(location, why=""):
    d = sg.revalidate_redirect_location(location, resolve=_PUBLIC)
    assert d.ok, f"EXPECTED redirect ALLOW ({why}) but blocked -> {d.reason}"


def _report(suite, results):
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, msg in results:
        if not ok:
            print(f"[{suite}] FAIL {name}: {msg}")
    print(f"[{suite}] {passed}/{total} PASS")
    return 0 if passed == total else 1


# ---- pytest collection ----
def test_ssrf_guard_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
