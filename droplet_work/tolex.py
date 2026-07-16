"""
Tolex — agent tooling & capability system.

Turns a *talking* voice agent into a *doing* one: grant capabilities (tools the LLM can call during a
call) per campaign with one click, and gate the dangerous ones. Four layers, all in this one module:

  1. CATALOG    — the capabilities an agent CAN be given (key, category, criticality, LLM param schema).
  2. GRANTS     — per-campaign: which tools are enabled + each tool's POLICY (off/allow/confirm/pin/
                  approve) and limits (max amount, allowed hours). Stored in $FAMIT_VAR/tolex_grants.json.
  3. POLICY     — before any tool runs: allowed? within limits/hours? execute now, or QUEUE for PIN /
                  human approval? Critical ops default to approve. Returns a decision + a spoken-safe line.
  4. EXECUTE    — runs the policy + the handler, appends an audit row to $FAMIT_VAR/tolex_ops.jsonl.

HOUSE LAWS: ADDITIVE · FLAG-GATED (TOLEX_ENABLED, default OFF) · IMPORT-GUARDED · BEST-EFFORT (never
raises into a live call) · DORMANT-SAFE. The control plane (panel + backend) is always safe; the agent
runtime hook is off by default ⇒ the live agent is byte-identical until you enable it.

v1 handler policy: INTERNAL ops (note / status / callback / lookup / book) execute for real (book reuses
the existing booking path via a callable in ctx); EXTERNAL / CRITICAL ops (whatsapp / brochure / payment
link / transfer / ticket) are durably CAPTURED as an operation request (never faked, never an un-wired
external call) and surfaced for the team — real provider wiring is the next iteration.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("tolex")

_VAR = os.getenv("FAMIT_VAR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "var"))
_GRANTS_PATH = os.path.join(_VAR, "tolex_grants.json")
_OPS_PATH = os.path.join(_VAR, "tolex_ops.jsonl")
_LOCK = threading.RLock()

MODES = ("off", "allow", "confirm", "pin", "approve")
CRITICALITY = ("normal", "sensitive", "critical")


def enabled() -> bool:
    """Master flag for the AGENT runtime hook. The panel/backend control plane works regardless."""
    return (os.getenv("TOLEX_ENABLED", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


# ════════════════════════════════════════════════════════════════════════════════════════════════
# 1) CATALOG — the capabilities an agent can be granted. `params` is a JSON-Schema object used BOTH
#    for the LLM function schema and the panel. `handler` selects the v1 implementation in _run().
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _p(props: dict, required: list | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


CATALOG: list[dict] = [
    {
        "key": "lookup_lead_info", "name": "Look up caller info", "category": "info",
        "criticality": "normal", "handler": "lookup",
        "description": "Recall what's already known about the caller (name, interest, past notes).",
        "llm_description": "Recall known details about the current caller (name, prior interest, notes). "
                           "Call when you need context you don't already have in the conversation.",
        "params": _p({"topic": {"type": "string", "description": "what to recall, e.g. 'budget', 'past visit'"}}),
    },
    {
        "key": "save_lead_note", "name": "Save a note", "category": "data",
        "criticality": "normal", "handler": "capture",
        "description": "Attach a short note about this caller for the team.",
        "llm_description": "Save a short note about the caller (their need, objection, preference) for the team. "
                           "Call when the caller shares something worth recording.",
        "params": _p({"note": {"type": "string", "description": "the note to save"}}, ["note"]),
    },
    {
        "key": "update_lead_status", "name": "Update lead status", "category": "data",
        "criticality": "sensitive", "handler": "capture",
        "description": "Set the caller's status (interested / hot / not interested / callback).",
        "llm_description": "Set the caller's lead status based on the call. Allowed values: "
                           "'interested','hot','warm','not_interested','callback'. Call once you can judge intent.",
        "params": _p({"status": {"type": "string",
                                 "enum": ["interested", "hot", "warm", "not_interested", "callback"],
                                 "description": "the lead status"}}, ["status"]),
    },
    {
        "key": "schedule_callback", "name": "Schedule a callback", "category": "scheduling",
        "criticality": "normal", "handler": "capture",
        "description": "Note a time the caller wants to be called back.",
        "llm_description": "Record a callback time the caller asked for. Call when they say to call back later.",
        "params": _p({"when": {"type": "string", "description": "the callback time in the caller's words"}}, ["when"]),
    },
    {
        "key": "book_site_visit", "name": "Book a site visit", "category": "scheduling",
        "criticality": "normal", "handler": "book",
        "description": "Book the caller's site visit / meeting once they agree a day & time.",
        "llm_description": "Book the site visit AFTER the caller verbally agrees a specific day & time. "
                           "Pass the time in their own words. Do not claim it's booked before calling this.",
        "params": _p({"when": {"type": "string", "description": "the agreed slot in the caller's words"},
                      "notes": {"type": "string", "description": "optional short context"}}, ["when"]),
    },
    {
        "key": "send_brochure", "name": "Send brochure", "category": "comms",
        "criticality": "normal", "handler": "capture",
        "description": "Queue a brochure / details link to the caller (WhatsApp/SMS).",
        "llm_description": "Send the caller the brochure / project details. Call when they ask for more info "
                           "or to receive details.",
        "params": _p({"item": {"type": "string", "description": "what to send, e.g. 'price list', 'brochure'"}}),
    },
    {
        "key": "send_whatsapp", "name": "Send WhatsApp message", "category": "comms",
        "criticality": "sensitive", "handler": "capture",
        "description": "Queue a WhatsApp follow-up message to the caller.",
        "llm_description": "Queue a short WhatsApp follow-up to the caller. Confirm the gist with them first.",
        "params": _p({"message": {"type": "string", "description": "the message to send"}}, ["message"]),
    },
    {
        "key": "transfer_to_human", "name": "Transfer to a human", "category": "handoff",
        "criticality": "sensitive", "handler": "capture",
        "description": "Hand the call / lead off to a human agent.",
        "llm_description": "Hand off to a human agent when the caller insists on a person or asks something "
                           "beyond your scope. Tell them a colleague will take over / call back.",
        "params": _p({"reason": {"type": "string", "description": "why the handoff is needed"}}),
    },
    {
        "key": "escalate_ticket", "name": "Raise a ticket", "category": "handoff",
        "criticality": "normal", "handler": "capture",
        "description": "Open a support / complaint ticket for the team.",
        "llm_description": "Open a support ticket for an issue or complaint the caller raises.",
        "params": _p({"summary": {"type": "string", "description": "short summary of the issue"}}, ["summary"]),
    },
    {
        "key": "send_payment_link", "name": "Send payment link", "category": "transaction",
        "criticality": "critical", "handler": "capture",
        "description": "Send the caller a payment / booking-amount link (money movement — gated).",
        "llm_description": "Send a payment link for a booking/token amount. Only when the caller explicitly "
                           "agrees to pay. State the amount clearly.",
        "params": _p({"amount": {"type": "number", "description": "amount in INR"},
                      "purpose": {"type": "string", "description": "what the payment is for"}}, ["amount"]),
    },
]
CATALOG_BY_KEY = {t["key"]: t for t in CATALOG}

# A safe default profile for one-click "Enable recommended": internal ops allowed, sensitive comms
# confirm, handoff confirm, critical money → human approval.
_RECOMMENDED = {
    "lookup_lead_info": "allow", "save_lead_note": "allow", "update_lead_status": "allow",
    "schedule_callback": "allow", "book_site_visit": "allow", "send_brochure": "allow",
    "send_whatsapp": "confirm", "transfer_to_human": "confirm", "escalate_ticket": "allow",
    "send_payment_link": "approve",
}


def catalog() -> list[dict]:
    """Public catalog view for the panel (no internal handler keys leaked beyond what's useful)."""
    return [{"key": t["key"], "name": t["name"], "category": t["category"],
             "criticality": t["criticality"], "description": t["description"],
             "params": t["params"]} for t in CATALOG]


# ════════════════════════════════════════════════════════════════════════════════════════════════
# 2) GRANTS — per-campaign config. Store: {"campaigns": {<cid>: GRANT}, "default": GRANT}.
#    GRANT = {"enabled": bool, "tools": {<key>: {"mode": ..., "max_amount": 0, "hours": "", "dry_run": False}}}
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _blank() -> dict:
    return {"enabled": False, "tools": {}}


def _load_store() -> dict:
    """Store v2 (tenant-scoped): {"tenants": {<tid>: {"default": GRANT, "campaigns": {<cid>: GRANT}}},
    "platform": {"default": GRANT, "campaigns": {<cid>: GRANT}}}. The super-admin manages `platform`
    (the fallback); each tenant manages only its own node ⇒ hard isolation. Migrates the v1 shape."""
    with _LOCK:
        d: dict = {}
        try:
            if os.path.exists(_GRANTS_PATH):
                with open(_GRANTS_PATH, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
        except Exception:  # noqa: BLE001
            d = {}
        if not isinstance(d, dict):
            d = {}
        # migrate v1 {campaigns, default} → platform
        if "platform" not in d and ("campaigns" in d or "default" in d):
            d = {"platform": {"default": d.get("default") or _blank(), "campaigns": d.get("campaigns") or {}},
                 "tenants": {}}
        d.setdefault("tenants", {})
        pl = d.setdefault("platform", {})
        pl.setdefault("default", _blank())
        pl.setdefault("campaigns", {})
        return d


def _is_platform(tenant_id: str) -> bool:
    t = (tenant_id or "").strip()
    return (not t) or t in ("_platform", "platform")


def _node(store: dict, tenant_id: str, *, create: bool = False) -> dict | None:
    """The grant node for a scope: store['platform'] for the super-admin scope, else the tenant's own
    node. With create=True a missing tenant node is created (for writes)."""
    if _is_platform(tenant_id):
        return store["platform"]
    tid = tenant_id.strip()
    if create:
        return store["tenants"].setdefault(tid, {"default": _blank(), "campaigns": {}})
    return store["tenants"].get(tid)


def _save_store(d: dict) -> None:
    with _LOCK:
        os.makedirs(_VAR, exist_ok=True)
        tmp = _GRANTS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _GRANTS_PATH)


def _norm_tool(cfg: dict) -> dict:
    mode = str((cfg or {}).get("mode", "off")).strip().lower()
    if mode not in MODES:
        mode = "off"
    out = {"mode": mode}
    try:
        out["max_amount"] = max(0, float((cfg or {}).get("max_amount", 0) or 0))
    except Exception:  # noqa: BLE001
        out["max_amount"] = 0
    out["hours"] = str((cfg or {}).get("hours", "") or "").strip()  # "HH-HH" e.g. "09-21"
    out["dry_run"] = bool((cfg or {}).get("dry_run", False))
    return out


def effective(tenant_id: str = "", campaign_id: str = "") -> dict:
    """The grant that actually applies to a (tenant, campaign) at call time. Most-specific EXISTING
    config wins: tenant-campaign → tenant-default → platform-campaign → platform-default. A present-but-
    disabled tenant entry overrides the platform (an explicit tenant opt-out)."""
    store = _load_store()
    cid = (campaign_id or "").strip()
    chain: list = []
    tn = _node(store, tenant_id) if not _is_platform(tenant_id) else None
    if tn:
        if cid and tn["campaigns"].get(cid):
            chain.append(tn["campaigns"][cid])
        if tn.get("default"):
            chain.append(tn["default"])
    pl = store["platform"]
    if cid and pl["campaigns"].get(cid):
        chain.append(pl["campaigns"][cid])
    if pl.get("default"):
        chain.append(pl["default"])
    for g in chain:
        if g is not None:
            return g
    return _blank()


def get_grants(tenant_id: str = "", campaign_id: str = "") -> dict:
    """For the PANEL editor: the stored entry for this (tenant, campaign), or the inherited baseline
    (with inherited=True) when this campaign has no entry yet."""
    store = _load_store()
    cid = (campaign_id or "").strip()
    node = _node(store, tenant_id)
    if not cid:
        return {"campaign_id": "", "inherited": False, **((node or {}).get("default") or _blank())}
    if node and node["campaigns"].get(cid):
        return {"campaign_id": cid, "inherited": False, **node["campaigns"][cid]}
    return {"campaign_id": cid, "inherited": True, **(effective(tenant_id, "") or _blank())}


def set_grants(tenant_id: str, campaign_id: str, enabled: bool, tools: dict) -> dict:
    """Save the grant for a (tenant, campaign), or the scope default when campaign_id is empty."""
    store = _load_store()
    cid = (campaign_id or "").strip()
    node = _node(store, tenant_id, create=True)
    entry = {"enabled": bool(enabled),
             "tools": {k: _norm_tool(v) for k, v in (tools or {}).items() if k in CATALOG_BY_KEY}}
    if cid:
        node["campaigns"][cid] = entry
    else:
        node["default"] = entry
    _save_store(store)
    return {"campaign_id": cid, "inherited": False, **entry}


def enable_recommended(tenant_id: str = "", campaign_id: str = "") -> dict:
    """One-click: enable the agent with the safe recommended capability profile."""
    return set_grants(tenant_id, campaign_id, True, {k: {"mode": m} for k, m in _RECOMMENDED.items()})


def granted_tools(tenant_id: str = "", campaign_id: str = "") -> list[tuple[dict, dict]]:
    """For the AGENT runtime: [(spec, tool_grant)] for every enabled, non-off tool. Empty when the
    effective grant is disabled — so the agent attaches no Tolex tools."""
    g = effective(tenant_id, campaign_id)
    if not g.get("enabled"):
        return []
    out = []
    for key, cfg in (g.get("tools") or {}).items():
        spec = CATALOG_BY_KEY.get(key)
        c = _norm_tool(cfg)
        if spec and c["mode"] != "off":
            out.append((spec, c))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════════
# 3) POLICY — decide what happens before a tool runs. Returns:
#    {"action": "execute"|"queue"|"deny", "needs": None|"pin"|"approve", "llm": <string for the LLM>}
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _hour_now() -> int:
    return datetime.now(timezone.utc).astimezone().hour


def _within_hours(spec_hours: str) -> bool:
    s = (spec_hours or "").strip()
    if not s or "-" not in s:
        return True
    try:
        a, b = s.split("-", 1)
        lo, hi = int(a), int(b)
        h = _hour_now()
        return (lo <= h <= hi) if lo <= hi else (h >= lo or h <= hi)
    except Exception:  # noqa: BLE001
        return True


def decide(spec: dict, grant: dict, args: dict) -> dict:
    mode = grant.get("mode", "off")
    name = spec.get("name", spec.get("key", "this"))
    if mode == "off":
        return {"action": "deny", "needs": None,
                "llm": f"not_allowed: {name} is disabled — do NOT do it; continue the conversation."}
    if not _within_hours(grant.get("hours", "")):
        return {"action": "deny", "needs": None,
                "llm": f"outside_hours: {name} is not allowed at this time — tell the caller the team "
                       f"will follow up during working hours; do NOT claim it's done."}
    # amount limit (transaction tools) → over-limit escalates to human approval, never silent.
    try:
        amt = float(args.get("amount", 0) or 0)
    except Exception:  # noqa: BLE001
        amt = 0.0
    cap = float(grant.get("max_amount", 0) or 0)
    if amt and cap and amt > cap:
        return {"action": "queue", "needs": "approve",
                "llm": f"needs_approval: ₹{int(amt)} exceeds the limit — tell the caller our team will "
                       f"confirm and send it shortly; do NOT claim it's sent."}
    if mode == "pin":
        return {"action": "queue", "needs": "pin",
                "llm": f"needs_verification: {name} needs verification — tell the caller it's logged and "
                       f"will be completed after a quick verification; do NOT claim it's done yet."}
    if mode == "approve":
        return {"action": "queue", "needs": "approve",
                "llm": f"needs_approval: {name} needs team approval — tell the caller it's been requested "
                       f"and the team will confirm shortly; do NOT claim it's done yet."}
    # allow / confirm → execute now (for 'confirm' the prompt guidance has the LLM confirm verbally first).
    return {"action": "execute", "needs": ("confirm" if mode == "confirm" else None), "llm": ""}


# ════════════════════════════════════════════════════════════════════════════════════════════════
# 4) OPS AUDIT + EXECUTE
# ════════════════════════════════════════════════════════════════════════════════════════════════
def log_op(rec: dict) -> None:
    """Append one audit row to tolex_ops.jsonl (append-only ⇒ race-free across worker + backend)."""
    try:
        os.makedirs(_VAR, exist_ok=True)
        rec = dict(rec)
        rec.setdefault("id", uuid.uuid4().hex[:10])
        rec.setdefault("ts", datetime.now(timezone.utc).isoformat())
        with open(_OPS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def recent_ops(campaign_id: str = "", limit: int = 200, tenant_id: str | None = None) -> list[dict]:
    out: list[dict] = []
    try:
        if not os.path.exists(_OPS_PATH):
            return []
        cid = (campaign_id or "").strip()
        with open(_OPS_PATH, "r", encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(r, dict):
                    continue
                if cid and (r.get("campaign_id") or "") != cid:
                    continue
                if tenant_id is not None and (r.get("tenant_id") or "") != tenant_id:
                    continue
                out.append(r)
    except Exception:  # noqa: BLE001
        return []
    out.reverse()
    return out[:max(1, min(limit, 2000))]


def execute(tool_key: str, args: dict, ctx: dict) -> dict:
    """Run a tool under policy. Returns {"ok": bool, "llm": <string returned to the LLM>}.
    NEVER raises. `ctx` carries call context: campaign_id, tenant_id, phone, lead_name, call_id, and an
    optional `book_fn(when, notes)->dict` so book_site_visit reuses the agent's real booking path."""
    spec = CATALOG_BY_KEY.get(tool_key)
    args = args or {}
    ctx = ctx or {}
    cid = ctx.get("campaign_id", "") or ""
    tid = ctx.get("tenant_id", "") or ""
    if spec is None:
        return {"ok": False, "llm": "unknown_tool: that capability isn't available."}
    grant = None
    for s, g in granted_tools(tid, cid):
        if s["key"] == tool_key:
            grant = g
            break
    if grant is None:
        log_op({"campaign_id": cid, "tenant_id": ctx.get("tenant_id", ""), "call_id": ctx.get("call_id", ""),
                "tool": tool_key, "args": args, "action": "deny", "reason": "not_granted"})
        return {"ok": False, "llm": f"not_allowed: {spec['name']} is not enabled — do NOT do it."}

    d = decide(spec, grant, args)
    base = {"campaign_id": cid, "tenant_id": ctx.get("tenant_id", ""), "phone": ctx.get("phone", ""),
            "call_id": ctx.get("call_id", ""), "tool": tool_key, "name": spec["name"],
            "criticality": spec["criticality"], "args": args, "mode": grant.get("mode"),
            "needs": d.get("needs"), "action": d["action"]}

    if d["action"] == "deny":
        log_op({**base, "result": "denied"})
        return {"ok": False, "llm": d["llm"]}

    if d["action"] == "queue":
        log_op({**base, "result": "queued"})
        return {"ok": True, "llm": d["llm"]}

    # action == execute → run the handler.
    try:
        res = _run(spec, args, ctx)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tolex execute %s error: %r", tool_key, exc)
        log_op({**base, "result": "error", "error": type(exc).__name__})
        return {"ok": False, "llm": f"tool_failed: I couldn't complete {spec['name']} just now — tell the "
                                    f"caller the team will follow up; do NOT claim it's done."}
    log_op({**base, "result": "executed", "detail": res.get("detail", "")})
    return {"ok": True, "llm": res.get("llm", f"done: {spec['name']} completed — confirm naturally to the caller.")}


def _run(spec: dict, args: dict, ctx: dict) -> dict:
    """v1 handlers. INTERNAL ops execute for real; EXTERNAL/CRITICAL ops are durably captured (queued
    for the team / future provider wiring) — never faked, never an un-wired external call."""
    handler = spec.get("handler")
    key = spec["key"]

    if handler == "book":
        book_fn = ctx.get("book_fn")
        if callable(book_fn):
            r = book_fn(args.get("when", ""), args.get("notes", "")) or {}
            if r.get("ok"):
                return {"llm": "booked=true: the site visit is confirmed. In one short warm line confirm the "
                               "day & time to the caller, then ask if there's anything else.",
                        "detail": r.get("datetime_iso", "")}
            return {"llm": "booking_unavailable: do NOT say it's booked — say you'll confirm shortly and continue."}
        # no booking path wired in this context → capture the intent
        return {"llm": "noted: I've logged the requested slot; the team will confirm the site visit.",
                "detail": args.get("when", "")}

    if handler == "lookup":
        # v1: no live CRM read wired here — tell the LLM to use what it has + ask if unsure.
        return {"llm": "no_extra_info: use what you already know from the conversation; if unsure, ask the "
                       "caller politely rather than guessing."}

    # handler == "capture": durably record the operation request for the team / downstream wiring.
    return {"llm": f"done: {spec['name']} has been logged for the caller — confirm warmly in one short line.",
            "detail": json.dumps(args, ensure_ascii=False)[:300]}
