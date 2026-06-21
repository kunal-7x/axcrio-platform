# Environment variables the working voice earner needs (NAMES only — NO values)

This documents WHICH env vars the golden brain needs. Real secret values live ONLY in the
out-of-band `.env` on the box (`famit:famit 660`). NEVER commit real key values.
On the box, each line below is a `NAME=value` entry in `/opt/famit-agent/.env`.

## VOICE LAW — never change these values (byte-identical voice)
- `EL_STABILITY` -> `0.55`  (do NOT change)
- `ELEVENLABS_VOICE_ID` -> `QTKSa2Iyv0yoxvXY2V8a`  (do NOT change)
- `ELEVENLABS_TTS_MODEL` -> `eleven_flash_v2_5`
- `ELEVENLABS_API_KEY` -> (secret)

## GROQ brain (the working config)
- `GROQ_API_KEY` ... `GROQ_API_KEY_14`  — 14 multi-account keys (~7M tokens/day; cures the daily-limit silence)
- `GROQ_LLM_MODEL` -> `meta-llama/llama-4-scout-17b-16e-instruct`
- `GROQ_LLM_TEMPERATURE` -> (set)
- `PROVIDER_KEYSTORE_SECRET` -> Fernet key; decrypts the 15 panel hot-store keys so the pool sees 29
- (systemd drop-in, not .env) `GROQ_MAX_TOKENS=220`, `GROQ_FREQ_PENALTY=0.5`, `GROQ_PRES_PENALTY=0.3`, `EARNER_POOL_LLM=1`, `KERNEL_OUTBOUND=0`

## STT (Sarvam)
- `SARVAM_API_KEY` ... `SARVAM_API_KEY_5`
- `SARVAM_STT_MODEL`

## LiveKit / SIP
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_SIP_TRUNK_ID`, `LIVEKIT_AGENT_NAME`

> The real `.env` has many more platform vars (Vobiz, Meta WhatsApp, DO Spaces, PG_DSN, AI-Manager,
> etc.) — see the box. This file lists only the voice-earner-critical + brain set.
