"""credits/pricing.py — the SERVICE COSTING MATRIX (single source of truth).

Every billable Haptica service is one row: a provider COST BASIS (₹ per unit, from the real
rate card / vendor actuals), a platform MARGIN (markup %), and the resulting customer PRICE in
both ₹ and CREDITS. Super-admin can override any row; overrides persist to
VAR/credits_pricing.json and are merged over this seed (seed = the always-present fallback).

The matrix is the ONE place pricing lives — the client "Pricing" tab reads it, the metering
layer prices usage against it, and the super-admin "Costing" editor writes it. Pure stdlib;
cannot crash anything.

CREDIT UNIT: 1 credit = ₹CREDIT_INR_RATE (default ₹1). Credits are the customer-facing currency;
the wallet underneath is denominated in INR (matching the existing wallet/topup), so the two are
interchangeable at the configured rate and there is never a hidden FX surprise.
"""
from __future__ import annotations

import os
from pathlib import Path

# Reuse the canonical rate card so component costs never drift from the voice engine's truth.
try:  # llm_router is a sibling top-level package on the box (and under droplet_work in the repo)
    from llm_router.tiers import RATE_CARD as _RATE_CARD, TIERS as _TIERS
except Exception:  # noqa: BLE001 — never let a pricing import break startup
    _RATE_CARD = {
        "assumptions": {"tts_chars_per_min": 900, "llm_tokens_per_min": 1200, "default_avg_call_min": 1.5},
        "stt": {"sarvam": {"label": "Sarvam Saarika", "inr_per_min": 0.50}},
        "llm": {"groq-llama-3.3-70b": {"label": "Groq Llama-3.3-70B", "inr_per_mtok": 57.0}},
        "tts": {"sarvam-bulbul-v3": {"label": "Sarvam Bulbul v3", "inr_per_1k": 3.0}},
        "telephony_inr_per_min": 0.0,
    }
    _TIERS = {"standard": {"est_inr_per_min": 1.3}}

PRICING_FILE = "credits_pricing.json"


def credit_rate() -> float:
    """₹ value of one credit. Default 1 credit = ₹1."""
    try:
        r = float(os.getenv("CREDIT_INR_RATE", "1") or "1")
        return r if r > 0 else 1.0
    except Exception:  # noqa: BLE001
        return 1.0


def inr_to_credits(inr: float) -> float:
    return round(float(inr or 0) / credit_rate(), 4)


def credits_to_inr(c: float) -> float:
    return round(float(c or 0) * credit_rate(), 4)


# Blended ₹/min voice basis = the Standard tier's authoritative est_inr_per_min (the number the
# tier authors vouch for and the live cost-meter shows). We deliberately do NOT re-derive it from
# the per-component card here: that card's `inr_per_1k`/`inr_per_mtok` fields are list-estimate
# placeholders that don't all reconcile to the tier total, so trusting the vetted tier figure keeps
# the headline voice price honest and stable.
def _voice_basis_inr_per_min() -> float:
    try:
        est = (_TIERS.get("standard") or {}).get("est_inr_per_min")
        if est:
            return round(float(est), 4)
    except Exception:  # noqa: BLE001
        pass
    return 1.3


# ── THE SEED MATRIX ─────────────────────────────────────────────────────────────────────────
# `price_inr=None` => price is DERIVED as basis_inr * (1 + markup_pct/100). A super-admin override
# may set price_inr explicitly (then markup is informational). `metered` flags whether the service
# emits real usage→credit events TODAY (voice + whatsapp do; the rest are wired in the metering phase).
def _seed() -> list[dict]:
    v = _voice_basis_inr_per_min()
    return [
        {"key": "voice.call", "label": "Voice call (outbound)", "category": "Voice",
         "unit": "minute", "basis_inr": v, "markup_pct": 30, "price_inr": None, "metered": True,
         "description": "AI voice agent talk-time (STT + LLM + TTS). Telephony billed separately."},
        {"key": "voice.telephony", "label": "Telephony (carrier)", "category": "Voice",
         "unit": "minute", "basis_inr": float(_RATE_CARD.get("telephony_inr_per_min", 0) or 0),
         "markup_pct": 0, "price_inr": None, "metered": True,
         "description": "SIP carrier (Vobiz) per-minute passthrough. Set basis once a firm CDR rate is known."},
        {"key": "voice.inbound", "label": "Voice call (inbound)", "category": "Voice",
         "unit": "minute", "basis_inr": v, "markup_pct": 20, "price_inr": None, "metered": False,
         "description": "Inbound AI answering per connected minute."},
        {"key": "whatsapp.message", "label": "WhatsApp message", "category": "Messaging",
         "unit": "message", "basis_inr": 0.70, "markup_pct": 20, "price_inr": None, "metered": True,
         "description": "Outbound WhatsApp business message (Meta conversation pricing)."},
        {"key": "sms.message", "label": "SMS", "category": "Messaging",
         "unit": "message", "basis_inr": 0.20, "markup_pct": 25, "price_inr": None, "metered": False,
         "description": "Outbound SMS segment."},
        {"key": "ai_manager.minute", "label": "AI Manager session", "category": "AI",
         "unit": "minute", "basis_inr": v, "markup_pct": 30, "price_inr": None, "metered": False,
         "description": "AI Manager live voice/chat command-center session time."},
        {"key": "creative.image", "label": "Creative image", "category": "Creative",
         "unit": "image", "basis_inr": 2.0, "markup_pct": 50, "price_inr": None, "metered": False,
         "description": "AI-generated marketing image."},
        {"key": "creative.video", "label": "Creative video", "category": "Creative",
         "unit": "video", "basis_inr": 15.0, "markup_pct": 50, "price_inr": None, "metered": False,
         "description": "AI-generated short video render."},
        {"key": "ads.spend", "label": "Ad management", "category": "Growth",
         "unit": "₹100 spend", "basis_inr": 100.0, "markup_pct": 10, "price_inr": None, "metered": False,
         "description": "Managed ad spend passthrough + management fee (per ₹100 of media spend)."},
        {"key": "kb.index", "label": "Knowledge indexing", "category": "Knowledge",
         "unit": "document", "basis_inr": 0.50, "markup_pct": 40, "price_inr": None, "metered": True,
         "description": "Document ingested + embedded into the knowledge base."},
        {"key": "crm.enrich", "label": "CRM enrichment", "category": "CRM",
         "unit": "record", "basis_inr": 1.0, "markup_pct": 50, "price_inr": None, "metered": True,
         "description": "Contact/company enriched + synced into the relational CRM."},
    ]


def _price_inr(row: dict) -> float:
    """Derive the customer ₹ price for a row (explicit override wins over basis*markup)."""
    explicit = row.get("price_inr")
    if explicit is not None:
        try:
            return round(float(explicit), 4)
        except Exception:  # noqa: BLE001
            pass
    basis = float(row.get("basis_inr", 0) or 0)
    markup = float(row.get("markup_pct", 0) or 0)
    return round(basis * (1 + markup / 100.0), 4)


def _decorate(row: dict) -> dict:
    """Add the computed price fields + margin so the UI never recomputes pricing math."""
    out = dict(row)
    price = _price_inr(row)
    basis = float(row.get("basis_inr", 0) or 0)
    out["price_inr"] = price
    out["price_credits"] = inr_to_credits(price)
    out["margin_inr"] = round(price - basis, 4)
    out["margin_pct"] = round((price - basis) / basis * 100, 1) if basis > 0 else None
    return out


def _overrides_path(var_dir) -> Path:
    return Path(var_dir) / PRICING_FILE


def load_overrides(var_dir) -> dict:
    """{service_key: {basis_inr?, markup_pct?, price_inr?, metered?, label?, ...}} — admin edits only."""
    try:
        import json
        p = _overrides_path(var_dir)
        if not p.exists():
            return {}
        data = json.loads(p.read_text() or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_overrides(var_dir, overrides: dict) -> bool:
    try:
        import json
        p = _overrides_path(var_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(overrides or {}, indent=2))
        return True
    except Exception:  # noqa: BLE001
        return False


def services(var_dir) -> list[dict]:
    """The merged, decorated service list: seed overlaid with the admin overrides."""
    ov = load_overrides(var_dir)
    out = []
    for row in _seed():
        merged = dict(row)
        patch = ov.get(row["key"]) or {}
        for k in ("basis_inr", "markup_pct", "price_inr", "metered", "label", "description"):
            if k in patch and patch[k] is not None:
                merged[k] = patch[k]
        out.append(_decorate(merged))
    # allow brand-new admin-defined services (keys not in the seed)
    seed_keys = {r["key"] for r in _seed()}
    for key, patch in ov.items():
        if key in seed_keys or not isinstance(patch, dict):
            continue
        row = {"key": key, "label": patch.get("label", key), "category": patch.get("category", "Custom"),
               "unit": patch.get("unit", "unit"), "basis_inr": patch.get("basis_inr", 0),
               "markup_pct": patch.get("markup_pct", 0), "price_inr": patch.get("price_inr"),
               "metered": patch.get("metered", False), "description": patch.get("description", "")}
        out.append(_decorate(row))
    return out


def price_for(var_dir, service_key: str, qty: float = 1.0) -> dict:
    """Resolve {price_inr, price_credits} for a quantity of one service. Unknown key => zero."""
    for row in services(var_dir):
        if row["key"] == service_key:
            return {
                "service": service_key,
                "qty": qty,
                "unit_price_inr": row["price_inr"],
                "unit_price_credits": row["price_credits"],
                "total_inr": round(row["price_inr"] * float(qty or 0), 4),
                "total_credits": round(row["price_credits"] * float(qty or 0), 4),
            }
    return {"service": service_key, "qty": qty, "unit_price_inr": 0.0,
            "unit_price_credits": 0.0, "total_inr": 0.0, "total_credits": 0.0}


def matrix(var_dir) -> dict:
    """Full costing-matrix payload for the API."""
    return {
        "currency": "INR",
        "credit_rate_inr": credit_rate(),
        "services": services(var_dir),
        "rate_card": _RATE_CARD,
    }
