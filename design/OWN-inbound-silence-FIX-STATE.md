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
- [x] Rebuilt aim_voice_agent.py on the outbound pattern (plain AgentSession + Agent;
      greeting via `await session.say()` right after `session.start()`; PIN gate + commands as
      Agent function-tools `verify_pin`/`manager_status`). Compiles + imports clean in venv
      (firewall_ready=True). Backup `aim_voice_agent.py.OWNbak.20260612-074847`.
- [x] Cleared `06375548830` lockout + re-activated founder forms; reverted PROBE_A_num
      (+919999900001) wrongly promoted -> now revoked/inert. JSONL backup `.OWNbak.20260612-074809`.
- [x] Deployed; restarted ONLY aim-voice-agent -> `active`, worker `manager` registered
      (AW_J4JR7MbHRY8K). Earner untouched (agent.py md5 9150fabe… unchanged, famit-agent active).
- [x] AFTER gate PASS: real outbound SIP call to +917861019021 created+rang (SCL_DxY8gdxmmtbZ),
      earner spoke opener (capsy room gatetest-7e5546), zero 5xx.
- [x] DTMF PIN added (git ab01c2d): founder can KEY the 4-digit PIN, not only speak it. Redeployed
      clean (worker AW_JanqkcVsKTwy), AFTER gate PASS (earner ring SCL_6zo3vrmqzZ3U, md5 unchanged).
      Backup `aim_voice_agent.py.OWNbak.20260612-080336`.
- [x] ✅✅ **FOUNDER REAL INBOUND CALL SUCCEEDED (08:02, room aim-_06375548830_Nk9F4B7RRkau).**
      SILENCE FIXED. Log proof: 08:02:29 greeting FIRED (~150ms after join); 08:02:44 + 08:02:54 two
      PIN mismatches (STT misheard the SPOKEN digits); 08:03:12 **PIN VERIFIED** — verify_pin tool
      fired + authenticated. Founder confirms: greets, he speaks, gets a response. Pipeline WORKS.

## ✅ SILENCE = SOLVED. NEXT PHASE = "the real thing" (answer QUALITY / actual manager work)
Founder report: greeting + speech + response all work, but the ANSWER content was "incorrect". Two gaps:
1. **Spoken-PIN unreliable** — Sarvam misheard the digits twice before it matched. FIX: use DTMF keying
   (now wired) — founder should KEY 4827. Optionally tighten the verify_pin spoken-digit extraction.
2. **No real command tools yet** — after verify, `manager_status` returns a generic line and there are
   NO action tools (run campaign, read leads/calls, send WhatsApp, status with real numbers). The old
   build's CommandMachine had the deterministic command spine (slot-fill, risk/step-up, confirm,
   delegate.execute → workforce.run_agent). NEXT BUILD = re-attach that command capability as Agent
   function-tools on the NOW-WORKING audio base (audio-first, tools on top), reusing the live
   ai_manager command/delegate/workforce modules. That is the "real thing" the founder means.

## ROLLBACK
Restore `aim_voice_agent.py.OWNbak.20260612-080336` (or earlier), restart ONLY aim-voice-agent.
Earner is never touched (agent.py md5 9150fabe… invariant; verified every deploy).
