# AI Manager — Voice / Telephony Design (Flow 1, the primary channel)

**Status:** READ-ONLY design. PLANNING only — no code shipped, no deploy, no git. Conforms to
`AI_MANAGER_MASTER_PROMPT.md` (the 28-section founder spec): DB schema `ai_manager_*`, intents §11,
risk matrix L0–L4 §6, security §7, telephony webhooks §10 (`/voice/inbound · /voice/events ·
/voice/status · /voice/recording`), and the Hinglish response style §13.

**Scope of THIS doc (the telephony slice only):** the inbound voice command PATH — how a phone call
becomes a verified, streaming command session and back to speech. It deliberately does NOT re-design
the CommandEngine / NLU / PolicyEngine / ExecutionRouter (those are the sibling `automation-aimanager.md`
+ `platform-ai-manager.md` + master §9). This doc owns: the inbound DID + `/voice/inbound` webhook →
LiveKit room/agent; caller-phone → authorized-user identification; the streaming session lifecycle
(STT partials → CommandEngine turn → TTS → barge-in) WITHOUT regressing the live agent's ~1.1s latency;
PIN over voice (spoken digits AND/OR DTMF) + the confirmation turn; transcript + recording capture into
`ai_manager_sessions`; the Hinglish business-assistant reply style.

**One hard rule honored throughout:** the LIVE outbound telecaller (`agent.py`, `agent_name="capsy"`,
its tuned `AgentSession`) is **NEVER touched**. The inbound AI Manager is a **SEPARATE worker persona**
(`agent_name="manager"`, its own entrypoint) registered alongside it — so we inherit the exact tuned
voice stack with zero risk of regressing the earner.

---

## 0. GROUND TRUTH — verified on disk 2026-06-10 (cited, not from memory)

| Asset | Path / line | What the inbound path reuses |
|---|---|---|
| **Outbound voice agent** | `droplet_work/agent.py` (874 ln) | `entrypoint(ctx: JobContext)`; `AgentSession(stt=sarvam.STT, llm=groq.LLM, tts=…)` **L597-651**; `_session_kwargs_filter` (L168, drops kwargs a build lacks); `_resolve_turn_detection` (L139); `_barge_in_kwargs` (L183); `_llm_opener` (L282); `WorkerOptions(entrypoint_fnc, agent_name=AGENT_NAME, port)` **L865-869**; `AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME","capsy")` **L50**. We register a **2nd worker** with a 2nd entrypoint + `agent_name="manager"`, reusing the SAME tuned session kwargs. |
| **Outbound dial primitive** | `place_call.py` L37/L40 + `caller.py` L1833 | `agent_dispatch.create_dispatch(room, agent_name)` + `sip.create_sip_participant(sip_trunk_id=TRUNK, sip_call_to=…)`. This is the **OUTBOUND** path (we call them). Inbound is the mirror: a provider INVITE → trunk → dispatch rule → room → our worker (we never `create_sip_participant`). |
| **SIP trunk (outbound only today)** | `caller.py` L132 `TRUNK = "ST_fmtVmNJmpzKa"` (VoBiz, +918071583488) | The existing trunk is **outbound** (`sip_call_to`). Inbound needs a **separate inbound trunk + dispatch rule** (the founder requirement, §10). VoBiz needs **TCP** transport (UDP gives 0 responses — `famit-voice-agent-working-setup` fix #1). |
| **Tuned latency knobs (do NOT regress)** | `agent.py` L625-650 | `preemptive_generation=True`, `min_endpointing_delay=0.25`, `max_endpointing_delay` (0.45 VAD / 1.8 semantic), `aec_warmup_duration=0.0`, `min_interruption_duration=0.25`, `false_interruption_timeout=1.0`, `turn_detection=_td`. Measured ~1.1-1.2s/turn (eou .75 + ttft .35 + ttfb .19). The inbound session COPIES these verbatim. |
| **STT / TTS / LLM** | `agent.py` L598-622 | Sarvam STT `saarika:v2.5` `language="unknown"` (auto code-mix — critical for Hinglish); TTS (ElevenLabs flash_v2_5 / Sarvam TTS, configurable); Groq `llama-4-scout-17b-16e-instruct` (30k TPM, no 429). Groq/Sarvam key round-robin already on box (FORTRESS). |
| **RTP firewall (don't re-break)** | `livekit-vobiz-fw.service` (`famit-voice-agent-working-setup` fix #2) | Inbound media arrives from VoBiz IPs ≠ signaling IP — the persistent `rtp-any` RETURN for udp 10000:10200 already covers BOTH directions. SIP 5060 stays locked to VoBiz. |
| **Thin /ai-manager mgmt API (the thing this supersedes)** | `caller.py` **L4588-4621** + `ai_manager/` package | Already mounted (flag `FEATURE_AI_MANAGER`, default OFF). It persists sessions as JSONL on the control plane and ships `/ai-manager/numbers/lookup` + `POST /ai-manager/sessions` (service-token, dormant). It is the MANAGEMENT surface only — comment L4600 states the LiveKit voice front + SIP dispatch are "a SEPARATE later wire (do NOT pass through caller.py)". **THIS doc is that wire.** The dedicated service (own `ai_manager_*` schema, own port) ABSORBS the JSONL-session shape into PG `ai_manager_sessions` (master §8) and OWNS the 4 `/voice/*` webhooks. |
| **Identity / JWT / firewall / wallet / audit** | `auth.py`, `firewall.py` (design), `wallet.py`, `audit.py` | `auth.issue_pair(tenant)` mints the verified caller's token; `firewall.verify_step_up_token(token, scope, expected_sub=tid)` (sub-bound, §7) gates risky turns; `wallet.reserve/settle` for billable; `audit.record(...)` immutable. The voice layer COMPOSES these — it owns none of the money/PIN math. |

**Net:** the inbound voice path adds **one LiveKit worker persona**, **one `/voice/inbound` (+ events/
status/recording) webhook on the dedicated AI Manager service**, **one caller→user identification step**,
**one streaming session state-machine**, and **transcript/recording capture into `ai_manager_sessions`**.
It adds **no new spend logic, no new tools, no spine edits to `agent.py`/`caller.py`**.

---

## 1. INBOUND DID → `/voice/inbound` → LiveKit room/agent (the front door)

### 1.1 The two valid wirings (pick by what the carrier supports)

LiveKit SIP routes an inbound PSTN call to a named agent via **inbound trunk + dispatch rule**
(verified via LiveKit SIP docs: `create-sip-trunk` inbound + `create-sip-dispatch-rule`). There are two
ways the dedicated AI Manager service participates:

**Wiring A — LiveKit-native dispatch (preferred; lowest latency, fewest moving parts).**
The provider's inbound call hits the **inbound SIP trunk**; a **dispatch rule** (`dispatchRuleIndividual`
or a per-DID `dispatchRuleDirect`) creates a room and **auto-dispatches `agent_name="manager"`** to it.
Our `inbound_agent.py` worker is already registered and picks the job up. The AI Manager service does
NOT sit in the media path; `/voice/inbound` here is an **optional notification webhook** (LiveKit
`SIP`/room `webhook` → our service) used only to pre-warm context / open the `ai_manager_sessions` row.
This is the mirror of the proven outbound path (`create_dispatch(room, agent_name)` at `place_call.py:37`).

**Wiring B — Service-mediated dispatch (when the carrier hits OUR HTTP first, or we want a gate before a room exists).**
The provider POSTs the inbound INVITE event to **`POST /voice/inbound`** on the dedicated service. The
service does the caller→tenant lookup FIRST (cheap, in-PG), decides accept/reject, then programmatically
`create_room` + `create_dispatch(room, agent_name="manager", metadata=…)` via the LiveKit server API and
returns a TwiML-like / SIP-redirect instruction (or 200 + room handle) so the carrier bridges the call
into that room. This gives the service a **pre-room veto** (unknown caller, AI Manager disabled for the
tenant, kill-switch on) before any media is established.

> **DECISION:** ship **Wiring A** as the default (carrier → trunk → dispatch rule → `manager` worker;
> `/voice/inbound` is the room-webhook that opens the session row), and keep **Wiring B** as the
> documented fallback for carriers that can't auto-dispatch. Both are signature-verified (§1.4). The
> state-machine (§3) is identical either way — only WHERE the room is created differs.

### 1.2 `/voice/inbound` request/response contract (master §10)

`POST /voice/inbound` (machine call from carrier/LiveKit webhook — **signature-verified, NOT tenant-auth'd**):

```json
// INBOUND (provider → service). Field names normalized across providers in _parse_inbound().
{ "provider": "livekit|vobiz|twilio", "event": "inbound_call",
  "provider_call_id": "<sip call id>",        // = sip.callID attribute downstream
  "from": "+9198XXXXXX21",                     // caller-ID (E.164 or raw; we normalize)
  "to":   "+91XXXXXXXXXX",                      // the AI Manager DID
  "trunk_id": "ST_inbound_<id>", "ts": "..." }
```
Service response (Wiring B): `{ "action":"accept", "room":"aim-<digits>-<rand>", "agent":"manager" }`
or `{ "action":"reject", "reason":"unregistered|disabled|killswitch" }`. (Wiring A: the webhook just
returns `200` after opening the session row; the dispatch rule already routed the call.)

The three sibling webhooks (master §10):
- `POST /voice/events` — mid-call provider events (answered, DTMF digit, hangup) → appended to the
  session metadata + drive the DTMF-PIN path (§4.2). Signature-verified.
- `POST /voice/status` — terminal call-status callback (completed/failed/no-answer/busy) → flips
  `ai_manager_sessions.status` and stamps `ended_at`. Signature-verified.
- `POST /voice/recording` — recording-ready callback (URL + duration) → writes
  `metadata.recording_url` onto the session (§5). Signature-verified.

### 1.3 The second worker (the key structural fact)

`agent.py` registers `WorkerOptions(entrypoint_fnc=entrypoint, agent_name="capsy", port=8090)` for
**outbound**. The AI Manager voice front registers a **second** worker:
`WorkerOptions(entrypoint_fnc=inbound_entrypoint, agent_name="manager", port=AIM_AGENT_HTTP_PORT)`
in its own process (own systemd unit, per the dedicated-service architecture). A dispatch rule routes
the AI-Manager DID → `agent_name="manager"`, so the two personas never collide and the outbound
telecaller is byte-unchanged. Both share the SAME Sarvam/TTS/Groq wiring and the SAME tuned
`AgentSession` kwargs (§3.3).

### 1.4 Webhook security (the master §10 "signature-verify webhooks" requirement)
Every `/voice/*` is a **machine** call, never carrying a tenant JWT. Verify a provider signature
(LiveKit webhook token / VoBiz shared-secret HMAC over the raw body / Twilio `X-Twilio-Signature`) BEFORE
parsing — copy the pattern `caller.py` already uses for the Meta WhatsApp webhook (`/whatsapp/inbound`
L3737, raw-body HMAC). Reject unsigned/bad-sig with 403; never reveal whether a `from` is registered in
the rejection (anti-enumeration). Tenant is derived from the looked-up caller record (§2), NEVER from the
webhook body.

---

## 2. CALLER-PHONE → AUTHORIZED USER / VENDOR IDENTIFICATION (master §7)

### 2.1 Where the caller-ID comes from (factual)
On the LiveKit side the inbound participant carries SIP attributes (verified via LiveKit SIP docs):
`sip.phoneNumber` (the caller's number = `from`), `sip.trunkPhoneNumber` (the DID dialed = which tenant's
AI Manager line, if per-tenant DIDs are ever issued), `sip.callID`, `sip.trunkID`. `inbound_entrypoint`
reads these off `ctx.room` participant attributes — the SAME shape `agent.py` reads `ctx.job.metadata`
for outbound campaign/lead. So the agent knows WHO is calling without a separate hop.

### 2.2 Normalization (Indian + intl) — REUSE, don't reinvent
`caller.py` already has `norm(p)` (strip non-digits, drop ONE leading 0, prepend `91` to a 10-digit,
return `+…`) and `place_call.normalize` (L18). CRM-core already solved the **silent-join bug**
(`_match_forms(phone)` returns every digit-rep: `91…`, bare-10, leading-0; SQL `regexp_replace(phone,
'\\D','') = ANY(:forms)`) — `brain/patterns.md` CRM-CORE. The AI Manager identification MUST use the SAME
`_match_forms` set when matching `ai_manager_authorized_users.normalized_phone_number`, or a manager
stored as `+91…` won't match a caller-ID arriving as `0…` / bare-10. Store BOTH `phone_number` (as
entered) and `normalized_phone_number` (canonical `91…` digits, per master §8) at registration; match on
the canonical form against the `_match_forms` expansion of the inbound `from`.

### 2.3 The lookup (master §8 `ai_manager_authorized_users`)
```
caller_id = sip.phoneNumber (E.164)            # from inbound participant attrs
forms     = _match_forms(caller_id)            # {91…, bare-10, 0…}
row = SELECT * FROM ai_manager_authorized_users
        WHERE is_active AND regexp_replace(normalized_phone_number,'\D','','g') = ANY(:forms)
        -- RLS-scoped; one human → one vendor+role (multiple authorized users per vendor allowed)
```
On hit: `tenant_id`, `user_id?`, `role`, `permissions(json)`, `pin_hash?`, lockout fields. On the dedicated
service, this is a direct PG read against `ai_manager_*` (FORCED RLS, admin-GUC) — NOT a network hop to the
monolith (identity is the service's OWN schema). The looked-up `tenant_id` is the ONLY source of tenant for
the whole session; nothing in the call can override it.

### 2.4 Unknown / unregistered caller (master §4 Flow 1 "cannot identify")
- **No match** → speak the registered fallback (§13 tone): *"Yeh number registered nahi hai. Apne
  registered number se call kijiye, ya dashboard se yeh number add kijiye."* Open a session row with
  `status="blocked"`, `user_id=null`, reveal **zero** business data, audit `aim.voice.unknown_caller`,
  hang up. (Master §4 also allows an offer to verify via registered-phone/email/OTP — designed as a
  **future** branch; v1 = reject + guide to dashboard, because a spoofed caller-ID that then "verifies"
  by speaking an email is weak. Spoken-OTP-to-a-second-channel can be added later behind the firewall's
  existing OTP `amr:"otp"` token.)
- **Disabled user / locked_until in the future** → speak *"Yeh account abhi locked hai"*, audit, hang up.
- **`ai_manager_profiles.enabled=false` for the tenant** → *"AI Manager abhi enabled nahi hai"*, hang up.

### 2.5 Caller-ID is a HINT, never a credential (anti-spoof — master §7)
Caller-ID is trivially spoofable, so identification (§2.3) only selects WHICH vendor the caller *claims*
to be + the verify policy. **Possession of the line is proven by the spoken/DTMF PIN in S2 (§3) BEFORE
any business data is spoken.** A spoofed caller-ID that doesn't know the PIN gets nothing and is locked
out after N tries (§4.3).

---

## 3. STREAMING SESSION LIFECYCLE (STT partials → CommandEngine turn → TTS → barge-in)

### 3.1 The state machine (deterministic; LLM only fills slots, never authorizes)
```
S0  CONNECT
      caller_id = participant attr sip.phoneNumber ; provider_call_id = sip.callID
      open ai_manager_sessions row (channel='phone', status='active', started_at, caller_phone,
        provider_call_id, stt/tts/llm provider tags)
      audit('aim.voice.call_start', meta={caller_id_redacted})

S1  IDENTIFY  (§2)
      row = lookup_authorized_user(caller_id)         # PG, RLS, _match_forms
      if not row: speak(unregistered); status='blocked'; → S_END
      tenant, user_id, role, perms = row...           # tenant fixed for the whole call

S2  AUTHENTICATE THE HUMAN  (anti-spoof; before ANY context spoken)
      verify_mode = profile.verify_mode               # 'voice_pin' | 'dtmf' | 'otp'
      pin = collect_digits(n=profile.pin_len)         # DTMF preferred (§4.2); else spoken (§4.1)
      ok  = firewall.check_pin(tenant, pin)           # salted hash; NEVER store/log raw
      on fail: failed_pin_attempts++ ; audit('aim.voice.auth_fail')
               if attempts >= require_pin policy max (default 3):
                   set locked_until=now+LOCK_TTL ; speak(lockout) ; status='blocked' ; → S_END
               else re-prompt
      on ok:  session_token = auth.issue_pair(tenant)['access_token']   # acts AS this tenant
              audit('aim.voice.authed', actor=tenant)
      # S2 = login. A SECOND fresh per-action step-up (S6) is STILL required per risky action.

S3  LOAD BUSINESS CONTEXT  (read-only; the CommandEngine analytics adapter)
      ctx = command_engine.read_context(tenant, session_token)
            # business name, today leads/hot/warm/cold, calls, wallet balance, live campaigns, caps left
      speak short Hinglish headline (§13):
            "Namaste {name} ji. Aaj 38 leads aaye — 9 hot. Wallet ₹4,200. 2 campaign live. Boliye?"

S4  CAPTURE INTENT  (loop until a clear single command or goodbye)
      partials stream from STT; on end-of-turn (turn_detector) → final utterance
      match = command_engine.nlu(utterance, ctx)      # closed-enum IntentMatch, master §22 JSON
      kind == query   -> answer from ctx (L0 read; no gate); loop S4
      kind == clarify -> ask the ONE missing field (§13 "ask only the minimum"); loop S4
      kind == command -> → S5
      kind == goodbye -> → S_END(ok)

S5  PERMISSION + RISK  (deterministic; master §6 L0–L4, never the LLM's label)
      action = command_engine.map_intent_to_action(match)
      if not policy.permits(role, perms, action): speak(not permitted); audit; loop S4
      risk = policy.classify_risk(action)             # L0..L4 table (§3.2)
      L4 -> speak refusal (§3.2); audit('aim.voice.blocked'); loop S4
      L0 -> answer/execute read-only; → S9
      L1 -> sometimes verbal confirm; → S7
      L2 -> verbal confirm (+ PIN by tenant policy); → S7 (PIN if policy)
      L3 -> → S6 (PIN MANDATORY) then S7

S6  STEP-UP FOR RISKY ACTION  (FRESH, per-action, scoped — master §7 confirmation)
      estimate cost if billable -> wallet pre-check (§ master 19)
      speak EXACT consequence + amount (§13):
            "Yeh paid action hai — Google Ads par campaign C2 ka budget ₹1,500/day. Apna PIN boliye."
      pin = collect_digits(profile.pin_len)           # DTMF/voice/OTP per policy
      step_up = firewall.verify_step_up_token(...)  IFF firewall.check_pin(tenant,pin) else None
      if not step_up: attempts++ ; lockout policy as S2 ; audit('aim.voice.stepup_fail') ; loop/abort
      audit('aim.voice.stepup_ok', meta={scope, action}); → S7 (carry step_up)

S7  CONFIRM  (explicit yes/no read-back — last human checkpoint before side effect)
      speak("Confirm karu? {NL summary incl. amount & scope}. Haan ya na?")
      if not yes: audit('aim.voice.cancelled'); speak("Theek hai, cancel kiya."); loop S4
      → S8

S8  DELEGATE & EXECUTE  (hand to CommandEngine → ExecutionRouter → monolith /api)
      result = command_engine.execute(tenant, session_token, action, step_up_token=step_up,
                                      idempotency_key=command_id)
            # the engine re-runs ITS own caps / wallet hold-settle / DND / kill-switch / idempotency
      audit('aim.voice.execute', actor=tenant, meta=redact(result))
      → S9

S9  REPORT  (speak outcome; offer next — §13)
      speak("Ho gaya — budget ₹1,500/day set. 50 hot leads calls ke liye queue kar diye.")
      loop S4  OR  S_END(ok) on goodbye

S_END  status = completed|failed|blocked ; ended_at ; persist full transcript + actions to
       ai_manager_sessions ; audit('aim.voice.call_end', meta={outcome, n_actions}) ; hang up.
```

**Safety properties baked into the ORDER (master §7):** (1) caller-ID alone never grants access — fresh
PIN in S2 proves the human before any business data is spoken; (2) every L3 action gets its OWN fresh,
scoped step-up in S6 (one login PIN can't silently authorize ten budget bumps); (3) explicit spoken
confirm with the amount read back (S7) precedes any side effect; (4) the engine re-enforces caps/
idempotency/wallet/DND/kill-switch in S8 — the voice layer is defense-in-depth, not the only gate;
(5) lockout after N PIN fails, rate-limited per number; (6) everything audited with the verified tenant
as `actor`, never "system".

### 3.2 Risk table (master §6 L0–L4) — deterministic, the LLM's `risk_level` is IGNORED
| Level | Examples (master §6/§22) | Gate in the state machine |
|---|---|---|
| **L0 read** | today summary, hot-lead count, wallet balance, running campaigns, own analytics | answer directly, no PIN (S3/S4) |
| **L1 write** | draft campaign/creative/workflow, add note, schedule reminder | logged-in caller; sometimes verbal confirm (S7) |
| **L2 exec** | WA to selected leads, limited call schedule, activate low-impact workflow, create booking | confirm required (S7); PIN by tenant policy (`require_pin_for_level`) |
| **L3 high** | launch ads, change budget, pause all, bulk call/WA, billing settings, team perms, export, delete high-impact | **PIN MANDATORY (S6)** + confirm (S7) + engine cap re-check (S8) |
| **L4 blocked** | delete vendor account, reveal secrets/keys/PIN, bypass DND/STOP/compliance, spam, spend over limit, transfer ownership, disable audit | **REFUSE** — speak what it CAN do (§13), audit `aim.voice.blocked` |
`classify_risk` is a code allow-list keyed on `action_type` (master §11 taxonomy). The NLU's claimed
`risk_level`/`safe_to_execute` is advisory only; a malformed IntentMatch claiming `risk:0` for
`campaign.update_budget` is re-classified L3 and still demands the PIN.

### 3.3 Reusing the tuned voice settings WITHOUT regressing latency (the load-bearing constraint)
The inbound `AgentSession` is built from the **same kwargs object** `agent.py` uses (L597-651) — copied,
not re-derived — so the ~1.1s/turn moat is inherited by construction:
- **STT:** `sarvam.STT(language="unknown", model="saarika:v2.5")` — auto code-mix is mandatory for
  Hinglish managers (forcing `hi-IN` garbled English words — `agent.py` VOICEFIX comment L600-606).
- **LLM:** `groq.LLM(model=llama-4-scout-17b-16e-instruct, temperature=0.3, max_completion_tokens=~140)`.
  Note: param is `max_completion_tokens`, NOT `max_tokens` (L618 — wrong name crashes the call).
- **TTS:** the configurable TTS (ElevenLabs flash_v2_5 / Sarvam), voice settings stability 0.45 /
  similarity 0.80 / style 0.0 — **never raise style** (latency), `famit-voice-agent-working-setup` fix #4.
- **Latency kwargs verbatim:** `preemptive_generation=True`, `min_endpointing_delay=0.25`,
  `max_endpointing_delay` (mode-conditional 0.45/1.8), `aec_warmup_duration=0.0`,
  `turn_detection=_resolve_turn_detection()`, all through `_session_kwargs_filter(...)` so a build that
  lacks a kwarg degrades instead of crashing (L168/L650).
- **Barge-in:** inherited from `_barge_in_kwargs()` (L183) — `min_interruption_duration`,
  `false_interruption_timeout`, optional `min_interruption_words`/`resume_false_interruption`. A
  command call NEEDS barge-in (the manager interrupts "ruko, na" mid-confirmation) — keep it ON exactly
  as tuned. The **one** deliberate deviation: during PIN/OTP digit capture (S2/S6), barge-in/false-
  interruption is irrelevant; what matters is recording suppression (§4.4).
- **One real difference from outbound:** the system prompt persona is the **inbound business-assistant**
  (§13), and the LLM call here is the CommandEngine NLU (closed-enum IntentMatch, master §22), NOT a
  sales pitch. The opener is generated short + Hinglish like `_llm_opener` (L282) but greets with the
  business headline (S3), not a sales hook. **Keep the prompt SMALL** — a big prompt busts Groq's prompt
  cache → 2.5s TTFT spikes (`agent.py` L659-663 lesson). The NLU prompt is the master §22 schema + a
  tight intent enum, nothing more.

### 3.4 STT partials and the turn
Sarvam STT streams **partials**; the CommandEngine NLU fires only on the FINAL utterance at end-of-turn
(decided by the LiveKit `turn_detector` / VAD per `_resolve_turn_detection`). Partials are used only for
UI/transcript liveness and barge-in detection — never to trigger an action (a partial could be a
half-spoken command). This matches the outbound agent's per-turn model and adds zero latency: the NLU is
the same single Groq call the outbound LLM makes, on the same hot path.

---

## 4. PIN OVER VOICE — spoken digits AND/OR DTMF + the confirmation turn (master §7)

### 4.1 Spoken-PIN path (`verify_mode:"voice_pin"`)
`collect_spoken_digits(n)` listens for the next utterance, extracts digits from the STT text (Sarvam
transcribes spoken Hindi/English numbers; normalize "do hazaar" / "five" / "५" → digits with a tiny
deterministic number-word map — NO LLM on the hot path), masks them in all logs/transcript as `"****"`,
verifies via `firewall.check_pin(tenant, pin)`, and discards the digits from memory immediately.

### 4.2 DTMF path (`verify_mode:"dtmf"`) — PREFERRED for the secret (factual, LiveKit-native)
LiveKit SIP supports **DTMF touch-tone** capture natively, and the inbound dispatch rule even supports a
**built-in DTMF PIN gate** (`dispatchRuleDirect.pin` → LiveKit plays "enter PIN", collects digits until
`#`, re-evaluates — verified via LiveKit SIP docs `inboundCall.pinPrompt` / `DispatchRequestPin`). Two
ways to use it:
- **In-agent DTMF (recommended):** the `manager` agent receives DTMF digit events (LiveKit data/`sip`
  events → surfaced to our worker; also mirrored via `POST /voice/events` from the carrier). Digits
  arrive as **events, never as audio through STT** → the PIN never transits Sarvam or any recording.
  This is the strongest leak-proof channel and is the default for high-value tenants.
- **Dispatch-rule PIN gate (optional pre-room gate):** LiveKit's native `dispatchRuleDirect.pin` can
  front the room — but it's a STATIC PIN per rule, not a per-tenant hashed PIN, so we do NOT use it as
  THE auth (it can't read `firewall.check_pin`). It's only viable as a coarse "is this even a real
  caller" speed-bump; the real, per-tenant, hashed-PIN check stays in-agent (S2/S6).

### 4.3 Lockout (master §7 "rate-limit; lock after repeated wrong")
- `failed_pin_attempts` + `locked_until` live on `ai_manager_authorized_users` (master §8) — the
  AUTHORITATIVE counter on the dedicated service's PG (FORCED RLS). After `MAX_PIN_ATTEMPTS` (default 3)
  in a window → set `locked_until = now + LOCK_TTL` (default 900s), speak the lockout line, end the call.
- A per-call fail-fast counter (in-session) drives the re-prompt/abort UX; the PG `locked_until` enforces
  the real cross-call lockout (a new call from a locked number is rejected at S1 before any prompt).
- Every fail audited (`aim.voice.auth_fail` / `aim.voice.stepup_fail`). PIN is reset ONLY via the secure
  dashboard / OTP (master §7), never over the voice line.

### 4.4 PIN hygiene — TEXT *and* AUDIO (the secret travels as speech AND can hit the recording)
A **spoken** PIN transits the Sarvam STT pipeline AND any call recording — so even with the transcript
masked to `"****"`, the code can leak into the recording file and the STT intermediate. Required hygiene:
- **Suppress recording around digit capture.** The state machine pauses the recorder/egress (§5) for the
  exact S2 and S6 PIN/OTP-collection turns (`recorder.pause()` before `collect_digits`, `resume()`
  after); digits are consumed in-memory only and never written to the transcript or session row.
- **Prefer a channel that never transits STT for the secret:** order of preference (a) **DTMF**
  (§4.2 — digits as events, never audio), (b) **OTP** via SMS/WhatsApp (`amr:"otp"` step-up, the code is
  generated+verified server-side, spoken back only as possession proof), (c) spoken voice-PIN with
  recording suppressed as the fallback. `ai_manager_profiles.verify_mode` defaults high-value tenants to
  DTMF/OTP.
- **Text masking** stays everywhere: digits stored as `"****"` in transcript/session, never persisted,
  verified by `firewall.check_pin` (salted hash). Never log/return raw (master §7/§8).

### 4.5 The confirmation turn (master §7 "AI summarizes → 'Should I continue?' → high risk → PIN after confirm")
Order is **PIN-then-confirm** for L3 (S6 → S7): the manager proves intent with a fresh scoped step-up
FIRST, then hears the exact consequence read back and says "haan/na". For L1/L2 it's confirm-only (S7)
unless tenant policy demands PIN. The confirm always states the **amount + scope** in plain Hinglish so
the human can't be tricked by an under-specified command (§13 example: *"Confirm karu? Meta budget
₹1,000/day campaign Urban Nest ke liye. Haan ya na?"*).

---

## 5. TRANSCRIPT + RECORDING CAPTURE INTO `ai_manager_sessions` (master §8)

### 5.1 Transcript (live, in the worker)
Each finalized turn (user + agent) appends to an in-memory turn buffer
`{role, text, ts}` (PIN digits ALWAYS `"****"`). On `S_END`, the worker writes the full
`transcript_text` + the per-command rows into `ai_manager_sessions` / `ai_manager_commands` (master §8).
For crash-safety (a hard exit-255 skips a shutdown hook — `agent.py` memory lesson #6), flush the
session row **incrementally** after each completed command turn, not only at hangup.

`ai_manager_sessions` row (master §8 fields):
```
id, vendor_id, user_id?, channel='phone', provider_call_id, caller_phone,
status(active|completed|failed|blocked), started_at, ended_at,
transcript_text, stt_provider='sarvam', tts_provider='elevenlabs|sarvam', llm_provider='groq',
metadata: { recording_url?, n_turns, n_actions, lang_detected, latency_p95_ms, trunk_id }
```
Each command → `ai_manager_commands` (raw_text, normalized_text, detected_intent, action_type,
action_payload, risk_level, status, pin_required, pin_verified, confirmation_status, cost_estimate,
execution_result, idempotency_key). Audit rows → `ai_manager_audit_logs` (immutable). This is the
dedicated service's OWN PG schema (`ai_manager_*`, FORCED RLS) — it ABSORBS the JSONL-session shape the
thin `/ai-manager` module used (§0).

### 5.2 Recording (LiveKit Egress → callback)
The inbound room can be recorded via **LiveKit Egress** (room composite or audio-only track egress) to
the configured object store — started when the session enters S3 (after auth, so the auth turn that may
contain a spoken PIN is excludable) and **paused around every PIN/OTP capture** (§4.4). When egress
finishes, LiveKit fires a recording-ready event → our `POST /voice/recording` writes
`metadata.recording_url` + duration onto the session row. Recording is **dormant-until-configured**
(`AIM_RECORDING_ENABLED` + an egress/object-store config); with it off, sessions still capture the
transcript and the voice path works unchanged. Compliance: recording consent + retention follow the
platform's existing call-recording posture (the Conversation-Intelligence module).

### 5.3 The session ships to the management surface
`GET /ai-manager/sessions` + `/sessions/:id` (master §10, already stubbed in the thin module) read these
rows for the dashboard Session-Detail page (full transcript, command chain, recording link, audit
timeline). PIN masked everywhere.

---

## 6. HINGLISH BUSINESS-ASSISTANT RESPONSE STYLE (master §13)

The inbound persona is a **real business assistant, not a robotic IVR and not a sales agent**. System-
prompt rules (kept SMALL for prompt-cache / latency):
- **Short turns, natural Indian business tone, Hinglish when the caller uses it** — mirror the caller's
  language (the model mirrors language itself; STT `language="unknown"` + multilingual LLM, exactly the
  outbound agent's cache-safe approach, NOT a per-turn prompt rewrite — `agent.py` L658-668).
- **Confirm key details, never long phone paragraphs.** Summarize risky actions (amount + scope) BEFORE
  executing. Ask only the **minimum** missing detail (one clarifying question per turn).
- **Never reveal sensitive on a wrong PIN.** On an unsupported command, say what it CAN do (the mapped
  intent set, master §11), not "I don't understand".
- **Canonical lines (master §13):**
  - Headline: *"Aaj 38 leads aaye. 9 hot, 17 warm, 12 low. Full report WhatsApp bhej du?"*
  - Paid gate: *"Ye paid action hai, apna AI Manager PIN boliye."*
  - Wrong PIN: *"PIN match nahi hua, ye action execute nahi kar sakta."*
  - Bulk confirm: *"42 hot leads, est ₹X, calling start karu?"*
- The opener (S3) is LLM-generated short Hinglish like `_llm_opener` but **business-headline first**, no
  sales hook. Numbers spoken in natural spoken form (the outbound prompt already does spoken-form numbers).

---

## 7. DATA / CONFIG / DORMANCY (what is inert until creds)

| Knob | Default | Effect |
|---|---|---|
| `AIM_AGENT_NAME` | `manager` | the 2nd worker's `agent_name`; dispatch rule routes the DID here |
| `AIM_INBOUND_TRUNK_ID` | unset | **THE founder requirement** — inbound trunk id. Unset → inbound dormant, status `sip:not_configured`, no worker dispatch |
| `AIM_VOICE_DID` | unset | the AI Manager phone number managers call |
| `AIM_VERIFY_MODE_DEFAULT` | `dtmf` | per-tenant override via `ai_manager_profiles.verify_mode` (dtmf|voice_pin|otp) |
| `AIM_MAX_PIN_ATTEMPTS` / `AIM_LOCK_TTL_S` | `3` / `900` | lockout policy (PG-authoritative) |
| `AIM_RECORDING_ENABLED` | `0` | LiveKit Egress recording; off → transcript-only |
| `AIM_NLU_PROVIDER` | `groq` | NLU LLM (groq default; `none` → deterministic keyword stub for the offline test) |
| `AIM_OTP_PROVIDER` | `none` | twilio|msg91|whatsapp for `verify_mode:otp`; none → DTMF/voice-PIN only |

Every external dep is import-safe and returns `{"status":"not_configured"}` until keyed (the `whatsapp.py`
dormant pattern). The full state machine (S0–S_END), auth, PIN gate, permission, risk classification,
recorder-pause, and audit are exercised **offline on stubs** (scripted utterances + DTMF strings,
StubFirewall/StubEngine) with zero keys/network — proving the safety machinery independent of any model
or carrier. The LIVE outbound `agent.py`/`capsy` worker is never imported, dispatched, or restarted by any
of this.

---

## 8. HOW THIS SUPERSEDES / ABSORBS THE THIN `/ai-manager` MODULE
- The thin module (caller.py L4588, `ai_manager/` package) keeps the **management HTTP surface**
  (numbers, sessions list, status) and stays mounted on the monolith for the dashboard.
- The **dedicated AI Manager service** OWNS the 4 `/voice/*` webhooks + the LiveKit `manager` worker +
  the `ai_manager_*` PG schema (sessions move from the thin module's JSONL to `ai_manager_sessions`).
- Migration is additive: the dedicated service writes `ai_manager_sessions`; a one-time backfill folds
  the thin module's JSONL sessions in; the `/ai-manager/sessions` reader switches its source to PG. No
  spine edit to `caller.py` beyond what's already mounted; `agent.py` untouched.

---

## 9. RESIDUAL RISKS (carried, not blockers)
1. **Inbound carrier specifics** — whether VoBiz can auto-dispatch (Wiring A) or only POST an INVITE
   (Wiring B) is carrier-dependent; both are designed. VoBiz **TCP-only** for SIP (UDP=0 responses)
   carries over to the inbound trunk.
2. **DTMF availability over VoBiz** — DTMF-as-events depends on the carrier sending RFC2833/SIP INFO
   digits; if absent, fall back to spoken-PIN (recording-suppressed) — designed, but the leak-proof
   channel is then OTP.
3. **Recording-consent/retention** — defers to the platform's call-recording compliance; recording is
   off by default.
4. **Cross-service identity** — identity lives in the dedicated service's OWN `ai_manager_*` schema; the
   EXECUTE hop (S8) still calls the monolith `/api` over the network with the verified tenant token +
   `X-Step-Up`, per the dedicated-service architecture (not re-designed here — sibling docs own it).
5. **Latency in a 2nd process** — the `manager` worker can co-locate on `famit-livekit` (same box as the
   media plane) so STT/LLM/TTS round-trips match the outbound agent; if it lands on the API box, the
   media→STT hop crosses hosts and may regress p95. Co-locate the worker with LiveKit.

---

## 10. SOURCES
- `AI_MANAGER_MASTER_PROMPT.md` (founder spec: §4 Flow 1, §6 risk L0–L4, §7 security, §8 schema, §10
  webhooks, §11 intents, §13 response style, §22 NLU JSON).
- In-repo verified 2026-06-10: `droplet_work/agent.py` (AgentSession L597-651, WorkerOptions L865-869,
  `_session_kwargs_filter` L168, `_llm_opener` L282, AGENT_NAME L50); `place_call.py` (create_dispatch +
  create_sip_participant); `caller.py` (TRUNK L132, /ai-manager mount L4588-4621, WA webhook HMAC L3737,
  `norm`); `firewall.py`/`auth.py`/`audit.py`/`wallet.py` design + code.
- Memory: `famit-voice-agent-working-setup.md` (TCP trunk, RTP fw, latency knobs, voice settings);
  `brain/patterns.md` CRM-CORE (`_match_forms` silent-join fix); `brain/decisions.md` (P2 voice brain,
  cache-safe language mirroring).
- LiveKit SIP docs (context7 `/livekit/sip`, 2026-active): inbound trunk + `create-sip-dispatch-rule`;
  `DispatchRequestPin` / `inboundCall.pinPrompt` native DTMF-PIN; SIP participant attributes
  `sip.phoneNumber` / `sip.trunkPhoneNumber` / `sip.callID` / `sip.trunkID`. LiveKit Egress for recording.
- Sibling designs (do not duplicate): `design/platform-ai-manager.md` (voice front-door, prior pass),
  `design/automation-aimanager.md` (orchestration brain / CommandEngine target),
  `design/credit-ledger-firewall.md` (firewall/wallet), `design/platform-crm-core.md` (`_match_forms`).
```
