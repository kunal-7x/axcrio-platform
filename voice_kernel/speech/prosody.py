"""voice_kernel.speech.prosody — adaptive, SPARSE punctuation & fillers, and the
per-provider render template.

Founder complaint (d): fillers/punctuation must be ADAPTIVE (not hardcoded). Per
the research + the on-disk W6 playbook, Sarvam Bulbul maps punctuation to prosody:
  comma      -> short pause
  full-stop  -> medium pause
  ellipsis … -> hesitation
  line-break -> breath
So we shape punctuation rather than injecting SSML. Fillers ("haan", "achha",
"toh") are added SPARSELY (at most one per few sentences) and NEVER inside a
price / phone / booking / compliance line (complaint (d) + (c): a misheard digit
in a price line loses money / breaks trust).

Founder complaint (e) downstream: the render template is keyed off the SELECTED
provider so Sarvam gets the Devanagari+Latin code-mix shape (+ mulaw-8k friendly
short lines) and ElevenLabs gets the concise telephony shape.

Pure, deterministic, stdlib-only, fail-open.
"""
from __future__ import annotations

import os
import re

# sparse fillers — a real telecaller's verbal nods. Used at MOST once per
# `_FILLER_EVERY` sentences, and only on non-sensitive lines.
_FILLERS_HINGLISH = ("haan", "achha", "toh", "dekhiye")
_FILLERS_EN = ("right", "okay", "so", "see")

_FILLER_EVERY = 3  # at most one filler per 3 sentences


def _fillers_enabled() -> bool:
    """W-VOICE-FIX (BUG4): filler injection is OFF by DEFAULT — the founder wants
    NEUTRAL/consistent delivery, not over-varied "sound human" rhythm (injected
    fillers create an uneven perceived pace/loudness). Punctuation-shaped pauses
    stay on; only the prepended verbal-nod fillers are gated. Set VOICE_FILLERS=1
    to re-enable (e.g. for an inbound persona tuned to want them)."""
    return os.getenv("VOICE_FILLERS", "0") in ("1", "true", "True")

# a line is SENSITIVE (no fillers, no extra pauses injected mid-number) if it
# carries a price, a phone number, a booking/appointment, an OTP, or a
# compliance/disclosure phrase. Detected AFTER normalization (spoken words), so
# we look for the spoken tokens too.
_SENSITIVE_RE = re.compile(
    r"\b("
    r"rupaye|rupees|lakh|crore|hazaar|percent|"
    r"otp|pin|account|booking|book\b|appointment|slot|register|"
    r"baje|o'clock|recorded|consent|disclosure|aadhaar|pan\b"
    r")\b|\d",
    re.IGNORECASE,
)


def is_sensitive_line(line: str) -> bool:
    """True if the sentence must stay clean (no filler, no extra pause)."""
    return bool(_SENSITIVE_RE.search(line or ""))


def _hesitation_to_ellipsis(line: str) -> str:
    """Map an em-dash hesitation to an ellipsis (Sarvam reads … as hesitation)."""
    return re.sub(r"\s*--\s*", " … ", line)


def shape_punctuation(line: str, hinglish: bool, sparse_filler_slot: bool) -> str:
    """Shape ONE sentence's punctuation for prosody, optionally prepend ONE sparse
    filler. Sensitive lines are returned untouched (clean)."""
    if not line:
        return line
    if is_sensitive_line(line):
        return line.strip()
    out = _hesitation_to_ellipsis(line.strip())
    if sparse_filler_slot:
        filler = (_FILLERS_HINGLISH if hinglish else _FILLERS_EN)[0]
        # only if the line doesn't already start with a filler/greeting
        first = out.split()[0].lower().strip(",.!?") if out.split() else ""
        if first not in set(_FILLERS_HINGLISH) | set(_FILLERS_EN) | {"haan", "ji", "namaste", "hello", "hi"}:
            out = f"{filler.capitalize()}, {out[0].lower() + out[1:] if out else out}"
    return out


def apply_prosody(
    sentences: tuple[str, ...], hinglish: bool, *, fillers: bool | None = None
) -> tuple[str, ...]:
    """Apply hesitation/punctuation shaping across the sentence list, and — only
    when fillers are enabled — at most one sparse verbal-nod filler per
    `_FILLER_EVERY` sentences (never on a sensitive line).

    `fillers`: None (default) => read the VOICE_FILLERS env (OFF by default for
    NEUTRAL delivery, W-VOICE-FIX BUG4). Pass True/False to force it (tests / a
    per-direction caller). When OFF, punctuation prosody still applies — only the
    prepended fillers are suppressed, keeping pace/loudness consistent."""
    use_fillers = _fillers_enabled() if fillers is None else bool(fillers)
    out: list[str] = []
    since_filler = _FILLER_EVERY  # allow the first eligible non-sensitive line
    for s in sentences:
        slot = False
        if use_fillers and not is_sensitive_line(s) and since_filler >= _FILLER_EVERY:
            slot = True
            since_filler = 0
        else:
            since_filler += 1
        out.append(shape_punctuation(s, hinglish, slot))
    return tuple(out)
