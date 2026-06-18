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

import re

# sparse fillers — a real telecaller's verbal nods. Used at MOST once per
# `_FILLER_EVERY` sentences, and only on non-sensitive lines.
_FILLERS_HINGLISH = ("haan", "achha", "toh", "dekhiye")
_FILLERS_EN = ("right", "okay", "so", "see")

_FILLER_EVERY = 3  # at most one filler per 3 sentences

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


def apply_prosody(sentences: tuple[str, ...], hinglish: bool) -> tuple[str, ...]:
    """Apply sparse fillers + hesitation shaping across the sentence list. One
    filler at most per `_FILLER_EVERY` sentences, never on a sensitive line."""
    out: list[str] = []
    since_filler = _FILLER_EVERY  # allow the first eligible non-sensitive line
    for s in sentences:
        slot = False
        if not is_sensitive_line(s) and since_filler >= _FILLER_EVERY:
            slot = True
            since_filler = 0
        else:
            since_filler += 1
        out.append(shape_punctuation(s, hinglish, slot))
    return tuple(out)
