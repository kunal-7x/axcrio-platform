"""
transcript_timed — word-accurate transcript timing for the synced ("Spotify") call
playback highlight.

The stored transcripts carry NO per-turn timing, so the panel can only ESTIMATE
when each line is spoken. This module re-transcribes the call RECORDING once (cached
forever per call) with ElevenLabs Scribe — a BATCH STT that returns per-WORD
start/end times + speaker diarization — and groups the words into role-labelled
turns. The panel then highlights word-by-word, exactly in sync with the audio.

WON'T HURT THE LIVE AGENT:
  * Uses a SEPARATE key (TRANSCRIPT_STT_API_KEY) when set, so it never draws on the
    voice agent's ElevenLabs quota. Falls back to ELEVEN_API_KEY only if no separate
    key is configured.
  * A global single-flight lock means at most ONE re-transcription runs at a time
    (no bursts), and every result is cached, so each recording is transcribed once.
  * It runs in caller.py (the panel process), never in agent.py (the earner).

NEVER raises into the request — any failure returns None and the panel falls back to
the estimate.
"""

from __future__ import annotations

import asyncio

import httpx

_SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
_DG_URL = "https://api.deepgram.com/v1/listen"  # Deepgram prerecorded (word ts + diarization)
_MAX_AUDIO = 60 * 1024 * 1024  # 60 MB cap on a recording we'll transcribe
_LOCK = asyncio.Lock()  # global single-flight: at most one re-transcription at a time


async def align(audio_url: str, *, api_key: str, model: str = "scribe_v1",
                duration: float | None = None) -> dict | None:
    """Re-transcribe `audio_url` with word timestamps + diarization, grouped into
    role-labelled turns. Returns {turns, duration, language} or None on any failure."""
    if not api_key or not audio_url:
        return None
    async with _LOCK:
        try:
            async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as cli:
                ar = await cli.get(audio_url)
                if ar.status_code != 200 or not ar.content:
                    return None
                audio = ar.content
                if len(audio) > _MAX_AUDIO:
                    return None
                ct = ar.headers.get("content-type", "") or "audio/ogg"
                resp = await cli.post(
                    _SCRIBE_URL,
                    headers={"xi-api-key": api_key},
                    data={"model_id": model, "diarize": "true",
                          "timestamps_granularity": "word", "num_speakers": "2"},
                    files={"file": ("recording", audio, ct)},
                )
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception:  # noqa: BLE001
            return None

    words = data.get("words") if isinstance(data, dict) else None
    if not isinstance(words, list):
        return None
    turns = _group_into_turns(words)
    if not turns:
        return None
    dur = turns[-1]["t1"] if turns else (duration or 0)
    return {"turns": turns, "duration": dur, "language": (data.get("language_code") if isinstance(data, dict) else None)}


def _group_into_turns(words: list) -> list[dict]:
    """Group consecutive same-speaker words into turns. Map the FIRST speaker → "ai"
    (in outbound calls Riya greets first), everyone else → "customer"."""
    groups: list[dict] = []
    cur: dict | None = None
    for w in words:
        if not isinstance(w, dict):
            continue
        if (w.get("type") or "word") != "word":
            continue  # skip spacing / audio_event tokens
        txt = (w.get("text") or "").strip()
        if not txt:
            continue
        sp = str(w.get("speaker_id") or "speaker_0")
        try:
            st = float(w.get("start"))
            en = float(w.get("end"))
        except (TypeError, ValueError):
            continue
        if cur is None or cur["sp"] != sp:
            cur = {"sp": sp, "words": [], "t0": st, "t1": en}
            groups.append(cur)
        cur["words"].append({"w": txt, "s": round(st, 2), "e": round(en, 2)})
        cur["t1"] = en

    if not groups:
        return []
    first_sp = groups[0]["sp"]
    out: list[dict] = []
    for g in groups:
        out.append({
            "role": "ai" if g["sp"] == first_sp else "customer",
            "text": " ".join(x["w"] for x in g["words"]),
            "t0": round(g["t0"], 2),
            "t1": round(g["t1"], 2),
            "words": g["words"],
        })
    return out


async def align_deepgram(audio_url: str, *, api_key: str, model: str = "nova-3",
                         language: str = "multi", duration: float | None = None) -> dict | None:
    """Word-accurate alignment via Deepgram prerecorded STT (word timestamps + diarization).
    FALLBACK ONLY (ElevenLabs Scribe is preferred — better Hindi + diarization). Must pass the
    SAME language the live agent uses ("multi" = code-switching Hindi/English) or it transcribes
    Hindi as garbled English. Returns {turns, duration, language} or None. Never raises."""
    if not api_key or not audio_url:
        return None
    async with _LOCK:
        try:
            async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as cli:
                ar = await cli.get(audio_url)
                if ar.status_code != 200 or not ar.content:
                    return None
                audio = ar.content
                if len(audio) > _MAX_AUDIO:
                    return None
                ct = ar.headers.get("content-type", "") or "audio/ogg"
                resp = await cli.post(
                    _DG_URL,
                    params={"model": model, "language": language, "diarize": "true",
                            "punctuate": "true", "smart_format": "true"},
                    headers={"Authorization": f"Token {api_key}", "Content-Type": ct},
                    content=audio,
                )
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception:  # noqa: BLE001
            return None
    try:
        dg_words = data["results"]["channels"][0]["alternatives"][0]["words"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(dg_words, list) or not dg_words:
        return None
    # Normalise Deepgram words into the ElevenLabs-Scribe word shape so we reuse _group_into_turns.
    norm: list[dict] = []
    for w in dg_words:
        if not isinstance(w, dict):
            continue
        txt = (w.get("punctuated_word") or w.get("word") or "").strip()
        if not txt:
            continue
        norm.append({"text": txt, "type": "word",
                     "speaker_id": "speaker_" + str(w.get("speaker", 0)),
                     "start": w.get("start"), "end": w.get("end")})
    turns = _group_into_turns(norm)
    if not turns:
        return None
    dur = turns[-1]["t1"] if turns else (duration or 0)
    lang = None
    try:
        lang = data["results"]["channels"][0].get("detected_language")
    except Exception:  # noqa: BLE001
        lang = None
    return {"turns": turns, "duration": dur, "language": lang}


async def align_any(audio_url: str, *, deepgram_key: str | None = None,
                    eleven_key: str | None = None, dg_model: str = "nova-3",
                    dg_lang: str = "multi", duration: float | None = None) -> dict | None:
    """Word-align with whatever works. PREFER ElevenLabs Scribe — it gives the best Hindi text
    AND reliable speaker diarization. Fall back to Deepgram (the live STT key) only if Scribe is
    unavailable/failing (e.g. EL key rotated or lacking speech_to_text). The caller applies a
    plausibility guard on the result (a real 2-party call can't collapse to 1 turn)."""
    if eleven_key:
        r = await align(audio_url, api_key=eleven_key, duration=duration)
        if r and r.get("turns"):
            return r
    if deepgram_key:
        r = await align_deepgram(audio_url, api_key=deepgram_key, model=dg_model,
                                 language=dg_lang, duration=duration)
        if r and r.get("turns"):
            return r
    return None
