#!/usr/bin/env python3
"""PVS B7 — generate the Sarvam v2 voice sample set ONCE (minimal, ~7 short clips).

Calls Sarvam TTS (bulbul:v2) once per speaker with a SHORT shared sentence, decodes the base64
audio, and writes var/voice_samples/sarvam/<speaker>.mp3. Idempotent: skips a speaker whose clip
already exists. Tiny one-time cost (~7 short synth). ElevenLabs previews are free (no synth needed).

Run on the box:  /opt/capsy-agent/.venv/bin/python _pvs_sarvam_samples.py
"""
import base64
import json
import os
import sys
import urllib.request

SPEAKERS = ["anushka", "manisha", "vidya", "arya", "abhilash", "karun", "hitesh"]
# short, neutral, language-mix sample line (~1 short utterance => minimal chars => minimal cost)
SAMPLE_TEXT = "Namaste! Main aapki Famit AI assistant hoon. Aapse baat karke khushi hui."

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "var", "voice_samples", "sarvam")
API = "https://api.sarvam.ai/text-to-speech"


def _key():
    for k in ("SARVAM_API_KEY", "SARVAM_API_KEY_2", "SARVAM_API_KEY_3"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return ""


def main():
    key = _key()
    if not key:
        print("NO_SARVAM_KEY", file=sys.stderr)
        sys.exit(2)
    os.makedirs(OUT_DIR, exist_ok=True)
    made, skipped, failed = [], [], []
    for sp in SPEAKERS:
        fp = os.path.join(OUT_DIR, f"{sp}.wav")
        if os.path.isfile(fp) and os.path.getsize(fp) > 1024:
            skipped.append(sp)
            continue
        body = json.dumps({
            "text": SAMPLE_TEXT,
            "target_language_code": "hi-IN",
            "speaker": sp,
            "model": "bulbul:v2",
            "speech_sample_rate": 22050,
        }).encode("utf-8")
        req = urllib.request.Request(API, data=body, method="POST", headers={
            "Content-Type": "application/json",
            "api-subscription-key": key,
        })
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            audios = data.get("audios") or []
            if not audios:
                failed.append((sp, "no audios in response"))
                continue
            raw = base64.b64decode(audios[0])
            # Sarvam returns WAV (PCM) base64 -> store as .wav, served audio/wav by the proxy.
            with open(fp, "wb") as fh:
                fh.write(raw)
            made.append((sp, len(raw)))
        except Exception as exc:  # noqa: BLE001
            failed.append((sp, repr(exc)[:120]))
    print(json.dumps({"made": made, "skipped": skipped, "failed": failed,
                      "out_dir": OUT_DIR}, ensure_ascii=False))
    if failed and not made and not skipped:
        sys.exit(1)


if __name__ == "__main__":
    main()
