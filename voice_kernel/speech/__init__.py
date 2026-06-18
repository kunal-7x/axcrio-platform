"""voice_kernel.speech — the W5 Speech Planner (HOT-path text renderer).

The mandatory step between the LLM and the TTS engine (contracts.SpeechPlanner).
It is a deterministic, SYNC, no-I/O, fail-OPEN rules engine that:

  1. Normalizes numbers / prices / dates / phone numbers / units / acronyms to
     SPOKEN form (EN + casual Hindi/Hinglish) — so the spoken output is identical
     across providers and immune to a provider silently regressing its normalizer
     (ElevenLabs Flash v2.5 + Turbo turn normalization OFF for latency; Sarvam
     bulbul:v3 has no enable_preprocessing). We own normalization upstream.
  2. Enforces casual Hinglish — bans literary-Hindi words ("mahatvapurn" -> "zaroori"),
     keeps English loan-words in Latin script for the Sarvam Devanagari path.
  3. Complete-sentence guard — never emits a truncated final word; chunks on safe
     sentence boundaries. This is the HALF-WORD fix at the text layer.
  4. Adaptive, SPARSE punctuation/fillers, keyed off the SELECTED provider, and
     NEVER inside a price / phone / booking / compliance line.
  5. Provider-specific render templates (Sarvam code-mix + mulaw-8k notes;
     ElevenLabs concise + telephony codec).

Fail-OPEN: on any internal error the planner returns the raw text unchanged with
`normalized=False` rather than dropping the turn (LEARNINGS §1 — never silently
fail, but for a HOT realtime path a degraded-but-spoken turn beats a dead turn).
"""
from __future__ import annotations

from .planner import DefaultSpeechPlanner, build_speech_planner

__all__ = ["DefaultSpeechPlanner", "build_speech_planner"]
