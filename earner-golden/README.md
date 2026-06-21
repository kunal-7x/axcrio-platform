# GOLDEN R9 ???????? working voice brain (2026-06-21)

This directory is a frozen, byte-exact snapshot of the LIVE outbound voice earner
at the moment the founder test-confirmed it working: **dead-air fixed, no 'haan'
loop, key-spread (multi-key) architecture, EL_STABILITY=0.55**.

## What's locked (the voice law)
| file | md5 |
|------|-----|
| `agent.py`  | `11a865feb758b25a20cc3e0c291b4ad2` |
| `prompt.py` | `4ae81ac64d2faf5da225b4b5965978e5` |
| TTS span (agent.py lines 596-616, the `elevenlabs.TTS(...)` block) | `4ada9f1e0cb8304ea69194ef38f0ae25` |

Voice tuning (non-secret): `EL_STABILITY=0.55`, `EL_SIMILARITY=0.80`,
`EL_SPEED=1.08`, model `eleven_flash_v2_5`, voice_id `QTKSa2Iyv0yoxvXY2V8a`,
`GROQ_MAX_TOKENS=90`, `KERNEL_OUTBOUND=0`.

## Files here
- `agent.py`, `prompt.py` ???????? the exact live earner brain.
- `llm_router/` ???????? the key-spread provider pool (multi-key round-robin).
- `kernel-outbound.conf` ???????? the systemd drop-in (non-secret env flags only).
- `famit-agent.service` ???????? the base unit (reads secrets from `/opt/famit-agent/.env`).
- `earner.env.example` ???????? env KEY NAMES ONLY (no secret values) + the 7 safe voice-shape values.
- `restore.sh` ???????? one-command restore that ASSERTS md5s + TTS span + EL_STABILITY=0.55
  before restarting, and ABORTS on any mismatch.

## Restore (one command)
```
sudo /opt/famit-agent/_GOLDEN_R9_20260621/restore.sh
```
This backs up the current files (`*.preR9restore.<ts>`), copies the golden files in,
asserts every md5 + the voice span + EL_STABILITY, `py_compile`s, then
`daemon-reload` + `restart famit-agent`. On ANY hash mismatch it aborts WITHOUT
restarting. After it runs, the founder makes ONE real call to confirm.

## Secrets
No secret values live here. The real keys stay only in `/opt/famit-agent/.env`
(git-ignored, never committed). `earner.env.example` is names-only.

