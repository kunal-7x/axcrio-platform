# Inbound AI Manager — STT-Crash Root Cause + Exact Fix

Box: `famit@168.144.153.145` (famit-livekit). Service: `aim-voice-agent` (inbound, agent_name=manager, :8091).
Earner `famit-agent` (agent.py, :8090) — DO NOT TOUCH. Diagnosed read-only 2026-06-12.

## CONFIRMED ROOT CAUSE (not what was assumed)

The assumption was "wrong/missing env keys." **FALSE.** Both services share the *same*
`EnvironmentFile=/opt/famit-agent/.env` and the same venv (`/opt/capsy-agent/.venv`).
Env has all keys: `SARVAM_API_KEY`..`_5` (5), `GROQ_API_KEY`..`_6` (6), `ELEVENLABS_*`.
`aim_voice_agent.py` builds STT identically to the earner (`sarvam.STT(api_key=_next_sarvam_key(),
language=unknown, model=saarika:v2.5)`). **So keys/region/model are NOT the cause.**

The REAL cause is in the Sarvam plugin's streaming connect path:
`livekit/plugins/sarvam/stt.py` — the streaming WS uses `_single_attempt_conn_options` with
**`max_retry=0`** (stt.py:567-571). `_run_connection()` (stt.py:1122) does
`ws = await asyncio.wait_for(self._session.ws_connect(...), self._conn_options.timeout)`.
At 17:16 a TRANSIENT DNS stall in aiohttp `_resolve_host` (CancelledError) blew the connect
`timeout` → `TimeoutError` → `APIConnectionError: Failed to connect to STT WebSocket`.
With `max_retry=0` there is **no retry**; the error propagates up `stt_node` → `_stt_pump`
(agents/voice/audio_recognition.py:126) and **kills the whole session/process** (`process exiting`,
17:16:10) BEFORE the greeting TTS at aim_voice_agent.py:481 is heard → total silence.

Network is healthy NOW: `api.sarvam.ai` → 20.235.220.20, DNS ~2ms (systemd-resolved 127.0.0.53),
TCP connect ~20ms, 10/10 curls OK. So it was a momentary resolver hiccup the inbound agent had
ZERO tolerance for. The earner survives the same risk only by luck/warmth — it is equally fragile.

## EXACT FIX (apply to aim_voice_agent.py ONLY; backup-first; restart only aim-voice-agent)

1. **Greet on join, independent of STT** — speak the greeting via `session.say(...)`/`session.generate_reply`
   (or pre-warm TTS) BEFORE/parallel to STT readiness, so the caller ALWAYS hears the line even if
   STT is momentarily slow. Move `transport.speak("Hello…PIN")` to fire immediately on `session.start`
   completion and `allow_interruptions=True`.
2. **Make STT resilient to a transient connect failure** — wrap the Sarvam STT so a single WS-connect
   timeout RECONNECTS instead of killing the call. Either (a) subclass/wrap `sarvam.STT` and register a
   `session.on("error")` / STT-error handler that recreates the stream + rotates `_next_sarvam_key()`,
   or (b) bump connect tolerance: pass `conn_options=APIConnectOptions(timeout=15, max_retry=2,
   retry_interval=0.5)` when starting the stream so the streaming path retries (default is single-attempt).
3. **Harden DNS** — eliminate the resolver race: pin `api.sarvam.ai 20.235.220.20` in `/etc/hosts` (or use
   `aiodns`/cached resolver) so `_resolve_host` cannot stall the connect timeout.
4. **Never let one STT error end the call** — add `try/except` around the STT pump path (or session-level
   error handler) so transient `APIConnectionError` triggers reconnect, not `process exiting`.

## REGRESSION GATE
Earner `famit-agent` healthy before+after (`systemctl is-active famit-agent`, recent journal clean).
Restart ONLY `aim-voice-agent`. Rollback = restore `aim_voice_agent.py.bak`. NO git. NO earner restart.
