"""voice_kernel.speech.planner — the DefaultSpeechPlanner (W5).

Implements the FROZEN `SpeechPlanner` Protocol:

    def plan(self, raw_text: str, lang: str, mode_card: CampaignCard) -> SpeechPlan

SYNC, HOT-path, no I/O, no await. Pipeline (order is load-bearing):

  1. enforce_casual_hinglish   — kill literary Hindi (complaint b)
  2. normalize_text            — numbers/price/phone/date/unit -> spoken (c)
  3. repair_truncation         — never emit a half-word (a)  [text-layer backstop]
  4. split_sentences           — safe TTS chunk boundaries (a)
  5. apply_prosody             — sparse fillers + adaptive punctuation (d),
                                 never on price/phone/booking/compliance lines
  6. provider render template  — Sarvam code-mix vs ElevenLabs concise (e)

Fail-OPEN: any internal exception -> return the RAW text with normalized=False,
so a realtime turn is never dropped (a degraded-but-spoken turn beats a dead one).
The provider is read from `provider_tts` (set by build_speech_planner / the
ProviderRouter choice) so adaptive shaping is keyed off the SELECTED engine.
"""
from __future__ import annotations

import logging

from ..contracts import SpeechPlan
from ..packet import CampaignCard
from .hinglish import enforce_casual_hinglish
from .normalize import normalize_text
from .prosody import apply_prosody
from .segment import repair_truncation, split_sentences

log = logging.getLogger("voice_kernel.speech")


def _to_tts_lang(lang: str, card_language: str) -> str:
    """Map the detected/campaign language to a TTS ISO-ish code the provider
    layer understands. Hinglish/Hindi -> hi-IN, else en-IN (telephony Indian
    English). Never empty (the TTS needs a concrete code)."""
    src = (lang or card_language or "").lower()
    if any(k in src for k in ("hi", "hing", "hindi", "deva")):
        return "hi-IN"
    if "en" in src or src in ("english", ""):
        return "en-IN"
    return "hi-IN"


def _render_for_provider(sentences: tuple[str, ...], provider_tts: str) -> tuple[str, ...]:
    """Provider-specific final shape.

    Sarvam (Bulbul) — keeps the Devanagari+Latin code-mix as-is; English
    loan-words already in Latin (hinglish.py). Bulbul streams over a mulaw-8k
    telephony leg, so SHORT lines flush faster — we keep sentence chunks small
    (they already are). No SSML; punctuation carries prosody.

    ElevenLabs — concise; collapse a trailing ellipsis to a comma-pause so the
    Flash/Turbo telephony codec doesn't over-hold; otherwise identical spoken
    text (we already normalized upstream so EL's disabled normalizer is moot).
    """
    prov = (provider_tts or "").strip().lower()
    if prov in ("", "elevenlabs", "el"):
        # EL telephony: trim trailing hesitation ellipses to a single pause.
        return tuple(s.rstrip(" …").rstrip() + ("." if s and s.rstrip()[-1:] not in ".!?।" else "") for s in sentences)
    # sarvam (and any Indic engine): keep code-mix + prosody punctuation verbatim.
    return sentences


class DefaultSpeechPlanner:
    """The REAL W5 planner. Construct via build_speech_planner(provider_tts=...)
    so the adaptive shaping knows which TTS engine it is rendering for."""

    def __init__(self, provider_tts: str = "elevenlabs") -> None:
        self.provider_tts = (provider_tts or "elevenlabs").strip().lower()

    def with_provider(self, provider_tts: str) -> "DefaultSpeechPlanner":
        """Return a planner bound to a different TTS provider (ProviderRouter may
        re-key the planner per-call after resolve())."""
        return DefaultSpeechPlanner(provider_tts)

    def plan(self, raw_text: str, lang: str, mode_card: CampaignCard) -> SpeechPlan:
        if not raw_text or not raw_text.strip():
            return SpeechPlan(text="", tts_lang=_to_tts_lang(lang, getattr(mode_card, "language", "")), segments=(), normalized=True)
        card_lang = getattr(mode_card, "language", "Hinglish") or "Hinglish"
        tts_lang = _to_tts_lang(lang, card_lang)
        hinglish = tts_lang == "hi-IN"
        try:
            t = enforce_casual_hinglish(raw_text)          # (b)
            t = normalize_text(t, lang or card_lang)        # (c)
            t = repair_truncation(t)                        # (a) text-layer guard
            sents = split_sentences(t)                      # (a) safe chunks
            sents = apply_prosody(sents, hinglish)          # (d) sparse, adaptive
            sents = _render_for_provider(sents, self.provider_tts)  # (e)
            full = " ".join(s for s in sents if s).strip()
            return SpeechPlan(text=full, tts_lang=tts_lang, segments=tuple(s for s in sents if s), normalized=True)
        except Exception as exc:  # noqa: BLE001 — FAIL-OPEN, never drop the turn
            log.warning("SpeechPlanner.plan failed, passing raw text through: %r", exc)
            return SpeechPlan(text=raw_text, tts_lang=tts_lang, segments=(raw_text,), normalized=False)


def build_speech_planner(provider_tts: str = "elevenlabs") -> DefaultSpeechPlanner:
    """Factory used at kernel wiring: build_kernel(cfg, speech=build_speech_planner(choice.tts))."""
    return DefaultSpeechPlanner(provider_tts=provider_tts)
