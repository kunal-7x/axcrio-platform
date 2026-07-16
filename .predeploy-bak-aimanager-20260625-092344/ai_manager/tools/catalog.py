"""workforce.tools.catalog — the LIVE tool catalog: each tool maps 1:1 to an existing caller.py route
over the authenticated loopback (transport.py). DORMANT until AIWF_SERVICE_TOKEN; no business logic is
duplicated — we REUSE the endpoints (spec §1, §12).

Every fn signature is fn(args, ctx) -> result dict. ctx MUST carry `run_token` (the per-run per-tenant
token the runner minted) so the loopback call is RLS-scoped to the run's org_id. result always includes
`actual_spend_minor` (0 for non-money tools) so the runner can settle the wallet hold.

risk_class + scopes + money mirror stub_tools EXACTLY so swapping registries doesn't change the gates.

B2: ad adapters re-pointed to the REAL ads_engine routes (/ads/campaigns/{id}/...); GAP adapters wired
for the LIVE modules (workflow-studio, booking, campaign create, wallet read). Cred-blocked modules
(creative/media_gen FEATURE_MEDIA off, ads_engine FEATURE_ADS off) are CORRECT-but-PARKED: a 404 (route
not mounted because FEATURE_* is off) is translated to a clean {ok:False, reason:"not_configured"} so the
runner parks gracefully instead of erroring.
"""
from __future__ import annotations

from typing import Any

from . import ToolRegistry, ToolSpec
from . import transport as _t
from .. import config as _cfg


def _tok(ctx) -> str:
    return (getattr(ctx, "run_token", None) or (ctx or {}).get("run_token") if isinstance(ctx, dict)
            else getattr(ctx, "run_token", "")) or ""


def _result(resp: dict, *, spend: int = 0) -> dict:
    if resp.get("ok"):
        d = resp.get("data") or {}
        d.setdefault("actual_spend_minor", spend)
        d["ok"] = True
        return d
    return {"ok": False, "reason": resp.get("reason") or resp.get("status"), "actual_spend_minor": 0}


def _result_parkable(resp: dict, *, spend: int = 0) -> dict:
    """Like _result but: a 404 (the module's FEATURE_* is OFF so its router is NOT mounted) is a clean
    `not_configured` park, NOT an error. Used by adapters whose backing module is cred/FEATURE-gated
    (creative/media_gen, ads_engine). The runner treats not_configured as a graceful skip, never a crash."""
    if resp.get("ok"):
        d = resp.get("data") or {}
        d.setdefault("actual_spend_minor", spend)
        d["ok"] = True
        return d
    status = resp.get("status")
    reason = resp.get("reason")
    if status == 404 or reason == "transport_dormant":
        return {"ok": False, "reason": "not_configured", "actual_spend_minor": 0}
    return {"ok": False, "reason": reason or status, "actual_spend_minor": 0}


# ---- SAFE reads (GET) ----
def _contacts_read(args, ctx):
    p = {k: v for k, v in (args or {}).items() if k in ("stage", "hot", "q", "sort", "limit")}
    return _result(_t.call("GET", "/contacts", run_token=_tok(ctx), params=p))


def _leads_read(args, ctx):
    return _result(_t.call("GET", "/leads", run_token=_tok(ctx), params=args or {}))


def _analytics_read(args, ctx):
    return _result(_t.call("GET", "/analytics", run_token=_tok(ctx), params=args or {}))


def _brain_retrieve(args, ctx):
    return _result(_t.call("GET", "/brain/retrieve", run_token=_tok(ctx), params=args or {}))


def _billing_read(args, ctx):
    return _result(_t.call("GET", "/billing/overview", run_token=_tok(ctx)))


def _wallet_read(args, ctx):
    # GAP-FILL: prepaid credit/wallet balance (SEPARATE from billing.balance prepaid — never summed).
    return _result(_t.call("GET", "/wallet", run_token=_tok(ctx)))


def _bookings_read(args, ctx):
    # GAP-FILL: "kal ke site visits batao". GET /booking/bookings; FEATURE_BOOKING gates mounting.
    p = {k: v for k, v in (args or {}).items() if k in ("day", "from", "to", "resource_id", "status")}
    return _result_parkable(_t.call("GET", "/booking/bookings", run_token=_tok(ctx), params=p))


# ---- RISKY writes/sends/spend ----
def _whatsapp_send(args, ctx):
    return _result(_t.call("POST", "/whatsapp/send", run_token=_tok(ctx), json=args or {}))


def _leads_enqueue_calls(args, ctx):
    # maps to /run (the real dialer); the runner only reaches here AFTER the gate passes.
    # caller.py POST /run is a FORM endpoint (campaign_id/use_stored/temps/source_mode/
    # lead_ids/force are Form(...) fields) -> we MUST send a form body (data=), NOT json=
    # (a JSON body is ignored by FastAPI Form params -> 0 leads, no dial). TCfix.
    a = dict(args or {})
    body = {}
    cid = a.get("campaign_id") or a.get("campaign") or ""
    if cid:
        body["campaign_id"] = str(cid)
    # explicit lead selectors win (a precise audience, e.g. one number for a test)
    if a.get("lead_ids"):
        body["lead_ids"] = str(a["lead_ids"])
        body["source_mode"] = "upload"
    if a.get("leads"):
        body["leads"] = str(a["leads"])
    # segment -> temperature filter over stored leads ("call hot leads" / "call all leads")
    seg = (a.get("segment") or a.get("temps") or "").strip().lower()
    if not body.get("lead_ids") and not body.get("leads"):
        if seg in ("hot", "warm", "cold"):
            body["temps"] = seg
            body["source_mode"] = "temperature"
        else:
            # all stored leads (default for "call all leads" / a named campaign run)
            body["use_stored"] = "1"
    if a.get("use_stored"):
        body["use_stored"] = "1"
    if a.get("force"):
        body["force"] = "1"
    return _result(_t.call("POST", "/run", run_token=_tok(ctx), data=body))


# ---- ADS (re-pointed to the REAL ads_engine routes; FEATURE_ADS off => parked not_configured) ----
def _ads_set_budget(args, ctx):
    """Set/raise an ad budget. The REAL ads_engine surface is a propose->approve->optimize flow, NOT a
    flat /ads/budget (the placeholder the catalog shipped against). A budget change rides POST /ads/optimize
    with a set_budget directive. FEATURE_ADS off => 404 => clean not_configured (parked)."""
    a = dict(args or {})
    plan_id = a.get("plan_id") or a.get("campaign_id") or a.get("campaign") or ""
    budget_minor = int(a.get("budget_minor", 0) or 0)
    body = {"action": "set_budget", "plan_id": plan_id, "campaign_id": plan_id,
            "budget_minor": budget_minor}
    return _result_parkable(_t.call("POST", "/ads/optimize", run_token=_tok(ctx), json=body),
                            spend=budget_minor)


def _ads_pause(args, ctx):
    """Pause an ad campaign. REAL route: POST /ads/campaigns/{plan_id}/pause (was placeholder /ads/pause).
    FEATURE_ADS off => parked not_configured."""
    a = dict(args or {})
    plan_id = a.get("plan_id") or a.get("campaign_id") or a.get("campaign") or ""
    body = {"reason": a.get("reason", "manual_pause")}
    return _result_parkable(_t.call("POST", f"/ads/campaigns/{plan_id}/pause",
                                    run_token=_tok(ctx), json=body))


def _ads_create_campaign(args, ctx):
    """Propose a new ad campaign (draft). REAL route: POST /ads/campaigns/propose. FEATURE_ADS off =>
    parked. Launch/approve is a SEPARATE high-risk step (POST /ads/campaigns/{id}/approve + step-up)."""
    a = dict(args or {})
    body = {"brief": a.get("brief") or a}
    return _result_parkable(_t.call("POST", "/ads/campaigns/propose", run_token=_tok(ctx), json=body))


def _leads_delete(args, ctx):
    lid = (args or {}).get("lead_id", "")
    return _result(_t.call("DELETE", f"/leads/{lid}", run_token=_tok(ctx)))


def _contacts_write(args, ctx):
    phone = (args or {}).get("phone") or (args or {}).get("contact_id", "")
    return _result(_t.call("PUT", f"/contacts/{phone}", run_token=_tok(ctx), json=args or {}))


def _suppression_add(args, ctx):
    return _result(_t.call("POST", "/suppression", run_token=_tok(ctx), json=args or {}))


# ---- CAMPAIGNS (caller.py LIVE: POST /campaigns is a FORM endpoint, fields_json) ----
def _campaigns_create(args, ctx):
    """GAP-FILL: create a campaign DRAFT. caller.py POST /campaigns takes the FORM field fields_json (a
    JSON string), so we use the transport `data=` form body. The draft itself is non-spend (L1); launch is
    the later gated step. LIVE module."""
    import json as _json
    a = dict(args or {})
    fields = a.get("fields") or {k: v for k, v in a.items()
                                  if k not in ("objective", "_summary", "fields")}
    if a.get("objective") and "objective" not in fields:
        fields["objective"] = a["objective"]
    return _result(_t.call("POST", "/campaigns", run_token=_tok(ctx),
                           data={"fields_json": _json.dumps(fields)}))


# ---- WORKFLOW (LIVE module workflow-studio; create DRAFT, never auto-activate) ----
def _workflow_create_draft(args, ctx):
    """GAP-FILL: voice -> a React-Flow workflow DRAFT (Flow-6). POST /workflows ("") creates a draft;
    activation is the SEPARATE publish/run step behind a step-up. FEATURE_WORKFLOWS off => parked."""
    a = dict(args or {})
    spec = a.get("workflow_spec") or a.get("definition") or a.get("draft") or {}
    body = {"name": a.get("name") or a.get("objective") or "Voice workflow",
            "draft": spec, "definition": spec}
    return _result_parkable(_t.call("POST", "/workflows", run_token=_tok(ctx), json=body))


def _workflow_activate(args, ctx):
    """GAP-FILL: publish (activate) a workflow — the gated step (step-up enforced by the route)."""
    wid = (args or {}).get("workflow_id") or (args or {}).get("id", "")
    return _result_parkable(_t.call("POST", f"/workflows/{wid}/publish", run_token=_tok(ctx),
                                    json=args or {}))


def _workflow_run_now(args, ctx):
    """GAP-FILL: run a published workflow now."""
    wid = (args or {}).get("workflow_id") or (args or {}).get("id", "")
    return _result_parkable(_t.call("POST", f"/workflows/{wid}/run", run_token=_tok(ctx),
                                    json=args or {}))


# ---- BOOKING (LIVE module; booking is FREE — no step-up) ----
def _booking_create(args, ctx):
    """GAP-FILL: book a slot (site visit). POST /booking/book. Booking is FREE (no spend, no step-up);
    slot-uniqueness is enforced server-side (no double-book). FEATURE_BOOKING off => parked."""
    a = dict(args or {})
    body = {k: a.get(k) for k in ("resource_id", "phone", "slot_start", "slot_end", "name", "notes")
            if a.get(k) is not None}
    return _result_parkable(_t.call("POST", "/booking/book", run_token=_tok(ctx), json=body))


def _booking_reschedule(args, ctx):
    """GAP-FILL: reschedule a booking. POST /booking/bookings/{id}/reschedule."""
    a = dict(args or {})
    bid = a.get("booking_id") or a.get("id", "")
    body = {k: a.get(k) for k in ("slot_start", "slot_end") if a.get(k) is not None}
    return _result_parkable(_t.call("POST", f"/booking/bookings/{bid}/reschedule",
                                    run_token=_tok(ctx), json=body))


def _booking_cancel(args, ctx):
    """GAP-FILL: cancel a booking. POST /booking/bookings/{id}/cancel."""
    a = dict(args or {})
    bid = a.get("booking_id") or a.get("id", "")
    return _result_parkable(_t.call("POST", f"/booking/bookings/{bid}/cancel",
                                    run_token=_tok(ctx), json=args or {}))


# ---- CREATIVE -> the LIVE dedicated AI Asset Service (:8310). B3 wiring. ----
# The asset service OWNS the money-path (reserve/settle ACTUAL internally, no-double-charge proven
# A4); these adapters return actual_spend_minor=0 (the asset service is authoritative on cost, the
# workforce wallet is NOT charged for creative). Tenant is token-derived from the per-run Bearer; a
# body tenant_id is ignored. Dormant-safe: service OFF / 503 / unreachable -> not_configured (park).
def _asset_generate(args, ctx, *, asset_type: str) -> dict:
    """Map an AI-Manager creative slot-set -> the AI Asset Service POST /generate payload and call
    it over the authenticated loopback. The asset service runs the 2-stage NO-INVENT prompt builder
    + the chosen provider (OpenRouter live for the admin tenant), reserves+settles credits itself,
    and returns a job. NEVER raises."""
    a = dict(args or {})
    # the asset /generate accepts both an explicit campaign_id (it enriches context server-side via
    # the U4 reader when present) AND bare explicit fields (the safe NO-INVENT default until then).
    payload = {
        "asset_type": asset_type,
        "campaign_id": a.get("campaign_id") or a.get("campaign") or a.get("campaign_ref") or "",
        "count": int(a.get("count") or a.get("n") or a.get("quantity") or 1),
        "instruction": a.get("instruction") or a.get("prompt") or a.get("brief") or a.get("text") or "",
        "platform": a.get("platform") or "meta",
        "language": a.get("language") or "en",
        # explicit campaign facts (used only if no campaign_id; never invented downstream):
        "business_name": a.get("business_name") or "",
        "industry": a.get("industry") or "",
        "product": a.get("product") or "",
        "location": a.get("location") or "",
        "price": a.get("price") or "",
        "offer": a.get("offer") or "",
        "audience": a.get("audience") or "",
        "goal": a.get("goal") or "",
        "style": a.get("style") or "",
        "size": a.get("size") or "",
        # pass the AIM idempotency key DOWN so a retried adapter call is single-charged (F4 ON
        # CONFLICT); falls back to a stable per-(campaign,type,instruction) key.
        "idempotency_key": a.get("idempotency_key") or a.get("idem_key") or "",
    }
    resp = _t.call_service("POST", "/generate", run_token=_tok(ctx),
                           base=_cfg.asset_service_base(), json=payload)
    # 503 = asset service OFF for this tenant (AIASSET_ENABLED) -> a clean park, like a parked module.
    if not resp.get("ok") and resp.get("status") == 503:
        return {"ok": False, "reason": "not_configured", "actual_spend_minor": 0}
    # 402 = over the tenant credit budget -> surface as a typed, non-crashing result.
    if not resp.get("ok") and resp.get("status") == 402:
        d = resp.get("data") or {}
        return {"ok": False, "reason": "insufficient_credits",
                "est_cost_minor": d.get("est_cost_minor"), "actual_spend_minor": 0}
    # the asset service settles ACTUAL itself; the workforce wallet is NOT charged here -> spend=0.
    return _result_parkable(resp, spend=0)


def _creative_generate_video(args, ctx):
    """Generate ad-video creative. The Asset Service makes only the COVER/hero image (full video is
    out-of-scope per the integrations spec); routed to /generate asset_type=video_cover. LIVE for a
    tenant with AIASSET_ENABLED; otherwise a clean not_configured park."""
    return _asset_generate(args, ctx, asset_type="video_cover")


def _creative_generate_image(args, ctx):
    """Generate a banner/brochure image via the LIVE Asset Service (/generate asset_type=banner).
    This is the real-banner path proven in A4. Credit-gated by the asset service; dormant-safe."""
    return _asset_generate(args, ctx, asset_type="banner")


# ---- WHATSAPP TEMPLATE BUILDER (LIVE module whatsapp_builder; FEATURE_WHATSAPP_BUILDER). ----
# The builder OWNS its money-path internally: generate.py does wallet.reserve(
# resource_type="wa_template_gen")/settle/release (failed gen never charges, idem no-double-reserve),
# exactly like the asset service owns creative cost. So this adapter returns actual_spend_minor=0 — the
# workforce wallet is NOT charged here (no double-charge by construction). The deterministic Meta-
# compliance validator (validate.py) is the AUTHORITY: the LLM only PROPOSES, fabricated facts are
# stripped (needs_fact) and cannot be approved. Tenant is token-derived from the per-run Bearer (the
# route reads t["tenant_id"], never a body field). FEATURE_WHATSAPP_BUILDER off => router not mounted
# => 404 => clean not_configured park (never a crash).
def _whatsapp_generate_templates(args, ctx):
    """Generate Meta-compliant WhatsApp template suggestions for a campaign via the whatsapp_builder
    module. Maps to POST /whatsapp/campaign/{campaign_id}/generate-templates over the authenticated
    loopback. The campaign_id is REQUIRED (resolve it from a campaigns.read first); the rest of args is
    the optional GenSpec (n / angles / language / tone). NEVER raises; parks gracefully if the module
    flag is OFF."""
    a = dict(args or {})
    campaign_id = (a.get("campaign_id") or a.get("campaign") or a.get("campaign_ref")
                   or a.get("id") or "")
    if not campaign_id:
        return {"ok": False, "reason": "campaign_id_required", "actual_spend_minor": 0}
    spec = {k: v for k, v in a.items()
            if k not in ("campaign_id", "campaign", "campaign_ref", "id", "run_token")}
    resp = _t.call("POST", f"/whatsapp/campaign/{campaign_id}/generate-templates",
                   run_token=_tok(ctx), json=spec)
    # the builder settles credits ACTUAL itself; the workforce wallet is NOT charged here -> spend=0.
    return _result_parkable(resp, spend=0)


_LIVE = [
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
             _bookings_read, risk_class="safe"),
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
    # --- PARKED-until-creds: creative/media_gen (FEATURE_MEDIA off => clean not_configured) ---
    ToolSpec("creative.generate_video", "Generate ad video(s) (async; returns a job — PARKED until "
             "FEATURE_MEDIA).", ("creative.generate_video",), _creative_generate_video,
             side_effecting=True, money=True, risk_class="risky"),
    ToolSpec("creative.generate_banner", "Generate a banner image (PARKED until FEATURE_MEDIA).",
             ("creative.generate_banner",), _creative_generate_image, side_effecting=True, money=True,
             risk_class="risky"),
    ToolSpec("creative.generate_brochure", "Generate a brochure (PARKED until FEATURE_MEDIA).",
             ("creative.generate_brochure",), _creative_generate_image, side_effecting=True, money=True,
             risk_class="risky"),
    # --- WHATSAPP TEMPLATE BUILDER (LIVE module; FEATURE_WHATSAPP_BUILDER gates the route mount) ---
    ToolSpec("whatsapp.generate_templates", "Generate Meta-compliant WhatsApp message-template "
             "suggestions for a campaign (the deterministic validator is the authority; no fabricated "
             "facts). Requires a campaign_id (resolve via campaigns.read first). Spend is metered by the "
             "builder itself. PARKED (not_configured) until FEATURE_WHATSAPP_BUILDER.",
             ("whatsapp.generate_templates",), _whatsapp_generate_templates, side_effecting=True,
             money=True, risk_class="risky"),
]


def register_live(reg: ToolRegistry) -> None:
    for t in _LIVE:
        reg.register(t)
