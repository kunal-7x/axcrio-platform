"""voice_ops.compliance.disclosure — the warm Tier-0 disclosure_ctx (W26 §5).

Resolves the founder's "never say I am an AI assistant" vs the legal disclosure duty
into a CONFIGURABLE product feature: a warm, branded one-line opener that names the
BRAND + PURPOSE + (when recording) a record cue, and NEVER contains the banned phrase.
This module builds the `DisclosureCtx` that `preflight` returns; the brain (W2) emits it
FIRST as control-flow.

Three tiers (config-driven, per-tenant/jurisdiction, default-safe):
  Tier 0 (DEFAULT)  brand identity + purpose + record cue. No banned phrase. In-force
                    compliant + founder-aligned. SHIP THIS.
  Tier 1            adds a natural "<Brand>'s digital assistant" safe-harbour cue
                    (recommended toggle for BFSI/regulated tenants).
  Tier 2 (dormant)  explicit "automated voice assistant from <Brand>" — flip the day
                    TRAI's proposed AI-disclosure mandate lands (config, not code).

CRITICAL GUARANTEE: the produced line is run through `assert_no_banned_phrase` so a
mis-templated brand/product can NEVER smuggle the banned "AI assistant / I'm a bot /
virtual assistant / main ek AI hoon / मैं एक AI हूँ" into the opener. The block-list is
the single source of truth the brain's generation-time filter (W2) also imports.

PURE: stdlib only; NEVER raises (a banned-phrase slip raises ValueError ONLY in the
explicit assert helper used by tests; the builder itself sanitises and falls back to a
safe template).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# The hard block-list — the founder's ban + anti-robotic register. The brain's
# generation-time filter (W2) imports THIS list so there is one source of truth.
BANNED_PHRASES: List[str] = [
    "ai assistant",
    "i am an ai",
    "i'm an ai",
    "i am a bot",
    "i'm a bot",
    "virtual assistant",
    "main ek ai",
    "मैं एक ai",
    "मैं एक एआई",
    "automated bot",
]

_BANNED_RE = re.compile("|".join(re.escape(p) for p in BANNED_PHRASES), re.IGNORECASE)


def contains_banned_phrase(text: str) -> bool:
    return bool(_BANNED_RE.search(text or ""))


def assert_no_banned_phrase(text: str) -> str:
    """Raise ValueError if `text` contains a banned phrase; else return it. Used by
    tests + the W2 generation-time filter to STRUCTURALLY guarantee the ban."""
    if contains_banned_phrase(text):
        raise ValueError(f"banned disclosure phrase in: {text!r}")
    return text


@dataclass(frozen=True)
class DisclosureCtx:
    """The structured disclosure context the brain emits FIRST (never a hardcoded string
    in agent.py). `say_*` are the rendered openers per language; `tier`/`record_cue`/
    `brand`/`purpose` let the brain compose its own variant if needed — but `require`
    means the brain MUST open with a compliant identity+purpose line."""
    tier: int
    brand: str
    purpose: str
    record_cue: bool
    jurisdiction: str = "IN"
    channel: str = "voice"
    require: bool = True
    say_en: str = ""
    say_hinglish: str = ""
    say_hindi: str = ""
    banned_phrases: List[str] = field(default_factory=lambda: list(BANNED_PHRASES))

    def as_metadata(self) -> Dict[str, object]:
        """Flatten to the metadata dict the seam injects into md_obj before
        json.dumps (caller.py:2941). PII-light, brain-consumable."""
        return {
            "tier": self.tier, "brand": self.brand, "purpose": self.purpose,
            "record_cue": self.record_cue, "jurisdiction": self.jurisdiction,
            "channel": self.channel, "require_disclosure": self.require,
            "say_en": self.say_en, "say_hinglish": self.say_hinglish,
            "say_hindi": self.say_hindi,
        }


_REC_EN = " Quick heads-up, this call may be recorded."
_REC_HINGLISH = " Ye call record ho sakti hai."
_REC_HINDI = " यह कॉल रिकॉर्ड हो सकती है।"


def _t0(brand: str, product: str, rec: bool):
    en = (f"Hi, this is Riya from {brand} — I'm reaching out about the {product} you looked at."
          + (_REC_EN if rec else "") + " Got a quick minute?")
    hi_lish = (f"Namaste! Main Riya, {brand} ki taraf se — aapne jo {product} mein interest "
               f"dikhaya tha usi ke baare mein baat karni thi." + (_REC_HINGLISH if rec else "")
               + " Bas do minute?")
    hindi = (f"नमस्ते! मैं रिया, {brand} की ओर से बात कर रही हूँ — {product} के बारे में थोड़ी बात "
             f"करनी थी।" + (_REC_HINDI if rec else "") + " दो मिनट हैं आपके पास?")
    return en, hi_lish, hindi


def _t1(brand: str, product: str, rec: bool):
    en = (f"Hi, you're speaking with {brand}'s digital assistant, Riya — calling about the "
          f"{product} you enquired about." + (_REC_EN if rec else "") + " Do you have a quick minute?")
    hi_lish = (f"Namaste! Main Riya, {brand} ki digital assistant — {product} ke baare mein baat "
               f"karni thi" + ("," + _REC_HINGLISH if rec else "") + " Sirf ek minute?")
    hindi = (f"नमस्ते! मैं रिया, {brand} की डिजिटल असिस्टेंट — {product} के बारे में बात करनी थी।"
             + (_REC_HINDI if rec else "") + " एक मिनट?")
    return en, hi_lish, hindi


def _t2(brand: str, product: str, rec: bool):
    en = (f"Hi — quick note, this is an automated voice assistant from {brand}"
          + (", and it may be recorded." if rec else ".")
          + f" I'll be quick — is now an okay time to talk about {product}?")
    hi_lish = (f"Namaste! Ye {brand} ki ek automated voice assistant hai"
               + (" aur call record ho sakti hai" if rec else "")
               + f" — bas ek minute {product} ke baare mein?")
    hindi = (f"नमस्ते! यह {brand} की एक automated voice assistant है"
             + (" और कॉल रिकॉर्ड हो सकती है" if rec else "")
             + f" — {product} के बारे में बस एक मिनट?")
    return en, hi_lish, hindi


_BUILDERS = {0: _t0, 1: _t1, 2: _t2}


def build_disclosure_ctx(*, brand: str = "", purpose: str = "", product: str = "",
                         tier: int = 0, record_cue: bool = True,
                         jurisdiction: str = "IN", channel: str = "voice") -> DisclosureCtx:
    """Build the warm disclosure context. `purpose`/`product` are interchangeable
    (the thing the lead enquired about). Renders all three languages, sanitises the
    brand/product so a banned phrase can't be smuggled in, and falls back to Tier 0 for
    an unknown tier. NEVER raises — a banned-phrase slip is SCRUBBED, not surfaced."""
    b = (brand or "our team").strip()
    p = (product or purpose or "your enquiry").strip()
    # defensive: never let a caller's brand/product smuggle the banned register in.
    if contains_banned_phrase(b):
        b = "our team"
    if contains_banned_phrase(p):
        p = "your enquiry"
    t = tier if tier in _BUILDERS else 0
    en, hi_lish, hindi = _BUILDERS[t](b, p, bool(record_cue))

    # final structural guarantee: scrub (not raise) if a template ever regressed.
    def _safe(s: str) -> str:
        return _BANNED_RE.sub("assistant", s) if contains_banned_phrase(s) else s

    return DisclosureCtx(
        tier=t, brand=b, purpose=p, record_cue=bool(record_cue),
        jurisdiction=jurisdiction, channel=channel, require=True,
        say_en=_safe(en), say_hinglish=_safe(hi_lish), say_hindi=_safe(hindi),
    )
