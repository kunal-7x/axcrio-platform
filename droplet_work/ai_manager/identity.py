"""ai_manager.identity — phone normalization, caller resolution, and the DETERMINISTIC
risk / permission spine (spec §B, security-critical).

THE LLM NEVER AUTHORIZES (GLOBAL INVARIANT #3). Every authorization decision in the package
flows through pure, deterministic code here:
  * `classify_risk` / `is_risky` label a tool's blast radius (safe | bulk | money | destructive),
  * `stepup_scope` names the fresh step-up a risky tool needs,
  * `permits` is a default-deny capability check.
The model's own "risk" guess is ignored; these functions are authoritative.

The risk sets MIRROR `ai_manager/tools/catalog.py` risk_class tags EXACTLY (so swapping the
live/stub registry never changes the gates): a tool tagged risk_class="risky"/money in the
catalog is `is_risky()==True` here, and every catalog risk_class="safe" tool is non-risky.
`is_risky` and `classify_risk` are kept consistent by construction: every non-'safe'
classification is risky, and only the 'safe' bucket is non-risky.

IMPORT-SAFE: this module does ZERO I/O and imports no heavy deps at module scope. `resolve()`
lazy-imports the sibling `registry` and degrades to None when it can't load (reveals nothing).
NEVER raises.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Phone normalization (E.164 India, caller-ID equivalence)
# ---------------------------------------------------------------------------
_NON_DIGITS = re.compile(r"\D+")


def canonical_phone(phone: str) -> str:
    """Normalize a phone to `+91XXXXXXXXXX` E.164 India form.

    Rules (spec §B): strip non-digits, drop a leading 0 / 91 / +91, take the LAST 10 digits
    and prefix `+91`. A non-Indian / short number that can't be coerced to a 10-digit Indian
    mobile degrades best-effort to `"+" + digits`. Empty / blank input → "". NEVER raises.
    """
    raw = (phone or "").strip()
    if not raw:
        return ""
    digits = _NON_DIGITS.sub("", raw)
    if not digits:
        return ""
    # Drop the India country code / trunk prefix if present, then keep the trailing 10.
    if len(digits) > 10:
        if digits.startswith("91") and len(digits) >= 12:
            digits = digits[2:]
        elif digits.startswith("0"):
            digits = digits.lstrip("0")
    if len(digits) >= 10:
        bare10 = digits[-10:]
        return "+91" + bare10
    # Too short to be an Indian mobile — best-effort E.164-ish so callers still get a stable key.
    return "+" + digits


def _bare10(phone: str) -> str:
    """The bare 10-digit local number (last 10 digits) or "" if it isn't 10+ digits."""
    digits = _NON_DIGITS.sub("", phone or "")
    if digits.startswith("91") and len(digits) >= 12:
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits.lstrip("0")
    return digits[-10:] if len(digits) >= 10 else ""


def match_forms(phone: str) -> set:
    """The caller-ID equivalence SET for `phone`: every form the same Indian number can arrive
    as, so a registry lookup matches whether the trunk delivered `+91...`, `91...`, `0...`, or a
    bare 10-digit number. Shape: `{canonical, bare10, "0"+bare10, "91"+bare10}` (plus the
    canonical for short/foreign numbers). Empty input → empty set. NEVER raises.
    """
    canon = canonical_phone(phone)
    if not canon:
        return set()
    forms = {canon}
    bare = _bare10(phone)
    if bare:
        forms.update({bare, "0" + bare, "91" + bare, "+91" + bare})
    return forms


# ---------------------------------------------------------------------------
# Caller resolution (caller-ID is a HINT only; reveals nothing on unknown)
# ---------------------------------------------------------------------------
def resolve(caller_id: str) -> Optional[dict]:
    """Resolve a caller-ID to its authorized-number row, or None.

    Lazy-imports the sibling `registry` and calls `registry.lookup(canonical_phone(caller_id))`.
    Returns the number row `{tenant_id, number_id, role, grants(list), verify_mode, ...}` or
    None when the number isn't registered (an unknown caller reveals NOTHING — the state machine
    rejects with a generic "not registered"). Degrades to None if the registry can't load (the
    package stays dormant-safe). NEVER raises.
    """
    canon = canonical_phone(caller_id)
    if not canon:
        return None
    try:
        from . import registry as _registry
        row = _registry.lookup(canon)
    except Exception:  # noqa: BLE001 — dormant/absent registry reveals nothing, never crashes.
        return None
    return row or None


# ---------------------------------------------------------------------------
# Risk classification (deterministic; AUTHORITATIVE — mirrors catalog risk_class)
# ---------------------------------------------------------------------------
# money: external spend / paid generation (catalog: money=True OR creative.* / template gen).
_MONEY_TOOLS = frozenset({
    "ads.set_budget",
    "ads.create_campaign",
    "creative.generate_video",
    "creative.generate_banner",
    "creative.generate_brochure",
    "whatsapp.generate_templates",
})

# destructive: irreversible deletes.
_DESTRUCTIVE_TOOLS = frozenset({
    "leads.delete",
})

# bulk: mass outreach / activation (side-effecting, risky, not money/destructive).
_BULK_TOOLS = frozenset({
    "leads.enqueue_calls",
    "whatsapp.send",
    "ads.pause",
    "workflow.activate",
    "workflow.run_now",
})

# RISKY = anything that demands a fresh, scoped step-up before it runs. This is the union of
# the three non-safe buckets and matches catalog.py risk_class="risky"/money EXACTLY. Every
# other catalog tool (contacts.read/write, leads.read, analytics.read, brain.retrieve,
# billing.read, wallet.read, booking.read/create/reschedule/cancel, suppression.add,
# campaigns.create, workflow.create_draft) is NOT risky.
RISKY_TOOLS = frozenset(_MONEY_TOOLS | _DESTRUCTIVE_TOOLS | _BULK_TOOLS)


def is_risky(tool: str) -> bool:
    """True iff `tool` requires a PIN/step-up before execution. Deterministic + authoritative;
    consistent with `classify_risk` (every non-'safe' classification is risky). NEVER raises."""
    return (tool or "").strip() in RISKY_TOOLS


def classify_risk(tool: str) -> str:
    """Label a tool's blast radius: one of `safe | bulk | money | destructive`.

    money={ads.set_budget, ads.create_campaign, creative.*, whatsapp.generate_templates};
    destructive={leads.delete}; bulk={leads.enqueue_calls, whatsapp.send, ads.pause,
    workflow.activate, workflow.run_now}; everything else → safe. Consistent with `is_risky`:
    `is_risky(t)` ⇔ `classify_risk(t) != "safe"`. NEVER raises.
    """
    t = (tool or "").strip()
    if t in _MONEY_TOOLS:
        return "money"
    if t in _DESTRUCTIVE_TOOLS:
        return "destructive"
    if t in _BULK_TOOLS:
        return "bulk"
    return "safe"


def stepup_scope(tool: str) -> str:
    """The fresh step-up SCOPE a risky tool needs (so one budget PIN can't authorize a delete):
    money→"spend", bulk→"bulk", destructive→"destructive", safe→"" (no step-up). NEVER raises."""
    risk = classify_risk(tool)
    if risk == "money":
        return "spend"
    if risk == "bulk":
        return "bulk"
    if risk == "destructive":
        return "destructive"
    return ""


# ---------------------------------------------------------------------------
# Capability check (default-deny)
# ---------------------------------------------------------------------------
# Read-only modules a low-privilege actor (viewer/operator) with NO explicit grants may still
# READ from (the empty-grants fallback grants reads, never writes/sends/spend).
_READ_MODULES = frozenset({
    "analytics", "leads", "contacts", "billing", "wallet", "booking", "brain",
})

# The catalog's read actions (verbs that only fetch, never mutate). The empty-grants viewer/
# operator fallback is limited to these (spec §B "reads only"): a `.write`/`.delete`/`.create`
# in a read module is NOT a read and is denied without an explicit grant.
_READ_VERBS = frozenset({"read", "retrieve", "list", "get", "overview"})


def _is_read_tool(tool: str) -> bool:
    """True iff `tool` is a pure read (its action verb only fetches). NEVER raises."""
    t = (tool or "").strip()
    if "." not in t:
        return False
    return t.rsplit(".", 1)[1] in _READ_VERBS

# Roles that hold the full capability set by default (owner/admin = all; manager with EMPTY
# grants is treated as full — matching endpoints' `_can` fallback, which hands manager the 8
# business modules). Explicit grants always NARROW from there.
_FULL_ROLES = frozenset({"owner", "admin"})
_LENIENT_EMPTY_ROLES = frozenset({"manager", "owner", "admin"})


def permits(role: str, grants, tool: str) -> bool:
    """Default-deny capability check: may an actor with this `role` + `grants` run `tool`?

    Deterministic + documented (spec §B). The LLM never reaches here — this is authoritative.

      * `owner` / `admin` → True (full capability set).
      * Otherwise let `module = tool.split(".")[0]`; allow iff:
          - `module in grants` (the actor was granted that whole business module), OR
          - `tool in grants` (granted that specific tool), OR
          - grants is FALSY and `role in {manager}` (a manager with no explicit grants gets the
            full set — matches endpoints' `_can` fallback that grants the 8 modules), OR
          - grants is FALSY and `module` is a READ module AND `tool` is a read verb (viewer/
            operator with no grants get READS ONLY — a write/delete/spend in a read module like
            `contacts.write` or `leads.delete` is still denied; spec §B "reads only").
      * Everything else → deny.

    `grants` may be any iterable of strings (list/set/tuple) or None. NEVER raises.
    """
    r = (role or "").strip().lower()
    t = (tool or "").strip()
    if not t:
        return False
    if r in _FULL_ROLES:
        return True

    grant_set = _norm_grants(grants)
    module = t.split(".")[0]

    # Explicit grants win (whole-module OR specific-tool).
    if module in grant_set or t in grant_set:
        return True

    # Empty grants: a manager is lenient-full (mirrors the endpoints fallback); any lower role
    # (viewer/operator) gets read-only access to the read modules. A non-empty grant set NEVER
    # falls through to read-only — it narrows the actor to exactly what was granted (default-deny).
    if not grant_set:
        if r in _LENIENT_EMPTY_ROLES:
            return True
        # Viewer/operator with no grants: READS ONLY — a read module AND a read verb (so a
        # write/delete/spend like contacts.write or leads.delete is still denied; spec §B).
        return module in _READ_MODULES and _is_read_tool(t)

    return False


def _norm_grants(grants) -> set:
    """Coerce a grants value (None / list / set / tuple / iterable of strings) into a clean set
    of trimmed lowercase tokens. NEVER raises."""
    if not grants:
        return set()
    try:
        if isinstance(grants, str):
            items: Iterable = [grants]
        else:
            items = grants
        return {str(g).strip().lower() for g in items if str(g).strip()}
    except Exception:  # noqa: BLE001
        return set()
