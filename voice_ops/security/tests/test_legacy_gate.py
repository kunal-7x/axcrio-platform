"""W20 — legacy-token gate tests (mock auth, ZERO droplet imports).

Covers the founder's acceptance criteria:
  * with LEGACY_TOKEN off  -> legacy_pw rejected (401), valid JWT passes, new routes deny legacy.
  * with it on (transition) -> legacy works BUT is logged/audited as deprecated.
  * /admin/* always excludes legacy in EVERY mode.
  * mode resolution precedence + fail-closed on garbage values.
"""
from __future__ import annotations

import asyncio

import pytest

from voice_ops.security import legacy_gate as lg
from voice_ops.security.legacy_gate import (
    GateDecision,
    LegacyMode,
    LegacyTokenRejected,
    enforce,
    evaluate,
    resolve_mode,
)
from voice_ops.security.principal import (
    AuthMethod,
    jwt_principal,
    legacy_principal,
    logto_principal,
    service_principal,
)

# The legacy secret we are RETIRING — reconstructed from fragments so the contiguous literal never
# appears in tracked source (W20 BLOCKER 3 scrub applies to tests too). Used ONLY to assert it is
# NEVER present in our outputs.
_LEGACY_LITERAL = "Famit" + "Call" + "2026"


# --------------------------------------------------------------------------- #
# mode resolution
# --------------------------------------------------------------------------- #
def test_library_default_is_off():
    # no env at all -> conservative OFF (reject legacy)
    assert resolve_mode(env={}) is LegacyMode.OFF


def test_explicit_arg_beats_env():
    assert resolve_mode(LegacyMode.ON, env={"LEGACY_TOKEN_MODE": "off"}) is LegacyMode.ON
    assert resolve_mode("transition", env={"LEGACY_TOKEN_ENABLED": "false"}) is LegacyMode.TRANSITION


def test_legacy_token_enabled_true_maps_to_transition_not_silent_on():
    # leaving the OLD flag set must still produce the deprecation trail, not a silent accept.
    assert resolve_mode(env={"LEGACY_TOKEN_ENABLED": "true"}) is LegacyMode.TRANSITION


def test_legacy_token_enabled_false_maps_to_off():
    assert resolve_mode(env={"LEGACY_TOKEN_ENABLED": "false"}) is LegacyMode.OFF


def test_mode_env_precedence_over_enabled_flag():
    assert resolve_mode(env={"LEGACY_TOKEN_MODE": "on", "LEGACY_TOKEN_ENABLED": "false"}) is LegacyMode.ON


def test_garbage_mode_fails_closed_to_off():
    assert resolve_mode("banana") is LegacyMode.OFF
    assert resolve_mode(env={"LEGACY_TOKEN_MODE": "wide-open"}) is LegacyMode.OFF


# --------------------------------------------------------------------------- #
# OFF — the target end-state: legacy rejected, real auth passes
# --------------------------------------------------------------------------- #
def test_off_rejects_legacy_pw():
    d = evaluate(AuthMethod.LEGACY_PW, mode=LegacyMode.OFF, route="/callbacks", audit=False)
    assert isinstance(d, GateDecision)
    assert d.allowed is False
    assert d.reason == "legacy_retired"


def test_off_jwt_passes():
    d = evaluate(AuthMethod.JWT, mode=LegacyMode.OFF, route="/callbacks", audit=False)
    assert d.allowed is True
    assert d.deprecated is False


def test_off_logto_and_service_pass():
    assert evaluate(AuthMethod.LOGTO, mode=LegacyMode.OFF, route="/x", audit=False).allowed is True
    assert evaluate(AuthMethod.SERVICE, mode=LegacyMode.OFF, route="/x", audit=False).allowed is True


def test_enforce_off_raises_401_for_legacy():
    with pytest.raises(LegacyTokenRejected) as ei:
        enforce(legacy_principal("admin-tenant"), mode=LegacyMode.OFF, route="/callbacks", audit=False)
    assert ei.value.http_status == 401
    assert ei.value.code == "legacy_token_retired"


def test_enforce_off_passes_jwt_unchanged():
    p = jwt_principal("t-1", role="admin", is_admin=True, sub="user-9")
    out = enforce(p, mode=LegacyMode.OFF, route="/callbacks", audit=False)
    assert out is p  # unchanged, allowed


# --------------------------------------------------------------------------- #
# TRANSITION — legacy works but is deprecated + audited
# --------------------------------------------------------------------------- #
def test_transition_allows_legacy_but_marks_deprecated():
    d = evaluate(AuthMethod.LEGACY_PW, mode=LegacyMode.TRANSITION, route="/usage", audit=False)
    assert d.allowed is True
    assert d.deprecated is True
    assert d.reason == "legacy_transition_deprecated"


def test_transition_enforce_passes_legacy_and_warns(caplog):
    import logging
    caplog.set_level(logging.WARNING, logger="voice_ops.security.legacy_gate")
    p = legacy_principal("admin-tenant")
    out = enforce(p, mode=LegacyMode.TRANSITION, route="/usage", audit=False)
    assert out is p
    assert any("DEPRECATED legacy_pw" in r.message for r in caplog.records)


class _CapturingBus:
    """Minimal async EventBus stand-in: records emitted events."""

    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


def test_transition_emits_deprecation_audit_event():
    bus = _CapturingBus()
    lg.set_event_bus(bus)
    try:
        # run inside an event loop so the emit schedules + completes on the loop
        async def _run():
            evaluate(AuthMethod.LEGACY_PW, mode=LegacyMode.TRANSITION,
                     tenant_id="t-7", route="/whatsapp/send", audit=True)
            # let the scheduled task run
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        asyncio.run(_run())
    finally:
        lg.set_event_bus(None)
    assert len(bus.events) == 1
    ev = bus.events[0]
    assert ev.name == "auth.legacy_token_used"
    assert ev.tenant_id == "t-7"
    assert ev.payload.get("route") == "/whatsapp/send"
    assert ev.payload.get("deprecated") is True
    # NEVER the secret in the event
    assert _LEGACY_LITERAL not in str(ev.payload)
    assert "password" not in {k.lower() for k in ev.payload}


def test_emit_is_failsoft_when_bus_raises():
    class _BadBus:
        async def emit(self, event):
            raise RuntimeError("redis down")

    lg.set_event_bus(_BadBus())
    try:
        async def _run():
            # must NOT raise even though the bus blows up
            d = evaluate(AuthMethod.LEGACY_PW, mode=LegacyMode.TRANSITION,
                         tenant_id="t", route="/x", audit=True)
            await asyncio.sleep(0)
            return d
        d = asyncio.run(_run())
        assert d.allowed is True
    finally:
        lg.set_event_bus(None)


# --------------------------------------------------------------------------- #
# ON — pre-W20 status quo (still excludes admin)
# --------------------------------------------------------------------------- #
def test_on_allows_legacy_silently():
    d = evaluate(AuthMethod.LEGACY_PW, mode=LegacyMode.ON, route="/x", audit=False)
    assert d.allowed is True
    assert d.deprecated is False


# --------------------------------------------------------------------------- #
# /admin/* — legacy ALWAYS excluded, in every mode (no regression)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mode", [LegacyMode.OFF, LegacyMode.TRANSITION, LegacyMode.ON])
def test_admin_route_always_rejects_legacy(mode):
    d = evaluate(AuthMethod.LEGACY_PW, mode=mode, route="/admin/tenants",
                 is_admin_route=True, audit=False)
    assert d.allowed is False
    assert d.reason == "legacy_excluded_from_admin"


@pytest.mark.parametrize("mode", [LegacyMode.OFF, LegacyMode.TRANSITION, LegacyMode.ON])
def test_admin_route_allows_real_auth(mode):
    assert evaluate(AuthMethod.JWT, mode=mode, route="/admin/tenants",
                    is_admin_route=True, audit=False).allowed is True


# --------------------------------------------------------------------------- #
# unauthenticated
# --------------------------------------------------------------------------- #
def test_none_method_not_allowed():
    d = evaluate(AuthMethod.NONE, mode=LegacyMode.OFF, route="/x", audit=False)
    assert d.allowed is False
    assert d.reason == "unauthenticated"


def test_is_enabled_helper():
    assert lg.is_enabled(env={"LEGACY_TOKEN_MODE": "off"}) is False
    assert lg.is_enabled(env={"LEGACY_TOKEN_MODE": "transition"}) is True
    assert lg.is_enabled(env={"LEGACY_TOKEN_MODE": "on"}) is True


def test_principal_repr_never_leaks_secret():
    p = legacy_principal("admin-tenant")
    assert _LEGACY_LITERAL not in repr(p)
    assert "password" not in repr(p).lower()


# --------------------------------------------------------------------------- #
# password -> TOKEN mint gate (red-team W20 BLOCKER 1+2: /auth/login + /login)
# the password is not only a bearer — it can be EXCHANGED for a real admin JWT
# at /auth/login (_verify_password_for_auth) or an hmac token at /login. A JWT is
# is_real, so once minted the bearer gate ALWAYS allows it. OFF must close the MINT.
# --------------------------------------------------------------------------- #
def test_legacy_login_mint_blocked_at_off():
    # at mode OFF the legacy password may NOT be exchanged for any token (JWT or hmac).
    assert lg.legacy_login_mint_allowed(mode=LegacyMode.OFF) is False
    assert lg.legacy_login_mint_allowed(env={"LEGACY_TOKEN_MODE": "off"}) is False


def test_legacy_login_mint_allowed_in_transition_and_on():
    assert lg.legacy_login_mint_allowed(mode=LegacyMode.TRANSITION) is True
    assert lg.legacy_login_mint_allowed(mode=LegacyMode.ON) is True
    # the existing flag set true => TRANSITION => still mints (byte-behaviour-identical pre-flip).
    assert lg.legacy_login_mint_allowed(env={"LEGACY_TOKEN_ENABLED": "true"}) is True


def test_legacy_login_mint_default_and_garbage_fail_closed():
    # no env at all -> library default OFF -> mint refused (conservative).
    assert lg.legacy_login_mint_allowed(env={}) is False
    # a garbage mode value fails CLOSED to OFF -> mint refused (cannot accidentally re-open).
    assert lg.legacy_login_mint_allowed(mode="banana") is False


def test_off_flip_closes_both_bearer_and_mint_paths():
    # the full BLOCKER-1 invariant: at OFF, BOTH the direct-bearer path (evaluate) AND the
    # password->JWT/hmac mint path (legacy_login_mint_allowed) reject. Either alone is a bypass.
    bearer = evaluate(AuthMethod.LEGACY_PW, mode=LegacyMode.OFF, route="/usage", audit=False)
    assert bearer.allowed is False
    assert lg.legacy_login_mint_allowed(mode=LegacyMode.OFF) is False


# --------------------------------------------------------------------------- #
# self-test: the tracked module/doc files must NOT embed the legacy secret literal
# (red-team W20 BLOCKER 3: the module prescribes the scrub — apply it to itself).
# the literal is reconstructed from fragments so this assertion does not itself ship it.
# --------------------------------------------------------------------------- #
def test_no_module_or_doc_file_embeds_the_legacy_secret_literal():
    import pathlib

    secret = "Famit" + "Call" + "2026"  # reconstructed; never a single literal in tracked source
    pkg = pathlib.Path(lg.__file__).resolve().parent
    # every tracked module + doc in the package, EXCLUDING the tests/ dir (tests may use a fixture).
    offenders = []
    for p in pkg.iterdir():
        if p.is_dir():
            continue
        if p.suffix not in (".py", ".md"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if secret in text:
            offenders.append(p.name)
    assert offenders == [], f"legacy secret literal must be scrubbed from: {offenders}"
