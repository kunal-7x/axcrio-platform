"""voice_kernel.language.mirror — the per-turn LANGUAGE MIRROR.

The proven outbound behaviour, ported one-to-one: on EVERY user turn, re-detect
the caller's language from the latest utterance and MIRROR it — return the
reply-language NAME, the SPEAKABLE TTS code, and whether it CHANGED from the
caller's current active language. Adaptive, NEVER hardcoded to one language: the
"active" language is supplied by the caller (its per-call LanguageTracker), so a
mid-call switch (Hindi->English->Hindi) flips the reply language immediately.

This is the pure decision function. Wiring (the per-call tracker + injecting the
turn-scoped directive into the kernel TurnLayer + setting the SpeechPlan/
ProviderChoice TTS code) lives in voice_kernel.integrations.{inbound,outbound};
the Speech Planner still renders casual Hinglish + no-half-words (W5) — the mirror
only decides LANGUAGE, never the rendering.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import detector as _ld


@dataclass(frozen=True)
class MirrorDecision:
    """The per-turn mirror result. `reply_language` is the language NAME
    (hindi|english|hinglish|gujarati) for the LLM steer; `tts_lang_code` is the
    SPEAKABLE realtime TTS code (hi|en, gu clamped to hi); `changed` is True iff
    the active language flipped on THIS turn (so the caller appends the per-turn
    reply directive + nudges TTS only on a real switch — zero cost on steady
    state); `instruction` is the ready-to-inject LLM steer for this turn."""

    reply_language: str
    tts_lang_code: str
    changed: bool
    instruction: str

    def as_dict(self) -> dict:
        """Plain dict for the agent boundary (no kernel/dataclass type leaks)."""
        return {
            "reply_language": self.reply_language,
            "tts_lang_code": self.tts_lang_code,
            "changed": self.changed,
            "instruction": self.instruction,
        }


def mirror_turn(user_text: str, tracker: "_ld.LanguageTracker") -> MirrorDecision:
    """THE per-turn mirror. Feeds the latest user utterance into the caller's
    stateful tracker (hysteresis-gated) and returns the mirror decision.

    Adaptive + NO hardcoded language: the reply language is whatever the tracker's
    sticky `active` resolves to AFTER ingesting this turn — Hindi->Hindi,
    English->English, switch-back->switch. The `tracker` carries the per-call
    active language (NOT a module constant), so nothing is pinned to one language.

    Never raises — on any failure it returns the tracker's current active language
    so the call never breaks.
    """
    try:
        active, changed = tracker.update(user_text or "")
        return MirrorDecision(
            reply_language=active,
            tts_lang_code=_ld.safe_tts_language_code(active),
            changed=bool(changed),
            instruction=_ld.reply_instruction(active),
        )
    except Exception:
        active = getattr(tracker, "active", _ld.DEFAULT_LANG)
        return MirrorDecision(
            reply_language=active,
            tts_lang_code=_ld.safe_tts_language_code(active),
            changed=False,
            instruction=_ld.reply_instruction(active),
        )


def mirror_once(user_text: str, active_lang: str) -> MirrorDecision:
    """Stateless single-turn mirror (no hysteresis): given the user's last
    utterance + the CURRENT active language, decide the reply language. Used where
    the caller does not hold a persistent tracker (and for unit assertions).
    Adaptive — `active_lang` is the caller's current language, never a constant."""
    tracker = _ld.LanguageTracker(default=active_lang or _ld.DEFAULT_LANG)
    return mirror_turn(user_text, tracker)


__all__ = ["MirrorDecision", "mirror_turn", "mirror_once"]
