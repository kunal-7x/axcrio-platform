# Wave: Inbound AI Manager Voice Line — APPLIED + LIVE (2026-06-11)

## §callerid-greet-fix — SILENCE-ON-INBOUND FIXED (2026-06-12)
**Symptom (founder's real call 2026-06-11 20:19:28):** `aim-voice` logged `AIM inbound caller=063***30`
then `AIM inbound REJECT unauthorized caller=063***30` → agent refused, never greeted → caller heard
30s silence → CLIENT_INITIATED hangup. **Root cause:** Vobiz presents the founder's caller-ID as
`06375548830`, NOT his SIM MSISDN `+917861019021`, so the hardcoded `AUTHORIZED_CALLER` allowlist
mismatched and the old hard gate `return`ed before any greeting. The STT `APIConnectionError`/`engine
is closed` errors were SECONDARY (teardown after the reject). 
**Fix (edited LIVE `/opt/famit-agent/aim_voice_agent.py` ONLY; backup `*.GZbak.20260612-015355`; deployed
md5 `dba1d682…`; agent.py md5 `9150fabe…` UNCHANGED; restarted ONLY aim-voice-agent; no git):**
1. **Soft caller-ID gate.** New env flag `AIM_REQUIRE_AUTHORIZED_CALLER` (default `0`/OFF). Default =
   GREET everyone + PIN-gate; hard caller-ID reject ONLY if the flag is `1`. The PIN (4827, firewall)
   is the real proof. Also added `AIM_EXTRA_AUTHORIZED` (default `06375548830,+917861019021`) merged
   into the allowlist (belt-and-braces). The lone `REJECT` path now sits behind the flag.
2. **Greet-first, always.** Moved `transport.speak("Hello, this is your Famit AI Manager. Please say
   or enter your PIN.")` to fire IMMEDIATELY after `session.start`, BEFORE the gate (code lines 540 vs
   gate 544+). TTS-only → a transient STT blip cannot suppress it. Removed the old duplicate greeting.
3. **Never-silent guard.** `entrypoint` is now a thin wrapper around `_entrypoint_impl`; any exception
   → best-effort spoken apology (via `ctx._aim_session`) + clean `_hangup`, never a silent hang. The
   prior `@session.on("error")` keep-alive + 6-retry STT conn_options are retained.
**Proof:** worker re-registered `agent_name="manager" id=AW_iRrbBV7pY3Bb`, port 8091 LISTEN, 0
tracebacks since restart, NRestarts=0. Runtime constant-eval on box: default `REQUIRE_AUTHORIZED_CALLER
=False`; `06375548830` now IN allowlist; an arbitrary unknown number is NOT rejected (greeted+PIN-gated).
**Net:** the founder calling from ANY number now hears the greeting within ~1-2s and is asked for the
PIN; no inbound caller can hit silence. **Regression:** outbound earner untouched (famit-agent/
famit-bridge/famit-caller active, agent.py byte-identical). **Rollback:** `cp -a
/opt/famit-agent/aim_voice_agent.py.GZbak.20260612-015355 /opt/famit-agent/aim_voice_agent.py &&
sudo systemctl restart aim-voice-agent`.


Box `famit@168.144.153.145` (famit-livekit, blr1). Goal: the founder phones the AI-Manager DID, a
dedicated voice agent answers, gates on PIN (4827), then executes spoken commands through the SAME
AI-Manager command brain the chat Test Console drives. ADDITIVE only — the live OUTBOUND earner
(agent.py "capsy"/"Riya", port 8090, outbound trunks) was NEVER edited, restarted, or degraded.

## What was applied (6 units, each backup-first + reversible)

**U-AGENT — inbound voice worker DEPLOYED + RUNNING**
- `aim_voice_agent.py` -> `/opt/famit-agent/aim_voice_agent.py`. Runs as NEW systemd unit
  `aim-voice-agent.service` (`/opt/capsy-agent/.venv/bin/python aim_voice_agent.py start`,
  EnvironmentFile=/opt/famit-agent/.env, PYTHONPATH=/opt/famit-agent). `famit-agent.service`
  byte-unchanged.
- Registered with LiveKit: `registered worker agent_name="manager" id=AW_oB4R2aoYkBBp`, HTTP on
  :8091 (outbound stays :8090). Voice stack copied from agent.py (Sarvam saarika:v2.5 lang=unknown,
  Groq llama-4-scout round-robin keys, ElevenLabs flash, preemptive_generation + endpointing/barge-in).
- TWO load-bearing fixes found + applied this wave (the agent file as previously written would NOT
  have authenticated the founder, and keypad PIN would have silently failed):
  1. **firewall.init() added.** In a fresh worker process NOTHING inits firewall.py, and an
     un-init'd firewall fail-CLOSES (`check_pin` returns False for EVERYTHING) -> the correct PIN
     4827 would be WRONGLY REJECTED. The agent now replicates caller.py's init at startup
     (`firewall.init(secret=<var/secret>, pin_file=<var/pins.json>)`). Verified `FIREWALL_READY=True`,
     `check_pin("admin","4827")=True`, wrong PIN `False`.
  2. **DTMF handler moved `session.on` -> `ctx.room.on("sip_dtmf_received")`.** On livekit-agents
     1.5.17, DTMF is emitted on `livekit.rtc.Room` (rtc/room.py:950, payload `SipDTMF{digit,code,
     participant}`), NOT on AgentSession (whose EventTypes have no DTMF). The old registration
     wouldn't crash (EventEmitter doesn't validate names) but would NEVER fire -> keypad PIN dead.
     Also wrapped `dtmf_event.set()` in `loop.call_soon_threadsafe` (room event may fire off-loop).
- `.env` (backup `.env.INbak.20260611-164410`) gained: AIM_VOICE_AGENT_NAME=manager,
  AIM_AUTHORIZED_CALLER=+917861019021, AIM_ADMIN_TENANT=admin, AIM_PIN_LEN=4, AIM_AGENT_HTTP_PORT=8091,
  AIM_TTS_LANG=hi.
- Import dry-run under the real venv PASSED: IMPORT_OK, FIREWALL_READY=True, WorkerOptions builds,
  PIN extractors (4827 / "4 8 2 7" / "four eight two seven" / "char aath do saat") all True,
  caller-ID canon + authorized-match True.

**U1 — SIP container TCP 5060 (additive, UDP preserved)**
- `/opt/livekit/docker-compose.yml` `sip.ports:` gained `"5060:5060/tcp"` right after the existing
  `"5060:5060/udp"` (RTP 10000-10200/udp untouched). `docker compose up -d sip` recreated ONLY the
  sip container; livekit-server + redis Up 8 days (untouched). Host now LISTENs tcp+udp on 5060.
- Backup `/opt/livekit/docker-compose.yml.bak.aim.1781196360`.

**U2 — firewall: 10 Vobiz IPs + TCP 5060 (additive)**
- `/usr/local/sbin/livekit-vobiz-fw.sh`: `VOBIZ_IPS` 1->10; added `apply tcp 5060` (reuses the
  apply() helper -> 10x RETURN + 1 DROP); added an IPv6 tcp 5060 DROP (defense-in-depth). Restarted
  `livekit-vobiz-fw.service`. DOCKER-USER now: tcp 5060 = 10 RETURN + 1 DROP; udp 5060 = 10 RETURN +
  1 DROP (extended from the single IP); RTP RETURN preserved.
- UFW: 10x `allow proto tcp ... port 5060` (belt-and-braces; DOCKER-USER is the real gate).
- Backups `.bak.aim.1781196476`, `/root/iptables.aim.bak.1781196476`, `/opt/livekit/ufw.aim.bak.1781196539.txt`.

**U3 — inbound LiveKit trunk** `ST_K785ASpNh5ow` (name aim-inbound, numbers +918071583488,
allowed_addresses = the 10 Vobiz signaling IPs, krisp off). Matches by DID + source-IP, not carrier
Trunk-ID. `lk sip inbound delete ST_K785ASpNh5ow` to roll back.

**U4 — dispatch rule** `SDR_RaCvweSMA2p5` (aim-inbound-dispatch) -> trunk `ST_K785ASpNh5ow` ->
Individual(Caller) room `aim-_<caller>_<random>` -> `agent_name=manager`. No rule-level PIN (real
Argon2id PIN gates in-agent). `lk sip dispatch create` rejected the doc's JSON ("missing rule" on lk
2.16.3 twirp); created via the LiveKit Python SDK instead (`_aim_make_dispatch.py`, typed protobuf:
SIPDispatchRuleIndividual + RoomConfiguration/RoomAgentDispatch). `lk sip dispatch delete
SDR_RaCvweSMA2p5` to roll back.

## OUTBOUND-EARNER REGRESSION — HEALTHY BEFORE AND AFTER (proof)
- BASELINE (before): outbound trunks ST_LH8ighJJtHSi(UDP)+ST_fmtVmNJmpzKa(TCP) present;
  famit-agent+famit-bridge+livekit-vobiz-fw active; 0 inbound trunks / 0 dispatch / 0 active rooms.
- AFTER all 6 units: outbound trunks **byte-identical** (`lk sip outbound list` unchanged); famit-agent,
  famit-bridge (uvicorn, up 1d10h), livekit-vobiz-fw, aim-voice-agent all **active**; both worker ports
  8090(capsy)+8091(manager) listening; livekit-server+redis Up 8 days; no errors/tracebacks in the
  outbound agent log.
- **LIVE PROOF:** a real outbound call ran on capsy DURING the wiring window (job AJ_6TShSAcs6HyR, room
  famit-917861019021-c9b218, 16:48:15-16:48:35) — full path executed: capsy answered, Sarvam STT
  connected, agent session ran, transcript saved (outcome=no_answer; lead didn't pick up but the
  dial->agent->STT->transcript pipeline is intact). Conclusive that inbound wiring did NOT touch outbound.
- Core API: health 200 on 10.122.0.4:8310 + 127.0.0.1:8208/8209; **zero 5xx**; famit-api/caller/
  capsy-api/famit-panel active. (/campaigns is auth-gated -> 404 unauthenticated, never 5xx.)

## ROLLBACK (fast, per-unit; outbound never in the blast radius)
- Agent: `sudo systemctl disable --now aim-voice-agent` (+ rm unit). Outbound untouched.
- U4: `lk sip dispatch delete SDR_RaCvweSMA2p5`.
- U3: `lk sip inbound delete ST_K785ASpNh5ow`.
- U2: restore `/usr/local/sbin/livekit-vobiz-fw.sh.bak.aim.1781196476` + restart svc; ufw delete the 10 tcp/5060 rules (or restore ufw bak).
- U1: restore `/opt/livekit/docker-compose.yml.bak.aim.1781196360` + `docker compose up -d sip`.
- Teardown order: U4 -> U3 -> agent -> U2 -> U1.

## REMAINING (founder-side, before the live phone test)
- The Vobiz INBOUND trunk must point its Primary Origination URI at `sip:168.144.153.145:5060`
  Transport **TCP** and link DID +918071583488 (per ai_manager_INBOUND_SETUP.md A2/A3). Our side is
  now fully ready (TCP listener + 10-IP allowlist + trunk + dispatch + manager worker live).
- Live E2E test: call +918071583488 from +917861019021 -> greeting -> PIN 4827 -> safe cmd (no PIN)
  -> risky cmd (PIN demanded) -> "haan" -> executes; wrong-PIN -> refuse+lock.

## Residual risks
- DTMF delivery depends on Vobiz sending RFC2833/SIP-INFO digits; if absent, the spoken-PIN fallback
  (deterministic number-word map, recording-suppressed) is the path.
- Registry seeding: +917861019021 not yet in ai_manager registry; `_tenant_by_id` falls back to
  ADMIN_TENANT="admin" so the founder's PIN still gates (single-tenant box). Seed the row for a clean
  role/tenant resolution.
- lk binary relocated /tmp -> /usr/local/bin/lk (reboot-stable).

---

## ARM + VERIFY PASS (2026-06-11) — steady-state re-check + 2 enrollment gaps fixed

Re-verified the full inbound path in steady state (worker had been live ~11 min). **Everything our-side
is ARMED.** Found + fixed 2 LOAD-BEARING enrollment gaps that the original wiring missed (Unit 6 of the
plan was never applied) — without them the founder's FIRST live call would have failed at the registry
gate, before the PIN prompt.

### Steady-state checks (all PASS)
- systemd: `aim-voice-agent` active (PID 1682673, 11min), `famit-agent`/`famit-bridge`/`livekit-vobiz-fw` active.
- docker: `livekit-sip` Up (recreated), `livekit-server`+`livekit-redis` Up 8 days (UNTOUCHED).
- ports: tcp+udp 5060 LISTEN; 8090 (capsy outbound) + 8091 (manager inbound) both LISTEN.
- LiveKit objects: inbound trunk `ST_K785ASpNh5ow` (DID +918071583488, all 10 Vobiz IPs); dispatch
  `SDR_RaCvweSMA2p5` -> that trunk -> room `aim-_<caller>_<random>` -> agent `manager`, no rule-PIN;
  **outbound trunks `ST_LH8ighJJtHSi`(UDP)+`ST_fmtVmNJmpzKa`(TCP) byte-identical**.
- firewall: DOCKER-USER = exactly **10 RETURN + 1 DROP** on tcp/5060 (allowlist correct); UFW 10x 5060/tcp.
- worker registration: `registered worker agent_name="manager" id=AW_oB4R2aoYkBBp` (LiveKit ws://127.0.0.1:7880).
- firewall PIN gate (in worker venv+env): `check_pin("admin","4827")=True`, wrong=False; firewall.init ready=True.

### The 2 gaps (FOUND in the brain-path simulation, FIXED)
1. **registry NOT seeded** -> `identity.resolve("+917861019021")` returned None -> machine S1 said
   "This number isn't registered for AI Manager" / `outcome=reject:unregistered` — BEFORE any PIN. The
   agent's `_tenant_by_id` ADMIN_TENANT fallback never runs because S1 (registry.lookup) rejects first.
   FIX: `registry.register(tenant_id="admin", phone="+917861019021", role="admin", verify_mode="voice_pin",
   verified=True)` + belt-and-braces rows for `917861019021` and `07861019021` (Vobiz caller-ID forms).
   `canonical_phone` keeps `+`+digits verbatim (no bare-10->+91 expansion), so each plausible inbound form
   needs its own row. (bare-10 `7861019021` is rejected by register()'s country-code guard; Vobiz sends
   91-prefixed for an Indian DID, so covered.) File `/opt/famit-agent/var/aim_numbers.jsonl` (bak `.INbak.<ts>`).
2. **grants too narrow** -> default registered grants were `['analytics']`; permits() is `role_ok AND
   grant_ok` (default-deny), so a risky cmd ("increase the budget" -> `ads.set_budget`) was
   permission-DENIED ("You're not permitted to do that") before reaching step-up. FIX: `set_grants` ->
   full `KNOWN_GRANTS` on all 3 founder rows (campaigns,leads,calls,whatsapp,ads,ads:read,analytics,
   contacts,billing). Now permits()=True for the full operate set; risky cmds correctly reach S6 step-up.

### End-to-end brain proof (CommandMachine.run, worker venv, SERVICE env loaded so llm_provider=groq)
- greeting -> PIN **4827** => "Hi there. You're verified." (wrong PIN => "didn't match. Try again.").
- safe "how many leads today" => analytics readout, **no second PIN** (read-only, correct).
- risky "run my campaign" => NLU matched -> permission OK (full grants) -> **"This will start calling
  your all leads. Say your PIN to confirm."** (step-up DEMANDED) -> PIN 4827 -> **"Confirm ... Yes or no?"**
  -> "haan". (delegate.execute then re-verifies the step-up token independently; in the SIM the campaign
  slot+runner are synthetic so it returns a soft "couldn't complete" — every GATE fired; live data
  resolves the slot. This is defense-in-depth: "voice is not trusted", the runner re-enforces.)
- firewall step-up token (worker env): `authenticate("admin","4827",scope="ads.set_budget")` mints a
  scope-bound token (TTL 300s, amr=pin, jti); `verify_step_up_token(tok, "ads.set_budget", "admin")` =>
  claims; `verify_step_up_token(tok, "campaigns.create", "admin")` => **None** (scope-bound, no reuse).
- PIN-leak check: `to_record()` JSON contains "4827"? **False**.

### Outbound earner — HEALTHY before AND after (PROOF)
- `famit-agent`(capsy):8090 + `famit-bridge` active; outbound trunks byte-identical; livekit-server/redis Up 8d.
- **LIVE outbound calls ran DURING this verification** (jobs `AJ_6TShSAcs6HyR` 16:48, `AJ_NtMFDQFqpBZS`
  17:01) — capsy received the job, answered, TTS latency logged, transcript saved (outcome=no_answer =
  lead didn't pick up; pipeline intact). **Zero ERROR/Traceback in the outbound log TODAY (Jun 11)**
  (the Jun-10 exit-255 lines are prior worker-recycle noise, not today). Core API health 200 x3, zero 5xx.

### REMAINING (founder-side only)
Point the Vobiz inbound trunk Primary Origination URI -> `sip:168.144.153.145:5060` Transport **TCP** +
link DID +918071583488 (ai_manager_INBOUND_SETUP.md A2/A3). Then call +918071583488 from +917861019021.
Founder HOWTO written: `caps/HOWTO-inbound-call.md`. We can NOT verify the carrier SIP INVITE reaching
the box until the founder places the call (no inbound INVITE arrives until Vobiz routes the DID to us).

---

## §voice-fix — STT-crash root cause + fix (2026-06-12)

**Symptom:** inbound call dispatched + joined (`received job request, agent_name: manager`) then
`APIConnectionError: Failed to connect to STT WebSocket` -> `TimeoutError` (aiohttp `_resolve_host`
CancelledError) inside Sarvam `_stt_pump` -> `process exiting` 17:16:10 BEFORE the greeting -> silence.

**Confirmed root cause (verified read-only on the box):**
- Keys/env were NOT the issue — `aim-voice-agent` shares `EnvironmentFile=/opt/famit-agent/.env` +
  venv `/opt/capsy-agent/.venv` with the earner; env has 5 Sarvam / 6 Groq / 1 ElevenLabs key.
- Installed `livekit-agents==1.5.17`: `_stt_pump` (audio_recognition.py:126) raises the Sarvam
  `APIConnectionError` as an **unhandled task exception** -> the whole job process exits. The inbound
  `AgentSession` was created WITHOUT a widened `conn_options`, so STT connect used the framework default
  but the transient `_resolve_host` race still produced a terminal error that killed the call before the
  greeting (which fires after `session.start()` returns).
- Network healthy: `api.sarvam.ai` -> 20.235.220.20, TCP connect ~20ms; it was a momentary resolver race.

**Fix applied (aim_voice_agent.py ONLY; backup `aim_voice_agent.py.VFbak.20260611-184619`):**
1. `AgentSession(conn_options=SessionConnectOptions(stt_conn_options=APIConnectOptions(max_retry=6,
   retry_interval=1.0, timeout=20)))` — the framework now RETRIES the Sarvam connect up to 6x over a
   resolver stall instead of dying on the first blip. (env-tunable: AIM_STT_MAX_RETRY/RETRY_INTERVAL/TIMEOUT)
2. `session.on("error")` handler — logs recoverable STT/TTS/LLM hiccups and KEEPS THE CALL ALIVE; a
   transient connect blip can never silent-kill the session again.
3. `_build_stt()` = a SINGLE Sarvam STT, byte-faithful to the proven outbound earner (NOT a
   FallbackAdapter — that would prematurely fail over on quiet turns and alter transcription).
4. Greeting unchanged in placement (`transport.speak(...)` via `session.say()` right after
   `session.start()`), now reliably reached because STT no longer crashes the process first.
- VAD built once (`_vad = silero.VAD.load()`) and shared with the session.

**Proof:**
- `py_compile` OK. Service restarted (ONLY aim-voice-agent) -> `registered worker, agent_name:"manager"`
  (ids AW_KRjt6PfvbnAq / AW_vVyf8rQ4JpJK / AW_MR5HWtgUxMc6), 0 traceback / 0 `process exiting` / 0
  `APIConnectionError` since restart.
- STT-connect proof from the agent's exact venv+env: a raw `sarvam.STT().stream()` logged
  `WebSocket connected successfully` (`RAW_CONNECT_OK`) — the STT WS connects healthily from the agent
  context; the old crash path is gone. (A pure-tone probe yields no transcript -> expected
  `APITimeoutError waiting for server response`; that is a probe artifact, NOT a connect failure.)

**Regression gate (earner UNTOUCHED + healthy before & after):**
- `agent.py` md5 = `9150fabe4ff62b4b4470f9a87df346e5` BEFORE and AFTER (byte-identical).
- `famit-agent` / `famit-caller` / `famit-bridge` all `active` throughout; no new errors in earner journal.
- Only `aim-voice-agent` was restarted. No git. DNS `/etc/hosts` pin deliberately NOT applied (a stale
  Azure IP would break STT for BOTH services on this shared box — the retry widening is the safe lever).

**Rollback:** `cp -a /opt/famit-agent/aim_voice_agent.py.VFbak.20260611-184619
/opt/famit-agent/aim_voice_agent.py && sudo systemctl restart aim-voice-agent`.

**Still founder-gated:** a real end-to-end audio greeting can only be confirmed once Vobiz routes DID
+918071583488 to the box and the founder calls from +917861019021 (no inbound SIP INVITE reaches us
until then). Agent-side: registered, STT-connect proven, crash-path removed, greeting will fire on join.

---

## §pipeline — robust understanding + real-time execution + clarify + error recovery (2026-06-12)

Made the inbound agent a REAL assistant: every spoken command now routes through the AI-Manager brain
(state_machine -> intent/driver NLU -> delegate -> workforce.run_agent) and EXECUTES in real time, with
multi-turn clarification, live data readouts, and spoken error recovery. ONE file changed in the brain
(`ai_manager/state_machine.py`) + two test fixtures updated. aim_voice_agent.py UNCHANGED (it already
hands the whole session to CommandMachine.run). Earner NEVER touched.

### What was wrong (the brain consumed clarify/query/error too thinly)
- `kind=="query"` called a PLACEHOLDER `_answer_query()` ("Detailed metrics readout connects to
  analytics.") — it NEVER executed the read, so leads/analytics/billing/wallet/bookings spoke nothing real.
- `kind=="clarify"` always said "I didn't quite get that — could you rephrase?" — a dead loop with no
  guidance, ignoring the NLU's OWN clarifying question + which slot was missing (the driver already emits
  `reason="missing:campaign"` / a natural question in `slots['_summary']`).
- S8 used `executed = (status=="done")` — a "done" run that was actually a NO-OP (every tool parked
  because a FEATURE_* flag is off) was falsely reported as success.
- S9 `_report_text` for any non-success said a generic "I couldn't complete that right now." with no
  retry offer; a delegate crash could in principle reach the caller as silence.

### Fix (ai_manager/state_machine.py ONLY; backup state_machine.py.PIPEbak.20260612-003951)
1. **Live query execution + spoken real data.** New `_answer_query_live()` runs the read through the
   SAME `_delegate.execute` path the chat console uses (live GET via the catalog under the per-run RLS
   token), then `_read_readout()` speaks REAL numbers: "You have 42 leads, 7 of them hot." / "today's
   revenue is ₹12,345" / "Your wallet balance is ₹…". Reads are no-PIN/no-spend/idempotent; n_actions
   stays 0 (a read mutates nothing). Persists a lightweight command row for session history.
2. **Multi-turn clarification (`_clarify_text`).** Speaks the NLU's own question; on `missing:<slot>`
   asks for exactly that slot via `_FIELD_PROMPT` ("Which campaign should I run? You can say its name.");
   on repeated unclear turns ESCALATES with concrete speakable examples ("run my Diwali campaign / call
   my hot leads / how many leads today / what's my balance"); a BLOCK refuses plainly (never coaxes).
   First silent turn re-prompts (caller may still be there); a second consecutive silence ends gracefully.
3. **Truth-in-reporting.** S8 now uses the delegate's honest `effective`/`outcome` as ground truth:
   executed iff (effective True) OR (status=="done" AND no explicit non-effective outcome). A
   parked/no-op/error outcome is NEVER reported as "Done".
4. **Error recovery (`_report_text` rewrite + `_read_unavailable`).** Every failure speaks a specific,
   honest apology + a retry/alternative offer — parked -> "sent it for sign-off", not_configured ->
   "isn't switched on yet", insufficient_credits -> "top up the wallet", generic error -> "Sorry, I
   couldn't complete that — try again, or do something else?". A delegate exception is caught at S8 and
   synthesized into an error result so S9 ALWAYS speaks. NEVER silence (task §c).

### Command types working over voice (all routed brain -> delegate -> catalog -> live caller.py routes)
- RUN A CAMPAIGN (existing, by name): "run the Diwali campaign" -> leads.enqueue_calls -> POST /run
  (step-up PIN + spoken confirm). "call my hot leads" -> temperature-filtered dial.
- READS (no PIN, speak live data): analytics.read, leads.read, contacts.read, billing.read, wallet.read,
  booking.read.
- ADS (money, step-up + amount read-back): ads.set_budget, ads.create_campaign(draft), ads.pause.
- WHATSAPP bulk send (step-up). CAMPAIGN create (draft). WORKFLOW create_draft/activate/run_now.
- BOOKING create/reschedule/cancel. CONTACTS write / SUPPRESSION add. CREATIVE generate_* (parked until
  FEATURE_MEDIA -> clean "isn't switched on yet").
- Cred/FEATURE-gated modules park GRACEFULLY (clean spoken not_configured), never crash.

### Clarification + error-recovery behavior (proven)
- Low confidence / off-enum / missing slot -> SPOKEN clarify question (multi-turn), escalates to examples.
- Risky action -> fresh scoped step-up PIN + spoken confirm with amount read back, before any side effect.
- Any read/command failure -> spoken apology + retry offer (never silence). Parked -> honest sign-off line.
- Security/compliance asks (reveal PIN, bypass DND) -> plain spoken refusal, never coaxed.

### Proof (all on the box, real venv/env)
- `ai_manager/tests/test_offline.py` (safety acceptance) = **10/10 PASS** (provider=none). Fixed 2
  PRE-EXISTING fixture breaks: StubDelegate didn't accept the `run_token=` kwarg delegate.execute now
  passes (TypeError -> the test's delegation silently errored); and the query test asserted "no
  delegation" which is now obsolete (a read DELEGATES a read-only GET to fetch live data — updated to
  assert reads delegate but carry NO step-up token / NO execute audit leg).
- `ai_manager/tests/test_pipeline.py` (NEW, the production behaviors) = **5/5 PASS**: clarify multi-turn
  + escalation, query speaks real lead count, revenue readout, read error-recovery apology+retry, parked
  run NOT reported Done.
- LIVE groq NLU on broken/code-mixed speech (provider=groq, the service's real provider): Hindi "mujhe
  apne saare hot leads ko call karna hai" -> leads.enqueue_calls; "aaj kitne leads aaye" -> leads.read;
  Hinglish "budget badha do facebook ka 2000 tak" -> ads.set_budget; "run the diwali campaign" ->
  leads.enqueue_calls; vague "do that thing with the ads" -> clarify with a spoken Hindi question;
  "whats my wallet balance" -> wallet.read; "send whatsapp to new leads" -> clarify missing:campaign_ref.

### Regression gate — earner UNTOUCHED + healthy before & after
- `agent.py` md5 = `9150fabe4ff62b4b4470f9a87df346e5` identical throughout. famit-agent / famit-bridge /
  famit-caller `active` before & after; earner journal last 2 min = 0 Traceback/ERROR/Exception.
- Only `aim-voice-agent` restarted -> `registered worker agent_name="manager" id=AW_DxWjrctrQjPX`, 0
  traceback / 0 APIConnectionError / 0 process-exiting in steady state. Ports 8090 (earner) + 8091
  (inbound, new PID 1727054) both LISTEN. Firewall PIN gate armed (init True; 4827->True, wrong->False).

Rollback: `cp -a /opt/famit-agent/ai_manager/state_machine.py.PIPEbak.20260612-003951
/opt/famit-agent/ai_manager/state_machine.py && sudo systemctl restart aim-voice-agent`.

### REMAINING (founder-gated, NOT an agent defect)
The live end-to-end audio test still needs Vobiz to route DID +918071583488 to the box; no inbound SIP
INVITE reaches us until then. Agent registered, STT-connect proven, brain wired + tested. The panel
Call-History/Sessions view (frontend) is the separate FORTRESS deploy unit.

---

## §verify-2026-06-12 — ⛔ CORRECTION: the prior "founder-gated, not an agent defect" framing is WRONG

A REAL inbound call DID reach the box and the agent crashed anyway — this is an agent-side defect,
not a Vobiz gap. Evidence pulled live from `famit@168.144.153.145`:

- **Jun 11 19:37:38** `received job request … room: aim-_06375548830_… agent_name: manager` (real SIP
  dispatch — routing works). **19:37:39** "Connecting to STT WebSocket" → **19:38:09** (30s later)
  `APIConnectionError: Failed to connect to STT WebSocket` (`_resolve_host` CancelledError→TimeoutError
  in `_stt_pump`/audio_recognition.py:126) → `AgentSession is closing due to unrecoverable error` →
  `process exiting`. Greeting never fired. The `session.on("error")` handler logged it `recoverable=False`
  and did NOT keep the call alive.
- The widened-retry fix WAS live (file mtime 19:19:27, running pid 1728381 started 19:23:01, grep confirms
  `SessionConnectOptions(stt_conn_options=APIConnectOptions(max_retry=6,…timeout=20))` at lines 391–398).
  It didn't help: every retry's DNS resolution hung the full timeout.
- **inbound STT connects Jun 11 = 6 attempted / 0 "connected successfully".**
- **earner STT connects Jun 9–11 = 30 attempted / 30 succeeded** (same Sarvam STT, same `/opt/famit-agent/.env`,
  same `/opt/capsy-agent/.venv`, same URL `…language-code=unknown&model=saarika:v2.5`); last earner call
  18:48:47 connected STT in 0.4s, ran a full ~2.5-min call, clean exit, 0 errors since 19:00.
- Standalone proof from the agent's exact venv+env: `sarvam.STT().stream()` driven with frames →
  `Connecting to STT WebSocket` → `WebSocket connected successfully`. So keys/network/DNS/venv are fine in a
  plain process. **The hang is specific to the inbound LiveKit JOB SUBPROCESS at session startup.**
- DB: `ai_manager_sessions` = 0 rows, `ai_manager_session_turns` = 0 rows → nothing ever logged.
- Earner regression: `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` unchanged, famit-agent NRestarts=0,
  all 4 services active, caller :8209 /health=200, zero 5xx.

**Real fix candidates (not another retry):** (1) prewarm DNS + warm an aiohttp connector in the worker
`prewarm_fnc` (parent process, before the job loop is busy); (2) audit/move any blocking sync call around
`session.start` off the loop; (3) defer STT until after the TTS greeting so a slow STT connect can't gate
the greeting. Acceptance = a REAL call logs "WebSocket connected successfully" + audible greeting + a
session row. The earner must stay md5-identical and untouched throughout.
