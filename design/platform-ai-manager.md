# `ai-manager` — Voice Command Center — Execution-Ready Design Spec

**Status:** READY-TO-BUILD design. PLANNING only (no code shipped, no live deploy). Verified against
live source on disk 2026-06-09 (`C:\Users\kunal\Desktop\caps\droplet_work\`).
**What this is (one line):** the **voice-first command center** for the platform — a vendor *calls a
phone number*, speaks natural commands ("call all my hot leads", "launch a campaign for my 2BHK",
"bump budget on the best ad", "today's revenue"), and the AI Manager **verifies who is calling →
loads their business context → checks permission → demands a spoken 4-digit PIN/OTP for any risky
action → delegates to the AI-workforce agents → executes across modules → reads the result back**.
**Security-critical.** It is the highest-privilege human-facing surface in the platform: a phone call
that can spend money and trigger bulk outreach.

**This spec is the INBOUND VOICE FRONT-DOOR. It is NOT a second brain.** It deliberately does NOT
reimplement planning, spend caps, approval logic, or ad adapters — those live in the already-designed
**`aimanager` orchestration meta-agent** (`design/automation-aimanager.md`) and the **Action Firewall +
Wallet ledger** (`design/credit-ledger-firewall.md`). This module is the *mouth and ears*: speech →
verified intent → a gated call into those existing engines → speech back. Build it on top; do not fork it.

**Hard invariants honored (same as the rest of the repo):**
- Does **NOT** edit the voice spine `agent.py` or the API spine `caller.py`/`auth.py`. All new code lives
  under `droplet_work/automation/ai_manager_voice/`. The one line that registers the inbound agent and
  the few lines that mount endpoints ship as **written, un-applied diffs** (`*.diff`) for the orchestrator
  to apply when "final wiring" is un-deferred.
- **Dormant-until-creds.** Every external dependency (inbound SIP trunk creds, the reasoning LLM, the
  SMS/WhatsApp OTP channel) is provider-agnostic and import-safe; each returns `{"status":"not_configured"}`
  until keys are pasted — exactly like `whatsapp.py`, the canonical pattern in this repo.
- **Offline acceptance** runs the entire command→verify→PIN→delegate→report state machine deterministically
  with **zero keys and zero network** (no LiveKit room, no LLM, no telephony), proving the *safety machinery*
  independent of any model or carrier.

---

## 0. GROUND TRUTH — what already exists on disk (cited; do not trust memory)

Verified 2026-06-09 against `droplet_work/`. This module is a thin composition over all of it.

> **HONESTY MARKER (see "## RED-TEAM FIXES (folded)" §C):** not every row below is *built code*. Two
> classes are mixed in this table. **BUILT on disk (Globbed, real `.py`):** `agent.py`, `auth.py`,
> `audit.py`, `whatsapp.py`, `ratelimit.py`, `caller.py`, `db/models.py`. **DESIGNED-ONLY (no `.py` yet —
> spec-on-spec dependency):** `firewall.py` (exists as `design/credit-ledger-firewall.md`), the
> `automation/aimanager/` engine (exists as `design/automation-aimanager.md`), and the `aiwf/` workforce
> spine (`design/platform-ai-workforce.md`). This module therefore depends on three sibling specs being
> built first — see build-order caveat in the folded fixes.

| Asset | Path / line | What ai-manager-voice reuses |
|---|---|---|
| **LiveKit voice agent** | `agent.py` (874 ln) | `entrypoint(ctx: JobContext)`, `AgentSession(stt=sarvam.STT, llm=groq.LLM, tts=…)`, dispatch-metadata parsing (`ctx.job.metadata` JSON), prompt-from-fields, `WorkerOptions(entrypoint_fnc=…, agent_name=AGENT_NAME)` (L865-867). **We register a SECOND worker with a different `agent_name` ("manager") and a different entrypoint** — inbound persona, command tools. The outbound telecaller is untouched. |
| **Identity / JWT / roles** | `auth.py` (233 ln) | `issue_pair(tenant)`, `resolve_token(cred)`, `access_claims(cred)`, role model (`role`, `is_admin`, tenant-scoped). The voice session **mints a real, short-lived tenant access token** for the verified caller via `issue_pair()` and acts as that tenant for every delegated call — never an anonymous "system" identity. |
| **Action Firewall (PIN/OTP step-up)** | `design/credit-ledger-firewall.md` §6 → `firewall.py` | **THE risk gate, reused verbatim.** `mint_step_up(tenant, scope)` / `verify_step_up(req, scope)` (HS256 token, `amr:"pin"`/`"otp"`, scope, 300 s TTL), PIN store `var/pins.json` (salted sha256, never plaintext), `POST /firewall/step-up`, `require_step_up(scope)` guard, audited `firewall.stepup.fail`, OTP-over-WhatsApp stub. **The voice flow collects the spoken PIN, calls `firewall.verify_pin()` → mints the step-up token → presents it on the delegated action.** No new PIN logic. |
| **Orchestration brain (delegation target)** | `design/automation-aimanager.md` → `automation/aimanager/` | The plan→approve→execute loop, the **tool registry** (`campaigns.create`, `leads.enqueue_calls`, `whatsapp.send`, `ads.set_budget`, `analytics.read`, …), the deterministic spend guardrails, and the ad adapters. **The voice command center DELEGATES here.** It does not own tools or caps. A voice command maps to a `Plan` (or a single tool action) handed to `orchestrator` with an attached step-up token. |
| **Immutable audit** | `audit.py` (L60 `record(actor, action, object_type, object_id, …, meta)`, L102 `tail(action_prefix="")`) | Every voice turn that mutates state writes here with new action names `aimanager_voice.*`. Append-only JSONL, never raises. |
| **Wallet / spend ledger** | `design/credit-ledger-firewall.md` §wallet | Internal call/WhatsApp actions debit the metered credit ledger; external ad spend hits the Postgres atomic-decrement cap. The voice layer triggers these; it never re-implements the money math. |
| **Dormant-integration template** | `whatsapp.py` (319 ln) | EXACT shape for the inbound-SIP config reader, the LLM intent-parser driver, and the SMS/WhatsApp OTP sender: `_cfg()` env read, `is_configured()`, no-op `{"status":"not_configured"}`, never raises, `redact()` secret hygiene. |
| **Rate-limit substrate** | `ratelimit.py` + redis:6380 (P0) | reused to throttle PIN attempts per caller and per number, and to lock out a number after N failures. |
| **Lead/contact lookup for caller-ID match** | `caller.py` tenant store + `db/models.py` (`Lead`, tenant `phone`) | resolve an inbound caller-ID → a registered manager phone → tenant + role. |

**Net:** ai-manager-voice introduces **one new LiveKit worker persona**, **one new caller-identity +
registered-number store**, **one voice state machine**, and a **thin delegation bridge** into the existing
`aimanager` orchestrator + `firewall`. It adds **no new spend logic, no new tools, no new caps, no new ad
code, no spine edits.**

---

## 1. WHY THIS IS A SEPARATE MODULE FROM `automation-aimanager.md` (and how they compose)

`automation-aimanager.md` is the **autonomous ops brain**: a backend tick-loop that *decides on its own
schedule* what to do and runs it under gates. `ai-manager-voice` is the **human-in-the-loop voice front
door**: a person *initiates*, speaks an intent, and the system executes *that one intent* (after
verifying identity + permission + PIN). Same engine underneath, two front-ends:

```
        ┌─────────────────────────────────────────────────────────────────┐
        │                  THE ONE ORCHESTRATION ENGINE                     │
        │  automation/aimanager/  (plan→approve→execute, tools, guardrails) │
        │  + firewall.py (PIN/OTP step-up)  + wallet ledger  + audit.py     │
        └───────────────▲───────────────────────────▲──────────────────────┘
                        │                            │
       autonomous tick  │                            │  human voice command
   (cron / Hatchet)     │                            │  (this spec)
        ┌───────────────┴────────┐      ┌────────────┴───────────────────────┐
        │ orchestrator.run_tick()│      │ ai_manager_voice  (LiveKit inbound) │
        │  (background brain)    │      │  verify → context → permit → PIN →  │
        └────────────────────────┘      │  delegate → execute → speak result  │
                                        └─────────────────────────────────────┘
```

Both produce the **same gated, audited actions**. The voice layer's job is purely: **turn speech into a
*verified, permissioned, PIN-backed* call into the engine, and turn the engine's result back into speech.**
It reuses the engine's guardrails wholesale — the model on the phone *cannot* spend more than the caps, can't
skip the PIN, can't act for a tenant it didn't authenticate as. The phone is just a new, high-trust trigger.

**On "delegate to the AI-workforce agents":** the platform vision names an "AI workforce" of agent *roles*
(AI Telecaller, WhatsApp Salesperson, Ad Operator, Campaign Strategist, …). **That role framework IS
concretely designed** — see `design/platform-ai-workforce.md` (the `AgentRunner` + `RoleSpec` +
scoped `ToolRegistry` spine; verified on disk 2026-06-09). **See "## RED-TEAM FIXES (folded)" below for the
corrected delegation target.** In short: this voice layer's `delegate.py` hands its *verified, permissioned,
PIN-backed* `Intent` to the workforce spine's surviving `aiwf/manager/delegate.py`, which selects the right
`RoleSpec` and calls `AgentRunner.run(role=…)` (the one runner that re-enforces the single `guardrails.check`
gate for every actor). The `aimanager` engine referenced throughout this doc is, per the workforce design,
**the `ops_manager` role** on that same runner — not a separate engine the voice layer talks to directly.
The interface is unchanged either way (a verified `Intent` in, a result out), so no change to the state
machine or gates; only the `delegate.py` target is re-pointed (folded below).

---

## 2. CHOSEN TOOLS & WHY (web-researched, 2026-active, cited)

### 2.1 Telephony / voice transport: **reuse the existing self-hosted LiveKit stack — inbound SIP**
The platform already runs self-hosted **LiveKit + LiveKit SIP** for the outbound telecaller (`agent.py`,
`agent_name="capsy"`). LiveKit SIP supports **inbound trunks + dispatch rules** that route a PSTN call to a
named agent — this is first-class and current. We add an **inbound SIP trunk** + a **dispatch rule** that
routes calls to the registered manager numbers to a new agent worker named `"manager"`. No new media stack.
- **STT:** reuse `sarvam.STT` (already wired, Hindi/Indic-strong — managers speak Hinglish). **TTS:** reuse
  the existing configurable TTS. **LLM (intent):** reuse `groq.LLM` by default (already integrated,
  cheap, low-latency) behind the provider-agnostic driver; Claude optional for harder reasoning.
- Sources: LiveKit Docs — [SIP inbound trunk](https://docs.livekit.io/sip/trunk-inbound/),
  [Dispatching agents to calls / explicit agent dispatch](https://docs.livekit.io/agents/start/telephony/),
  [Inbound calls quickstart](https://docs.livekit.io/sip/quickstarts/configuring-sip-trunk/).

### 2.2 Agent persona / tool-calling: **LiveKit Agents `@function_tool`**, thin and explicit
The inbound persona is a LiveKit `Agent` whose **function tools are deliberately narrow**: `who_am_i`
(verify), `load_business_context`, `propose_action` (parse intent → structured action), `request_pin`,
`submit_pin`, `confirm_and_execute`, `report`. The agent does **not** get a generic "do anything" tool —
each capability is a typed function the state machine gates (Anthropic agent-design guidance: promote
hard-to-reverse actions to dedicated, typed tools, never a generic escape hatch). The LLM proposes; the
**deterministic state machine + firewall decide**.
- Sources: LiveKit Docs — [Tool definition & use (`@function_tool`)](https://docs.livekit.io/agents/build/tools/),
  [Workflows / handoffs](https://docs.livekit.io/agents/build/workflows/).

### 2.3 Intent parsing: **provider-agnostic LLM driver, dormant-until-creds** (default Groq)
One interface `intent/driver.py` (mirrors `whatsapp.py`). `parse_intent(utterance, ctx) -> IntentMatch`
returns one of a **closed set** of command intents (enum) + extracted slots — never free-form code.
Unknown/ambiguous → `clarify`. Default provider `groq` (integrated); `claude` optional (model
`claude-opus-4-8`, adaptive thinking, manual tool-use loop, `output_config.format` for the structured
IntentMatch — **no** `budget_tokens`/`temperature`/`top_p` on Opus 4.8); `none` → deterministic
keyword-matcher stub (offline path). Selection: `AIM_VOICE_LLM_PROVIDER = groq|claude|none` (default `none`).

### 2.4 OTP delivery: **reuse the firewall's OTP path** (SMS or WhatsApp, dormant)
The firewall already specifies an OTP-over-WhatsApp stub with the same `amr:"otp"` step-up token shape. We
add an SMS provider option (provider-agnostic `otp/sender.py`: `twilio|msg91|whatsapp|none`) for managers
who'd rather receive an SMS code than speak a memorized PIN. Dormant until a key exists. Cite:
[Twilio Verify](https://www.twilio.com/docs/verify), [MSG91 OTP](https://docs.msg91.com/otp) (Indian SMS).

### 2.5 Rejected
Twilio/Vonage **media** stack (we already self-host LiveKit — no second telephony plane); Bland/Vapi/Retell
(SaaS voice-agent platforms — we own the stack and the brain; they'd re-host our money-spending logic
off-box); a generic "LLM with shell/HTTP" agent (unacceptable on a money surface).

---

## 3. ARCHITECTURE & DIRECTORY LAYOUT (all new; nothing in the spine edited)

```
droplet_work/automation/ai_manager_voice/
├── __init__.py              # exports: inbound_entrypoint, run_command_offline, status
├── config.py                # env: provider selection, registered-number store path, PIN attempt caps, flags
├── inbound_agent.py         # LiveKit Agent persona + @function_tool set + WorkerOptions(agent_name="manager")
├── state_machine.py         # THE core: VERIFY → CONTEXT → INTENT → PERMIT → PIN → CONFIRM → DELEGATE → REPORT
├── identity.py              # caller-ID → registered number → tenant + role; verification (PIN/OTP/voice-PIN)
├── registry.py              # registered-phone-number store (own JSONL) + per-number permission grants
├── intent/
│   ├── __init__.py
│   └── driver.py            # provider-agnostic intent parser: groq | claude | none (dormant)
├── otp/
│   ├── __init__.py
│   └── sender.py            # provider-agnostic OTP: twilio | msg91 | whatsapp | none (dormant)
├── delegate.py              # bridge → automation/aimanager/orchestrator (+ attaches step-up token); maps intent→Plan/action
├── firewall_bridge.py       # thin wrapper over firewall.py: verify_pin / mint_step_up / require for an action scope
├── audit_bridge.py          # wrapper over audit.py — action names aimanager_voice.*
├── endpoints.py             # FastAPI APIRouter (additive): number registration, status, transcript fetch — mounted via diff
├── wiring/
│   ├── caller_endpoints.diff # un-applied: app.include_router(aimanager_voice_router)
│   └── sip_dispatch.md       # un-applied ops recipe: create inbound trunk + dispatch rule -> agent_name "manager"
└── tests/
    └── test_offline.py       # offline acceptance (§9): full state machine, zero keys, zero network
```

### 3.1 Two LiveKit workers (the key structural fact)
`agent.py` registers `WorkerOptions(entrypoint_fnc=entrypoint, agent_name="capsy")` for **outbound**
telecalling. We register a **second** worker — `inbound_agent.py` with
`WorkerOptions(entrypoint_fnc=inbound_entrypoint, agent_name="manager")`. A LiveKit **inbound dispatch
rule** routes any call arriving on the AI-Manager DID to `agent_name="manager"`, so the two personas never
collide. The outbound telecaller is byte-unchanged. Both share the same STT/TTS/LLM vendor wiring.

### 3.2 CROSS-PLANE TRANSPORT — the load-bearing decision (the voice box is NOT the API box)
**This is the difference between a spec that demos single-process and one that works deployed.** The settled
"planes" architecture puts the **voice plane** (LiveKit agent workers, the `famit-livekit` droplet) on a
**separate host** from the **control-plane API** (`caller.py` + `firewall.py` + `auth.py` + the `aimanager`
engine, the box at `168.144.153.145`). Therefore the voice worker **cannot** reach its dependencies via a
local file or `localhost` loopback — a number registered on the dashboard (API box) writes a JSONL the voice
box never sees; `firewall.verify_pin` on the voice box would read an empty local `var/pins.json`; the engine
is not on `localhost`. **All three hops (identity/registry, PIN/step-up, delegation) MUST be authenticated
network calls to the control-plane API**, exactly the `AIMANAGER_SERVICE_TOKEN` pattern the sibling
`automation-aimanager.md` red-team already mandated — but addressed to the **API base URL** (`AIM_VOICE_API_BASE`),
**not** `localhost`, **not** a local file:

| Hop | WRONG (single-box assumption) | RIGHT (cross-plane) |
|---|---|---|
| caller-ID → registered number | read local `var/aim_voice_numbers.jsonl` | `GET {API}/ai-manager/numbers/lookup?phone=…` (service token) — registry is **authoritative on the API box** |
| spoken PIN → step-up token | in-process `firewall.verify_pin` (local `var/pins.json`) | `POST {API}/firewall/step-up` (form `pin`, as the verified tenant) → returns the step-up token; PIN is verified **only on the API box where `var/pins.json` lives** |
| intent → execute | `localhost` loopback to engine | `POST {API}/aimanager/tick` (or the action endpoint) with the tenant token **+ `X-Step-Up`** header |

So `registry.py`/`firewall_bridge.py`/`delegate.py` are **thin HTTP clients to the control-plane API**, each
holding `AIM_VOICE_SERVICE_TOKEN` (a real admin/manager tenant token minted via `auth.issue_pair()`, injected
server-side, never logged/committed; dormant-until-set → live registry returns `{"status":"not_configured"}`
and the offline test runs on stubs). The **PIN never travels to the voice box for local checking** — the
voice agent forwards the spoken digits to the API box's `/firewall/step-up`, which is the only place a PIN is
verified. This keeps the single source of truth on the control plane, preserves the plane split, and means
the only thing co-located with the voice worker is the LLM/STT/TTS clients. (Alternative — co-locating engine
+firewall+registry on the voice box — is explicitly **rejected**: it fragments the money/PIN authority across
two hosts and fights the settled plane boundary.) The **offline test (§9) is single-process by design** and
swaps these HTTP clients for in-memory stubs, which is exactly why it must not be read as proof the live
transport works — that is asserted here and exercised by an integration test once the boxes exist.

---

## 4. THE CALL FLOW — the exact state machine (security-critical, deterministic)

`state_machine.run(session_ctx)` — every transition is code-decided; the LLM only *fills slots*, never
*authorizes*. (Drawn as the literal sequence the spec body requires: intent → business-context →
permission check → PIN/OTP for risky actions → delegate → execute → report.)

```
S0  CONNECT
      caller_id = inbound SIP From-number (E.164)
      audit('aimanager_voice.call_start', meta={caller_id_redacted})

S1  VERIFY IDENTITY  (identity.resolve)
      number = registry.lookup(caller_id)            # registered manager number?
      if not number:  speak("This number isn't registered."); → S_END(reject, 'unregistered')
      tenant  = tenant_by_id(number.tenant_id); role = number.role
      # Caller-ID is NECESSARY but NOT SUFFICIENT (spoofable). Always step up:
      challenge = number.verify_mode                 # 'voice_pin' | 'otp' (per-number policy)
      → S2

S2  AUTHENTICATE THE HUMAN  (anti-spoof; before ANY context is revealed or any action runs)
      if challenge == 'otp':
          code = otp.sender.send(number.contact)     # SMS/WA; dormant→ falls back to voice_pin
          collect spoken 6-digit; firewall.verify_otp(tenant, code)
      else:  # voice_pin
          speak("Please say your 4-digit PIN.")
          pin = collect_spoken_digits(n=4)           # masked in logs ALWAYS
          ok  = firewall.verify_pin(tenant, pin)     # salted sha256 in var/pins.json
      on fail: attempts++; ratelimit; audit('aimanager_voice.auth_fail')
               if attempts >= MAX_PIN_ATTEMPTS (3): lock number TTL; speak; → S_END(reject,'lockout')
               else: re-prompt
      on ok: session_token = auth.issue_pair(tenant)['access_token']   # acts AS this tenant
             audit('aimanager_voice.authed', actor=tenant_id)
             → S3
      # NOTE: this S2 auth proves WHO is calling. A SECOND, fresh step-up (S6) is still required
      # per risky action — login-auth and per-action authorization are distinct (see §6).

S3  LOAD BUSINESS CONTEXT  (read-only; via the engine's analytics.read / billing.read tools)
      ctx = delegate.read_context(tenant, session_token)   # business name, today's leads/calls/revenue,
                                                            # active campaigns, wallet balance, caps remaining
      speak short greeting + headline ("Hi {name}. 12 hot leads today, ₹4,200 wallet, 2 live campaigns.")
      → S4

S4  CAPTURE INTENT  (loop until a clear, single actionable command or hangup)
      utterance = listen()
      match = intent.driver.parse_intent(utterance, ctx)   # closed enum + slots; 'none' provider → stub
      if match.kind == 'query':        answer from ctx (read-only, no gate);  loop S4
      if match.kind == 'clarify':      speak the clarifying question;          loop S4
      if match.kind == 'command':      → S5
      if match.kind == 'goodbye':      → S_END(ok,'hangup')

S5  PERMISSION CHECK  (deterministic RBAC — the engine's `can(tenant, action)` semantics)
      action = delegate.map_intent_to_action(match)        # e.g. ads.set_budget / leads.enqueue_calls
      if not permits(role, number.grants, action):         # role + per-number grant must BOTH allow
          audit('aimanager_voice.permission_denied'); speak("You're not permitted to do that."); loop S4
      risk = classify_risk(action)                         # money|bulk|destructive|export => RISKY; else SAFE
      → S6 if RISKY else S7

S6  STEP-UP FOR RISKY ACTION  (PIN/OTP — FRESH, per-action, scoped)
      # spend / bulk-message / launch-pause-ads / mass-calls / price / refund / export / delete
      speak the EXACT consequence + amount:
          "This will spend up to ₹1,500/day on Google Ads for campaign C2. Say your PIN to confirm."
      pin = collect_spoken_digits(4)   (or OTP per policy)
      step_up = firewall.mint_step_up(tenant, scope=risk_scope) IF firewall.verify_pin(tenant,pin) else None
      if not step_up:  attempts++; lockout policy as S2; audit('aimanager_voice.stepup_fail'); loop/abort
      audit('aimanager_voice.stepup_ok', meta={scope, action})
      → S7 (carry step_up)

S7  CONFIRM  (explicit yes/no read-back — last human checkpoint before side effect)
      speak("Confirm: {natural-language summary incl. amount & scope}. Yes or no?")
      if not yes: audit('aimanager_voice.cancelled'); speak("Cancelled."); loop S4
      → S8

S8  DELEGATE & EXECUTE  (hand to the engine; the engine re-enforces caps independently)
      result = delegate.execute(tenant, session_token, action, step_up_token=step_up)
        # delegate builds a Plan (or single action) and calls automation/aimanager/orchestrator,
        # which re-runs its OWN deterministic guardrails (caps, kill-switch, idempotency) and
        # requires the step_up for money:true actions. The voice layer cannot bypass them.
      audit('aimanager_voice.execute', actor=tenant_id, meta=redact(result))
      → S9

S9  REPORT  (speak outcome; offer next)
      speak(natural-language result: "Done — budget set to ₹1,500/day; 50 hot leads queued for calls.")
      loop S4   (more commands)  OR  S_END(ok) on goodbye

S_END  audit('aimanager_voice.call_end', meta={outcome, n_actions}); hang up.
```

**Safety properties baked into the order:** (1) caller-ID alone never grants access — a fresh PIN/OTP in S2
proves the human *before any business data is spoken*; (2) every risky action gets its **own** fresh,
scoped step-up in S6 (a single login PIN cannot silently authorize ten ad-budget bumps); (3) an explicit
spoken **confirm with the amount read back** (S7) precedes any side effect; (4) the engine re-enforces all
caps/idempotency/kill-switch in S8 — the voice layer is *not trusted* to be the only gate (defense in
depth); (5) lockout after N PIN failures, rate-limited per number; (6) everything is audited with the
verified tenant as `actor`, never "system".

---

## 5. DATA MODEL (no spine schema change)

**Ownership (per §3.2):** the registry and sessions are **authoritative on the control-plane API box** —
written by the §7 registration endpoints (which run on the API box). Voice-side `registry.py` is a **read
client** over the API (`GET /ai-manager/numbers/lookup`), not the owner of a local file. The schemas below
are the records the **API box** persists (JSONL there, mirroring `audit.py`, with the optional PG migration).

### 5.1 Registered number — owned/written by the API box (`var/aim_voice_numbers.jsonl` *on the API box*; last-write-wins)
```json
{
  "number_id": "num_<uuid>",
  "tenant_id": "<org_id>",
  "phone": "+9198XXXXXX21",          // E.164; the manager's caller-ID
  "label": "Owner mobile",
  "role": "manager",                  // manager | admin | operator — scopes what can be commanded
  "verify_mode": "voice_pin",         // voice_pin | otp
  "grants": ["campaigns","leads","whatsapp","analytics","ads:read"],  // per-number capability allow-list
  "verified": true,                   // was the number ownership-verified at registration (OTP)?
  "status": "active",                 // active | locked | revoked
  "registered_by": "<user_id>",
  "registered_at": "2026-06-09T18:00:00+05:30"
}
```
A number is **registered + ownership-verified once** (an OTP sent to it at registration, via the dashboard
endpoint §7) before it can command anything. `grants` is the per-number capability allow-list; the effective
permission for an action = `role allows` **AND** `grants allows`.

### 5.2 Voice session — the voice worker POSTs each completed session to the API box (`POST /ai-manager/sessions`), which persists it to `var/aim_voice_sessions.jsonl`. The voice box keeps no authoritative local copy (it may buffer in-memory mid-call, then ship on `call_end`).
```json
{
  "session_id": "vs_<uuid>", "tenant_id": "...", "number_id": "...",
  "caller_id": "+9198XXXXXX21", "started_at": "...", "ended_at": "...",
  "authed": true, "auth_method": "voice_pin",
  "turns": [{"role":"user","text":"call all hot leads"},{"role":"agent","text":"…"}],  // PIN digits NEVER stored
  "actions": [{"intent":"leads.enqueue_calls","risk":"bulk","stepup":true,"executed":true,"result_status":"ok"}],
  "outcome": "ok", "n_actions": 2
}
```

### 5.3 Auth-attempt lockout — AUTHORITATIVE on the API box (the firewall), not the voice box
The **authoritative** PIN/OTP lockout is the **firewall's**, on the API box: `credit-ledger-firewall.md` §6
already rate-limits `/firewall/step-up` fails (audited `firewall.stepup.fail`) using the API box's redis.
Since PINs are verified **only** there (§3.2), that is the single counter of record — the voice box cannot
hold a second authority, or two counters could disagree. The voice layer keeps **only a fail-fast
convenience** counter in-session (re-prompt/abort UX after N tries in one call); it relies on the API box's
firewall response to enforce the real cross-call lockout (a `/firewall/step-up` that returns "locked" ends
the call). No new authoritative store.

**No new columns in `db/models.py`.** (Optional future migration of registry+sessions to Postgres tables
`aim_voice_numbers` / `aim_voice_sessions` is noted, not required — same posture `audit.py` takes about its
own JSONL.)

---

## 6. SECURITY / GUARDRAILS (this is the whole point of the module)

A phone call that can spend money is the single highest-risk surface in the platform. Layered defenses:

### 6.1 Identity — caller-ID is a hint, never a credential
Caller-ID is trivially spoofable. It is used **only** to *look up which tenant a caller claims to be* and
to choose the verify policy. **Possession of the phone is proven by a fresh PIN/OTP in S2 before any
business data is revealed.** A spoofed caller-ID that doesn't know the PIN gets nothing and is locked out
after N tries.

### 6.2 Login-auth vs per-action authorization are DISTINCT (defense in depth)
- **S2 PIN/OTP** = "this is really the owner" (a session login). It mints a normal short-lived tenant
  **access token** via `auth.issue_pair()` — the voice session now *acts as that tenant*, scoped to its role.
- **S6 step-up PIN/OTP** = "authorize THIS specific risky action, right now" — a **fresh**, **scoped**,
  300-second `firewall.mint_step_up(tenant, scope)` token (`amr:"pin"`/`"otp"`). One per risky action.
  A single S2 login can **never** silently authorize a money action; the caller must re-prove intent with a
  fresh, time-boxed, scope-bound step-up that the downstream engine *also* checks. This mirrors the
  firewall's existing `require_step_up(scope)` posture exactly — the voice layer is just another caller of it.

### 6.3 Risk classification (which actions demand S6 step-up)
`classify_risk(action)` is a **deterministic allow-list table**, never the LLM's opinion:

| Risk | Actions | Gate |
|---|---|---|
| **money** | `ads.create_campaign`, `ads.set_budget` (increase), wallet top-up, any external spend | S6 step-up (scope `spend`) + S7 confirm + engine cap re-check |
| **bulk** | `leads.enqueue_calls` (mass), `whatsapp.send` (broadcast) above per-tick cap | S6 step-up (scope `bulk`) + S7 confirm |
| **destructive** | delete/pause-all, `suppression` mass-add, data **export**, price/refund changes | S6 step-up (scope `destructive`) + S7 confirm |
| **safe** | read queries, single-record edits below thresholds, `ads.pause_campaign` (de-risking) | S7 confirm only (no PIN) — or auto for pure reads |

### 6.4 The model never holds authority
The intent LLM returns a **closed-enum** IntentMatch. It cannot invent a tool, cannot set a budget the caps
disallow, cannot mark its own action "safe", cannot skip S6/S7. Risk class, permission, caps, PIN check, and
the confirm read-back are **all deterministic code**. The phone is a high-trust *trigger*, not an authority.

### 6.5 PIN hygiene — TEXT *and* AUDIO (the secret travels as speech, not just text)
Text masking alone is insufficient: a **spoken** PIN transits the **STT pipeline (Sarvam) and any call
recording**, and this platform has a Conversation-Intelligence / call-recording module — so the code can leak
into the audio file and the STT intermediate even when the transcript shows `"****"`. Required hygiene:
- **Suppress recording during digit capture.** The state machine MUST disable call/STT recording for the S2
  and S6 PIN/OTP-collection turns (pause the recorder around `collect_spoken_digits`), and the digits are
  consumed in-memory only.
- **Prefer a channel that never transits our STT for the secret.** Order of preference:
  (a) **OTP via SMS/WhatsApp** (`verify_mode:"otp"`) — the code is generated and verified on the API box and
  spoken back by the human only as confirmation of possession; (b) **DTMF / keypad entry** for the PIN where
  the SIP path supports it (digits arrive as DTMF events, never as audio through STT); (c) spoken voice-PIN
  only as the fallback, with recording suppressed as above. The per-number `verify_mode` policy should default
  high-value tenants to OTP/DTMF.
- **Text masking** stays in force everywhere: PIN/OTP digits are stored as `"****"` in transcripts/sessions,
  never persisted, verified by the API box (`/firewall/step-up` → salted sha256 in `var/pins.json`).
- **Lockout** (`MAX_PIN_ATTEMPTS=3`, `LOCK_TTL=900 s`) per number, redis-backed, plus a global per-tenant
  per-hour ceiling. Every fail audited (`aimanager_voice.auth_fail` / `.stepup_fail`).

### 6.6 Immutable audit (reuse `audit.py`, do not reinvent)
Every transition that matters writes `audit.record(actor=verified_tenant, action="aimanager_voice.<x>", …)`:
`call_start`, `authed`, `auth_fail`, `permission_denied`, `stepup_ok`, `stepup_fail`, `cancelled`,
`execute`, `call_end`. Money/bulk executes carry the action + redacted result + the step-up scope used, so
the spend/approval trail is tamper-evident by construction (append-only JSONL).

### 6.7 DND / compliance / calling-window
Bulk outreach commanded by voice still flows through the engine's existing **DND/suppression + calling-window
+ consent** checks (already in the leads/run path) — voice cannot bypass compliance. A command that would
violate DND is refused at delegate time with a spoken reason.

### 6.8 Kill-switch
The engine's global `POST /aimanager/killswitch` halts all autonomous + voice-initiated side effects; when
on, S8 refuses and the agent speaks "operations are paused by admin." Checked again inside the engine.

---

## 7. ADDITIVE ENDPOINTS (`endpoints.py`, FastAPI APIRouter — mounted via the un-applied diff)

These are for the **dashboard** to manage registered numbers and review voice sessions (the call itself is
LiveKit, not HTTP). Mounted behind the existing auth dependency; risky ones require firewall step-up.

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `POST` | `/ai-manager/numbers` | Register a manager phone (sends ownership OTP) | manager+ |
| `POST` | `/ai-manager/numbers/{id}/verify` | Confirm ownership OTP → mark verified | manager+ |
| `GET`  | `/ai-manager/numbers` | List registered numbers + grants + status | manager+ |
| `GET`  | `/ai-manager/numbers/lookup` | **caller-ID resolution hop (§3.2):** `?phone=` → number record + tenant + role + grants, or 404 | **service token** (voice worker) |
| `POST` | `/ai-manager/numbers/{id}/grants` | Set per-number capability allow-list | admin + step-up |
| `POST` | `/ai-manager/numbers/{id}/revoke` | Revoke / lock a number | admin + step-up |
| `POST` | `/ai-manager/sessions` | **voice worker ships a completed session (§5.2)**; PIN-masked | **service token** (voice worker) |
| `GET`  | `/ai-manager/sessions` | List recent voice sessions (transcripts, PIN masked) | manager+ |
| `GET`  | `/ai-manager/status` | Dormancy/config: SIP configured?, LLM provider, OTP provider, caps | manager+ |

`wiring/caller_endpoints.diff` (the only thing that ever touches `caller.py`, delivered un-applied):
```diff
+ from automation.ai_manager_voice.endpoints import router as aimanager_voice_router
  ...
+ app.include_router(aimanager_voice_router)   # additive; behind existing auth deps
```
`wiring/sip_dispatch.md` — ops recipe (un-applied): create the LiveKit **inbound SIP trunk** for the
AI-Manager DID, then a **dispatch rule** routing it to `agent_name="manager"`; register the second worker.

---

## 8. DORMANT-UNTIL-CREDS MODULES (interfaces)

### 8.1 `intent/driver.py` (mirrors `whatsapp.py`)
```python
def is_configured() -> bool          # provider != none AND its key present
def status() -> str                  # configured | not_configured | error
def parse_intent(utterance: str, ctx: dict) -> dict
  # provider=none  -> deterministic keyword/regex matcher (offline path; closed enum)
  # provider=groq  -> OpenAI-compatible chat w/ structured output -> IntentMatch
  # provider=claude-> claude-opus-4-8, adaptive thinking, output_config.format=INTENT_SCHEMA; NO temperature
  # NEVER raises; on error -> {"kind":"clarify","reason":"error:<redacted>"}
```
`IntentMatch` is a **closed schema**: `kind ∈ {query,command,clarify,goodbye}`, `intent ∈ <enum of mapped
engine actions>`, `slots:{...}`, `confidence`. Anything off-enum or low-confidence → `clarify`.

### 8.2 `otp/sender.py` (mirrors `whatsapp.py`)
```python
def is_configured() -> bool
def send(to_e164: str) -> dict   # twilio|msg91|whatsapp; none -> {"status":"not_configured"} (falls back to voice_pin)
def verify(to_e164: str, code: str) -> dict   # for provider-side verify (Twilio Verify); else firewall.verify_otp
```

### 8.3 Inbound SIP config (`config.py`)
Reads `AIM_VOICE_SIP_TRUNK_ID`, `AIM_VOICE_DID` (the AI-Manager phone number), `AIM_VOICE_AGENT_NAME`
(default `"manager"`). When the trunk id is absent, `status()` reports `sip:not_configured` and the worker
does not register an inbound dispatch — the module is import-safe and inert.

---

## 9. OFFLINE ACCEPTANCE TEST (`tests/test_offline.py`) — ZERO keys, ZERO network

Run: `python -m pytest droplet_work/automation/ai_manager_voice/tests/test_offline.py -q`
Must pass with **no env keys, no LiveKit, no LLM, no telephony**. Drives `state_machine.run()` with an
injected fake transport (scripted utterances + DTMF-like digit strings) and `StubDelegate`/`StubFirewall`.

1. **Import-safe & dormant:** import the package; `intent.driver.status()=="not_configured"`,
   `otp.sender.is_configured() is False`, SIP `status()=="sip:not_configured"`; no exception.
2. **Unregistered caller rejected:** caller-ID not in registry → state machine ends `reject:unregistered`,
   no context revealed, audit `call_start`+`call_end` only.
3. **Wrong PIN locks out:** 3 wrong PINs → `reject:lockout`, redis lock key set, audit shows 3
   `auth_fail`; **no business context was ever spoken** before auth succeeded.
4. **Happy read path:** registered number + correct PIN → authed; a `query` intent ("today's revenue") is
   answered from `StubDelegate` context with **no step-up** and **no execute**.
5. **Risky action requires step-up + confirm:** command "set Google budget to ₹1,500/day" →
   permission ok → classified `money` → **parked for PIN**; supplying the correct PIN mints a step-up
   (scope `spend`); the **confirm read-back states ₹1,500**; on "yes", `delegate.execute` is called **with
   the step-up token attached**; audit order = `authed → stepup_ok → execute`.
6. **Step-up cannot be skipped / model cannot self-authorize:** a malformed IntentMatch claiming
   `risk:"safe"` for an `ads.set_budget` action is re-classified `money` by deterministic
   `classify_risk` and still demands the PIN — the model's risk label is ignored.
7. **Permission denied:** a number whose `grants` excludes `ads` issues an ads command → `permission_denied`,
   no PIN prompt, no execute.
8. **PIN never persisted (text):** assert the session record's transcript and digits are masked (`"****"`);
   grep the written JSONL for the test PIN → **zero hits**.
8b. **PIN audio suppressed:** assert the state machine calls `recorder.pause()` (a stub) around every
   `collect_spoken_digits` turn and `recorder.resume()` after — i.e. the recorder was paused for the exact
   span the PIN was spoken (the code never reaches the recording/STT-persistence layer). With `verify_mode:"otp"`
   or DTMF, assert the PIN digits never enter the STT-input path at all.
9. **Engine re-enforces caps (defense in depth):** with `StubDelegate` configured to reject over-cap, a
   confirmed money action above the cap is refused by the engine even though the voice layer passed it,
   and the agent speaks the cap rejection.

A tiny `selftest_bad_intent` feeds the parser garbage and asserts it returns `clarify` (never executes) —
proving the closed-enum gate without an LLM (mirrors the repo's `eval/selftest_bad_model.py` convention).

---

## 10. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

Nothing here is needed to **build** or to pass the **offline test**. These light up dormant modules.
**All server-side only — paste into the droplet env/secret store, never the frontend, never git.**

### A. Inbound telephony (the phone number managers call)
- A **DID / phone number** for the AI Manager, provisioned on the existing LiveKit SIP trunk (or a new
  inbound trunk). Env: `AIM_VOICE_DID`, `AIM_VOICE_SIP_TRUNK_ID`. (Reuses the self-hosted LiveKit + SIP
  already running for outbound — typically just a new number + an inbound dispatch rule.)

### A2. Cross-plane wiring (REQUIRED for live — the voice box talks to the API box; see §3.2)
- `AIM_VOICE_API_BASE` — base URL of the control-plane API box (where `caller.py`/`firewall.py`/engine run),
  e.g. `https://api.internal/…`. **Not `localhost`** — the voice worker is on a different host.
- `AIM_VOICE_SERVICE_TOKEN` — a real admin/manager tenant **access token** minted via `auth.issue_pair()`,
  injected server-side only (never logged/committed). Dormant-until-set → registry/firewall/delegate clients
  return `{"status":"not_configured"}` and the offline test runs on stubs.

### B. Intent LLM (pick ONE; or leave blank → deterministic stub matcher)
- **Groq (recommended; already integrated):** `GROQ_API_KEY` (round-robin `GROQ_API_KEY_1..N` already
  supported). Set `AIM_VOICE_LLM_PROVIDER=groq`.
- **Claude (optional, harder reasoning):** `ANTHROPIC_API_KEY`; `AIM_VOICE_LLM_PROVIDER=claude`.

### C. OTP delivery (only if any number uses `verify_mode:"otp"` instead of a spoken PIN; else skip)
- **Twilio Verify:** `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`. Or
- **MSG91 (Indian SMS):** `MSG91_AUTHKEY`, `MSG91_OTP_TEMPLATE_ID`. Or
- reuse the **dormant Meta WhatsApp** pipeline (HANDOFF WAVE A2) for WhatsApp OTP — same `amr:"otp"` token.
- Set `AIM_VOICE_OTP_PROVIDER=twilio|msg91|whatsapp|none` (default `none` → spoken PIN only).

### D. Guardrail / policy config (optional — sane defaults shipped)
`AIM_VOICE_LLM_PROVIDER` (`none`), `AIM_VOICE_OTP_PROVIDER` (`none`), `AIM_VOICE_MAX_PIN_ATTEMPTS` (`3`),
`AIM_VOICE_LOCK_TTL_S` (`900`), `AIM_VOICE_AGENT_NAME` (`manager`). Spend caps, approval thresholds, and the
kill-switch are **inherited from the engine** (`automation-aimanager.md` / firewall) — not redefined here.

### E. Prerequisites already in the repo (no new creds)
PIN store + step-up token = `firewall.py` (`var/pins.json`, `var/secret`). Identity/JWT = `auth.py`.
Audit = `audit.py`. Rate-limit/lockout = `ratelimit.py` + redis:6380. Engine = `automation/aimanager/`.

---

## 11. HOW IT SITS ON THE SETTLED FOUNDATION

- **Voice plane:** runs as a **second LiveKit agent worker** (`agent_name="manager"`) alongside the
  outbound telecaller — same self-hosted LiveKit + SIP, same STT/TTS/LLM vendors. No new media plane.
- **Control-plane API (modular monolith):** registration/session/status endpoints are an **additive
  APIRouter** mounted via the un-applied diff — no new service. Acts as a real tenant via `auth.py` tokens.
- **Hatchet worker-spine:** not required for the synchronous voice path; a *post-call* job (transcript
  summarize, session→Postgres archive, follow-up scheduling) is an optional Hatchet task per
  `orchestration-hatchet.md` — additive, dormant.
- **Postgres:** the **registry is authoritative on the control-plane API box** (see §3.2); it starts as
  JSONL there (mirroring `audit.py`) with a clean optional migration to `aim_voice_numbers` /
  `aim_voice_sessions` tables when the platform is fully on PG. **Authority of record per the cited designs:**
  **PINs live in `var/pins.json`** (salted sha256, `firewall.py` §6) — *file-backed, on the API box*, **not**
  Postgres; the **wallet/spend** authority lives in **Postgres** (`credit-ledger-firewall.md` wallet tables,
  atomic decrement). The voice layer verifies PINs only by calling the API box's `/firewall/step-up` and never
  holds or bypasses either store.
- **Planes boundary:** the voice plane and the control-plane API are **separate hosts** (§3.2); the voice
  layer reaches the engine + firewall + auth + audit **only over authenticated API calls**, owns no money
  math, no ad code, no caps, no PIN store. It is a front-door, replaceable without touching the engine.

---

## 12. WHAT IT REUSES vs ADDS (explicit ledger)

| | REUSES (no new code) | ADDS (new, under `ai_manager_voice/`) |
|---|---|---|
| Voice transport | LiveKit + SIP, `AgentSession`, Sarvam STT, TTS, Groq LLM | inbound persona `inbound_agent.py`, `agent_name="manager"`, dispatch rule |
| Identity | `auth.py` `issue_pair`/`resolve_token`/roles | caller-ID→tenant `identity.py`, registered-number store `registry.py` |
| Risk gate | `firewall.py` PIN/OTP step-up (HS256, `var/pins.json`, `var/secret`) | voice collection of spoken PIN + `firewall_bridge.py` |
| Execution | `automation/aimanager/` orchestrator + tools + guardrails + ad adapters | `delegate.py` intent→Plan bridge (attaches step-up) |
| Spend/caps | wallet ledger + engine caps + DND/suppression | nothing — inherited |
| Audit | `audit.py` append-only JSONL | `audit_bridge.py` (action names `aimanager_voice.*`) |
| Rate-limit | `ratelimit.py` + redis | per-number PIN lockout keys |
| Intent / OTP | — | provider-agnostic dormant drivers `intent/driver.py`, `otp/sender.py` |

---

## 13. HONEST REAL-VS-HYPE

| Claim | Reality |
|---|---|
| "Call a number and run your whole business by voice" | True for the **mapped command set** (campaigns, leads, calls, WhatsApp, ads budget, analytics) — a closed enum of intents wired to engine tools. Not arbitrary natural-language anything; off-enum → "I can't do that yet." |
| "Voice can spend money autonomously" | Only after a **fresh per-action spoken PIN/OTP** + an explicit **spoken confirm with the amount read back** + the engine's own caps/kill-switch re-check. Default posture (firewall/engine): **every rupee of external ad spend is human-confirmed.** |
| "Caller-ID logs you in" | No. Caller-ID is a spoofable hint; a fresh PIN/OTP authenticates the human before any data is spoken. |
| "Replaces the dashboard" | Reduces dependence on it for *commands*; number registration, grants, and audits are still dashboard surfaces. It's a high-trust *trigger*, complementary to the panel. |
| "Works offline" | The full state machine, auth, PIN gate, permission, risk classification, and audit are exercised offline on stubs. Real STT/LLM/telephony obviously need keys — the *safety machinery* does not. |

---

## 14. BUILD ORDER (each a verifiable unit; PLANNING doc — not executed here)

1. `config.py` + `registry.py` + `identity.py` (pure) → unit test caller-ID lookup + permission table.
2. `firewall_bridge.py` + `audit_bridge.py` (thin wrappers) → unit test PIN verify + step-up mint via stubs.
3. `state_machine.py` + `delegate.py` (StubDelegate/StubFirewall) → **offline acceptance test (§9) green.**
   This unit delivers the entire safety spine with no external dependency.
4. `intent/driver.py` (dormant; `none` first, then `groq`, then `claude`) → status() + stub-match test.
5. `otp/sender.py` (dormant) + `endpoints.py` + `wiring/*.diff` (un-applied) → router import + dormancy test.
6. `inbound_agent.py` (LiveKit persona, `agent_name="manager"`) + `wiring/sip_dispatch.md` → live wiring,
   un-deferred only when the founder provisions the DID and pastes keys.

Ship 1–3 first: that is the entire security spine, fully offline-tested, before any phone/LLM/spend is live.

---

## 15. MODULES THIS UNBLOCKS

The voice command center is the **universal front-door** the platform's vision promises. Once live it
directly unblocks / activates:
- **AI Manager (the 34-module command center)** — this IS its voice interface.
- **Campaigns, Leads, AI Voice Calls, WhatsApp Automation** — launch/pace/enqueue by voice.
- **Ad Automation, Billing/Credits/Wallet** — budget changes + balance checks by voice (gated).
- **Analytics/Reports** — spoken daily revenue/lead/funnel readouts.
- **Workflow Builder** — voice becomes a **Trigger** node ("when I call and say X, run workflow Y").
- **Compliance/DND/Consent, Team/Roles/Permissions, AI Quality Review** — every voice action is RBAC-scoped,
  PIN-gated, DND-checked, and lands in the immutable audit these modules read.
- **Notifications/Omnichannel Inbox** — voice sessions + their outcomes surface as inbox items.

---

## RED-TEAM FIXES (folded)

Adversarial review 2026-06-09 against live source on disk (Globbed, not from memory) and the sibling
design docs. Verdict: **NO-GO as originally submitted; GO with the three folds below applied.** The
guardrail design (login-vs-step-up split §6.2, fresh per-action scoped step-up §6.3, recorder-pause for
the PIN audio-leak §6.5, caller-ID-is-a-hint anti-spoof §6.1, cross-plane transport honesty §3.2) is
**sound and preserved unchanged** — these fixes only correct three factual/reuse defects.

**Ownership confirmed (the review's first inversion, corrected):** this doc IS the settled owner of the
voice front-door. `design/platform-ai-workforce.md` top-matter (RT-1, L29-45) explicitly states **"DO NOT
re-implement the voice AI Manager; DELEGATE to the settled `platform-ai-manager.md`"** and *deletes* its own
`aiwf/manager/intent.py` + `voice_cmd.py`, keeping only `aiwf/manager/delegate.py` as a thin handoff target.
(That doc's §9 body, L569+, still describes the deleted files — it is **internally stale**, superseded by
its own RT-1 block. Flagged for that doc's owner; does not affect this one.) So number registration, intent
parsing, the call state machine, and the voice PIN correctly live HERE.

**FIX A — false "no workforce doc" claim (was §1, L84-86).** Original text asserted "There is no
`*workforce*` design doc on disk yet … that role framework is not concretely designed." **This was factually
wrong:** `design/platform-ai-workforce.md` exists and is a complete, ready-to-build spec for exactly that
framework. Corrected in §1.

**FIX B — wrong delegation target (consequent to A).** Original `delegate.py` pointed at
`automation/aimanager/`'s tool registry directly. The settled architecture (`platform-ai-workforce.md`
L20-45) demotes that prototype engine to **the `ops_manager` role on the shared `AgentRunner`**, and routes
ALL actors — autonomous roles, this voice manager, and Workflow-Studio AI nodes — through **one
`guardrails.check` gate** so no front-end can be a side-door around the firewall. **Corrected target:** this
doc's `delegate.py` hands the verified/permissioned/PIN-backed `Intent` to the surviving
`aiwf/manager/delegate.py` → `AgentRunner.run(role=…, trigger="manager_voice")`. This is a **contained
re-point, not a teardown** — the spec already anticipated it (§1: "the target swaps behind the same
interface — no change to the state machine or gates"). The §3 directory, the §4 state machine, all §6 gates,
and the §9 offline test are **unchanged**; only `delegate.py`'s downstream call address moves from
`automation/aimanager/orchestrator` to `aiwf/manager/delegate` (both behind the same `Intent`-in/result-out
contract and the same step-up token). The §3.2 cross-plane HTTP hop is likewise unchanged — it now addresses
the workforce-runner's action endpoint instead of the bare engine, still on the control-plane API box.

**FIX C — §0 GROUND-TRUTH built-vs-designed honesty.** The §0 table mixed *built code* with
*designed-only* deps. Corrected via the HONESTY MARKER added under §0. Specifically: `firewall.py`, the
`automation/aimanager/` engine, and the `aiwf/` spine are **designs, not code on disk** (Glob returned no
`.py`). This module is therefore a **spec-on-spec build**: it cannot be built until `firewall.py`
(`credit-ledger-firewall.md`), the workforce `AgentRunner` (`platform-ai-workforce.md`), and at least the
`ops_manager` tool catalog (`automation-aimanager.md`) are built. **Build-order caveat:** §14's units 1-3
(config/registry/identity/firewall_bridge/state_machine + offline test on stubs) can proceed immediately
against `StubFirewall`/`StubDelegate` — that is the entire safety spine and depends on *no* sibling code.
Units 5-6 (live `delegate.py` + endpoints + SIP) are blocked until the three sibling specs ship real code.

**NON-FIX (deliberately left as-is) — §6.3 risk table.** The voice-side `classify_risk` allow-list is a
deterministic **pre-filter**, backstopped by the engine/runner re-enforcing its own `risk_class`/caps
independently (§4 S8 defense-in-depth), and `platform-knowledge-rag.md` L597 cites §6.3 as an authoritative
gate for the voice path. It is **not** a competing money authority. **Residual (not blocking):** it should
converge to *consuming* the runner's `risk_class` rather than maintaining a parallel table, to remove
long-term drift risk. Noted; not re-engineered here.

**RESIDUAL RISKS (carried, not blockers):**
1. **Spec-on-spec dependency stack** — `firewall.py` + the `aimanager` engine + the `aiwf/` runner are all
   unbuilt designs; this voice layer's live path can't ship until they do (FIX C build-order).
2. **Sibling doc internally inconsistent** — `platform-ai-workforce.md` RT-1 (delete `intent.py`/
   `voice_cmd.py`) vs its stale §9 body (still describes them): re-divergence risk until that doc's owner
   reconciles. Not this doc's fix.
3. **Cross-plane HTTP transport is integration-test-only** — the §3.2 voice-box→API-box hops (registry/
   PIN/delegate) are asserted, exercised only by an integration test once both hosts exist; the §9 offline
   test runs single-process on stubs by design and is **not** proof the live transport works.
4. **Risk-table convergence** (above NON-FIX) — long-term, fold §6.3 into the runner's `risk_class`.

---

## Sources
- LiveKit Docs — [SIP inbound trunk](https://docs.livekit.io/sip/trunk-inbound/),
  [Telephony / agent dispatch](https://docs.livekit.io/agents/start/telephony/),
  [Configuring a SIP trunk (inbound quickstart)](https://docs.livekit.io/sip/quickstarts/configuring-sip-trunk/),
  [Tool definition & use `@function_tool`](https://docs.livekit.io/agents/build/tools/),
  [Agent workflows / handoffs](https://docs.livekit.io/agents/build/workflows/).
- [Twilio Verify (OTP)](https://www.twilio.com/docs/verify) · [MSG91 OTP API (Indian SMS)](https://docs.msg91.com/otp).
- Anthropic claude-api skill (in-repo): model `claude-opus-4-8`, adaptive thinking, manual tool-use loop for
  human-in-the-loop, `output_config.format` for structured output, no `budget_tokens`/`temperature` on Opus 4.8.
- In-repo prior art (verified 2026-06-09): `droplet_work/agent.py` (LiveKit `AgentSession`,
  `WorkerOptions(agent_name=…)` L865-867, dispatch-metadata pattern); `auth.py` (JWT `issue_pair`/
  `resolve_token`/roles); `audit.py` (append-only `record`/`tail`); `whatsapp.py` (dormant-until-creds
  template); `ratelimit.py` + redis:6380. Sibling specs: `design/automation-aimanager.md` (the orchestration
  engine this delegates to), `design/credit-ledger-firewall.md` (`firewall.py` PIN/OTP step-up §6 + wallet).
