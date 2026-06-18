"""voice_kernel.brain_packs.delivery — the human-DELIVERY directives (W-VOICE-HEART).

The founder's outbound complaints were not about WHAT the brain says but HOW it
delivers it, and these are PROMPT rules (not TTS knobs):

  * #1/#5  double greeting + double intro -> exactly ONE greeting; after the opener
           turn, NEVER re-greet or repeat the intro (the kernel owns the single
           greeting; the worker's spoken opener is suppressed on KERNEL_OUTBOUND).
  * #3a    the lead's name said again and again every line -> say the name AT MOST
           once or twice in the WHOLE call, naturally, never as a per-turn prefix.
  * #3b    the name too LOUD / too fast -> say it at the SAME normal volume + pace
           as every other word; no exclamation, ALL-CAPS, or emphasis markup on the
           name (loud-on-name is a TEXT->prosody artifact, killed in the prompt).

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


def name_directive() -> str:
    """How to use the lead's name (sparingly + at constant volume). Behavioral —
    contains NO actual name; the runtime lead_name is referenced abstractly."""
    return (
        f"{NAME_DIRECTIVE_CUE} use the caller's name AT MOST once or twice in the WHOLE call "
        "(naturally, e.g. once at the greeting to confirm identity) — NEVER prefix every turn "
        "with their name and never repeat it line after line. Say the name at the SAME normal "
        f"volume and pace as the rest of the sentence: {NO_EMPHASIS_CUE} — no exclamation, no "
        "ALL-CAPS, no drawn-out or louder/faster delivery on the name token."
    )


def single_greeting_directive() -> str:
    """Exactly ONE greeting for the whole call; after the opening turn never re-greet
    or repeat the self-intro. This is the PROMPT-side single-greeting guarantee that
    rides ALONGSIDE the worker-opener suppression (Hunk H) — so even if the model is
    nudged to open, it greets ONCE and then only advances the conversation. Closes the
    red-team's 'kernel prefix has no opener-already-said' gap directly."""
    return (
        f"{SINGLE_GREETING_CUE} greet the caller EXACTLY ONCE, in your opening turn "
        "(time-of-day wish -> greetings from the company -> confirm you're speaking with the "
        "right person -> WAIT for their reply -> reason for calling + permission). After that "
        "opening turn, do NOT greet again, do NOT say 'namaste/hello' again, and do NOT repeat "
        "your name/company/intro — just respond and move the conversation forward."
    )


def delivery_directive() -> str:
    """The combined single-greeting + name-use delivery block for the prompt."""
    return f"{single_greeting_directive()} {name_directive()}"


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
