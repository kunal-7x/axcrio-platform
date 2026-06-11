# Inbound AI Manager Voice Agent — implementation notes

**File:** `C:\Users\kunal\Desktop\caps\droplet_work\aim_voice_agent.py` (deploy to
`/opt/famit-agent/aim_voice_agent.py`). **Status:** written locally, NOT deployed / NOT restarted.

## What it is
A SECOND, independent LiveKit worker (`agent_name="manager"`, HTTP port 8091) that answers inbound
calls to the AI Manager DID (`+918071583488`) and runs a real-time, PIN-gated command loop. It is
**additive**: it never imports, edits, or restarts the live outbound earner (`agent.py`,
`agent_name="capsy"`, port 8090) or the outbound trunks. Its own systemd unit, dormant until a SIP
inbound dispatch rule routes the DID to `agent_name="manager"`.

## How it reuses the proven voice stack (latency moat inherited, not re-derived)
The `AgentSession` is built from the SAME kwargs `agent.py` uses (L597-651), COPIED:
Sarvam STT `saarika:v2.5` `language="unknown"` (code-mix Hinglish — never force `hi-IN`); Groq
`llama-4-scout` with **per-call round-robin keys** (GROQ_API_KEY/_2/_3…) and Sarvam key round-robin;
ElevenLabs flash_v2_5 TTS (stability 0.45 / style 0.0 / speed 1.08); `preemptive_generation=True`,
`min_endpointing_delay=0.25`, mode-conditional `max_endpointing_delay`, `aec_warmup_duration=0.0`,
barge-in kwargs, and `turn_detection` (semantic-with-VAD-fallback). `max_completion_tokens` (NOT
`max_tokens` — the known call-crashing pitfall). The **one** difference from outbound: this session
has NO sales persona; the LLM only serves the state machine's NLU. All caller-facing speech is authored
by the deterministic state machine via `transport.speak()`.

## How it calls the AI Manager brain (SAME path as the chat Test Console)
The agent owns NONE of the auth/PIN/risk/delegate logic. It drives the already-built, offline-tested
`ai_manager.state_machine.CommandMachine` — the exact spine the dashboard Test Console uses
(`endpoints._run_test_command` / `_transition_command`):

```
CommandMachine(transport=VoiceTransport(session),
               recorder=None,            # LiveKit Egress dormant; machine pauses a no-op recorder
               firewall=None,            # bridge imports the live firewall.py (PIN 4827, var/pins.json)
               runner=None,              # delegate.execute -> workforce.run_agent (in-process)
               tenant_by_id=_tenant_by_id,
               channel="phone").run(caller_id)
```

State machine flow (deterministic; the LLM only fills slots, never authorizes):
`S0 connect -> S1 identify (registry.lookup by caller-ID) -> S2 PIN (firewall.check_pin, BEFORE any
business data) -> S3 context headline -> S4 capture intent (STT final -> intent.driver.parse_intent /
NLU) -> S5 permission (identity.permits) -> S6 fresh per-action step-up PIN for risky (money/bulk/
destructive) -> S7 spoken confirm with amount read back -> S8 delegate.execute -> workforce.run_agent
-> S9 speak result -> loop`.

## The async/sync bridge (load-bearing)
`CommandMachine.run()` is **synchronous** (speak / listen / collect_secret); `AgentSession` is
**async**. So `machine.run(caller_id)` runs in a worker thread (`asyncio.to_thread`), and
`VoiceTransport` hops each call back onto the event loop with
`asyncio.run_coroutine_threadsafe(...).result()`:
- `speak(text)` -> `session.say(text)` + `wait_for_playout()` (turns don't overlap).
- `listen()` -> blocks for the next FINAL user transcript (pushed by the `conversation_item_added`
  callback into an `asyncio.Queue`); a 30s silence returns `""` -> the machine ends gracefully.
- `collect_secret(n, mode)` -> **DTMF preferred** (keypad digits arrive via the `sip_dtmf_received`
  event into a buffer — they NEVER transit STT/recording; auto-fire at N digits or on `#`), with a
  **spoken-digit fallback** that extracts a PIN from the next utterance via a tiny deterministic
  number-word map (`4827`, `4 8 2 7`, `four eight two seven`, `char aath do saat`, Devanagari `४८२७`
  — all verified). The state machine already wraps this span in `recorder.pause()/resume()`.

## PIN + security
- **PIN = 4827** for the admin tenant, verified by `firewall.check_pin` (salted-sha256, `var/pins.json`)
  via `firewall_bridge.authenticate`. Raw PIN is consumed in-memory, masked `"****"` everywhere,
  never logged/persisted. S2 = login; every risky action demands its OWN fresh scoped step-up (S6).
- **Caller-ID gate (belt-and-braces):** `AIM_AUTHORIZED_CALLER` (default `+917861019021`) is matched
  with the CRM-core `_match_forms` expansion (`+91…` / bare-10 / leading-0) BEFORE any prompt; an
  unauthorized number hears a refusal and is hung up. Caller-ID is a HINT, never a credential — the
  PIN is the real proof, and lockout after `AIM_MAX_PIN_ATTEMPTS` (default 3) is enforced by the
  machine + registry.
- Risk is DETERMINISTIC (`identity.classify_risk`): money/bulk/destructive require PIN; the model's
  self-label is ignored. The workforce runner re-enforces caps/kill-switch/wallet independently (S8).

## Activation env (all dormant by default)
`AIM_VOICE_AGENT_NAME=manager`, `AIM_AUTHORIZED_CALLER=+917861019021`, `AIM_ADMIN_TENANT=admin`,
`AIM_PIN_LEN=4`, `AIM_AGENT_HTTP_PORT=8091`, `AIM_TTS_LANG=hi`. Reuses the box's existing
`ELEVENLABS_API_KEY`, `GROQ_API_KEY[_2..]`, `SARVAM_API_KEY[_2..]`, `LIVEKIT_*`, and the firewall
secret. Requires the wiring in `design/aim-inbound-wiring-plan.md` (TCP 5060, Vobiz IP allowlist,
inbound trunk, dispatch rule -> `agent_name="manager"`) — that wiring is NOT applied here.

## Deploy / regression gate (do later, NOT in this task)
1. Confirm OUTBOUND earner still works (`.\call.ps1`, `systemctl status famit-agent`) BEFORE.
2. Copy file to `/opt/famit-agent/aim_voice_agent.py`; add a SEPARATE systemd unit
   (`aim-voice-agent.service`) running `python aim_voice_agent.py start`; never touch
   `famit-agent.service`.
3. Apply the inbound wiring plan units 1-6. Call `+918071583488` from `+917861019021` -> greeting ->
   PIN 4827 -> safe command (no PIN) -> risky command (PIN demanded) -> confirm -> execute.
4. Confirm OUTBOUND earner still works AFTER. Rollback (stop the new unit + remove trunk/rule) on any
   doubt — the outbound path is byte-unchanged throughout.

## Residual risks (carried)
1. **LiveKit event names** — `sip_dtmf_received` and the participant attr `sip.phoneNumber` are the
   documented shapes; if the pinned `livekit-agents` build surfaces DTMF under a different event, the
   spoken-PIN fallback still works (recording-suppressed). Verify the DTMF event name against the box's
   installed build at activation; the handler is guarded so a wrong name degrades, never crashes.
2. **Vobiz DTMF delivery** — depends on the carrier sending RFC2833/SIP INFO digits; if absent,
   spoken-PIN is the path (then OTP is the leak-proof upgrade).
3. **Co-location** — must run on the famit-livekit box (same media plane) to match outbound latency;
   do NOT land it on the API box (residual #5 in the telephony design).
4. **Registry seeding** — `+917861019021` should be registered in `ai_manager` (registry/authorized
   users) for the tenant so S1 supplies tenant/role; `_tenant_by_id` falls back to `ADMIN_TENANT` for
   the single-tenant box so the founder's PIN still gates if the row isn't seeded yet.
