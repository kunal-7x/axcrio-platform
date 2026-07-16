"""ads_engine.compliance — the FAIL-CLOSED pre-dial gate + immutable consent ledger (W6).

This is the most legally-load-bearing module in the package. A miss here is a TCCCPR (Rs2-10 lakh)
or DPDP (up to Rs250 cr) liability + a telecom-header blacklist that kills the live earner. So the
ENTIRE design philosophy is: any uncertainty => NO dial. The permissive default is UNSHIPPABLE
(assert_fail_closed() trips at import + at build_router mount if a knob is mis-set).

What this module enforces (every redteam compliance mustFix wired):

  * DUAL CONSENT (compliance C4 / research §9): a dial requires BOTH a non-revoked DPDP `process`
    consent AND a non-revoked DCA `commercial` consent. For promotional VOICE specifically the DCA
    row MUST be DLT/OTP-backed (method ∈ {otp_127_dlt} with a real dlt_consent_id) — a
    `form_checkbox` DCA row is REJECTED for the voice dial path (it satisfies DPDP-process, NOT the
    TRAI commercial-comms basis). There is NO ncpr_mode bypass: `bypass_consented` is removed.

  * QUIET-HOURS force_window (compliance C2 / earner M1): force_window is COMPUTED structurally as
    `(now is within 09:00-21:00 IST)` AND a verified-fresh DCA consent — NEVER a literal True, never
    a global config knob that can enable night-time promo dialing. Outside 09-21 IST force_window is
    ALWAYS False (the dial then auto-resumes at 09:00 via run_job's own window idle).

  * REAL-TIME NCPR/DND scrub + Real-Estate-category honor (compliance §4 / M2): the gate calls the
    injected scrub provider just-before-dispatch. NOT configured / a scrub error / a cache miss =>
    FAIL-CLOSED (deny). A full-DND hit OR a Real-Estate (cat #2) block => deny. No `bypass_consented`.

  * APPEND-ONLY HASH-CHAINED LEDGER (compliance C3): consent rows are written to the per-tenant
    append-only `consent_log` artifact (store.append_consent_row), each carrying prev_hash +
    hash_chain. Revocation is a NEW appended row, never an in-place edit. verify_chain() re-walks
    and reports the first break (tamper evidence). Plus DPDP retention/erasure + 72h-breach hooks.

NO `from caller import ...`. All IO via the injected store seam (ads_engine.store). The scrub
provider + clock are injectable so the offline tests are deterministic and fail-closed by default.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from . import store

# ---------------------------------------------------------------------------
# Constants — the legal windows + the consent vocabulary (single-sourced).
# ---------------------------------------------------------------------------
IST = timezone(timedelta(hours=5, minutes=30))

QUIET_START_HOUR = 9          # 09:00 IST — earliest a promo dial may fire
QUIET_END_HOUR = 21           # 21:00 IST — latest a promo dial may fire (exclusive of 21:00+)

# DPDP record retention floor (>= 7 years) — research/india-compliance-channels.md.
RETENTION_SECONDS = 7 * 365 * 24 * 3600
# 90-day cool-off after a revocation (design §A.20).
COOLOFF_SECONDS = 90 * 24 * 3600

# Consent kinds (the two SEPARATE legal bases — both mandatory to dial).
KIND_DPDP = "dpdp_process"
KIND_DCA = "dca_commercial"

# Consent capture methods. For promotional VOICE the DCA basis MUST be DLT/OTP-backed; a
# self-captured form checkbox is the CRM flag the regulator says is INSUFFICIENT for promo voice.
METHOD_FORM_CHECKBOX = "form_checkbox"
METHOD_OTP_127_DLT = "otp_127_dlt"
METHOD_WA_QUICK_REPLY = "wa_quick_reply"
# The ONLY methods that satisfy DCA for a promotional VOICE dial (DLT/OTP-backed).
_VOICE_DCA_VALID_METHODS = frozenset({METHOD_OTP_127_DLT})

# The purpose scope a real-estate promo dial requires (DPDP itemised purpose).
SCOPE_REALESTATE = "real_estate_promo_voice_whatsapp"


# ---------------------------------------------------------------------------
# THE FAIL-CLOSED INVARIANT — the permissive default must be UNSHIPPABLE.
#
# These module-level switches encode "the safe state". assert_fail_closed() trips (raises) if any
# is mis-set to a permissive value — it is called at import AND re-asserted at build_router mount,
# so a broken/permissive config can NEVER ship. There is NO env knob that loosens them.
# ---------------------------------------------------------------------------
# Removed entirely (no code path sets it True). Kept as a constant the assert pins to False so a
# future edit that re-introduces a bypass trips the import-time assertion.
NCPR_BYPASS_CONSENTED = False         # compliance M2 — bypass_consented is NOT a shipped option.
ALLOW_NIGHT_PROMO_DIAL = False        # compliance C2 — never dial 21:00-09:00 IST on a checkbox.
ALLOW_FORM_CHECKBOX_DCA_VOICE = False # compliance C4 — form checkbox is NOT valid promo-voice DCA.


def assert_fail_closed() -> None:
    """Trip LOUDLY (AssertionError) if the permissive default ever becomes shippable.

    Called at import (below) and again at build_router mount. The three bypass switches MUST be
    False; if a future edit flips one, the package fails to import/mount rather than silently
    dialing non-compliantly. This is the 'permissive default is unshippable' guarantee.
    """
    assert NCPR_BYPASS_CONSENTED is False, \
        "compliance: NCPR bypass_consented must be False (redteam M2) — no consent-only NCPR bypass"
    assert ALLOW_NIGHT_PROMO_DIAL is False, \
        "compliance: night-time promo dialing must be impossible (redteam C2)"
    assert ALLOW_FORM_CHECKBOX_DCA_VOICE is False, \
        "compliance: form_checkbox is not valid promo-voice DCA (redteam C4)"


# ---------------------------------------------------------------------------
# Injected NCPR scrub provider (default = None => FAIL-CLOSED). caller/host wires a real provider
# later; until then EVERY promo dial is denied ncpr_unavailable. There is no permissive fallback.
# ---------------------------------------------------------------------------
_NCPR_SCRUB: Optional[Callable[[str, str], Any]] = None
# A clock seam so tests can pin "now" deterministically (quiet-hours boundary tests).
_NOW_FN: Callable[[], float] = time.time


def set_ncpr_scrub(fn: Optional[Callable[[str, str], Any]]) -> None:
    """Inject the NCPR/DND scrub provider: fn(tenant_id, phone) -> {block:bool, categories:[...]}|None.
    None (default) keeps the gate fail-closed (deny ncpr_unavailable). NEVER required to ship."""
    global _NCPR_SCRUB
    _NCPR_SCRUB = fn


def set_clock(fn: Callable[[], float]) -> None:
    """Inject a clock (tests pin quiet-hours boundaries). Default = time.time."""
    global _NOW_FN
    _NOW_FN = fn or time.time


# ===========================================================================
# QUIET HOURS — the structural force_window computation (compliance C2).
# ===========================================================================
def in_quiet_hours_window(now_epoch: Optional[float] = None) -> bool:
    """True iff `now` is within 09:00-21:00 IST (the only legal promo-dial window).

    This is the SOLE input to force_window: there is no config knob that can make a night-time dial
    'forced'. Outside the window this returns False and force_window stays False (run_job then idles
    the lead until 09:00 IST, auto-resuming — caller.py:3309-3313)."""
    now = float(now_epoch if now_epoch is not None else _NOW_FN())
    ist_now = datetime.fromtimestamp(now, IST)
    return QUIET_START_HOUR <= ist_now.hour < QUIET_END_HOUR


def compute_force_window(decision: "Decision", *, now_epoch: Optional[float] = None) -> bool:
    """STRUCTURAL force_window for an ad-lead enqueue (NEVER a literal True; redteam C2 + M1).

    Returns True ONLY when BOTH:
      (a) now is within 09:00-21:00 IST (in_quiet_hours_window), AND
      (b) the gate verified a fresh DLT/OTP-backed DCA voice consent (decision.checks['dca_voice_ok']).
    Outside the window OR without a verified voice consent => False (the dial respects the window,
    auto-resuming at 09:00). There is no path to a True at night.
    """
    if not in_quiet_hours_window(now_epoch):
        return False
    return bool(decision.allow and decision.checks.get("dca_voice_ok") is True)


# ===========================================================================
# CONSENT LEDGER — append-only, hash-chained (compliance C3).
# ===========================================================================
def _canonical(row: dict) -> str:
    """Deterministic JSON of the row's CONTENT fields (excludes the hash fields themselves)."""
    payload = {k: v for k, v in row.items() if k not in ("hash_chain", "prev_hash")}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _row_hash(row: dict, prev_hash: str) -> str:
    return hashlib.sha256((prev_hash + "\n" + _canonical(row)).encode("utf-8")).hexdigest()


def _mint_consent_id() -> str:
    import uuid
    return "cl_" + uuid.uuid4().hex[:10]


def record_consent(tenant_id: str, *, lead_id: str, phone: str, kind: str, who: str,
                   source: str, method: str, scope: str = SCOPE_REALESTATE,
                   scope_text: str = "", evidence: Optional[dict] = None,
                   granted: bool = True, now_epoch: Optional[float] = None) -> dict:
    """Append ONE consent row to the tenant's immutable, hash-chained consent_log.

    The row is hash-chained to the current ledger tail (prev_hash = latest hash, hash_chain =
    sha256(prev_hash + canonical_row)). It is ONLY appended — never an in-place edit. Returns the
    stored row (incl. its consent_id). Caller validates kind/method upstream; this is the durable
    append + chaining.
    """
    now = float(now_epoch if now_epoch is not None else _NOW_FN())
    prev = store.latest_consent_hash(tenant_id)
    row = {
        "consent_id": _mint_consent_id(),
        "tenant_id": str(tenant_id),
        "lead_id": str(lead_id or ""),
        "phone": str(phone or ""),
        "kind": str(kind),
        "who": str(who or "")[:256],
        "when": now,
        "source": str(source or ""),
        "scope": str(scope or SCOPE_REALESTATE),
        "scope_text": str(scope_text or "")[:512],
        "method": str(method or ""),
        "evidence": dict(evidence or {}),
        "granted": bool(granted),
        "revoked": False,
        "revoked_ts": None,
        "cooloff_until": None,
        "retention_until": now + RETENTION_SECONDS,
    }
    row["prev_hash"] = prev
    row["hash_chain"] = _row_hash(row, prev)
    return store.append_consent_row(tenant_id, row)


def revoke_consent(tenant_id: str, *, phone: str, kind: Optional[str] = None,
                   now_epoch: Optional[float] = None) -> dict:
    """Record a REVOCATION as a NEW appended row (compliance C3 immutability; M3 withdrawal).

    DPDP requires 'withdrawal as easy as giving consent'. A revocation never edits the prior grant;
    it appends a row with granted=False, revoked=True, and a 90-day cooloff_until. Applies to the
    matching (phone[, kind]) rows. Returns a summary {revoked: n, cooloff_until}.
    """
    now = float(now_epoch if now_epoch is not None else _NOW_FN())
    cooloff_until = now + COOLOFF_SECONDS
    ph = str(phone or "")
    rows = store.consent_log_rows(tenant_id)
    # The set of (kind) currently granted for this phone (so we append one revocation per kind).
    active_kinds = set()
    for r in rows:
        if r.get("phone") != ph:
            continue
        k = r.get("kind")
        if r.get("granted") and not r.get("revoked"):
            active_kinds.add(k)
        if r.get("revoked"):
            active_kinds.discard(k)
    target_kinds = {kind} if kind else active_kinds
    appended = 0
    for k in sorted(target_kinds):
        prev = store.latest_consent_hash(tenant_id)
        row = {
            "consent_id": _mint_consent_id(),
            "tenant_id": str(tenant_id),
            "lead_id": "",
            "phone": ph,
            "kind": str(k),
            "who": ph,
            "when": now,
            "source": "revoke_request",
            "scope": SCOPE_REALESTATE,
            "scope_text": "Consent withdrawn by data principal",
            "method": "revoke",
            "evidence": {},
            "granted": False,
            "revoked": True,
            "revoked_ts": now,
            "cooloff_until": cooloff_until,
            "retention_until": now + RETENTION_SECONDS,
        }
        row["prev_hash"] = prev
        row["hash_chain"] = _row_hash(row, prev)
        store.append_consent_row(tenant_id, row)
        appended += 1
    return {"revoked": appended, "cooloff_until": cooloff_until}


def _resolve_consent_state(tenant_id: str, phone: str,
                           now_epoch: Optional[float] = None) -> dict:
    """Walk the append-only ledger -> the CURRENT consent state for a phone.

    A later revocation row overrides an earlier grant (append-only semantics: newest wins per kind).
    Returns {kind: {granted, revoked, method, dlt_consent_id, cooloff_until, scope}} for both kinds.
    """
    now = float(now_epoch if now_epoch is not None else _NOW_FN())
    ph = str(phone or "")
    state: dict = {}
    # The cool-off is a STICKY property of a revocation, NOT of the newest row. A revocation sets
    # cooloff_until = revoked_ts + 90d; a LATER re-consent row (captured within that window) carries
    # cooloff_until=None and, under pure newest-wins, would silently CLEAR the cool-off and re-arm
    # the dial immediately — defeating the DPDP/DCA 90-day post-withdrawal cool-off (design §A.20).
    # So we carry forward the MAX still-active cooloff_until seen for the kind across the whole
    # ledger; a fresh grant can flip `granted` back True but can NEVER shorten an in-force cool-off.
    sticky_cooloff: dict = {}
    for r in store.consent_log_rows(tenant_id):
        if r.get("phone") != ph:
            continue
        k = r.get("kind")
        ev = r.get("evidence") or {}
        co = r.get("cooloff_until")
        if co is not None and float(co) > now:
            prev_co = sticky_cooloff.get(k)
            sticky_cooloff[k] = float(co) if prev_co is None else max(float(prev_co), float(co))
        state[k] = {
            "granted": bool(r.get("granted")) and not bool(r.get("revoked")),
            "revoked": bool(r.get("revoked")),
            "method": r.get("method", ""),
            "dlt_consent_id": ev.get("dlt_consent_id", ""),
            # carry the sticky (max still-active) cool-off, not just this row's value.
            "cooloff_until": sticky_cooloff.get(k),
            "scope": r.get("scope", ""),
            "when": r.get("when", 0),
        }
    # Re-stamp the sticky cool-off onto the final per-kind state (later grant rows reset the row's
    # own cooloff_until to None, so the loop's last write would otherwise drop a still-active one).
    for k, co in sticky_cooloff.items():
        if k in state:
            state[k]["cooloff_until"] = co
    return state


def verify_chain(tenant_id: str) -> dict:
    """Re-walk the tenant's consent_log hash-chain; report the first break (tamper evidence).

    Returns {ok:bool, length:int, broken_at:int|None, reason:str}. A break means a row was edited
    in place or the file was tampered (the recomputed hash no longer matches the stored one, or
    prev_hash doesn't chain to the prior row). Used by the tick integrity pass + the offline test.
    Never raises (degrade-safe)."""
    try:
        rows = store.consent_log_rows(tenant_id)
    except Exception:  # noqa: BLE001
        return {"ok": False, "length": 0, "broken_at": None, "reason": "read_failed"}
    prev = ""
    for i, r in enumerate(rows):
        stored_prev = r.get("prev_hash", "")
        stored_hash = r.get("hash_chain", "")
        if stored_prev != prev:
            return {"ok": False, "length": len(rows), "broken_at": i, "reason": "prev_hash_mismatch"}
        recomputed = _row_hash(r, prev)
        if recomputed != stored_hash:
            return {"ok": False, "length": len(rows), "broken_at": i, "reason": "hash_mismatch"}
        prev = stored_hash
    return {"ok": True, "length": len(rows), "broken_at": None, "reason": "ok"}


# ===========================================================================
# DPDP RETENTION / ERASURE / BREACH HOOKS (compliance M3).
# ===========================================================================
def due_for_erasure(tenant_id: str, now_epoch: Optional[float] = None) -> list:
    """Consent rows whose retention_until has passed (DPDP deletion-after-retention sweep input).

    Returns the consent_ids due for erasure. The actual erasure is a tombstone APPEND (we never
    delete a chain row in place — that would break the hash-chain); the tombstone records the
    erasure event so the artifact stays verifiable. The tick erasure pass consumes this list.
    """
    now = float(now_epoch if now_epoch is not None else _NOW_FN())
    out = []
    for r in store.consent_log_rows(tenant_id):
        ru = r.get("retention_until")
        if ru is not None and float(ru) <= now and not r.get("erased"):
            out.append(r.get("consent_id"))
    return out


def record_breach(tenant_id: str, *, summary: str, affected: int,
                  now_epoch: Optional[float] = None) -> dict:
    """72h-breach NOTIFICATION hook (DPDP §). Appends a breach marker to the consent_log chain so
    the breach + its 72h deadline are an immutable, auditable record. Returns the marker.

    This does NOT itself notify the DPB/data-principals (that is an operator action surfaced in the
    UI + HUMAN_TASKS); it records the obligation + deadline immutably so it cannot be lost."""
    now = float(now_epoch if now_epoch is not None else _NOW_FN())
    prev = store.latest_consent_hash(tenant_id)
    row = {
        "consent_id": _mint_consent_id(),
        "tenant_id": str(tenant_id),
        "kind": "breach_notice",
        "phone": "",
        "lead_id": "",
        "who": "data_fiduciary",
        "when": now,
        "source": "breach_hook",
        "scope": "dpdp_breach",
        "scope_text": str(summary or "")[:512],
        "method": "breach",
        "evidence": {"affected": int(affected or 0)},
        "granted": False,
        "revoked": False,
        "revoked_ts": None,
        "cooloff_until": None,
        "notify_deadline": now + 72 * 3600,   # DPDP 72h breach-notification window
        "retention_until": now + RETENTION_SECONDS,
    }
    row["prev_hash"] = prev
    row["hash_chain"] = _row_hash(row, prev)
    return store.append_consent_row(tenant_id, row)


# ===========================================================================
# THE DECISION + THE GATE.
# ===========================================================================
@dataclass
class Decision:
    allow: bool
    reason: str
    checks: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"allow": self.allow, "reason": self.reason, "checks": dict(self.checks)}


def _deny(reason: str, checks: dict) -> Decision:
    checks = dict(checks)
    checks[reason] = False
    return Decision(allow=False, reason=reason, checks=checks)


def pre_dial_gate(tenant_id: str, lead: dict, *, channel: str = "voice",
                  now_epoch: Optional[float] = None) -> Decision:
    """The FAIL-CLOSED pre-dial gate. Returns a Decision; allow=True ONLY when EVERY check passes.

    A deny => NO enqueue, full stop (the caller never dials). For promotional VOICE the DCA basis
    must be DLT/OTP-backed (form_checkbox rejected). Order (cheapest deny first):
      1. DPDP process consent present + not revoked.
      2. DCA commercial consent present + not revoked; for voice => DLT/OTP-backed (not checkbox).
      3. 90-day cool-off: a revoked consent within cooloff_until => deny.
      4. NCPR full-DND scrub — fail-CLOSED (unconfigured / error / cache-miss => deny).
      5. NCPR Real-Estate (cat #2) scrub — a category block => deny even if not full-DND.
    The gate NEVER raises into the caller — an internal error is a DENY (fail-closed)."""
    # Re-assert the unshippable-permissive-default invariant on every gate call (defense in depth).
    assert_fail_closed()
    checks: dict = {"channel": channel}
    try:
        phone = str(lead.get("phone") or "")
        if not phone:
            return _deny("no_phone", checks)
        now = float(now_epoch if now_epoch is not None else _NOW_FN())
        cs = _resolve_consent_state(tenant_id, phone, now_epoch=now)

        # 1. DPDP process consent
        dpdp = cs.get(KIND_DPDP)
        if not dpdp or not dpdp.get("granted"):
            return _deny("no_dpdp_consent", checks)
        checks["dpdp_ok"] = True

        # 2. DCA commercial consent
        dca = cs.get(KIND_DCA)
        if not dca or not dca.get("granted"):
            return _deny("no_dca_consent", checks)
        checks["dca_present"] = True

        # 2b. For promotional VOICE the DCA basis MUST be DLT/OTP-backed (compliance C4). A
        # self-captured form_checkbox is the CRM flag the regulator says is INSUFFICIENT.
        if channel == "voice":
            method = str(dca.get("method") or "")
            dlt_id = str(dca.get("dlt_consent_id") or "")
            if method not in _VOICE_DCA_VALID_METHODS or not dlt_id:
                checks["dca_voice_ok"] = False
                return _deny("dca_not_dlt_backed_for_voice", checks)
            checks["dca_voice_ok"] = True

        # 3. 90-day cool-off (a revocation within the cooloff blocks re-dial).
        for kind in (KIND_DPDP, KIND_DCA):
            st = cs.get(kind) or {}
            co = st.get("cooloff_until")
            if co is not None and now < float(co):
                return _deny("cooloff_90d", checks)
        checks["cooloff_ok"] = True

        # 4 + 5. NCPR / DND scrub — fail-CLOSED.
        scrub_decision = _run_scrub(tenant_id, phone)
        checks["ncpr_scrub_ran"] = scrub_decision is not None
        if scrub_decision is None:
            # unconfigured OR error OR cache-miss => NEVER dial unscrubbed promo.
            return _deny("ncpr_unavailable", checks)
        if scrub_decision.get("block"):
            return _deny("ncpr_full_dnd", checks)
        cats = scrub_decision.get("categories") or []
        # Real-Estate is NCPR preference category #2; a block in it is a violation for our vertical.
        if "real_estate" in cats or 2 in cats:
            return _deny("ncpr_realestate_cat", checks)
        checks["ncpr_ok"] = True

        return Decision(allow=True, reason="allow", checks=checks)
    except Exception as exc:  # noqa: BLE001 — ANY internal error is a DENY (fail-closed)
        return _deny("gate_error", {**checks, "error_type": type(exc).__name__})


def _run_scrub(tenant_id: str, phone: str) -> Optional[dict]:
    """Call the injected NCPR scrub provider. None (unconfigured / error / miss) => fail-closed.

    Returns {block:bool, categories:[...]} on a definitive scrub, or None on ANY uncertainty (no
    provider, an exception, or a non-dict result). The gate treats None as a hard deny."""
    fn = _NCPR_SCRUB
    if fn is None:
        return None
    try:
        res = fn(tenant_id, phone)
    except Exception:  # noqa: BLE001 — a scrub error is fail-closed (deny), never a default-allow
        return None
    if not isinstance(res, dict):
        return None
    return res


# Trip the fail-closed assertion at IMPORT time: a permissive default cannot even import.
assert_fail_closed()
