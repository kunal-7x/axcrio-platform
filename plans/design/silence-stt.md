# silence-stt.md — why Sarvam STT fails to connect on the INBOUND AI-Manager call, and the robust fix

Scope: inbound agent only (`/opt/famit-agent/aim_voice_agent.py`) + its venv `/opt/capsy-agent/.venv`
(livekit-agents 1.5.17, livekit-plugins-sarvam, aiohttp 3.14.0, Python 3.12). The outbound earner
`agent.py` is REFERENCE ONLY — do not touch it. All findings below are read off the LIVE box
(`famit@168.144.153.145`), the installed library source, and the 20:31/20:34 journal tracebacks.

We CANNOT place a real SIP call from here. This doc proves the **code path + root cause + fix on disk**;
the founder verifies the audio by calling +918071583488.

---

## 10-LINE ROOT CAUSE + FIX (the answer)

1. The in-call failure is NOT a network/DNS-server problem. From the box, DNS resolves in **0.00s** and a
   raw `ws_connect` to `wss://api.sarvam.ai/...` completes the TCP+TLS+handshake in **0.11s** (403 only
   because I used a fake key) — the path is healthy and fast in isolation (matches the founder's RAW_CONNECT_OK).
2. The journal traceback shows the real failure: `aiohttp/connector.py:1171 _resolve_host` ->
   `await asyncio.shield(resolved_host_task)` raises **`asyncio.CancelledError`**, which surfaces as
   `TimeoutError` -> `APIConnectionError("Failed to connect to STT WebSocket")`. It dies in **DNS resolution**, not the socket.
3. `aiodns` is **NOT installed**, so aiohttp 3.14.0 uses `ThreadedResolver` (`socket.getaddrinfo` on the
   loop's default ThreadPoolExecutor). At `session.start()` the loop + that executor are saturated (LiveKit
   room join, WebRTC negotiation, **Silero `VAD.load()` blocks the loop**, TTS/LLM plugin init, the sync<->async
   worker bridge), so the shielded getaddrinfo task is **starved past the timeout and cancelled** during session
   bring-up. That is the resolver race.
4. Layer-2 bug that turns a transient blip into a fatal: the Sarvam plugin's `STT.stream()` forces
   **`max_retry=0`** (`_single_attempt_conn_options`, stt.py:567 + 842/875). So the base `RecognizeStream._main_task`
   (`stt/stt.py:388`) takes the `if max_retries == 0:` branch on the first failure -> `_emit_error(recoverable=False)`
   -> **raise immediately, ZERO retries**.
5. Therefore the inbound "fix" already in the file — `conn_options=SessionConnectOptions(stt_conn_options=
   APIConnectOptions(max_retry=6,...))` (aim_voice_agent.py:426-433) — IS correctly wired (it reaches
   `voice/agent.py:432-433`), but is **silently neutered**: the plugin keeps the widened `timeout` yet
   overwrites `max_retry` to 0. The retry never happens. The greeting fix is real, but STT is still dead.
6. Once STT raises `recoverable=False`, livekit logs "AgentSession is closing due to unrecoverable error" and
   tears the session down -> by the time `transport.speak()` runs the session is closing -> "AgentSession is
   closing, cannot use say()" -> SILENCE. (The greeting-before-gate is right; STT death races it.)
7. ROBUST FIX — apply all three, smallest first, in the INBOUND file/venv only:
   (a) **Kill the resolver race at the source:** pin `api.sarvam.ai` -> `20.235.220.20` in `/etc/hosts`
       (NO DNS lookup -> ThreadedResolver returns instantly even under loop pressure). Cheapest, highest-leverage.
   (b) **Make the loop not starve the resolver:** run `silero.VAD.load()` in `prewarm` (the worker process, before
       the call) instead of inside the per-call entrypoint, so `session.start()` isn't competing with a blocking
       CPU load. (livekit's `WorkerOptions(prewarm_fnc=...)` is the intended home for VAD.)
   (c) **Restore real retry tolerance** so any future blip self-heals: wrap the Sarvam STT in a thin
       `FallbackAdapter` (livekit's `stt.FallbackAdapter([sarvam_a, sarvam_b])` with two rotated keys) OR subclass
       Sarvam STT and stop forcing `max_retry=0`. This converts a one-shot fatal into a retried/recoverable connect.
8. Highest-confidence single action if you change ONE thing: **(a) the /etc/hosts pin** — it directly removes the
   exact line that throws (`_resolve_host`), is reversible, touches no code, and matches the proven-fast isolated path.
9. Do NOT force `language="hi-IN"` and do NOT change the model — config is identical to the earner and correct;
   the failure is connect-time, not transcription. Keep `language="unknown"`, `saarika:v2.5`.
10. Verification that is honest: after the fix, restart ONLY `aim-voice-agent`, then watch
    `journalctl -u aim-voice-agent -f` for `Connecting to STT WebSocket` -> CONNECTED (no "Connection failed")
    on the founder's next real call. We assert the code path is fixed; the founder confirms he hears + can command.

---

## EVIDENCE (exact lines)

### A. The connect dies in DNS resolution, not the socket (journal 20:31 & 20:34)
```
aiohttp/connector.py:1171, in _resolve_host
    return await asyncio.shield(resolved_host_task)
asyncio.exceptions.CancelledError
  -> the above caused: TimeoutError (asyncio.wait_for(..., timeout) in sarvam stt.py:1122 _run_connection)
  -> APIConnectionError("Failed to connect to STT WebSocket: ")   # note: empty message = it was a bare TimeoutError
```
Two real calls, same stack. `Connecting to STT WebSocket` is logged, then ~30s later `Connection failed:`
(empty), then `AIM session error (recoverable=False, source=STT)`, then `AgentSession is closing due to
unrecoverable error`.

### B. Isolated connect is instant and healthy (run on the box, this session)
```
getent hosts api.sarvam.ai            -> 0.00s,  20.235.220.20
aiohttp ws_connect (real TLS+handshake) -> 0.11s, 0.11s, 0.10s   (403 = fake key, connect itself fine)
```
So the network + Sarvam endpoint are fine. The failure is context-specific to session bring-up.

### C. Resolver is the unhardened ThreadedResolver
```
aiodns:           NOT installed (ImportError)
aiohttp:          3.14.0
DefaultResolver:  ThreadedResolver        # getaddrinfo on loop ThreadPoolExecutor -> starvable
nproc: 4, load avg 0.34 (idle) — fine at rest; the spike is the session.start() burst, not steady load
```

### D. The retry is structurally disabled in the Sarvam plugin (livekit-plugins-sarvam, this venv)
```
stt.py:567  _single_attempt_conn_options(...) -> APIConnectOptions(max_retry=0, retry_interval=..., timeout=...)
stt.py:842  single_attempt_conn_options = self._single_attempt_conn_options(conn_options)   # in stream()
stt.py:875  SpeechStream(..., conn_options=single_attempt_conn_options, ...)                # max_retry=0 baked in
```
And the base retry loop honors the stream's OWN conn_options (set at construction), not the call-site's:
```
agents/stt/stt.py:319  self._conn_options = conn_options          # <- the max_retry=0 one
agents/stt/stt.py:388  async def _main_task: max_retries = self._conn_options.max_retry   # == 0
agents/stt/stt.py:404  if max_retries == 0: self._emit_error(e, recoverable=False); raise # ONE attempt, fatal
```
=> The AgentSession-level `SessionConnectOptions(stt_conn_options=max_retry=6)` is read at
`voice/agent.py:432` and passed into `wrapped_stt.stream(conn_options=...)`, but the Sarvam plugin
overwrites `max_retry` to 0 before constructing the stream. **The widened retry is a no-op for streaming STT.**
(It WOULD apply to the non-streaming `recognize()` path, which a telephony session never uses.)

### E. Earner vs inbound — same STT, same latent bug
- Outbound `agent.py:509-519`: `AgentSession(stt=sarvam.STT(language="unknown", model="saarika:v2.5"), ...)`
  with **no `conn_options`** at all. It shares the identical `max_retry=0` + ThreadedResolver vulnerability;
  it survives by timing luck (its STT first-connect doesn't coincide with the same VAD-load + room-join burst,
  and DNS happens to win the race). It is NOT immune — the same /etc/hosts pin + prewarm would harden it too,
  but per the task we DO NOT edit the earner.
- Inbound `aim_voice_agent.py:635-660`: builds the identical Sarvam STT, plus the (neutered) widened conn_options.
  Config is byte-faithful to the earner; the only behavioral delta is the bring-up contention that loses the DNS race.

---

## WHY THE THREE-PART FIX (and the order)

| Fix | What it removes | Cost / risk | Reversible |
|-----|-----------------|-------------|------------|
| (a) `/etc/hosts` pin `20.235.220.20 api.sarvam.ai` | the exact `_resolve_host` call that throws CancelledError | 1 line, no code, no restart of earner | delete the line |
| (b) move `silero.VAD.load()` into `prewarm_fnc` | the CPU spike that starves the loop during `session.start()` | small code move in inbound only | revert the edit |
| (c) Sarvam `FallbackAdapter`/unset `max_retry=0` | the zero-retry one-shot fatal | wrap STT in inbound only | revert the edit |

- (a) alone should make the founder hear the greeting AND be able to command, because the only failing
  operation (DNS) is removed; the socket/TLS/handshake were already proven 0.11s.
- (b) removes the root contention so the loop has headroom for the WS connect and the early audio frames.
- (c) is insurance: even a momentary real network blip becomes a logged retry instead of a session-killing fatal.

CAUTION reminders honored: edits are confined to `aim_voice_agent.py` + the `/etc/hosts` line + venv-level
choices for the inbound process; `agent.py` (md5 9150fabe4ff62b4b4470f9a87df346e5) and the live earner services
(famit-agent / famit-caller / famit-bridge) are untouched; restart ONLY `aim-voice-agent`; no git. Sarvam STT
**config** (language="unknown", saarika:v2.5) is correct — do not change it; this is a CONNECT problem, not a transcription one.

## SECOND, SEPARATE BLOCKER (out of scope for this doc, noted for completeness)
Even with STT fixed, `outcome=reject:unregistered` persists until the founder caller-ids are seeded in the
ai_manager registry: Vobiz CLI **06375548830** AND SIM **7861019021** (S1-identify does `registry.lookup(caller_id)`).
That is the registry-seed half of the GOAL, handled separately — STT fix above unblocks the GREETING + COMMAND audio.
