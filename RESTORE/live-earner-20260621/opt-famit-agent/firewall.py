"""firewall.py — Action Firewall: PIN/OTP step-up gate on spend-sensitive + destructive actions.

Spec: design/credit-ledger-firewall.md §6 (RED-TEAM F3 folded). The AI-Manager / Workflow Studio call
this BEFORE executing spend / bulk / delete actions.

REUSE, don't reinvent (spec §6): the HS256 + var/secret signing machinery already lives in auth.py.
The firewall mints a SHORT-TTL step-up token proving a recent PIN match, then verifies it (bound to the
caller — F3) on a gated action.

  * PIN store  = var/pins.json: {tenant_id: {salt, pin_hash, set_at}}, pin_hash = sha256(salt+":"+pin)
    — IDENTICAL hashing to the existing tenant pass_hash (caller._hash_pw). The PIN is NEVER stored.
  * step-up token = jwt.encode({sub:tenant_id, amr:"pin", scope, exp:now+TTL}, SECRET, HS256).
  * require_step_up(request, scope, resolve_tenant) — reads X-Step-Up header, verifies HS256 + scope +
    exp AND (F3 — SECURITY BLOCKER) sub == the authenticated tenant of THIS request. A token leaked from
    tenant A is therefore NOT replayable by tenant B. Returns None (proceed) on success, else a 403/401.

FLAG: FIREWALL_ENABLED (default OFF). OFF -> require_step_up ALWAYS returns None (no gating) so nothing
breaks today. Also pass-through when the tenant has NO PIN set (can't gate what isn't enrolled).

OTP-over-WhatsApp: request_otp()/verify_otp() are stubs (return not_configured) until the dormant Meta
WA pipeline is enabled; same amr:"otp" step-up token shape (spec §6).

import-safe: no hard dep beyond pyjwt (already in venv, used by auth.py). If pyjwt is absent, available()
is False and require_step_up degrades to pass-through (never blocks a request because a dep is missing).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import jwt as _jwt  # PyJWT (same lib auth.py uses)
except Exception:  # noqa: BLE001
    _jwt = None

ALGO = "HS256"
STEP_UP_TTL_S = int(os.getenv("FIREWALL_STEPUP_TTL_S", "300") or 300)   # 5 min
PIN_MIN_LEN = 4
PIN_MAX_LEN = 12

# ---- injected from caller.py via init() ----
_SECRET: str = ""
_PIN_FILE: Optional[Path] = None
_ready = False

# Risk classification (spec §6). The AI-Manager / Workflow Studio map an action -> a scope; a "safe"
# action returns "" (no step-up). spend = money-moving / bulk dial; destructive = delete / plan change.
_SPEND_ACTIONS = {
    "wallet.topup", "ads.spend", "whatsapp.bulk_send", "run.large", "brain.write_ai",
}
_DESTRUCTIVE_ACTIONS = {
    "tenant.delete", "campaign.bulk_delete", "billing.plan_change",
}


def init(secret: str, pin_file: Path) -> bool:
    """Wire the firewall to var/secret (reused) + a pins store. Returns True if the step-up path is
    available (pyjwt present + a secret), False if it degraded to pass-through."""
    global _SECRET, _PIN_FILE, _ready
    _SECRET = secret or ""
    _PIN_FILE = Path(pin_file)
    try:
        _PIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    _ready = _jwt is not None and bool(_SECRET)
    return _ready


def available() -> bool:
    return _ready


def enabled() -> bool:
    """FIREWALL_ENABLED flag (default OFF). Read live each call so a flag flip + restart takes effect."""
    return (os.getenv("FIREWALL_ENABLED", "false") or "false").strip().lower() \
        in ("1", "true", "yes", "on")


def classify(action: str) -> str:
    """Map an action name -> required step-up scope ('spend' | 'destructive' | '' for safe)."""
    if action in _SPEND_ACTIONS:
        return "spend"
    if action in _DESTRUCTIVE_ACTIONS:
        return "destructive"
    return ""


# ---------------- PIN store (salted sha256 — identical to caller._hash_pw) ----------------
def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256((salt + ":" + (pin or "")).encode("utf-8")).hexdigest()


def _read_pins() -> dict:
    try:
        if _PIN_FILE and _PIN_FILE.exists():
            return json.loads(_PIN_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def _write_pins(data: dict) -> None:
    try:
        _PIN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PIN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(_PIN_FILE, 0o600)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass


def has_pin(tenant_id: str) -> bool:
    return bool(_read_pins().get(tenant_id, {}).get("pin_hash"))


def set_pin(tenant_id: str, pin: str) -> dict:
    """Set/replace a tenant's PIN. Returns {ok, reason?}. PIN is digit-ish 4-12 chars; never stored raw."""
    pin = (pin or "").strip()
    if not (PIN_MIN_LEN <= len(pin) <= PIN_MAX_LEN):
        return {"ok": False, "reason": f"pin must be {PIN_MIN_LEN}-{PIN_MAX_LEN} chars"}
    salt = secrets.token_hex(8)
    store = _read_pins()
    store[tenant_id] = {"salt": salt, "pin_hash": _hash_pin(pin, salt), "set_at": int(time.time())}
    _write_pins(store)
    return {"ok": True}


def check_pin(tenant_id: str, pin: str) -> bool:
    """Constant-ish comparison of a presented PIN against the stored salted hash."""
    rec = _read_pins().get(tenant_id, {})
    if not rec.get("pin_hash"):
        return False
    cand = _hash_pin((pin or "").strip(), rec.get("salt", ""))
    return secrets.compare_digest(cand, rec.get("pin_hash", ""))


# ---------------- PIN-CHANGE brute-force LOCKOUT (ADDITIVE; isolated from verify/step-up) ----------------
# A self-contained, time-boxed lockout that gates ONLY the PIN-CHANGE flow (old-PIN verification). It does
# NOT touch check_pin / set_pin / mint_step_up / verify_step_up_token / require_step_up — those stay
# byte-identical. State lives in its OWN file (var/pin_lockout.json), never in pins.json, so the PIN store
# is unchanged. Default thresholds: 5 failures inside a rolling 15-min window -> lock for 15 min.
LOCKOUT_MAX_FAILS = int(os.getenv("FIREWALL_PIN_LOCKOUT_FAILS", "5") or 5)
LOCKOUT_WINDOW_S = int(os.getenv("FIREWALL_PIN_LOCKOUT_WINDOW_S", "900") or 900)   # 15 min
LOCKOUT_DURATION_S = int(os.getenv("FIREWALL_PIN_LOCKOUT_S", "900") or 900)        # 15 min


def _lockout_file() -> Optional[Path]:
    """Sibling of the pins file (same var/ dir, same 0600 posture). None if the firewall isn't init()'d."""
    if _PIN_FILE is None:
        return None
    return _PIN_FILE.parent / "pin_lockout.json"


def _read_lockouts() -> dict:
    try:
        f = _lockout_file()
        if f and f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def _write_lockouts(data: dict) -> None:
    try:
        f = _lockout_file()
        if f is None:
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(f, 0o600)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass


def lockout_state(tenant_id: str) -> dict:
    """Current lockout state for a tenant: {locked, retry_after_s, fails, max_fails}. Self-expiring."""
    now = int(time.time())
    rec = _read_lockouts().get(tenant_id, {})
    locked_until = int(rec.get("locked_until", 0) or 0)
    if locked_until > now:
        return {"locked": True, "retry_after_s": locked_until - now,
                "fails": int(rec.get("fails", 0) or 0), "max_fails": LOCKOUT_MAX_FAILS}
    # not currently locked: only count fails still inside the rolling window
    win_start = now - LOCKOUT_WINDOW_S
    fails = [t for t in (rec.get("fail_ts", []) or []) if int(t) >= win_start]
    return {"locked": False, "retry_after_s": 0, "fails": len(fails), "max_fails": LOCKOUT_MAX_FAILS}


def is_locked_out(tenant_id: str) -> bool:
    return bool(lockout_state(tenant_id).get("locked"))


def record_pin_fail(tenant_id: str) -> dict:
    """Append a failed old-PIN attempt; lock the tenant out if it crosses the threshold inside the
    rolling window. Returns the post-record lockout_state."""
    now = int(time.time())
    win_start = now - LOCKOUT_WINDOW_S
    store = _read_lockouts()
    rec = store.get(tenant_id, {})
    fail_ts = [int(t) for t in (rec.get("fail_ts", []) or []) if int(t) >= win_start]
    fail_ts.append(now)
    rec["fail_ts"] = fail_ts[-LOCKOUT_MAX_FAILS * 4:]  # bounded
    if len(fail_ts) >= LOCKOUT_MAX_FAILS:
        rec["locked_until"] = now + LOCKOUT_DURATION_S
    store[tenant_id] = rec
    _write_lockouts(store)
    return lockout_state(tenant_id)


def clear_pin_fails(tenant_id: str) -> None:
    """Reset the failure counter + any active lock (called on a SUCCESSFUL PIN change)."""
    store = _read_lockouts()
    if tenant_id in store:
        store.pop(tenant_id, None)
        _write_lockouts(store)


def change_pin(tenant_id: str, old_pin: str, new_pin: str) -> dict:
    """Change a tenant's Action-Firewall PIN: verify `old_pin` against the EXISTING salted hash
    (check_pin — unchanged), then set `new_pin` (set_pin — unchanged). Brute-force protected by the
    time-boxed lockout above. Returns a result dict; the route turns it into an HTTP status + audit row.

      {"ok": True}                                              -> changed
      {"ok": False, "reason": "locked", "retry_after_s": N, ...}-> too many bad old-PIN attempts (429)
      {"ok": False, "reason": "no PIN set"}                     -> nothing to change (400)
      {"ok": False, "reason": "invalid old PIN", "fails": F, "locked": bool, "retry_after_s": N} (401)
      {"ok": False, "reason": "pin must be 4-12 chars"}        -> new PIN failed validation (400)

    NEVER mutates the existing verify/step-up machinery; isolated to its own lockout file."""
    # 0) already locked? refuse without even touching the PIN store (constant work).
    st = lockout_state(tenant_id)
    if st.get("locked"):
        return {"ok": False, "reason": "locked", "retry_after_s": st.get("retry_after_s", 0),
                "fails": st.get("fails", 0), "max_fails": LOCKOUT_MAX_FAILS}
    # 1) must have an existing PIN to change.
    if not has_pin(tenant_id):
        return {"ok": False, "reason": "no PIN set"}
    # 2) verify the OLD pin via the EXISTING (byte-identical) check_pin.
    if not check_pin(tenant_id, old_pin):
        post = record_pin_fail(tenant_id)
        return {"ok": False, "reason": "invalid old PIN",
                "fails": post.get("fails", 0), "max_fails": LOCKOUT_MAX_FAILS,
                "locked": post.get("locked", False), "retry_after_s": post.get("retry_after_s", 0)}
    # 3) old verified -> set the new PIN via the EXISTING (byte-identical) set_pin (validates 4-12 chars,
    #    re-salts, never stores raw). Reject a no-op (new == old) so a "change" actually rotates the hash.
    if check_pin(tenant_id, (new_pin or "").strip()):
        return {"ok": False, "reason": "new PIN must differ from old PIN"}
    res = set_pin(tenant_id, new_pin)
    if res.get("ok"):
        clear_pin_fails(tenant_id)   # successful change resets the lockout counter
    return res


# ---------------- step-up token mint / verify ----------------
def mint_step_up(tenant_id: str, scope: str = "spend") -> Optional[dict]:
    """Mint a short-TTL HS256 step-up token bound to tenant_id (sub) + scope (spec §6)."""
    if not _ready:
        return None
    now = int(time.time())
    payload = {"sub": tenant_id, "amr": "pin", "scope": scope, "type": "step_up",
               "iat": now, "exp": now + STEP_UP_TTL_S, "jti": secrets.token_hex(8)}
    token = _jwt.encode(payload, _SECRET, algorithm=ALGO)
    return {"step_up_token": token, "expires_in": STEP_UP_TTL_S, "scope": scope}


def verify_step_up_token(token: str, scope: str, expected_sub: str) -> Optional[dict]:
    """Verify an HS256 step-up token: signature + exp + type + scope + (F3) sub == expected_sub.
    Returns the claims dict on success, else None. NEVER raises."""
    if not _ready or not token:
        return None
    try:
        claims = _jwt.decode(token, _SECRET, algorithms=[ALGO])
    except Exception:  # noqa: BLE001 (expired/invalid/not-a-jwt)
        return None
    if claims.get("type") != "step_up":
        return None
    if scope and claims.get("scope") != scope:
        return None
    # F3 (SECURITY BLOCKER): bind the token to the CALLER — a leaked tenant-A token must NOT be
    # replayable by tenant-B. The mint sets sub:tenant_id; verify ENFORCES it here.
    if claims.get("sub") != expected_sub:
        return None
    return claims


# ---------------- the guard caller.py wraps gated endpoints with ----------------
class StepUpDenied(Exception):
    """Raised by require_step_up when a gated action lacks a valid step-up. Carries (status, body)."""
    def __init__(self, status: int, body: dict):
        self.status = status
        self.body = body
        super().__init__(body.get("error", "step-up required"))


def require_step_up(request: Any, scope: str, tenant: dict) -> Optional[dict]:
    """Guard mirroring caller.can(): returns None to PROCEED, or raises StepUpDenied(status, body).

    Pass-through (returns None) when: FIREWALL_ENABLED is OFF, OR the firewall is unavailable, OR the
    tenant has NO PIN set (not enrolled — can't gate what doesn't exist). When gating IS active, reads
    the X-Step-Up header and verifies it bound to scope + this tenant (F3). Caller passes the already-
    resolved `tenant` dict (so we never re-resolve / trust a body param)."""
    tenant_id = (tenant or {}).get("tenant_id", "")
    # Non-breaking pass-throughs.
    if not enabled() or not _ready or not has_pin(tenant_id):
        return None
    token = ""
    try:
        token = request.headers.get("x-step-up", "") or request.headers.get("X-Step-Up", "")
    except Exception:  # noqa: BLE001
        token = ""
    if not token:
        raise StepUpDenied(403, {"error": "step-up required", "scope": scope})
    claims = verify_step_up_token(token, scope, tenant_id)
    if claims is None:
        # distinguish identity mismatch (replay attempt) from a plain bad/expired token
        try:
            raw = _jwt.decode(token, _SECRET, algorithms=[ALGO])
            if raw.get("sub") and raw.get("sub") != tenant_id:
                raise StepUpDenied(403, {"error": "step-up identity mismatch", "scope": scope})
        except StepUpDenied:
            raise
        except Exception:  # noqa: BLE001
            pass
        raise StepUpDenied(403, {"error": "step-up required", "scope": scope, "detail": "invalid or expired"})
    return None


# ---------------- provider.reveal step-up (ADDITIVE; Provider-Framework W3) ----------------
# A NARROWER, single-use step-up for the most-sensitive action in the platform: revealing a
# provider API key in plaintext (PROVIDER-FRAMEWORK-PLAN §6 reveal-gate row + §12.10). It is a
# SEPARATE mint/verify pair from the generic step-up above — the generic path
# (mint_step_up / verify_step_up_token / require_step_up / change_pin / the PIN store) is NOT
# touched and stays byte-identical. This pair adds three properties the generic token lacks:
#   * 60s TTL (vs 300s) — a reveal token is hot; minimize the replay window.
#   * aud = provider_def_id — a token minted to reveal provider X cannot reveal provider Y.
#   * SINGLE-USE jti — the jti is consumed on first successful verify and rejected on replay
#     (closing the live jti-replay gap: the generic verify_step_up_token mints a jti but never
#     consumes it, so a captured generic token is replayable until exp). State lives in its OWN
#     file (var/provider_used_jti.json), never in pins.json / pin_lockout.json.
REVEAL_STEP_UP_TTL_S = int(os.getenv("PROVIDER_REVEAL_STEPUP_TTL_S", "60") or 60)   # 60s (§6)
REVEAL_SCOPE = "provider.reveal"
# Bound the consumed-jti store so it can't grow without limit; entries past 2x the TTL are pruned
# on every read (a consumed jti only needs to outlive its own token's exp to block replay).
_JTI_PRUNE_TTL_S = REVEAL_STEP_UP_TTL_S * 2


def _used_jti_file() -> Optional[Path]:
    """Sibling of the pins file (same var/ dir + 0600 posture). None if firewall not init()'d."""
    if _PIN_FILE is None:
        return None
    return _PIN_FILE.parent / "provider_used_jti.json"


def _read_used_jti() -> dict:
    try:
        f = _used_jti_file()
        if f and f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def _write_used_jti(data: dict) -> None:
    try:
        f = _used_jti_file()
        if f is None:
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(f, 0o600)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass


def _prune_used_jti(store: dict, now: int) -> dict:
    """Drop consumed-jti records older than the prune TTL (a consumed jti only needs to outlive
    its token's exp). Keeps the file bounded. Returns the pruned store."""
    cutoff = now - _JTI_PRUNE_TTL_S
    return {j: ts for j, ts in store.items() if int(ts or 0) >= cutoff}


def _jti_already_used(jti: str) -> bool:
    if not jti:
        return True  # a token with no jti can't be made single-use -> refuse it (fail-closed)
    return jti in _read_used_jti()


def _consume_jti(jti: str) -> bool:
    """Atomically-ish record a jti as consumed. Returns True if THIS call consumed it (first use),
    False if it was already consumed (replay). File-locked enough for a single-box deployment;
    the small race window is acceptable (the token is also exp-bounded to 60s)."""
    if not jti:
        return False
    now = int(time.time())
    store = _prune_used_jti(_read_used_jti(), now)
    if jti in store:
        return False  # replay
    store[jti] = now
    _write_used_jti(store)
    return True


def mint_reveal_step_up(tenant_id: str, provider_def_id: str) -> Optional[dict]:
    """Mint a 60s, single-use, aud-bound step-up token for a provider-key REVEAL.

    Bound to: sub=tenant_id (F3 caller-binding, same as the generic mint), aud=provider_def_id
    (this token can ONLY reveal that one provider def), scope='provider.reveal', a fresh jti
    (consumed on verify). Returns None if the firewall isn't available."""
    if not _ready:
        return None
    pdid = (provider_def_id or "").strip()
    if not pdid:
        return None
    now = int(time.time())
    payload = {"sub": tenant_id, "amr": "pin", "scope": REVEAL_SCOPE, "type": "step_up",
               "aud": pdid, "iat": now, "exp": now + REVEAL_STEP_UP_TTL_S,
               "jti": secrets.token_hex(16)}
    token = _jwt.encode(payload, _SECRET, algorithm=ALGO)
    return {"step_up_token": token, "expires_in": REVEAL_STEP_UP_TTL_S,
            "scope": REVEAL_SCOPE, "aud": pdid}


def consume_reveal_step_up(token: str, provider_def_id: str, expected_sub: str) -> Optional[dict]:
    """Verify + CONSUME a provider.reveal step-up token. Returns the claims on first valid use,
    else None (expired / wrong scope / wrong sub / wrong aud / replayed jti / missing jti).

    The jti is consumed ON SUCCESS so a second call with the same token returns None (single-use
    — the live jti-replay gap closed for the reveal path). NEVER raises. The caller maps None to
    a 403; the route audits the attempt either way."""
    if not _ready or not token:
        return None
    pdid = (provider_def_id or "").strip()
    try:
        # Disable PyJWT's built-in audience validation (it raises InvalidAudienceError on ANY
        # `aud` claim unless you pass `audience=`). We verify aud ourselves below for a stable,
        # explicit, version-independent check. Signature + exp are STILL verified.
        claims = _jwt.decode(token, _SECRET, algorithms=[ALGO],
                             options={"verify_aud": False})
    except Exception:  # noqa: BLE001 (expired/invalid/not-a-jwt)
        return None
    if claims.get("type") != "step_up":
        return None
    if claims.get("scope") != REVEAL_SCOPE:
        return None
    # F3 caller-binding: sub must be the authenticated tenant of THIS request.
    if claims.get("sub") != expected_sub:
        return None
    # aud-binding: this token may only reveal the provider def it was minted for.
    if not pdid or claims.get("aud") != pdid:
        return None
    jti = claims.get("jti") or ""
    # SINGLE-USE: refuse a token with no jti, and refuse a replayed jti. Consume on first valid use.
    if _jti_already_used(jti):
        return None
    if not _consume_jti(jti):
        return None  # lost a race -> treat as replay (fail-closed)
    return claims


# ---------------- OTP-over-WhatsApp (DORMANT stub; spec §6) ----------------
def request_otp(tenant_id: str, channel: str = "whatsapp") -> dict:
    """Dormant until the Meta WA pipeline is enabled. Same amr:'otp' step-up token shape when live."""
    return {"ok": False, "reason": "not_configured", "channel": channel}


def verify_otp(tenant_id: str, otp: str, scope: str = "spend") -> dict:
    return {"ok": False, "reason": "not_configured"}


def status(tenant_id: str = "") -> dict:
    out = {"firewall_enabled": enabled(), "available": _ready,
           "pin_set": has_pin(tenant_id) if tenant_id else None,
           "step_up_ttl_s": STEP_UP_TTL_S}
    if tenant_id:
        st = lockout_state(tenant_id)
        out["pin_change_locked"] = st.get("locked", False)
        out["pin_change_retry_after_s"] = st.get("retry_after_s", 0)
    return out
