# OWN — Inbound AI Manager silence: diagnosis + rebuild (IN PROGRESS)

Box `famit@168.144.153.145`. Inbound worker `manager` :8091 (`aim-voice-agent.service`). Earner `capsy`
:8090 (`famit-agent`, agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5`) = READ-ONLY reference, NEVER edit.

## DIAGNOSIS (from LIVE logs of founder's calls 06:41 / 07:00 / 07:02 on 2026-06-12)
1. `manager` agent JOINS the room fine; reads caller `06375548830`.
2. **Sarvam STT first WS-connect HANGS exactly 30s during `session.start()`** (06:41:00 -> 06:41:30),
   then `_ResilientSarvamSTT` retry connects instantly.
3. **PROVEN: the connect is NOT slow** — same URL+key from the box connects in **0.16s** standalone.
   So the 30s is **event-loop STARVATION during session bring-up**, NOT DNS/network. Prior
   "resolver-race / /etc/hosts" diagnosis is WRONG (hosts pin already in place; connect still hung 30s).
4. The greeting `transport.speak()` is AFTER `await session.start()`, so it **cannot fire for 30s** ->
   founder hears SILENCE.
5. Downstream symptom: with STT dead, `collect_secret()` returns "" -> `_authenticate` burns
   `max_pin_attempts` (3) on empty input -> `reject:lockout` -> number `06375548830` set `locked`.
   Next call -> lookup may return None -> `reject:unregistered`. Self-perpetuating lock cycle.
6. `engine: connection error: engine is closed` = room torn down while agent still flailing.

## ROOT CAUSE
The inbound session's CUSTOM bring-up (SessionConnectOptions + `_ResilientSarvamSTT` subclass +
`close_on_disconnect=False` + the CommandMachine sync-thread bridge that the greeting/PIN run through)
makes `session.start()` block ~30s on STT, unlike the proven outbound earner which does plain
`AgentSession(stt=sarvam.STT(...), vad=silero.VAD.load(), ...)` then `await session.say(opener)` and
greets in ~1s on every real call.

## FIX (founder's correct insight): rebuild inbound to MIRROR outbound agent.py
- Plain `AgentSession` with the EXACT outbound STT/VAD/TTS/turn config (no SessionConnectOptions, no
  `_ResilientSarvamSTT`, no `close_on_disconnect=False`).
- A normal `Agent(instructions=...)` manager persona; greet via `await session.say(greeting)` right
  after `session.start()` (the proven audio path).
- PIN gate + manager command logic layered as Agent function-tools / instructions ON TOP, NOT as a
  blocking sync thread that gates the greeting.
- Make lockout NOT cause silence: greet first (now genuinely reached); forgiving PIN.
- Clear current lock on `06375548830`; fix stale unverified `7861019021 manager` row.

## REGRESSION GATE (run BEFORE + AFTER every change)
- `famit-agent` active + agent.py md5 `9150fabe...` UNCHANGED + zero 5xx + a real outbound call to
  +917861019021 RINGS (earner spoke opener at 07:31 — PASS before).
- Restart ONLY `aim-voice-agent`. Backup `aim_voice_agent.py.OWNbak.<ts>` first.

## STATUS
- [x] Diagnosed from live logs (above).
- [x] BEFORE gate PASS (earner active, md5 ok, real outbound opener spoke 07:31, no 5xx).
- [ ] Rebuild aim_voice_agent.py on outbound pattern (greeting via session.say, plain STT).
- [ ] Clear lock + stale row.
- [ ] Deploy (restart aim-voice-agent only), AFTER gate, founder test call.
