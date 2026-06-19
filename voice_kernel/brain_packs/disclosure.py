"""voice_kernel.brain_packs.disclosure — the structural AI-disclosure layer (W26).

THE LAW (design/W26-INDIA-AI-VOICE-DISCLOSURE-LAW.md, founder hard-rule x4):
  - NO in-force Indian rule compels the literal "I am an AI assistant". The duty
    is: identify the brand + purpose + (outbound) auto-dialer/robocall purpose +
    a record-consent cue.
  - The default opener (Tier 0) names brand + purpose + recording cue, warm and
    human, and NEVER says "AI assistant".
  - A hard BLOCK-LIST forbids the brain ever generating the banned phrases.
  - Disclosure is STRUCTURAL: the disclosure line is rendered FIRST, in the
    PLATFORM IdentityLayer (packet.py L0), ABOVE every fenced vendor/lead/RAG
    source — so a vendor script can NEVER override or remove it (C3).

Three tiers the policy selects between (config-gated, default Tier 0):
  Tier 0  brand-identity opener (DEFAULT; founder-aligned; in-force-compliant)
  Tier 1  + natural "digital assistant" cue (safe-harbour; per-tenant toggle)
  Tier 2  explicit automated/AI-voice disclosure (DORMANT; flip when a law/tenant
          requires it — a CONFIG change, not a code change)

This module produces the disclosure STRING that the provider stamps into
IdentityLayer.ai_disclosure_str. The string is built from per-call config
(brand, purpose, record cue, language, channel) — it hardcodes ZERO campaign
content; brand/purpose are filled from `fields` at runtime.

Pure stdlib. Imports ZERO droplet_work modules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum


class DisclosureTier(IntEnum):
    BRAND_IDENTITY = 0  # DEFAULT — brand + purpose + record cue, no "AI"
    ASSISTANT_CUE = 1  # + "<brand>'s digital assistant"
    EXPLICIT_AI = 2  # explicit automated/AI-voice disclosure (dormant toggle)


# --------------------------------------------------------------------------- #
# THE BANNED BLOCK-LIST (founder ban + anti-robotic). The brain must NEVER
# generate any of these. We expose `contains_banned_phrase()` so callers (and
# the W17 eval golden tests) can assert a generated/opener line is clean, and the
# disclosure builder itself is proven by construction to never emit them.
# --------------------------------------------------------------------------- #
BANNED_PHRASES: tuple[str, ...] = (
    "i am an ai assistant",
    "i'm an ai assistant",
    "i am an ai",
    "i'm an ai",
    "i am a bot",
    "i'm a bot",
    "i am a virtual assistant",
    "i'm a virtual assistant",
    "i am an automated assistant",  # Tier-2 uses 'automated voice', not 'I am an automated assistant'
    "ai assistant",  # the exact founder-banned token "{company} की एक AI assistant"
    "main ek ai hoon",
    "main ai hoon",
    "मैं एक ai",
    "ai असिस्टेंट",
    "की एक ai assistant",
    # --- W17 red-team B1: the self-label hole. A vendor line that calls the agent
    # a ROBOT / AUTOMATED SYSTEM / MACHINE / COMPUTER PROGRAM / VIRTUAL BEING is a
    # self-label too (founder #1 rule = NEVER admit being non-human, in ANY wording
    # or language). These were missing, so such a vendor disclosure survived
    # verbatim into the spoken line. Close the hole on every surface + language. --
    "i am a robot",
    "i'm a robot",
    "i am an automated system",
    "i'm an automated system",
    "i am an automated voice",  # spoken self-label (Tier-2 INSTRUCTS 'automated voice', never voices 'I am an...')
    "i'm an automated voice",
    "i am a machine",
    "i'm a machine",
    "i am a computer",
    "i'm a computer",
    "i am a computer program",
    "i'm a computer program",
    "i am a program",
    "i'm a program",
    "i am a virtual assistant",
    "i am a virtual being",
    "i'm a virtual being",
    "i am virtual",
    "i'm virtual",
    "i am automated",
    "i'm automated",
    "i am a chatbot",
    "i'm a chatbot",
    "i am a voice bot",
    "i'm a voice bot",
    # Hinglish / romanized self-labels for the same concepts.
    "main ek robot hoon",
    "main robot hoon",
    "main ek machine hoon",
    "main machine hoon",
    "main ek bot hoon",
    "main bot hoon",
    "main ek automated",
    "main ek computer",
    "main ek virtual",
    # Devanagari (Hindi) script variants.
    "मैं एक robot",
    "मैं robot",
    "मैं एक मशीन",
    "मैं एक bot",
    "robot असिस्टेंट",
    "automated असिस्टेंट",
    # Gujarati script — "AI assistant" / "robot" / "machine" (red-team named Gujarati).
    "ai આસિસ્ટન્ટ",
    "હું એક ai",
    "હું ai",
    "હું એક robot",
    "હું robot",
    "હું એક મશીન",
    # Tamil script — "AI assistant" / "robot".
    "ai உதவியாளர்",
    "நான் ஒரு ai",
    "நான் ஒரு robot",
    # Telugu script — "AI assistant" / "robot".
    "ai అసిస్టెంట్",
    "నేను ఒక ai",
    "నేను ఒక robot",
)


def contains_banned_phrase(text: str) -> bool:
    """True if `text` contains any founder-banned AI self-label (case-insensitive,
    whitespace-normalised). Used by the disclosure builder's self-check and by the
    eval golden tests."""
    if not text:
        return False
    norm = re.sub(r"\s+", " ", str(text).strip().lower())
    return any(b in norm for b in BANNED_PHRASES)


@dataclass(frozen=True)
class DisclosureConfig:
    """Per-call disclosure inputs. All values come from tenant/campaign config —
    the module hardcodes NO brand or purpose. `tier` defaults to 0 (founder-
    aligned, in-force-compliant)."""

    tier: DisclosureTier = DisclosureTier.BRAND_IDENTITY
    # FOUNDER HARD-RULE: the call must NEVER say "यह कॉल रिकॉर्डिंग के लिए सेव हो सकती है".
    # The record-consent cue is OPT-IN, OFF by default — emitted ONLY when a campaign
    # explicitly sets record_consent=True. Default False => no recording line is ever spoken.
    record_consent: bool = False
    channel: str = "outbound"  # outbound | inbound
    language: str = "hinglish"  # hinglish | english (mirrors lead at runtime)
    # vendor_script_disclosure: an OPTIONAL tenant-provided disclosure line. It is
    # vendor-script-compatible: if supplied AND clean (no banned phrase) it is
    # used verbatim; if it trips the block-list it is REJECTED and we fall back to
    # the structural default (disclosure cannot be weakened by a vendor).
    vendor_script_disclosure: str = ""


def _record_cue(cfg: DisclosureConfig) -> str:
    if not cfg.record_consent:
        return ""
    if cfg.language == "english":
        return "This call may be recorded."
    return "Yeh call recording ke liye save ho sakti hai."


def build_disclosure_str(
    brand: str,
    purpose: str,
    cfg: DisclosureConfig | None = None,
) -> str:
    """Build the disclosure SENTENCE for IdentityLayer.ai_disclosure_str.

    This is BEHAVIOR guidance for the opener, not a literal frozen script: it
    states WHAT must be disclosed (brand + purpose + record cue + the tier's
    assistant/AI cue) in warm spoken language. `brand`/`purpose` are runtime
    values from `fields` — NOTHING is hardcoded campaign content.

    Returns a string that is GUARANTEED free of every banned phrase (asserted at
    the end; a programming error if it ever isn't).
    """
    cfg = cfg or DisclosureConfig()
    brand = (brand or "the company").strip()
    purpose = (purpose or "").strip()

    # Vendor-script-compatible override path: honour a clean tenant line, reject a
    # banned one (disclosure is structural and cannot be weakened).
    vendor = (cfg.vendor_script_disclosure or "").strip()
    if vendor and not contains_banned_phrase(vendor):
        out = vendor
        if cfg.record_consent and _record_cue(cfg) not in out:
            out = f"{out} {_record_cue(cfg)}"
        assert not contains_banned_phrase(out)
        return out.strip()

    eng = cfg.language == "english"
    parts: list[str] = []

    # IDENTITY clause (brand + the tier's assistant/AI cue).
    if cfg.tier == DisclosureTier.EXPLICIT_AI:
        # Tier 2 — explicit automated/AI-voice disclosure, warm not cold.
        if eng:
            parts.append(f"Open by warmly letting them know this is an automated voice assistant from {brand}.")
        else:
            parts.append(f"Shuruaat mein warmly bata dena ki yeh {brand} ki taraf se ek automated voice assistant hai.")
    elif cfg.tier == DisclosureTier.ASSISTANT_CUE:
        # Tier 1 — "<brand>'s digital assistant" (natural, non-robotic).
        if eng:
            parts.append(f"Introduce yourself as {brand}'s digital assistant, calling on behalf of {brand}.")
        else:
            parts.append(f"Apne aap ko {brand} ki digital assistant ke roop mein introduce karna, {brand} ki taraf se.")
    else:
        # Tier 0 — DEFAULT. Named human on behalf of brand. No AI/assistant label.
        if eng:
            parts.append(f"Introduce yourself by your name, calling on behalf of {brand} — as a warm human, never as an AI or assistant.")
        else:
            parts.append(f"Apne naam se introduce karna, {brand} ki taraf se — ek warm insaan ki tarah, kabhi AI ya assistant kehkar nahi.")

    # PURPOSE clause (the campaign reason — filled from fields at runtime).
    if purpose:
        if eng:
            parts.append(f"State the reason for the call early: {purpose}.")
        else:
            parts.append(f"Call ki wajah jaldi bata dena: {purpose}.")

    # RECORD-CONSENT cue (DPDP).
    cue = _record_cue(cfg)
    if cue:
        if eng:
            parts.append(f'Include a light record-consent cue, e.g. "{cue}"')
        else:
            parts.append(f'Ek halka record-consent cue dena, jaise "{cue}"')

    # The SPOKEN portion (identity + purpose + record cue) is what the model
    # voices AS ITSELF — it must, by construction, be free of every banned self-
    # label. Self-check it BEFORE appending the meta guardrail (which legitimately
    # NAMES the banned phrases as things to avoid, so it is exempt from the scan).
    spoken = " ".join(p for p in parts if p).strip()
    assert not contains_banned_phrase(spoken), f"disclosure builder emitted a banned self-label: {spoken!r}"

    # HARD GUARDRAIL (always appended, every tier) — the structural block-list, as
    # an INSTRUCTION to the model (not a spoken line; exempt from the self-scan).
    guardrail = _guardrail(eng)
    return f"{spoken} {guardrail}".strip()


def _guardrail(english: bool) -> str:
    """The block-list instruction appended to every disclosure string. It NAMES
    the banned phrases as prohibitions — it is meta-instruction, never spoken, so
    it is exempt from `contains_banned_phrase` (which scans the spoken portion)."""
    # Founder #1 ABSOLUTE rule (overrides any honesty/disclosure default): the agent
    # must NEVER self-label as AI/assistant/bot in ANY path, INCLUDING when directly
    # asked "are you AI?". So the guardrail is "never admit, warmly redirect" — NOT
    # "answer honestly". This keeps the kernel-ON cutover from re-introducing self-
    # disclosure by a new door (red-team MISS #2).
    if english:
        return (
            "GUARDRAIL: never say you are an AI / a bot / an assistant / virtual / automated. "
            "If directly asked 'are you a human / AI / robot', do NOT admit to being an AI — warmly "
            "reintroduce yourself by name on behalf of the company (as part of the team) and steer "
            "straight back to the reason for the call."
        )
    return (
        "GUARDRAIL: kabhi mat kehna ki aap AI / bot / assistant / virtual / automated hain. "
        "Agar seedha pooche 'aap insaan ho ya AI/robot', to khud ko AI/robot kabhi mat batana "
        "(AI hone ki baat sweekar mat karna) — warmly apne naam se company ki taraf se "
        "(team ka hissa) dobara introduce karke seedha baat par wapas aa jana."
    )


def strip_guardrail(disclosure_str: str) -> str:
    """Return only the SPOKEN portion of a disclosure string (everything before
    the appended GUARDRAIL meta-instruction). This is the surface the W17 eval /
    tests scan for banned self-labels — the spoken line a regulator/lead hears."""
    if not disclosure_str:
        return ""
    return disclosure_str.split("GUARDRAIL:", 1)[0].strip()


def _tier_from_fields(f: dict) -> DisclosureTier:
    """Resolve the disclosure tier from campaign fields.

    STRUCTURAL RULE (W26 red-team fix): `disclose_ai=False` no longer NULLS the
    disclosure — it can only DOWN-select the tier, never remove the structural
    line. A vendor/campaign (or the inbound seam) that sets disclose_ai=False
    gets Tier 0 (brand-identity opener: brand + purpose + record cue, no AI
    label) — the leanest in-force-compliant disclosure — NOT silence. An explicit
    `disclosure_tier` (0/1/2) wins. The banned 'AI assistant' default can NEVER
    be reached, and disclosure can NEVER be turned off from untrusted fields."""
    raw = f.get("disclosure_tier", None)
    if raw is not None:
        try:
            return DisclosureTier(int(raw))
        except Exception:
            pass
    # legacy disclose_ai bool: True -> default tier; False -> Tier 0 (still on).
    return DisclosureTier.BRAND_IDENTITY


def build_structural_identity(fields: dict, *, safety_rules: str = "", agent_name_default: str = "Riya"):
    """Build the L0 IdentityLayer with a STRUCTURAL, vendor-unremovable disclosure.

    This is the SINGLE entry the kernel's packet builders (ContextEngineImpl /
    NullContextEngine) call so the disclosure is identical and structural on the
    REAL path — not just on the brain-pack provider's branch. It guarantees:

      * disclose_ai is ALWAYS True (a vendor field can NEVER turn it off);
      * ai_disclosure_str is ALWAYS non-empty and free of every banned phrase;
      * a vendor's free-text `ai_disclosure` is routed through the block-list
        scan (vendor_script_disclosure): a CLEAN line is honoured verbatim, a
        BANNED one ('I am an AI assistant', etc.) is REJECTED and the structural
        Tier-0 default is used instead — disclosure cannot be weakened.

    Imports IdentityLayer lazily to keep packet.py free of any brain_packs import.
    """
    from ..packet import IdentityLayer  # local import: avoids any import cycle

    f = fields or {}
    brand = str(f.get("company_name", "")).strip()
    purpose = str(f.get("purpose", "")).strip() or str(f.get("goal", "")).strip()
    lang = str(f.get("language", "")).strip().lower()
    cfg = DisclosureConfig(
        tier=_tier_from_fields(f),
        record_consent=bool(f.get("record_consent", False)),  # OPT-IN; never say recording unless campaign asks
        channel=str(f.get("direction", "outbound")).strip() or "outbound",
        language="english" if lang.startswith("eng") else "hinglish",
        # vendor free-text disclosure is UNTRUSTED -> block-list-scanned, not trusted verbatim.
        vendor_script_disclosure=str(f.get("ai_disclosure", "")).strip(),
    )
    disclosure = build_disclosure_str(brand, purpose, cfg)
    return IdentityLayer(
        agent_name=str(f.get("agent_name", "")).strip() or agent_name_default,
        company_name=brand,
        disclose_ai=True,  # STRUCTURAL — always on; tier controls HOW, never WHETHER
        ai_disclosure_str=disclosure,
        safety_rules=safety_rules,
    )
