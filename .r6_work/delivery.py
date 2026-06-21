"""voice_kernel.brain_packs.delivery — the human-DELIVERY directives (W-VOICE-HEART).

The founder's outbound complaints were not about WHAT the brain says but HOW it
delivers it, and these are PROMPT rules (not TTS knobs):

  * #1/#5  double greeting + double intro -> exactly ONE greeting; after the opener
           turn, NEVER re-greet or repeat the intro (the kernel owns the single
           greeting; the worker's spoken opener is suppressed on KERNEL_OUTBOUND).
  * STYLE  the greeting wish is ENGLISH ("good morning / good afternoon / good
           evening") + a soft "hello sir/ji" — pure-Hindi greetings are BANNED
           ('सुप्रभात'/'शुभ रात्रि'/'नमस्ते'/'नमस्कार') — and identity is confirmed BY
           THE LEAD'S REAL NAME ("क्या मेरी बात {name} से हो रही है?"), never the generic
           'सही व्यक्ति'.
  * CLOSE  the goodbye is a warm, natural LLM line ("thank you for your time, good
           day") — the word 'अलविदा' (Alvida) is BANNED entirely.
  * NAMES  company/product/English proper nouns stay in their original Latin/English
           spelling (e.g. 'Agaro', 'Godrej') — never transliterated to Devanagari or
           garbled.
  * #3a    the lead's name said again and again every line -> say the name AT MOST
           once or twice in the WHOLE call, naturally, never as a per-turn prefix.
  * #3b    the name too LOUD / too fast -> say it at the SAME normal volume + pace
           as every other word; no exclamation, ALL-CAPS, or emphasis markup on the
           name (loud-on-name is a TEXT->prosody artifact, killed in the prompt). The
           same no-shout rule covers fillers/acknowledgements: 'ठीक है' never 'ठीक है!',
           never an ALL-CAPS Hindi word.

These render as ONE compact directive block appended to the L1 objective layer, so
they ship on the kernel-ON outbound path (and inbound). They are pure BEHAVIOR text
— NO campaign content, NO hardcoded name. Inert until KERNEL_OUTBOUND/INBOUND flips.

Pure stdlib. Imports ZERO droplet_work modules.
"""
from __future__ import annotations

import re

# The token the gates / replay look for to prove the rule shipped.
NAME_DIRECTIVE_CUE = "NAME USE:"
SINGLE_GREETING_CUE = "SINGLE GREETING:"
NO_EMPHASIS_CUE = "no emphasis"
CLOSING_DIRECTIVE_CUE = "CLOSING:"
ENGLISH_NAMES_CUE = "ENGLISH NAMES:"


def name_directive(lead_name: str = "") -> str:
    """How to use the lead's name (sparingly + at constant volume, NEVER shouted).
    `lead_name` is the runtime caller name (may be empty); when present we instruct
    the model to confirm identity BY NAME, never with a generic 'sahi vyakti'."""
    name = (lead_name or "").strip()
    name_clause = (
        f"The caller's name is '{name}'. "
        if name else "If you know the caller's name, "
    )
    return (
        f"{NAME_DIRECTIVE_CUE} {name_clause}use it AT MOST once or twice in the WHOLE call "
        "(e.g. once at the greeting to confirm identity) — never prefix every turn with their "
        f"name. Say the name at the SAME calm volume/pace as the rest: {NO_EMPHASIS_CUE} — no "
        "exclamation mark, no ALL-CAPS, no louder/faster delivery on the name. SAME no-shout "
        "rule for EVERY word: never write a whole Hindi/Hinglish word in CAPITALS and never put "
        "'!' on a filler/acknowledgement (write 'ठीक है', NEVER 'ठीक है!') — keep them soft and even."
    )


def single_greeting_directive(lead_name: str = "") -> str:
    """Exactly ONE greeting for the whole call; after the opening turn never re-greet
    or repeat the self-intro. This is the PROMPT-side single-greeting guarantee that
    rides ALONGSIDE the worker-opener suppression (Hunk H) — so even if the model is
    nudged to open, it greets ONCE and then only advances the conversation. Closes the
    red-team's 'kernel prefix has no opener-already-said' gap directly.

    GREETING STYLE (founder hard-rule): the time-of-day wish is the ENGLISH-Hindi mix
    "good morning / good afternoon / good evening, hello sir" (chosen by the real IST
    time of day) — NEVER 'namaste'/'namaskar'. Identity is confirmed BY NAME when the
    caller's name is known: "क्या मेरी बात {name} से हो रही है?" — never the generic
    "क्या मैं सही व्यक्ति से बात कर रहा/रही हूँ"."""
    name = (lead_name or "").strip()
    confirm = (
        f"confirm you are speaking with them BY NAME — say exactly "
        f"\"क्या मेरी बात {name} से हो रही है?\" (use the real name '{name}', "
        f"NEVER the generic 'सही व्यक्ति'/'right person')"
        if name else
        "confirm you are speaking with the right person by their name if you have it"
    )
    return (
        f"{SINGLE_GREETING_CUE} greet EXACTLY ONCE, in the opening turn: a warm time-of-day wish "
        "in plain ENGLISH words (\"good morning\" before noon, \"good afternoon\" till evening, "
        "else \"good evening\") + a soft \"hello sir\"/\"hello ji\"/\"hello ma'am\". The wish "
        "itself MUST be the English phrase (a little Hindi-English mix around it is fine). "
        "BANNED as the greeting (never say/write): 'नमस्ते'/'namaste', 'नमस्कार'/'namaskar', "
        "'सुप्रभात', 'शुभ रात्रि'/'shubh ratri'. "
        f"Then briefly say who you are + the company, {confirm} -> WAIT for their reply -> then "
        "the reason for calling + permission. This is an OUTBOUND call — YOU called the caller, "
        "they did NOT call you — so frame the reason in the first person (\"मैंने आपको <product> "
        "के बारे में call किया है\" / \"आपने <product> में interest dikhaya tha इसलिए call कर रही/रहा "
        "हूँ\"); NEVER say \"आपने call किया था\" / \"you contacted us\" (that is inbound framing and is "
        "wrong). After that opening turn NEVER greet again and NEVER repeat your name/company/intro "
        "— you have ALREADY greeted; just answer what they said and move the conversation forward."
    )


def closing_directive() -> str:
    """How to END the call — a PRINCIPLE, never a ready-to-speak line (R5-P1.2).

    The old version baked a verbatim farewell EXAMPLE ('...आपका दिन अच्छा रहे' /
    'thank you for your time, have a great day'). agent.py's `_FAREWELL_MARKERS`
    matched that exact phrasing and converted it into a REAL hangup — so the brain
    could be nudged into speaking the example string and ending the call mid-
    engagement. We now state the close as a PRINCIPLE only: close ONLY when the
    outcome is clearly resolved (a next step agreed, or the caller declined / asked
    to stop), with ONE short warm self-authored line in the caller's language — and
    we give NO line to copy. The banned word 'अलविदा' (heavy/formal farewell) stays
    banned. The "when to close" gate lives in the L0 engagement block; this only
    governs HOW the close sounds when it is genuinely time."""
    return (
        f"{CLOSING_DIRECTIVE_CUE} when it is genuinely time to end (see the ENGAGEMENT rule for "
        "WHEN), confirm the agreed next step in a line, then sign off with ONE short warm line in "
        "the caller's language, thanking them in your OWN words — do NOT recite a fixed/canned "
        "phrase and do NOT repeat the intro. BANNED closing word: NEVER say 'अलविदा' / 'alvida' "
        "(heavy/formal). No second pitch or new question after the close."
    )


def english_names_directive() -> str:
    """Company / product / brand / English proper nouns are spoken in their ORIGINAL
    Latin/English form — never transliterated to Devanagari, never mangled into garbled
    or Cyrillic look-alikes. Generalizes the Agaro fix to ALL English proper nouns."""
    return (
        f"{ENGLISH_NAMES_CUE} write every company/product/brand and English proper noun in its "
        "ORIGINAL English spelling (e.g. 'Agaro', 'Godrej', 'WhatsApp') — never transliterate to "
        "Devanagari (never 'गोदरेज') and never garble it. Only the surrounding Hindi words are in "
        "Devanagari; the English names stay in clean English letters so they are spoken correctly."
    )


DISCUSSION_DIRECTIVE_CUE = "DISCUSSION:"


def discussion_directive() -> str:
    """R6 (P1 mirror of the P0 SHARED_RULES additions): how the agent NUMBERS, sparks
    CURIOSITY, and stays grounded in REAL campaign facts only. Pure behavior text — no
    campaign content, no hardcoded data. Ships on the kernel-ON outbound/inbound path."""
    return (
        f"{DISCUSSION_DIRECTIVE_CUE} NUMBERS — speak every amount/number in natural spoken "
        "words, never digits/symbols/abbreviations: say 'दो सौ rupees', 'पचासी लाख rupees', "
        "'एक करोड़ बत्तीस लाख rupees', 'तीन BHK' — NEVER 'RS'/'Rs.'/'₹'/'200'/'85,00,000'/'1.32'/'Cr'/'L'/'3BHK'. "
        "Break big amounts naturally ('करीब एक करोड़ नब्बे लाख rupees'). "
        "CURIOSITY — frame interest-building questions to make the caller WANT more: 'क्या आप इस "
        "project के बारे में और जानना चाहते हैं?' / '…thoda aur batau?' — never a flat 'क्या आपको "
        "जानना है?'; end each discussion beat with a tiny curiosity hook. "
        "REAL FACTS ONLY — speak ONLY facts present in the campaign data; never invent a price, "
        "location, configuration, offer or detail. If you don't have it, say you'll confirm with "
        "the team or send it on WhatsApp — never a made-up number/fact."
    )


def has_discussion_rule(prompt: str) -> bool:
    """True iff the rendered prompt carries the numbers/curiosity/real-facts rule."""
    return DISCUSSION_DIRECTIVE_CUE.lower() in (prompt or "").lower()


def delivery_directive(lead_name: str = "") -> str:
    """The combined single-greeting + name-use + closing + english-names + discussion delivery
    block for the prompt. Threads the runtime `lead_name` so the greeting confirms identity by name."""
    return (
        f"{single_greeting_directive(lead_name)} {name_directive(lead_name)} "
        f"{closing_directive()} {english_names_directive()} {discussion_directive()}"
    )


# --------------------------------------------------------------------------- #
# Detectors used by the W17 gates / replay (assert the rules are LIVE in the
# rendered prompt, and FLAG a regressed prompt that violates them).
# --------------------------------------------------------------------------- #
def has_name_sparingly_rule(prompt: str) -> bool:
    """True iff the rendered prompt carries the name-sparingly + no-emphasis rule."""
    low = (prompt or "").lower()
    return NAME_DIRECTIVE_CUE.lower() in low and NO_EMPHASIS_CUE in low


def has_single_greeting_rule(prompt: str) -> bool:
    """True iff the rendered prompt carries the single-greeting / no-re-greet rule."""
    return SINGLE_GREETING_CUE.lower() in (prompt or "").lower()


# A literal name token written with shouting/emphasis markup — the TEXT artifact
# that makes flash_v2_5 render the name louder/faster. The brain must never emit it.
_EMPHASIS_ON_NAME = re.compile(
    r"(?:[A-Z][a-z]+ ?){0,2}[A-Z]{3,}!"        # ALL-CAPS word followed by '!'
    r"|\b[A-Z][a-z]+!!+"                          # Name followed by 2+ '!'
)


def text_emphasizes_name(text: str, name: str = "") -> bool:
    """Heuristic: does a SPOKEN line shout/emphasize a name token (ALL-CAPS or
    multiple exclamation marks on the name)? Used by the BAD-transcript replay to
    prove the loud-on-name artifact is gone on the new path."""
    if not text:
        return False
    if name:
        n = re.escape(name.strip())
        if re.search(rf"\b{n.upper()}\b", text) and name.strip() and name.strip() != name.strip().upper():
            return True  # the name written in ALL-CAPS (shout)
        if re.search(rf"\b{n}\b!{{2,}}", text, re.IGNORECASE):
            return True  # name!! / name!!!
    return bool(_EMPHASIS_ON_NAME.search(text))


__all__ = [
    "NAME_DIRECTIVE_CUE", "SINGLE_GREETING_CUE", "NO_EMPHASIS_CUE",
    "CLOSING_DIRECTIVE_CUE", "ENGLISH_NAMES_CUE", "DISCUSSION_DIRECTIVE_CUE",
    "name_directive", "single_greeting_directive", "closing_directive",
    "english_names_directive", "discussion_directive", "delivery_directive",
    "has_name_sparingly_rule", "has_single_greeting_rule", "has_discussion_rule",
    "text_emphasizes_name",
]
