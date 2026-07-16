"""verticals — multi-vertical / multi-persona / multi-language brain layer.

A SELF-CONTAINED, pure-stdlib package that lets one voice agent adapt to any
industry (medical, sales, education, finance, …) with named personas and languages,
WITHOUT changing the proven lean brain. It is designed to be copied verbatim between
services (haptica-agent, famit-haptica, …) — the same way voice-tune knobs are.

Public API (all pure, never raise, byte-identical when FEATURE_VERTICALS is off):

    from agent_svc import verticals
    verticals.enabled()                          # master gate (env FEATURE_VERTICALS)
    fields = verticals.fill_fields(fields)        # fill persona/language identity blanks
    prompt = verticals.apply_to_prompt(prompt, fields)   # append lean domain directive
    voice  = verticals.resolve_voice(fields, tts_provider="sarvam")  # provider-aware voice
    cat    = verticals.catalogue()                # fields/personas/languages for a UI

Registries (data-driven, overlay-extendable via verticals/overlay.py):
    verticals.registry.FIELDS      # vertical -> sub-options (goal/directive/slots/compliance)
    verticals.personas.PERSONAS    # named personas (name/gender/tone/voice-per-provider)
    verticals.languages.LANGUAGES  # languages + per-provider speakability
"""

from __future__ import annotations

from .composer import (
    VERSION,
    apply_to_prompt,
    catalogue,
    enabled,
    fill_fields,
    resolve_profile,
    resolve_voice,
    tts_language,
)

__all__ = [
    "VERSION",
    "enabled",
    "fill_fields",
    "apply_to_prompt",
    "resolve_voice",
    "tts_language",
    "resolve_profile",
    "catalogue",
]
