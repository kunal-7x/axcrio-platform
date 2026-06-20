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
# Rates from the spec §0 research. ₹/min figures assume a typical conversational minute of
# ~150 spoken words ≈ ~900 TTS characters + ~1.2K LLM tokens (in+out). These are the numbers the
# frontend multiplies for the live cost meter; all are list estimates labelled "≈" in the UI.
#
# Telephony (Vobiz) is TIER-INDEPENDENT and dominates real spend — surfaced separately so the
# vendor sees the tier delta is the modest part.
RATE_CARD = {
    "assumptions": {
        "tts_chars_per_min": 900,      # ~150 wpm * ~6 chars/word
        "llm_tokens_per_min": 1200,    # in+out combined, conversational
        "default_avg_call_min": 1.5,   # editable in the UI for projected campaign spend
    },
    # STT — ₹ per minute of audio.
    "stt": {
        "sarvam":     {"label": "Sarvam Saarika", "inr_per_min": 0.50},   # ₹30/hr
    },
    # LLM — ₹ per 1M tokens (in≈out blended); UI converts via llm_tokens_per_min.
    "llm": {
        "groq-gpt-oss-20b":   {"label": "Groq gpt-oss-20B",  "inr_per_mtok": 8.0},    # ~$0.05-0.15/M -> ~₹8 blended
        "groq-llama-3.3-70b": {"label": "Groq Llama-3.3-70B","inr_per_mtok": 57.0},   # ~$0.59/$0.79 -> ~₹57 blended
    },
    # TTS — ₹ per 1K characters; UI converts via tts_chars_per_min.
    "tts": {
        "sarvam-bulbul-v2":   {"label": "Sarvam Bulbul v2",      "inr_per_1k": 1.5},   # ₹15/10K
        "sarvam-bulbul-v3":   {"label": "Sarvam Bulbul v3",      "inr_per_1k": 3.0},   # ₹30/10K
        "elevenlabs-flash-v2.5": {"label": "ElevenLabs Flash v2.5", "inr_per_1k": 4.2},# ~$0.05/1K
    },
    # Carrier telephony — same on every tier; shown as an honest footnote, NOT part of the tier delta.
    "telephony_inr_per_min": 0.0,   # set when a firm per-min Vobiz figure is known; UI hides if 0
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
        "blurb": "Cheapest — Sarvam voice + fast small model. Great for big cold lists.",
        "est_inr_per_min": 0.75,     # ≈ 0.50 STT + 0.10 LLM + 0.14 Bulbul-v2 TTS  (spec §0)
        "stt": {"provider": "sarvam",     "model": "saarika:v2.5",     "rate_key": "sarvam"},
        "llm": {"provider": "groq",       "model": "gpt-oss-20b",      "rate_key": "groq-gpt-oss-20b"},
        "tts": {"provider": "sarvam",     "model": "bulbul:v2",        "rate_key": "sarvam-bulbul-v2"},
        "voice": {"provider": "sarvam", "voice_id": "anushka"},
    },
    "standard": {
        "key": "standard",
        "name": "Standard",
        "quality": "Great",
        "blurb": "Balanced — richer Sarvam v3 voice + the smarter 70B model.",
        "est_inr_per_min": 1.3,      # ≈ 0.50 + 0.50 + 0.27 Bulbul-v3
        "stt": {"provider": "sarvam",     "model": "saarika:v2.5",     "rate_key": "sarvam"},
        "llm": {"provider": "groq",       "model": "llama-3.3-70b",    "rate_key": "groq-llama-3.3-70b"},
        "tts": {"provider": "sarvam",     "model": "bulbul:v3",        "rate_key": "sarvam-bulbul-v3"},
        "voice": {"provider": "sarvam", "voice_id": "manisha"},
    },
    "premium": {
        "key": "premium",
        "name": "Premium",
        "quality": "Studio",
        "blurb": "Studio-grade ElevenLabs Flash voice + the smartest model. ~2x Lean per minute.",
        "est_inr_per_min": 1.6,      # ≈ 0.50 + 0.70 + 0.38 EL Flash
        "stt": {"provider": "sarvam",     "model": "saarika:v2.5",     "rate_key": "sarvam"},
        "llm": {"provider": "groq",       "model": "llama-3.3-70b",    "rate_key": "groq-llama-3.3-70b"},
        "tts": {"provider": "elevenlabs", "model": "eleven_flash_v2_5","rate_key": "elevenlabs-flash-v2.5"},
        "voice": {"provider": "elevenlabs", "voice_id": ""},   # blank -> UI picks/keeps the campaign's EL voice
    },
}

TIER_ORDER = ["lean", "standard", "premium"]
DEFAULT_TIER = "lean"   # unset/legacy campaigns behave as today (Sarvam-equivalent default pipeline)


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


def tiers_payload() -> dict:
    """The full payload for GET /tiers — the single source the frontend consumes for BOTH the
    slider->triple mapping AND the cost-meter math."""
    return {
        "tiers": [TIERS[k] for k in TIER_ORDER],
        "order": list(TIER_ORDER),
        "default": DEFAULT_TIER,
        "rate_card": RATE_CARD,
        # convenience: spell out the ₹/min cost-math formula the UI implements (documentation only).
        "cost_formula": {
            "stt_inr_per_min": "rate_card.stt[stt.rate_key].inr_per_min",
            "llm_inr_per_min": "rate_card.llm[llm.rate_key].inr_per_mtok * assumptions.llm_tokens_per_min / 1_000_000",
            "tts_inr_per_min": "rate_card.tts[tts.rate_key].inr_per_1k * assumptions.tts_chars_per_min / 1000",
            "total_inr_per_min": "stt + llm + tts (+ telephony_inr_per_min, shown separately)",
            "projected_campaign_inr": "total_inr_per_min * est_avg_call_min * num_leads",
        },
        # PHASE note surfaced honestly in the UI.
        "phase_note": ("Voice selection within ElevenLabs is live on outbound today. Switching the "
                       "STT/LLM/TTS PROVIDER on the live outbound call (Lean=Sarvam vs Premium=ElevenLabs) "
                       "is pending Phase 2 (OB-PROV, founder approval)."),
        "ob_prov_pending": True,
    }
