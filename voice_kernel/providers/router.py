"""voice_kernel.providers.router — DefaultProviderRouter (W5, fail-LOUD).

Implements the FROZEN `ProviderRouter` Protocol:

    def resolve(self, ctx: CallContext) -> ProviderChoice
    def on_error(self, provider: str, code: int) -> ProviderChoice

AUTHORITATIVE selection: the provider triple comes from the campaign fields
(plan tier / explicit overrides), and the SAME ProviderChoice is what preview,
live, usage and billing all read — there is no second, divergent default.

FAIL-LOUD: when a provider/key is unavailable we return an EXPLICIT ProviderChoice
whose `reason` names the fallback, AND we log it. We NEVER silently swap Sarvam
for ElevenLabs (the live bug). If the selected provider has no healthy key we
fall back with a loud reason; we never return a provider the caller didn't
intend without saying so in `reason` + the log.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..contracts import CallContext, ProviderChoice
from .keypool import KeyPool

log = logging.getLogger("voice_kernel.providers")

# ---- Sarvam realtime-streaming WS contract (mulaw-8k telephony leg) --------- #
# Captured from the Sarvam streaming TTS docs so the live wiring buffers correctly
# over the 8k narrowband telephony codec. min_buffer_size = chars to accumulate
# before the first synth flush (lower = lower TTFB, higher = smoother); max chunk
# bounds a single WS frame. These are the values the LATER live cutover uses.
SARVAM_WS_CONTRACT = {
    "min_buffer_size": 30,       # chars buffered before first flush (low-latency)
    "max_chunk_length": 250,     # max chars per WS synth frame
    "output_audio_codec": "mulaw",
    "output_sample_rate": 8000,  # telephony narrowband
    "model": "bulbul:v2",        # v3 lacks enable_preprocessing -> we normalize upstream
}

# default live triple — matches the deployed _DEFAULT_PROV_TRIPLE.
_DEFAULT = ProviderChoice(stt="sarvam", llm="groq", tts="elevenlabs", reason="default-triple")

# plan-tier -> TTS engine (the lean/standard tiers SHOULD speak Sarvam Bulbul;
# premium speaks ElevenLabs). This is the AUTHORITATIVE mapping the live file's
# resolve_providers approximates but never reaches (INBOUND_PROV_LOCK off).
_TIER_TTS = {
    "lean": "sarvam",
    "standard": "sarvam",
    "growth": "elevenlabs",
    "premium": "elevenlabs",
    "enterprise": "elevenlabs",
}


@dataclass
class ProviderDiagnostics:
    """Per-call provenance: SELECTED vs ACTUAL provider + the decision trail. A
    silent EL-swap is impossible to hide because `actual_tts != selected_tts`
    with an empty trail would be a loud anomaly. Billing reads `actual_tts`."""

    call_id: str = ""
    selected_stt: str = ""
    selected_llm: str = ""
    selected_tts: str = ""
    actual_tts: str = ""
    trail: list[str] = field(default_factory=list)

    def log_decision(self, msg: str) -> None:
        self.trail.append(msg)
        log.info("provider-router[%s]: %s", self.call_id or "?", msg)

    @property
    def silent_swap(self) -> bool:
        """True if the actual TTS diverged from the selected one with NO logged
        reason — the exact failure mode this wave kills."""
        return bool(self.actual_tts) and self.actual_tts != self.selected_tts and len(self.trail) <= 1


def _tier_of(ctx: CallContext) -> str:
    f = dict(getattr(ctx, "fields", None) or {})
    for k in ("plan", "tier", "plan_tier", "voice_tier"):
        v = str(f.get(k, "")).strip().lower()
        if v:
            return v
    return ""


def _explicit_tts(ctx: CallContext) -> str:
    f = dict(getattr(ctx, "fields", None) or {})
    for k in ("tts_provider", "tts", "voice_provider"):
        v = str(f.get(k, "")).strip().lower()
        if v in ("sarvam", "elevenlabs"):
            return v
    return ""


class DefaultProviderRouter:
    """Authoritative, fail-LOUD provider router. Construct with optional key pools
    so health-scored rotation is available; without pools it still resolves
    authoritatively (selection is config-driven, pools only affect fallback)."""

    def __init__(
        self,
        pools: Optional[dict[str, KeyPool]] = None,
        default: ProviderChoice = _DEFAULT,
    ) -> None:
        self.pools = pools or {}
        self.default = default
        self.diag: Optional[ProviderDiagnostics] = None

    # ------------------------------------------------------------- resolve -- #
    def resolve(self, ctx: CallContext) -> ProviderChoice:
        """Authoritative selection. Order: explicit field override > plan tier >
        default triple. STT stays Sarvam (Indic ASR), LLM stays Groq; only the
        TTS engine varies by tier today. Records diagnostics so preview/live/
        usage/billing all consume THIS choice."""
        diag = ProviderDiagnostics(call_id=getattr(getattr(ctx, "meta", None), "call_id", "") or "")
        tts = _explicit_tts(ctx)
        if tts:
            diag.log_decision(f"explicit tts override -> {tts}")
        else:
            tier = _tier_of(ctx)
            tts = _TIER_TTS.get(tier, self.default.tts)
            diag.log_decision(f"tier={tier or 'unknown'} -> tts={tts}")
        # fail-LOUD key check: if the selected TTS has a pool with NO healthy key,
        # say so explicitly (the caller may still try; we never silently swap).
        pool = self.pools.get(tts)
        if pool is not None and pool.healthy_count == 0:
            diag.log_decision(f"WARNING selected tts={tts} has NO healthy key — will fail loud, not silent-swap")
        choice = ProviderChoice(
            stt=self.default.stt,
            llm=self.default.llm,
            tts=tts,
            llm_model=self.default.llm_model,
            reason=f"resolved: {' | '.join(diag.trail)}",
        )
        diag.selected_stt, diag.selected_llm, diag.selected_tts = choice.stt, choice.llm, choice.tts
        diag.actual_tts = choice.tts
        self.diag = diag
        return choice

    # ------------------------------------------------------------ on_error -- #
    def on_error(self, provider: str, code: int) -> ProviderChoice:
        """EXPLICIT, LOGGED fallback. 429 -> rotate key on the SAME provider (the
        pool demotes the hot key); if no healthy key remains, fall back to the
        alternate engine WITH a loud reason. 400/5xx -> alternate engine. Never
        silent — every path logs and stamps `reason`."""
        diag = self.diag or ProviderDiagnostics()
        prov = (provider or "").strip().lower()
        pool = self.pools.get(prov)
        if code == 429 and pool is not None:
            # demote nothing here (the key id is unknown to this signature); the
            # caller demotes via pool.report_failure(key, code). We just decide.
            if pool.healthy_count > 0:
                diag.log_decision(f"{prov} 429 -> rotate key, SAME provider (healthy keys left)")
                return ProviderChoice(tts=prov, reason=f"429 rotate-key on {prov}")
        alt = "elevenlabs" if prov == "sarvam" else "sarvam"
        diag.log_decision(f"{prov} {code} -> FALLBACK to {alt} (logged, not silent)")
        diag.actual_tts = alt
        return ProviderChoice(
            stt=self.default.stt,
            llm=self.default.llm,
            tts=alt,
            llm_model=self.default.llm_model,
            reason=f"fallback: {prov} returned {code} -> {alt}",
        )


def build_provider_router(
    sarvam_keys: tuple[str, ...] = (),
    elevenlabs_keys: tuple[str, ...] = (),
    groq_keys: tuple[str, ...] = (),
) -> DefaultProviderRouter:
    """Factory used at kernel wiring: build_kernel(cfg, router=build_provider_router(...))."""
    pools: dict[str, KeyPool] = {}
    if sarvam_keys:
        pools["sarvam"] = KeyPool("sarvam", sarvam_keys)
    if elevenlabs_keys:
        pools["elevenlabs"] = KeyPool("elevenlabs", elevenlabs_keys)
    if groq_keys:
        pools["groq"] = KeyPool("groq", groq_keys)
    return DefaultProviderRouter(pools=pools)
