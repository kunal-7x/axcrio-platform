"""voice_ops.research.features — honest per-turn acoustic/prosodic feature extraction.

TWO paths, picked by what is actually available — and every value carries a `confidence`
and a `source` so the dashboard can badge provenance (never a confident fake number):

  1. turn_features_from_metadata()  — the CHEAP, in-call-SAFE signal. Derives speech rate
     from the ASR transcript + the STT audio_duration the agent already computes, plus pause
     and reply-latency timing. NO raw PCM (the LiveKit turn boundary does not expose frames),
     NO heavy deps. This is what the live agent can emit fire-and-forget. source='asr_metadata'.

  2. extract_acoustics()            — the REAL acoustics, POST-CALL, off the egress recording,
     in a separate process. Correct methods only:
        * F0 via librosa.pyin (pYIN) — NOT piptrack. Reports mean/range/slope/variability.
        * loudness via RMS in dB.
        * speech rate via a de Jong & Wempe (2009) style intensity-peak syllable-nuclei count
          over VOICED frames — NOT librosa.beat.beat_track (a music tempo tracker; category error).
        * pause ratio + voiced duration from the pYIN voiced mask.
     Optional clinical extras (jitter/shimmer/HNR via parselmouth) are computed ONLY over
     >=1 s of aggregated voiced speech, flagged `low_conf=True`, and de-rated hard on 8 kHz
     telephony — per the verdict they are unreliable on running narrow-band speech and do not
     even predict stress, so they are never headline.

Everything is best-effort: any failure degrades to the metadata path / drops the optional
extra, and NOTHING raises into a caller.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Dict, Optional

logger = logging.getLogger("research.features")

_VOWEL_GROUP = re.compile(r"[aeiouyAEIOUY]+")
# tiny, transparent lexical-valence lists (NOT a sentiment model — a cheap nudge, -1..1).
_POS = {"yes", "great", "good", "interested", "sure", "perfect", "love", "okay", "ok",
        "haan", "theek", "achha", "definitely", "absolutely", "nice", "amazing"}
_NEG = {"no", "not", "expensive", "costly", "busy", "later", "never", "stop", "remove",
        "nahi", "mehenga", "problem", "issue", "wrong", "bad", "cancel", "dont", "won't"}


def _estimate_syllables(text: str) -> int:
    """Vowel-group syllable estimate. Crude for Hinglish/Devanagari (flagged in confidence)
    but robust and dependency-free; the post-call path prefers acoustic syllable nuclei."""
    if not text:
        return 0
    total = 0
    for w in re.findall(r"[A-Za-zऀ-ॿ]+", text):
        if re.search(r"[ऀ-ॿ]", w):     # Devanagari: ~chars/2 as a rough nucleus count
            total += max(1, round(len(w) / 2))
        else:
            total += max(1, len(_VOWEL_GROUP.findall(w)))
    return total


def _valence_hint(text: str) -> float:
    if not text:
        return 0.0
    toks = re.findall(r"[a-z']+", text.lower())
    if not toks:
        return 0.0
    score = sum(1 for t in toks if t in _POS) - sum(1 for t in toks if t in _NEG)
    return max(-1.0, min(1.0, score / max(4.0, len(toks) ** 0.5)))


def turn_features_from_metadata(
    *,
    transcript: str = "",
    audio_duration_s: float = 0.0,
    silence_s: float = 0.0,
    turn_latency_ms: float = 0.0,
) -> Dict:
    """The cheap, in-call-safe feature set. No PCM, no acoustic libs. confidence is modest
    (~0.45) because there is no real acoustic signal — only timing + lexical proxies."""
    dur = max(float(audio_duration_s or 0.0), 0.0)
    speech_s = max(dur - max(float(silence_s or 0.0), 0.0), 0.05)
    syl = _estimate_syllables(transcript)
    rate = syl / speech_s if speech_s > 0 else 0.0
    pause_ratio = (silence_s / dur) if dur > 0 else 0.0
    # clamp speech rate to a human plausible band so a bad ASR duration can't spike the trace.
    rate = max(0.0, min(rate, 9.0))
    return {
        "f0_mean_hz": 0.0, "f0_range_hz": 0.0, "f0_slope_hz_s": 0.0, "f0_var_hz": 0.0,
        "loudness_db": 0.0,
        "speech_rate_sps": round(rate, 2),
        "pause_ratio": round(max(0.0, min(pause_ratio, 1.0)), 3),
        "turn_latency_ms": round(float(turn_latency_ms or 0.0), 1),
        "voiced_sec": round(speech_s, 2),
        "valence_hint": round(_valence_hint(transcript), 3),
        "confidence": 0.45,
        "source": "asr_metadata",
        "low_conf": True,
    }


# --------------------------------------------------------------------------- #
# Offline acoustic path (librosa pyin + RMS + de Jong-Wempe nuclei). Lazy imports so the
# cheap path and the rest of the package never pay for librosa/numpy.
# --------------------------------------------------------------------------- #
def extract_acoustics(
    y,
    sr: int,
    *,
    transcript: str = "",
    turn_latency_ms: float = 0.0,
    with_voice_quality: bool = False,
) -> Dict:
    """Correct prosody over one turn's audio (mono float waveform `y` at `sr` Hz).

    Returns the same feature dict shape as the metadata path, plus a real `confidence`
    derived from voiced fraction and sample rate (8 kHz telephony is de-rated). Falls back
    to a metadata-only dict on any failure. Never raises.
    """
    try:
        import numpy as np
        import librosa
    except Exception:  # noqa: BLE001 — libs absent: degrade to the cheap path
        return turn_features_from_metadata(transcript=transcript, turn_latency_ms=turn_latency_ms)

    try:
        y = np.asarray(y, dtype=float)
        if y.size < sr * 0.1:                       # <100 ms: nothing reliable to measure
            return turn_features_from_metadata(transcript=transcript, turn_latency_ms=turn_latency_ms)
        total_s = y.size / float(sr)

        # --- F0 via pYIN (voiced mask + per-frame F0) ---------------------- #
        fmin, fmax = 65.0, 400.0                    # human conversational range
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=fmin, fmax=fmax, sr=sr,
            frame_length=min(2048, _pow2(int(sr * 0.04))),
        )
        f0v = f0[np.isfinite(f0)] if f0 is not None else np.array([])
        voiced_frac = float(np.mean(voiced_flag)) if voiced_flag is not None and voiced_flag.size else 0.0
        if f0v.size >= 2:
            f0_mean = float(np.mean(f0v))
            f0_range = float(np.max(f0v) - np.min(f0v))
            f0_var = float(np.std(f0v))
            # slope (Hz/sec) via least-squares over voiced-frame times
            ts = np.linspace(0, total_s, num=f0v.size)
            f0_slope = float(np.polyfit(ts, f0v, 1)[0]) if f0v.size >= 3 else 0.0
        else:
            f0_mean = f0_range = f0_var = f0_slope = 0.0

        # --- loudness via RMS in dB --------------------------------------- #
        rms = librosa.feature.rms(y=y)[0]
        mean_rms = float(np.mean(rms)) if rms.size else 0.0
        loudness_db = 20.0 * math.log10(mean_rms + 1e-6)

        # --- pause ratio + voiced seconds --------------------------------- #
        voiced_sec = total_s * voiced_frac
        pause_ratio = 1.0 - voiced_frac

        # --- speech rate: de Jong & Wempe intensity-peak syllable nuclei --- #
        rate = _syllable_nuclei_rate(rms, sr, hop=512, voiced_sec=voiced_sec)
        if rate <= 0.0:                              # fall back to ASR-derived if nuclei fail
            syl = _estimate_syllables(transcript)
            rate = syl / max(voiced_sec, 0.05)
        rate = max(0.0, min(rate, 9.0))

        # --- confidence: voiced fraction × telephone-band penalty --------- #
        conf = voiced_frac
        if sr <= 8000:
            conf *= 0.7                             # narrow-band degrades fine estimates
        if voiced_sec < 0.4:
            conf *= 0.6
        conf = max(0.0, min(conf, 0.95))            # never claim full certainty on a call

        out = {
            "f0_mean_hz": round(f0_mean, 1), "f0_range_hz": round(f0_range, 1),
            "f0_slope_hz_s": round(f0_slope, 2), "f0_var_hz": round(f0_var, 1),
            "loudness_db": round(loudness_db, 2),
            "speech_rate_sps": round(rate, 2),
            "pause_ratio": round(max(0.0, min(pause_ratio, 1.0)), 3),
            "turn_latency_ms": round(float(turn_latency_ms or 0.0), 1),
            "voiced_sec": round(voiced_sec, 2),
            "valence_hint": round(_valence_hint(transcript), 3),
            "confidence": round(conf, 3),
            "source": "acoustic_pyin",
            "low_conf": bool(sr <= 8000 or conf < 0.4),
        }

        # --- OPTIONAL clinical extras (confidence-gated, never headline) --- #
        if with_voice_quality and voiced_sec >= 1.0:
            vq = _voice_quality(y, sr)
            if vq:
                out.update(vq)                       # all flagged low_conf inside _voice_quality
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_acoustics degraded to metadata: %r", exc)
        return turn_features_from_metadata(transcript=transcript, turn_latency_ms=turn_latency_ms)


def _pow2(n: int) -> int:
    return 1 << max(8, (max(1, n) - 1).bit_length())


def _syllable_nuclei_rate(rms, sr: int, hop: int, voiced_sec: float) -> float:
    """Simplified de Jong & Wempe (2009): count intensity peaks (syllable nuclei) that are
    local maxima, >= (peak - 9 dB), separated by a >= 4 dB dip and a min inter-peak distance.
    rate = nuclei / voiced_seconds. A real implementation gates on voicing per peak; we gate
    globally by voiced_sec which is adequate for a turn-level rate."""
    try:
        import numpy as np
        if rms is None or len(rms) < 3 or voiced_sec <= 0.05:
            return 0.0
        db = 20.0 * np.log10(np.asarray(rms, dtype=float) + 1e-6)
        thr = float(np.max(db)) - 9.0
        frame_s = hop / float(sr)
        min_dist = max(1, int(0.10 / frame_s))      # >=100 ms between nuclei (~max 10 syl/s)
        peaks = []
        last = -10_000
        for i in range(1, len(db) - 1):
            if db[i] >= db[i - 1] and db[i] > db[i + 1] and db[i] >= thr:
                if i - last >= min_dist:
                    # require a dip since the last accepted peak (de Jong-Wempe dip rule)
                    if not peaks or (db[last] - float(np.min(db[last:i + 1])) >= 4.0):
                        peaks.append(i)
                        last = i
        return len(peaks) / max(voiced_sec, 0.05)
    except Exception:  # noqa: BLE001
        return 0.0


def _voice_quality(y, sr: int) -> Optional[Dict]:
    """parselmouth (Praat) jitter/shimmer/HNR over aggregated voiced speech. Correct method
    (PointProcess → Get jitter/shimmer local) — but ALWAYS flagged low_conf because on 8 kHz
    running speech these are unreliable (verdict). Returns None if parselmouth is absent."""
    try:
        import parselmouth                          # type: ignore
        from parselmouth.praat import call          # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        snd = parselmouth.Sound(values=y, sampling_frequency=float(sr))
        pp = call(snd, "To PointProcess (periodic, cc)", 65, 400)
        jitter = call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
        shimmer = call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
        harm = call(snd, "To Harmonicity (cc)", 0.01, 65, 0.1, 1.0)
        hnr = call(harm, "Get mean", 0, 0)
        clean = lambda v: None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 4)  # noqa: E731
        return {"jitter_local": clean(jitter), "shimmer_local": clean(shimmer),
                "hnr_db": clean(hnr), "low_conf": True}
    except Exception:  # noqa: BLE001
        return None
