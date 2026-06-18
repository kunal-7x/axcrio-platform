"""voice_kernel.providers — the W5 ProviderRouter (authoritative, fail-LOUD).

Founder complaint (e): SARVAM TTS goes SILENT on lean plans. Root cause in the
live file (documented in design/W5-SARVAM-AND-SPEECH-SEAM.md, NOT edited here):
aim_voice_agent.py:2437 `INBOUND_PROV_LOCK` defaults FALSE, so the resolver is
never consulted and the agent ALWAYS builds ElevenLabs — the Sarvam construction
path at :424-439 is unreachable. Worse, when it IS reached and fails, the only
trace is a WARNING while the session log still records the INTENDED provider →
"billed Sarvam, actually spoke ElevenLabs".

This package replaces that with an AUTHORITATIVE router:
  * resolve(ctx) -> ProviderChoice is the SINGLE source of truth used by preview,
    live, usage AND billing — they all read the SAME selected provider.
  * a health-scored key pool picks a healthy key (round-robin among healthy).
  * on_error() returns an EXPLICIT, LOGGED fallback ProviderChoice (429 rate-limit
    -> rotate key / same provider; 400/5xx -> alternate provider) — NEVER silent.
  * per-call diagnostics (ProviderDiagnostics) record selected vs actual so a
    silent EL-swap is impossible to hide.
  * the Sarvam realtime-streaming WS contract (min_buffer_size / max_chunk_length)
    is captured so the live wiring streams correctly over mulaw-8k.
"""
from __future__ import annotations

from .router import (
    DefaultProviderRouter,
    ProviderDiagnostics,
    SARVAM_WS_CONTRACT,
    build_provider_router,
)

__all__ = [
    "DefaultProviderRouter",
    "ProviderDiagnostics",
    "SARVAM_WS_CONTRACT",
    "build_provider_router",
]
