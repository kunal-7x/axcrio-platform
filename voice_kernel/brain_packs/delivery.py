"""voice_kernel.brain_packs.delivery — the human-DELIVERY directives (W-VOICE-HEART).

The founder's outbound complaints were not about WHAT the brain says but HOW it
delivers it, and these are PROMPT rules (not TTS knobs):

  * #1/#5  double greeting + double intro -> exactly ONE greeting; after the opener
           turn, NEVER re-greet or repeat the intro (the kernel owns the single
           greeting; the worker's spoken opener is suppressed on KERNEL_OUTBOUND).
  * STYLE  the greeting is a time-aware English-Hindi wish ("good morning / good
           afternoon / good evening, hello sir") — NEVER 'namaste'/'namaskar' — and
           confirms identity BY THE LEAD'S REAL NAME ("क्या मेरी बात {name} से हो रही है?"),
           never the generic 'सही व्यक्ति'.
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
        "(naturally, e.g. once at the greeting to confirm identity) — NEVER prefix every turn "
        "with their name and never repeat it line after line. Say the name at the SAME normal, "
        f"calm volume and pace as the rest of the sentence: {NO_EMPHASIS_CUE} — no exclamation "
        "mark, no ALL-CAPS, no drawn-out or louder/faster delivery on the name token. The SAME "
        "no-shout rule applies to EVERY word: never write a whole Hindi/Hinglish word in CAPITALS "
        "and never put an exclamation mark ('!') on a filler or acknowledgement (e.g. write "
        "'ठीक है', NEVER 'ठीक है!' or ' बढ़िया!') — keep all fillers/acknowledgements soft and even."
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
        f"{SINGLE_GREETING_CUE} greet the caller EXACTLY ONCE, in your opening turn, like this: "
        "open with a warm time-of-day wish in English-Hindi mix — \"good morning\" before noon, "
        "\"good afternoon\" till evening, else \"good evening\", followed by \"hello sir\" "
        "(or \"hello ma'am\") — NEVER say 'namaste' or 'namaskar'. Then briefly say who you are "
        f"and the company, {confirm} -> WAIT for their reply -> then the reason for calling + "
        "permission. After that opening turn, do NOT greet again, do NOT say any greeting "
        "('namaste'/'hello'/'good morning') again, and do NOT repeat your name/company/intro — "
        "just respond to what they said and move the conversation forward. If the conversation "
        "has already started, you have ALREADY greeted: never restate the intro or greeting."
    )


def delivery_directive(lead_name: str = "") -> str:
    """The combined single-greeting + name-use delivery block for the prompt. Threads
    the runtime `lead_name` so the greeting confirms identity by the real name."""
    return f"{single_greeting_directive(lead_name)} {name_directive(lead_name)}"


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
    "name_directive", "single_greeting_directive", "delivery_directive",
    "has_name_sparingly_rule", "has_single_greeting_rule", "text_emphasizes_name",
]
