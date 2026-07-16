"""workforce.tools.stub_tools — the OFFLINE in-memory mirror of the live catalog.

Every tool name the live catalog (catalog.py `_LIVE`) ships is registered here with an IDENTICAL
ToolSpec metadata footprint — same `name`, `scopes`, `required_slots`, `risk_class`, `money`,
`side_effecting`. ONLY the bound `fn` differs: the live `fn` reaches caller.py over the authenticated
loopback (transport.py), whereas the stub `fn` returns a DETERMINISTIC in-memory result with ZERO
network. This is load-bearing per the contract: because the gate-bearing fields are byte-identical,
swapping `build_registry("stub")` <-> `build_registry("live")` moves NO gate (risk/scope/money/slots),
so the offline command lifecycle test exercises the exact same policy surface as production.

Each stub `fn(args, ctx) -> dict`:
  * READS  -> {"ok":True,"data":{...plausible sample...},"actual_spend_minor":0,"status":200}
  * WRITES/SENDS/SPEND -> {"ok":True,"data":{"id":"stub_...","queued":True},"actual_spend_minor":0,
                          "status":200,"run_id":"stub_run_..."}
Never touches the network. Never raises. Spend is ALWAYS 0 (offline: no real wallet charge), matching
the live adapters whose money-path is owned downstream (creative/whatsapp builder also settle spend=0).
"""
from __future__ import annotations

from typing import Any, Optional

from . import ToolRegistry, ToolSpec


# --------------------------------------------------------------------------- #
# Deterministic ID helpers (no randomness, no clock — same args -> same shape) #
# --------------------------------------------------------------------------- #
def _stub_id(prefix: str, *parts: Any) -> str:
    """A stable, readable stub id derived ONLY from the given parts (deterministic, no uuid/clock)."""
    seed = "_".join(str(p) for p in parts if p not in (None, "")) or "0"
    # short, ascii-safe, deterministic — fnv-ish fold so two different arg-sets differ.
    h = 0
    for ch in seed:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return f"stub_{prefix}_{h:08x}"


def _ok_read(data: dict) -> dict:
    """A read result: ok, plausible sample payload, zero spend, 200."""
    return {"ok": True, "data": dict(data or {}), "actual_spend_minor": 0, "status": 200}


def _ok_write(*, kind: str, args: Optional[dict] = None, **extra: Any) -> dict:
    """A write/send/spend result: ok, queued stub id, zero spend, 200, plus a run_id."""
    a = dict(args or {})
    sid = _stub_id(kind, *(sorted(f"{k}={v}" for k, v in a.items()) or ["empty"]))
    data = {"id": sid, "queued": True}
    data.update(extra)
    return {"ok": True, "data": data, "actual_spend_minor": 0, "status": 200,
            "run_id": _stub_id("run", sid)}


# =========================================================================== #
# SAFE reads — deterministic plausible sample payloads, no network.           #
# =========================================================================== #
def _contacts_read(args, ctx) -> dict:
    return _ok_read({"contacts": [
        {"phone": "+919800000001", "name": "Asha", "stage": "hot", "tags": ["site_visit"]},
        {"phone": "+919800000002", "name": "Ravi", "stage": "warm", "tags": []},
    ], "count": 2})


def _leads_read(args, ctx) -> dict:
    return _ok_read({"leads": [
        {"lead_id": "stub_lead_1", "phone": "+919800000001", "score": 0.82, "temp": "hot"},
        {"lead_id": "stub_lead_2", "phone": "+919800000002", "score": 0.41, "temp": "warm"},
    ], "count": 2})


def _analytics_read(args, ctx) -> dict:
    return _ok_read({"calls_today": 12, "answered": 7, "bookings": 3, "spend_minor": 0,
                     "conversion_rate": 0.25})


def _brain_retrieve(args, ctx) -> dict:
    q = (dict(args or {}).get("q") or dict(args or {}).get("query") or "").strip()
    return _ok_read({"facts": [
        {"text": "Sample grounding fact from the Business Brain (stub).", "source": "stub_kb"},
    ], "query": q})


def _billing_read(args, ctx) -> dict:
    return _ok_read({"balance_minor": 250000, "currency": "INR", "plan": "stub",
                     "invoices": []})


def _wallet_read(args, ctx) -> dict:
    return _ok_read({"credits_minor": 100000, "currency": "INR", "low_balance": False})


def _booking_read(args, ctx) -> dict:
    return _ok_read({"bookings": [
        {"id": "stub_booking_1", "resource_id": "site_a", "slot_start": "2026-06-26T10:00:00+05:30",
         "slot_end": "2026-06-26T10:30:00+05:30", "phone": "+919800000001", "status": "confirmed"},
    ], "count": 1})


# =========================================================================== #
# RISKY writes / sends / spend — queued stub jobs, zero spend, with run_id.    #
# =========================================================================== #
def _whatsapp_send(args, ctx) -> dict:
    return _ok_write(kind="wa_send", args=args)


def _leads_enqueue_calls(args, ctx) -> dict:
    return _ok_write(kind="enqueue_calls", args=args)


def _leads_delete(args, ctx) -> dict:
    return _ok_write(kind="lead_delete", args=args)


def _contacts_write(args, ctx) -> dict:
    return _ok_write(kind="contact_write", args=args)


def _suppression_add(args, ctx) -> dict:
    return _ok_write(kind="suppression_add", args=args)


def _ads_set_budget(args, ctx) -> dict:
    # money tool, but offline = zero real spend (mirrors live which settles via the optimize endpoint).
    return _ok_write(kind="ads_set_budget", args=args)


def _ads_pause(args, ctx) -> dict:
    return _ok_write(kind="ads_pause", args=args)


def _ads_create_campaign(args, ctx) -> dict:
    return _ok_write(kind="ads_propose", args=args)


def _campaigns_create(args, ctx) -> dict:
    return _ok_write(kind="campaign_draft", args=args)


def _workflow_create_draft(args, ctx) -> dict:
    return _ok_write(kind="workflow_draft", args=args)


def _workflow_activate(args, ctx) -> dict:
    return _ok_write(kind="workflow_publish", args=args)


def _workflow_run_now(args, ctx) -> dict:
    return _ok_write(kind="workflow_run", args=args)


def _booking_create(args, ctx) -> dict:
    return _ok_write(kind="booking", args=args)


def _booking_reschedule(args, ctx) -> dict:
    return _ok_write(kind="booking_reschedule", args=args)


def _booking_cancel(args, ctx) -> dict:
    return _ok_write(kind="booking_cancel", args=args)


def _creative_generate_video(args, ctx) -> dict:
    return _ok_write(kind="asset_video_cover", args=args, asset_type="video_cover")


def _creative_generate_banner(args, ctx) -> dict:
    return _ok_write(kind="asset_banner", args=args, asset_type="banner")


def _creative_generate_brochure(args, ctx) -> dict:
    # brochure reuses the banner asset_type server-side; mirror that here.
    return _ok_write(kind="asset_brochure", args=args, asset_type="banner")


def _whatsapp_generate_templates(args, ctx) -> dict:
    # mirror the live fn's hard guard: campaign_id is required (the ELICIT loop won't pre-prompt).
    a = dict(args or {})
    campaign_id = (a.get("campaign_id") or a.get("campaign") or a.get("campaign_ref")
                   or a.get("id") or "")
    if not campaign_id:
        return {"ok": False, "reason": "campaign_id_required", "actual_spend_minor": 0, "status": 400}
    return _ok_write(kind="wa_templates", args=args, campaign_id=str(campaign_id),
                     templates=[{"name": _stub_id("tpl", campaign_id), "status": "proposed"}])


# =========================================================================== #
# Catalog — metadata MUST mirror catalog._LIVE EXACTLY (only `fn` differs).   #
# Keep this list in lockstep with catalog._LIVE; risk/scope/money/slots are   #
# load-bearing (a stub<->live swap must move no gate).                        #
# =========================================================================== #
_STUB = [
    # ---- SAFE reads (GET) ----
    ToolSpec("contacts.read", "List/read contacts (hot leads, profiles) before acting.",
             ("contacts.read",), _contacts_read, risk_class="safe"),
    ToolSpec("leads.read", "Read leads and scores.", ("leads.read",), _leads_read, risk_class="safe"),
    ToolSpec("analytics.read", "Read analytics/reports.", ("analytics.read",), _analytics_read,
             risk_class="safe"),
    ToolSpec("brain.retrieve", "Retrieve grounding facts from the Business Brain/KB before any factual "
             "claim.", ("brain.retrieve",), _brain_retrieve, risk_class="safe"),
    ToolSpec("billing.read", "Read billing overview.", ("billing.read",), _billing_read,
             risk_class="safe"),
    ToolSpec("wallet.read", "Read prepaid credit/wallet balance (separate from billing).",
             ("billing.read",), _wallet_read, risk_class="safe"),
    ToolSpec("booking.read", "Read upcoming bookings / site-visits (read-only).", ("contacts.read",),
             _booking_read, risk_class="safe"),
    # ---- RISKY writes / sends / spend ----
    ToolSpec("whatsapp.send", "Send WhatsApp (bulk gated; honor opt-outs).", ("whatsapp.send",),
             _whatsapp_send, side_effecting=True, risk_class="risky",
             required_slots=("segment",)),
    ToolSpec("leads.enqueue_calls", "Enqueue outbound calls (mass-calling gated).",
             ("leads.enqueue_calls",), _leads_enqueue_calls, side_effecting=True, risk_class="risky",
             required_slots=("campaign", "segment")),
    ToolSpec("ads.set_budget", "Set/raise ad budget — EXTERNAL SPEND, always approved.",
             ("ads.set_budget",), _ads_set_budget, side_effecting=True, money=True, risk_class="risky",
             required_slots=("budget_minor",)),
    ToolSpec("ads.pause", "Pause an ad campaign.", ("ads.pause",), _ads_pause, side_effecting=True,
             risk_class="risky"),
    ToolSpec("ads.create_campaign", "Propose a new ad campaign (draft; launch is a separate approval).",
             ("ads.create_campaign",), _ads_create_campaign, side_effecting=True, risk_class="risky"),
    ToolSpec("leads.delete", "Delete a lead — DESTRUCTIVE, always approved.", ("leads.delete",),
             _leads_delete, side_effecting=True, risk_class="risky"),
    ToolSpec("contacts.write", "Update a contact (tags/stage/name/note).", ("contacts.write",),
             _contacts_write, side_effecting=True, risk_class="safe"),
    ToolSpec("suppression.add", "Add a number to the DND/suppression set.", ("suppression.add",),
             _suppression_add, side_effecting=True, risk_class="safe"),
    # --- GAP-FILLED: LIVE modules (campaign create / workflow / booking) ---
    ToolSpec("campaigns.create", "Create a campaign DRAFT (non-spend; launch is a separate approval).",
             ("campaigns.create",), _campaigns_create, side_effecting=True, risk_class="safe",
             required_slots=("objective",)),
    ToolSpec("workflow.create_draft", "Create a workflow DRAFT from a voice spec — NEVER auto-activate.",
             ("workflow.create_draft",), _workflow_create_draft, side_effecting=True, risk_class="safe",
             required_slots=("objective",)),
    ToolSpec("workflow.activate", "Publish/activate a workflow — gated (step-up).",
             ("workflow.activate",), _workflow_activate, side_effecting=True, risk_class="risky",
             required_slots=("workflow_id",)),
    ToolSpec("workflow.run_now", "Run a published workflow now.", ("workflow.run_now",),
             _workflow_run_now, side_effecting=True, risk_class="risky",
             required_slots=("workflow_id",)),
    ToolSpec("booking.create", "Book a slot / site-visit (FREE — no spend).", ("booking.create",),
             _booking_create, side_effecting=True, risk_class="safe",
             required_slots=("slot_start",)),
    ToolSpec("booking.reschedule", "Reschedule a booking.", ("booking.reschedule",),
             _booking_reschedule, side_effecting=True, risk_class="safe"),
    ToolSpec("booking.cancel", "Cancel a booking.", ("booking.cancel",), _booking_cancel,
             side_effecting=True, risk_class="safe"),
    # --- PARKED-until-creds in live; in stub they succeed deterministically (no FEATURE gate offline) ---
    ToolSpec("creative.generate_video", "Generate ad video(s) (async; returns a job — PARKED until "
             "FEATURE_MEDIA).", ("creative.generate_video",), _creative_generate_video,
             side_effecting=True, money=True, risk_class="risky"),
    ToolSpec("creative.generate_banner", "Generate a banner image (PARKED until FEATURE_MEDIA).",
             ("creative.generate_banner",), _creative_generate_banner, side_effecting=True, money=True,
             risk_class="risky"),
    ToolSpec("creative.generate_brochure", "Generate a brochure (PARKED until FEATURE_MEDIA).",
             ("creative.generate_brochure",), _creative_generate_brochure, side_effecting=True,
             money=True, risk_class="risky"),
    # --- WHATSAPP TEMPLATE BUILDER ---
    ToolSpec("whatsapp.generate_templates", "Generate Meta-compliant WhatsApp message-template "
             "suggestions for a campaign (the deterministic validator is the authority; no fabricated "
             "facts). Requires a campaign_id (resolve via campaigns.read first). Spend is metered by the "
             "builder itself. PARKED (not_configured) until FEATURE_WHATSAPP_BUILDER.",
             ("whatsapp.generate_templates",), _whatsapp_generate_templates, side_effecting=True,
             money=True, risk_class="risky"),
]


def register_stub(reg: ToolRegistry) -> None:
    """Register the full offline mirror of the live catalog into `reg` (every live tool name, same gates)."""
    for t in _STUB:
        reg.register(t)
