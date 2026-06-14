"""Sarvam meter — NO billing API. Cost from internally-metered usage (usage_events.json
rows with vendor='sarvam') × rate card (marked estimated).

Rate card (configurable via env):
- STT  ₹30/hour  -> SARVAM_STT_RATE_PER_HR (default 30)
- Bulbul v2 TTS ₹15/10k chars -> SARVAM_TTS_RATE_V2_PER_10K (default 15)
- Bulbul v3 TTS ₹30/10k chars -> SARVAM_TTS_RATE_V3_PER_10K (default 30)
- SARVAM_TTS_RATE_PER_10K = legacy fallback when model version is unknown (default 30)
status() == 'configured' (internal metering, no external API).
"""
from __future__ import annotations

import os

STT_RATE_PER_HR = float(os.getenv("SARVAM_STT_RATE_PER_HR", "30") or 30)
# v2 = Bulbul v2  ₹15/10K chars; v3 = Bulbul v3  ₹30/10K chars
TTS_RATE_V2_PER_10K = float(os.getenv("SARVAM_TTS_RATE_V2_PER_10K", "15") or 15)
TTS_RATE_V3_PER_10K = float(os.getenv("SARVAM_TTS_RATE_V3_PER_10K", "30") or 30)
# Legacy fallback for events that don't carry a model_version tag (default to v3 — higher = safer)
TTS_RATE_PER_10K = float(os.getenv("SARVAM_TTS_RATE_PER_10K", "30") or 30)


def status() -> str:
    return "configured"


def _tts_rate(model_version: str | None = None) -> float:
    """Return the correct per-10K-char rate for the given Bulbul model version.
    model_version: 'v2' -> ₹15, 'v3' -> ₹30, None/unknown -> legacy fallback."""
    v = (model_version or "").strip().lower()
    if v == "v2":
        return float(os.getenv("SARVAM_TTS_RATE_V2_PER_10K", TTS_RATE_V2_PER_10K))
    if v == "v3":
        return float(os.getenv("SARVAM_TTS_RATE_V3_PER_10K", TTS_RATE_V3_PER_10K))
    return float(os.getenv("SARVAM_TTS_RATE_PER_10K", TTS_RATE_PER_10K))


def cost_for_stt_seconds(seconds: float) -> float:
    rate = float(os.getenv("SARVAM_STT_RATE_PER_HR", STT_RATE_PER_HR))
    return round(float(seconds or 0) / 3600.0 * rate, 6)


def cost_for_tts_chars(chars: int, model_version: str | None = None) -> float:
    """Compute TTS cost; pass model_version='v2' or 'v3' for the correct rate split."""
    rate = _tts_rate(model_version)
    return round(int(chars or 0) / 10000.0 * rate, 6)


def summarize(usage_events: list[dict]) -> dict:
    """Sum Sarvam STT seconds (+ any TTS chars) + est cost. Returns
    {status, vendor, stt_seconds, tts_chars, tts_chars_v2, tts_chars_v3, cost, estimated}."""
    stt_s = 0.0
    tts_chars = 0
    tts_v2 = 0
    tts_v3 = 0
    cost = 0.0
    for ev in usage_events or []:
        if ev.get("vendor") != "sarvam":
            continue
        if ev.get("service_type") == "stt":
            stt_s += float(ev.get("qty", 0) or 0)
        elif ev.get("service_type") == "tts":
            chars = int(ev.get("qty", 0) or 0)
            tts_chars += chars
            mv = (ev.get("model_version") or "").strip().lower()
            if mv == "v2":
                tts_v2 += chars
            elif mv == "v3":
                tts_v3 += chars
        cost += float(ev.get("est_cost_inr", 0) or 0)
    return {"status": "configured", "vendor": "sarvam", "stt_seconds": round(stt_s, 2),
            "tts_chars": tts_chars, "tts_chars_v2": tts_v2, "tts_chars_v3": tts_v3,
            "cost": round(cost, 4), "estimated": True}
