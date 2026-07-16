"""ai_manager.firewall_bridge — thin wrapper over the box `firewall.py` (spec §H).

The AI-Manager PIN / step-up gate. On THIS box `firewall.py` is PRESENT (the Action Firewall:
salted-PIN store + HS256 step-up tokens), so this bridge lazily imports it and adapts its real
API to the small surface the state machine + endpoints consume. The bridge stays:

  * IMPORT-SAFE — `firewall` is imported LAZILY inside each call, guarded; absence -> graceful.
  * FAIL-CLOSED on money/PIN (spec invariant #4): when the firewall can't verify (absent /
    un-init'd / no PIN enrolled), `authenticate()` returns ok=False — a risky action is BLOCKED,
    never bypassed. No raw PIN is ever stored / logged / returned.
  * NEVER raises at the boundary.

`authenticate()` is the seam the state machine drives; it accepts an INJECTED firewall module
(`fw=`) so the offline test can pass a StubFirewall (a known PIN then verifies) with ZERO real
firewall init. When no `fw` is injected we fall back to the real top-level `firewall` module.

Real `firewall.py` API this bridge rides (read from droplet_work/firewall.py):
  * firewall.available() -> bool                 (pyjwt present + a signing secret)
  * firewall.has_pin(tenant_id) -> bool
  * firewall.check_pin(tenant_id, pin) -> bool   (salted sha256, constant-time)
  * firewall.mint_step_up(tenant_id, scope) -> {"step_up_token", "expires_in", "scope"} | None
"""
from __future__ import annotations

from typing import Any, Optional


def _firewall_mod():
    """Lazy-import the top-level `firewall` module, or None when it's absent / un-importable.
    NEVER raises."""
    try:
        import firewall as _fw  # type: ignore  # top-level box module (present locally)
        return _fw
    except Exception:  # noqa: BLE001
        return None


def available() -> bool:
    """Is the firewall importable + ready? Best-effort True when the module is present and its
    `available()` probe (pyjwt + secret) passes; True as a fallback if the probe is missing but
    the module imports. False when absent. NEVER raises."""
    fw = _firewall_mod()
    if fw is None:
        return False
    try:
        probe = getattr(fw, "available", None)
        if callable(probe):
            return bool(probe())
        return True  # module present but no probe -> assume usable
    except Exception:  # noqa: BLE001
        return False


def has_pin(tenant_id: str) -> bool:
    """Does this tenant have a PIN enrolled? Fail-closed (False) on blank tenant / absence /
    error. NEVER raises."""
    if not (tenant_id or "").strip():
        return False
    fw = _firewall_mod()
    if fw is None:
        return False
    try:
        fn = getattr(fw, "has_pin", None)
        return bool(fn(tenant_id)) if callable(fn) else False
    except Exception:  # noqa: BLE001
        return False


def check_pin(tenant_id: str, pin: str) -> bool:
    """Verify a presented PIN against the stored salted hash. Fail-closed (False) on blank
    tenant / absence / error. The raw PIN is passed straight through to the firewall and never
    retained / logged here. NEVER raises."""
    if not (tenant_id or "").strip():
        return False
    fw = _firewall_mod()
    if fw is None:
        return False
    try:
        fn = getattr(fw, "check_pin", None)
        return bool(fn(tenant_id, pin)) if callable(fn) else False
    except Exception:  # noqa: BLE001
        return False


def _normalize_mint(mint: Any) -> Optional[dict]:
    """Normalize the firewall's mint result into a dict that exposes BOTH `step_up_token`
    (state_machine reads this) and `token` (endpoints reads `.get("token")`). Returns None when
    the firewall returned None / a non-dict / no usable token. NEVER raises."""
    if not isinstance(mint, dict):
        return None
    try:
        token = mint.get("step_up_token") or mint.get("token") or ""
        if not token:
            return None
        out = dict(mint)
        out["step_up_token"] = token
        out["token"] = token
        return out
    except Exception:  # noqa: BLE001
        return None


def mint_step_up(tenant_id: str, scope: str) -> Optional[dict]:
    """Mint a short-TTL, scoped step-up token for `tenant_id`. Returns a dict carrying `token`
    (+ `step_up_token`) on success, or None when the firewall is absent / un-init'd / declines.
    Fail-closed on blank tenant. NEVER raises."""
    if not (tenant_id or "").strip():
        return None
    fw = _firewall_mod()
    if fw is None:
        return None
    try:
        fn = getattr(fw, "mint_step_up", None)
        if not callable(fn):
            return None
        return _normalize_mint(fn(tenant_id, scope or ""))
    except Exception:  # noqa: BLE001
        return None


def authenticate(tenant_id: str, secret: str, *, scope: str = "", method: str = "voice_pin",
                 fw: Any = None) -> dict:
    """The state-machine auth seam. Verify `secret` (a PIN/OTP, never logged) for `tenant_id`,
    and — when `scope` is set (an ACTION step-up, not a login) — mint a fresh scoped step-up
    token. Returns:

        {"ok": bool, "reason": str, "step_up": {"step_up_token": str, ...} | None}

    Semantics (spec §H):
      * scope falsy  -> LOGIN auth. ok iff the PIN verifies. `step_up` is a truthy marker WITHOUT
        a token (login doesn't need a step-up token) so callers that gate on `step_up` truthiness
        still see success; the marker carries no secret.
      * scope set    -> ACTION step-up. ok iff the PIN verifies AND a token mints; `step_up`
        carries the minted token. If the PIN verifies but the firewall can't mint (un-init'd),
        ok=True but step_up=None — the state machine treats that as "verified, no token" and
        proceeds with no token to attach.
      * `fw` injected (tests inject a StubFirewall) takes precedence over the real module so the
        offline suite verifies a KNOWN PIN with zero real-firewall init.
      * firewall absent / un-resolvable -> FAIL-CLOSED:
        {"ok": False, "reason": "firewall_unavailable", "step_up": None}.

    NEVER raises."""
    module = fw if fw is not None else _firewall_mod()
    if module is None:
        return {"ok": False, "reason": "firewall_unavailable", "step_up": None}

    # 1) Verify the secret (PIN/OTP). Any error / missing method -> fail-closed.
    try:
        check = getattr(module, "check_pin", None)
        verified = bool(check(tenant_id, secret)) if callable(check) else False
    except Exception:  # noqa: BLE001
        verified = False

    if not verified:
        return {"ok": False, "reason": "bad_pin", "step_up": None}

    # 2) LOGIN (no scope): success, no step-up token needed — a non-secret truthy marker.
    scope = (scope or "").strip()
    if not scope:
        return {"ok": True, "reason": "", "step_up": {"verified": True}}

    # 3) ACTION step-up: PIN verified, now mint a fresh scoped token. A degraded firewall that
    #    can't mint still counts as verified (ok=True) but with no token to attach.
    try:
        mint_fn = getattr(module, "mint_step_up", None)
        mint = mint_fn(tenant_id, scope) if callable(mint_fn) else None
    except Exception:  # noqa: BLE001
        mint = None
    minted = _normalize_mint(mint)
    if minted is None:
        return {"ok": True, "reason": "no_token", "step_up": None}
    return {"ok": True, "reason": "", "step_up": minted}


__all__ = ["available", "has_pin", "check_pin", "mint_step_up", "authenticate"]
