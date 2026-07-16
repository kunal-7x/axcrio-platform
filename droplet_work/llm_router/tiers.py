"""llm_router/tiers.py — SINGLE SOURCE OF TRUTH for the LEAN/STANDARD/PREMIUM tier system.

PHASE-1 SAFE, ADDITIVE, PURE-DATA. Imported by caller.py's GET /tiers route ONLY. It does NOT
touch agent.py (the outbound earner), trunks, firewall, or SIP. Pure stdlib; cannot crash anything.

This module is the ONE place that defines:
  1. the 3 preset tiers (Lean / Standard / Premium) -> a concrete {stt, llm, tts} provider+model
     triple + a default voice, and
  2. the per-component ₹/min RATE CARD that the frontend cost-meter does its pure-client-side math
     against (zero token burn — no call is placed to compute an estimate).

The frontend reads GET /tiers for BOTH the slider mapping AND the cost-meter math, so the mapping is
data (here), never duplicated in the UI. The campaign persists the chosen `tier` NAME *and* a
snapshot of the resolved triple (see caller.py _coerce_fields) so a later edit to this file never
silently rewrites an in-flight campaign.

⚠ PHASE-1 vs PHASE-2: choosing a tier writes the config to the campaign and drives the UI + cost
meter TODAY. Switching the *voice* within ElevenLabs is already honored on the outbound call by
agent.py:485 (fields.voice_id) — live now, ZERO agent.py edit. Switching the STT/LLM/TTS *provider*
on the live OUTBOUND leg (Lean=Sarvam vs Premium=ElevenLabs) is PHASE-2 / OB-PROV — gated, founder
sign-off, agent.py edit. So `tts_provider`/`stt_provider`/`llm_provider` are PERSISTED here but only
take effect on outbound once OB-PROV ships. The UI surfaces this honestly.
"""
from __future__ import annotations

# ── per-component RATE CARD (list ₹; the wallet meters real actuals) ──────────────────────
# Rates VERIFIED against each provider's official pricing page (2026-06-26) and converted at the
# spot USD→INR rate below. ₹/min figures assume a typical conversational minute of ~150 spoken
# words ≈ ~900 TTS characters + ~1.2K LLM tokens (in+out) — derived from real per-turn token logs.
# These are the numbers the frontend multiplies for the live cost meter; all labelled "≈" in the UI.
#
# Telephony (now "Famit AI Telecom Infrastructure") is TIER-INDEPENDENT. It used to be hidden (0.0 ⇒
# "pending CDR") which left it OUT of the headline total; it is now a real, INCLUDED line at a flat
# per-min rate that super-admin can override (VAR/tier_overrides.json → telephony_inr_per_min).
FX_USD_INR = 94.5   # spot USD→INR used to convert the USD-priced providers (Deepgram/Groq/ElevenLabs)
RATE_CARD = {
    "assumptions": {
        "tts_chars_per_min": 900,      # ~150 wpm * ~6 chars/word (matches logged ~100 out-tok/turn × ~9 turns/min)
        "llm_tokens_per_min": 1200,    # in+out combined, conversational
        "default_avg_call_min": 1.5,   # editable in the UI for projected campaign spend
    },
    # STT — ₹ per minute of audio. (Production runs Deepgram Nova-3 on Standard/Premium; Sarvam on Lean.)
    "stt": {
        "sarvam":     {"label": "Sarvam Saarika",  "inr_per_min": 0.50},   # ₹30/hr (native INR)
        "deepgram":   {"label": "Deepgram Nova-3",  "inr_per_min": 0.55},   # $0.0058/min multilingual streaming → ₹0.55
    },
    # LLM — ₹ per 1M tokens. `inr_per_mtok` = blended (per-min tier math); `inr_in`/`inr_out` = the
    # split rates used by the PER-CALL cost engine (call_cost) for correct numbers.
    "llm": {
        "groq-gpt-oss-20b":   {"label": "Groq gpt-oss-20B",   "inr_per_mtok": 7.5,  "inr_in": 6.3,  "inr_out": 25.0},   # $0.075/$0.30
        "groq-llama-3.3-70b": {"label": "Groq Llama-3.3-70B", "inr_per_mtok": 57.0, "inr_in": 49.0, "inr_out": 66.0},   # $0.59/$0.79
        "sarvam-30b":         {"label": "Sarvam-30b",         "inr_per_mtok": 4.75, "inr_in": 2.5,  "inr_out": 10.0},   # ₹2.5/₹10 (native, no cap)
        "sarvam-105b":        {"label": "Sarvam-105b",        "inr_per_mtok": 7.6,  "inr_in": 4.0,  "inr_out": 16.0},   # ₹4/₹16 (native, no cap)
    },
    # TTS — ₹ per 1K characters; UI converts via tts_chars_per_min.
    "tts": {
        "sarvam-bulbul-v2":   {"label": "Sarvam Bulbul v2",      "inr_per_1k": 1.5},   # ₹15/10K (native INR)
        "sarvam-bulbul-v3":   {"label": "Sarvam Bulbul v3",      "inr_per_1k": 3.0},   # ₹30/10K (native INR)
        "elevenlabs-flash-v2.5": {"label": "ElevenLabs Flash v2.5", "inr_per_1k": 4.73},# $0.05/1K direct-API → ₹4.73
    },
    # Carrier telephony — same on every tier. Now a REAL, INCLUDED line (₹0.40/min flat) rather than a
    # hidden footnote. `telephony_verified` flips the UI from "est. — pending CDR" to a summed line.
    "telephony_inr_per_min": 0.40,   # flat-rate Famit AI Telecom Infra (Jio/Tata SIP); super-admin editable
    "telephony_verified": True,      # True ⇒ telephony is summed into the headline total
    "telephony_note": ("Famit AI Telecom Infrastructure flat-rate SIP (₹0.40/min). Editable in "
                       "super-admin; real per-call carrier cost still reconciles against the CDR."),
    "fx_usd_inr": FX_USD_INR,
    # per-component source attributions (shown in the cost-card info tooltips; kept honest + dated).
    "sources": {
        "stt": "Deepgram Nova-3 ($0.0058/min) · Sarvam Saarika (₹30/hr) — official pricing, 2026-06-26",
        "llm": "Groq on-demand: Llama-3.3-70B $0.59/$0.79 per Mtok, gpt-oss-20B $0.075/$0.30 — groq.com/pricing",
        "tts": "ElevenLabs Flash v2.5 $0.05/1k (direct API) · Sarvam Bulbul ₹15–30/10k — official pricing",
        "telephony": "Famit AI Telecom Infrastructure — flat-rate domestic SIP, ≈₹0.40/min (editable)",
        "fx": f"USD→INR {FX_USD_INR} (spot, 2026-06-26)",
    },
}


# ── the 3 PRESET TIERS ─────────────────────────────────────────────────────────────────────
# Each stop resolves to a concrete {stt, llm, tts} provider+model + a default voice for that tier.
# `voice_id`/`voice_provider` are the recommended default voice for the tier; the UI's voice
# dropdown can override within the tier's TTS provider, and Advanced mode can override everything
# (which flips the campaign to tier "custom").
TIERS = {
    "lean": {
        "key": "lean",
        "name": "Lean",
        "quality": "Good",
        "available": True,
        "blurb": "Cheapest — Deepgram + Sarvam-30b + Sarvam Bulbul v3. Great for big cold lists.",
        "est_inr_per_min": 3.66,     # 0.40 tel + 0.55 Deepgram STT + ~0.01 Sarvam-30b LLM + 2.70 Bulbul-v3 TTS
        "stt": {"provider": "deepgram",   "model": "nova-3",           "rate_key": "deepgram"},
        "llm": {"provider": "sarvam",     "model": "sarvam-30b",       "rate_key": "sarvam-30b"},
        "tts": {"provider": "sarvam",     "model": "bulbul:v3",        "rate_key": "sarvam-bulbul-v3"},
        "voice": {"provider": "sarvam", "voice_id": "anushka"},
    },
    "standard": {
        "key": "standard",
        "name": "Standard",
        "quality": "Great",
        "available": True,
        "recommended": True,         # Haptica Recommended — the default pick (Neha/Riya ElevenLabs voice)
        "blurb": "Recommended — Deepgram + Sarvam-105b + ElevenLabs studio voice (Neha).",
        "est_inr_per_min": 5.22,     # 0.40 tel + 0.55 Deepgram STT + ~0.01 Sarvam-105b LLM + 4.26 ElevenLabs TTS
        "stt": {"provider": "deepgram",   "model": "nova-3",           "rate_key": "deepgram"},
        "llm": {"provider": "sarvam",     "model": "sarvam-105b",      "rate_key": "sarvam-105b"},
        "tts": {"provider": "elevenlabs", "model": "eleven_flash_v2_5","rate_key": "elevenlabs-flash-v2.5"},
        "voice": {"provider": "elevenlabs", "voice_id": "QTKSa2Iyv0yoxvXY2V8a"},  # Neha (Riya) — Haptica default
    },
    "premium": {
        "key": "premium",
        "name": "Premium",
        "quality": "Studio",
        "available": False,          # currently OFF — superadmin can flip via the Stack Builder override
        "unavailable_reason": "Due to high demand",
        "blurb": "Deepgram + Groq Llama-3.3-70B (or stronger) + ElevenLabs. Currently unavailable due to high demand.",
        "est_inr_per_min": 5.28,     # 0.40 tel + 0.55 Deepgram STT + 0.07 Groq-70B LLM + 4.26 ElevenLabs TTS
        "stt": {"provider": "deepgram",   "model": "nova-3",           "rate_key": "deepgram"},
        "llm": {"provider": "groq",       "model": "llama-3.3-70b",    "rate_key": "groq-llama-3.3-70b"},
        "tts": {"provider": "elevenlabs", "model": "eleven_flash_v2_5","rate_key": "elevenlabs-flash-v2.5"},
        "voice": {"provider": "elevenlabs", "voice_id": ""},   # blank -> UI picks/keeps the campaign's EL voice
    },
}

TIER_ORDER = ["lean", "standard", "premium"]
DEFAULT_TIER = "standard"   # Standard is the Haptica-recommended default (Neha voice + Sarvam-105b)


def resolve_triple(tier: str) -> dict:
    """Return the concrete {stt,llm,tts,voice} triple for a named preset tier.

    Returns {} for an unknown tier (incl. "custom" — the campaign carries its own explicit
    *_provider + voice_id in that case, see caller.py _coerce_fields). NEVER raises."""
    t = (tier or "").strip().lower()
    spec = TIERS.get(t)
    if not spec:
        return {}
    return {
        "tier": spec["key"],
        "stt": dict(spec["stt"]),
        "llm": dict(spec["llm"]),
        "tts": dict(spec["tts"]),
        "voice": dict(spec["voice"]),
    }


def _deep_merge(base: dict, over: dict) -> dict:
    """Recursively merge `over` onto a COPY of `base` (dicts merge, scalars/lists replace). Pure,
    never mutates inputs, never raises into the caller — bad override types are simply ignored."""
    out = dict(base)
    try:
        for k, v in (over or {}).items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = _deep_merge(out[k], v)
            else:
                out[k] = v
    except Exception:  # noqa: BLE001
        return dict(base)
    return out


def apply_overrides(overrides: dict | None) -> tuple[dict, dict]:
    """Merge a super-admin override doc (VAR/tier_overrides.json, set from the Voice-Defaults panel)
    over the static RATE_CARD + TIERS and return (rate_card, tiers_by_key). Recognized keys:
      * top-level rate_card fields: telephony_inr_per_min / telephony_verified / telephony_note /
        assumptions.{...} — e.g. {"telephony_inr_per_min": 0.35}
      * "tiers": {"<tier>": {"stt"|"llm"|"tts"|"voice": {...}, "est_inr_per_min": N}} — the moved
        Advanced per-component picker writes here so a tier's default stack is operator-controlled.
    Unknown/garbage shapes degrade to the static defaults. NEVER raises."""
    rc = dict(RATE_CARD)
    tiers = {k: dict(TIERS[k]) for k in TIER_ORDER}
    try:
        o = overrides if isinstance(overrides, dict) else {}
        # rate-card level overrides (telephony rate/flags, assumptions)
        for fld in ("telephony_inr_per_min", "telephony_verified", "telephony_note"):
            if fld in o:
                rc[fld] = o[fld]
        if isinstance(o.get("assumptions"), dict):
            rc["assumptions"] = _deep_merge(rc.get("assumptions", {}), o["assumptions"])
        # per-tier component overrides
        tov = o.get("tiers")
        if isinstance(tov, dict):
            for tk in TIER_ORDER:
                if isinstance(tov.get(tk), dict):
                    tiers[tk] = _deep_merge(tiers[tk], tov[tk])
    except Exception:  # noqa: BLE001
        return dict(RATE_CARD), {k: dict(TIERS[k]) for k in TIER_ORDER}
    return rc, tiers


def tiers_payload(overrides: dict | None = None) -> dict:
    """The full payload for GET /tiers — the single source the frontend consumes for BOTH the
    slider->triple mapping AND the cost-meter math. `overrides` (VAR/tier_overrides.json, loaded by
    the /tiers route) lets super-admin retune the per-tier stack + telephony rate without a deploy."""
    rate_card, tiers = apply_overrides(overrides)
    return {
        "tiers": [tiers[k] for k in TIER_ORDER],
        "order": list(TIER_ORDER),
        "default": DEFAULT_TIER,
        "rate_card": rate_card,
        # convenience: spell out the ₹/min cost-math formula the UI implements (documentation only).
        # NOTE: telephony is now INCLUDED in the total when telephony_verified is true.
        "cost_formula": {
            "stt_inr_per_min": "rate_card.stt[stt.rate_key].inr_per_min",
            "llm_inr_per_min": "rate_card.llm[llm.rate_key].inr_per_mtok * assumptions.llm_tokens_per_min / 1_000_000",
            "tts_inr_per_min": "rate_card.tts[tts.rate_key].inr_per_1k * assumptions.tts_chars_per_min / 1000",
            "telephony_inr_per_min": "rate_card.telephony_inr_per_min (included when telephony_verified)",
            "total_inr_per_min": "telephony + stt + llm + tts",
            "projected_campaign_inr": "total_inr_per_min * est_avg_call_min * num_leads",
        },
        # PHASE note surfaced honestly in the UI.
        "phase_note": ("Voice selection within ElevenLabs is live on outbound today. Switching the "
                       "STT/LLM/TTS PROVIDER on the live outbound call (Lean=Sarvam vs Premium=ElevenLabs) "
                       "is pending Phase 2 (OB-PROV, founder approval)."),
        "ob_prov_pending": True,
    }


def rate_key_for(kind: str, provider: str, model: str = "") -> str:
    """Map an ACTUAL analytics provider+model → the RATE_CARD key for that component. Used by the
    per-call cost engine so the cost reflects what really ran (Sarvam-105b, Deepgram, etc.)."""
    p = (provider or "").strip().lower()
    m = (model or "").strip().lower()
    if kind == "stt":
        return "deepgram" if p == "deepgram" else "sarvam"
    if kind == "tts":
        if p == "elevenlabs":
            return "elevenlabs-flash-v2.5"
        return "sarvam-bulbul-v3" if "v3" in m else "sarvam-bulbul-v2"
    if kind == "llm":
        if p == "sarvam":
            return "sarvam-105b" if "105" in m else "sarvam-30b"
        if p == "groq":
            return "groq-gpt-oss-20b" if ("20b" in m or "oss" in m) else "groq-llama-3.3-70b"
        if p == "cerebras":
            return "groq-llama-3.3-70b"  # nearest known rate until a cerebras card is added
        return "groq-llama-3.3-70b"
    return ""


def call_cost(usage: dict, overrides: dict | None = None) -> dict:
    """PER-CALL 4-component cost in ₹ from REAL usage. `usage` keys (all optional):
      duration_s, stt_speech_s, llm_in_tokens, llm_out_tokens, tts_chars,
      stt_rate_key | (stt_provider, stt_model),
      llm_rate_key | (llm_provider, llm_model),
      tts_rate_key | (tts_provider, tts_model).
    STT + telephony bill on call minutes; LLM on in/out tokens (split rates); TTS on characters.
    Returns {telephony, stt, llm, tts, total, per_min, duration_min, currency, rate_keys}. NEVER raises."""
    try:
        rc, _ = apply_overrides(overrides)
        u = usage if isinstance(usage, dict) else {}
        dur_s = float(u.get("duration_s") or 0) or float(u.get("stt_speech_s") or 0)
        dur_min = dur_s / 60.0

        stt_key = u.get("stt_rate_key") or rate_key_for("stt", u.get("stt_provider", ""), u.get("stt_model", ""))
        llm_key = u.get("llm_rate_key") or rate_key_for("llm", u.get("llm_provider", ""), u.get("llm_model", ""))
        tts_key = u.get("tts_rate_key") or rate_key_for("tts", u.get("tts_provider", ""), u.get("tts_model", ""))

        tel = (float(rc.get("telephony_inr_per_min", 0.40)) * dur_min) if rc.get("telephony_verified", True) else 0.0
        stt = float((rc.get("stt", {}).get(stt_key, {}) or {}).get("inr_per_min", 0.0)) * dur_min

        llm_rc = rc.get("llm", {}).get(llm_key, {}) or {}
        tin = float(u.get("llm_in_tokens") or 0)
        tout = float(u.get("llm_out_tokens") or 0)
        if llm_rc.get("inr_in") is not None and (tin or tout):
            llm = (tin * float(llm_rc["inr_in"]) + tout * float(llm_rc.get("inr_out", llm_rc["inr_in"]))) / 1_000_000.0
        else:
            llm = float(llm_rc.get("inr_per_mtok", 0.0)) * (tin + tout) / 1_000_000.0

        tts = float((rc.get("tts", {}).get(tts_key, {}) or {}).get("inr_per_1k", 0.0)) * float(u.get("tts_chars") or 0) / 1000.0

        total = tel + stt + llm + tts
        return {
            "telephony": round(tel, 4), "stt": round(stt, 4), "llm": round(llm, 4), "tts": round(tts, 4),
            "total": round(total, 4), "per_min": round(total / dur_min, 4) if dur_min > 0 else 0.0,
            "duration_min": round(dur_min, 3), "currency": "INR",
            "rate_keys": {"stt": stt_key, "llm": llm_key, "tts": tts_key},
        }
    except Exception:  # noqa: BLE001
        return {"telephony": 0, "stt": 0, "llm": 0, "tts": 0, "total": 0, "per_min": 0,
                "duration_min": 0, "currency": "INR", "rate_keys": {}}
