# RESEARCH — BEST AI→HUMAN WARM TRANSFER FOR **OUR** LIVEKIT + VOBIZ SIP STACK

> **Status:** READ-ONLY web + on-box research (2026-06-12). No code, no deploy, no git. Writes only this doc.
> **Supersedes the mechanism guesswork in** `plan-research-transfer.md` / `plan-handoff-hotlead.md` /
> `INBOUND-PIPELINE-MASTER-PLAN-V2.md §3` — those concluded "Pattern C, hand-roll a conference." **This doc
> verifies, on the box, that LiveKit ships a FIRST-CLASS warm-transfer primitive (`WarmTransferTask`) that
> already does Pattern C/B for us — so we DON'T hand-roll the conference.** That is the headline update.
>
> **#1 RULE (absolute):** every capability here is **ADDITIVE + ISOLATED** and **NEVER touches the live
> outbound earner** — `agent.py` / worker `agent_name="capsy"` / `famit-agent.service` / outbound trunks
> `ST_fmtVmNJmpzKa` + `ST_LH8ighJJtHSi`. The earner was just restored after an infra mistake. The human-leg
> dial **reuses the outbound trunk ID READ-ONLY** (never edits the trunk, dispatch, or `agent.py`). Outbound
> regression-gate `G` (`famit-agent is-active` + one real Riya test call) runs **before + after every step**.
>
> **Box (read-only, verified this session):** `famit@168.144.153.145`. Voice venv `/opt/capsy-agent/.venv` =
> **livekit-api 1.1.0 · livekit-agents 1.5.17**. API/worker venv `/opt/famit-agent/.venv`.

---

## 0. THE QUESTION (founder framing)
"Do not assume Vobiz limits — we have LiveKit. Find the BEST AI→human warm-transfer for OUR stack
(self-hosted LiveKit + Vobiz SIP)." The four candidate mechanisms to weigh:
(a) `transfer_sip_participant` / SIP **REFER** — does it need carrier REFER support?
(b) dial-the-human-INTO-the-room **CONFERENCE** (carrier-agnostic — works even if Vobiz lacks REFER);
(c) **cold/blind** transfer;
(d) how to **pass context** to the human (AI whisper/summary + the hot-lead WhatsApp).

---

## 1. HEADLINE FINDING — LiveKit gives us the warm transfer NATIVELY (no hand-rolling, no REFER)

The earlier plans were right to pick "conference / dial-human-in," but they assumed we'd **hand-build** it from
`CreateSIPParticipant`. **We don't have to.** The installed `livekit-agents 1.5.17` ships
`livekit.agents.beta.workflows.**WarmTransferTask**` — an officially-supported, agent-aware warm-transfer task —
and `livekit-api 1.1.0` ships the `**MoveParticipant**` RPC it depends on. **Both are present on THIS box
(verified by import, not docs):**

```
$ /opt/capsy-agent/.venv/bin/python -c "from livekit.agents.beta.workflows import WarmTransferTask, WarmTransferResult; \
    from livekit import api; print(hasattr(api.room_service.RoomService,'move_participant'))"
WarmTransferTask, WarmTransferResult   ->  importable
move_participant                       ->  True
```

`WarmTransferTask.__init__` (verbatim from the box) already exposes **everything we need**:

```
WarmTransferTask(
  sip_call_to,            # the human's E.164 (e.g. "+9198...") — the handoff number
  sip_trunk_id,           # REUSE THE EARNER'S OUTBOUND TRUNK ID  ST_fmtVmNJmpzKa  (read-only)
  hold_audio,             # audio looped to the CALLER while the human is briefed -> never-silent
  chat_ctx,               # the live conversation context -> this IS the whisper/brief to the human
  instructions,           # extra brief line ("hot on 2BHK, budget ~80L, wants Saturday site-visit")
  ringing_timeout,        # no-answer timeout per number (~25s) -> drives the fallback ladder
  dtmf, stt, vad, llm, tts, allow_interruptions, ...
)
```

**Its internal sequence (read from the box source `…/beta/workflows/warm_transfer.py`, lines cited) IS exactly
the warm/attended pattern the research recommended — and it needs NO carrier REFER:**
1. `warm_transfer.py:333/347` — builds `api.CreateSIPParticipantRequest(...)` and calls
   `job_ctx.api.sip.create_sip_participant(...)` → **dials the human into a SEPARATE transfer room over the
   trunk** (the exact call the earner already makes — see §3).
2. `warm_transfer.py:181-183` — `self._background_audio.play(hold_audio, loop=True)` → **loops hold audio to
   the caller** while the human is being briefed (never-silent guard, built in).
3. A short agent session briefs the human using `chat_ctx`/`instructions` (the **private spoken whisper**).
4. `warm_transfer.py:361-365` — `job_ctx.api.room.move_participant(api.MoveParticipantRequest(
   destination_room=self._caller_room.name, ...))` → **moves the briefed human into the caller's room** → the
   warm 3-way bridge. The AI can then skip-turn / leave.

**So the canonical LiveKit warm transfer = `CreateSIPParticipant` (dial human to a staging room) → brief with
`chat_ctx` → `MoveParticipant` (merge into caller room).** `WarmTransferTask` wraps all three. **All three RPCs
+ the wrapper are present on the box.** This is a Pattern-B private-whisper *and* Pattern-C conference in one,
and it is **carrier-agnostic — it places a normal OUTBOUND SIP call (which Vobiz already does for the earner)
and uses LiveKit-internal room moves; Vobiz never has to honour REFER.**

---

## 2. THE FOUR MECHANISMS, JUDGED FOR OUR STACK

| | Mechanism | LiveKit call(s) | Needs Vobiz REFER? | Context to human | Verdict |
|---|---|---|---|---|---|
| **(a)/(c)** | **Cold / blind REFER** | `transfer_sip_participant(TransferSIPParticipantRequest{participant_identity, room_name, transfer_to="tel:+91…", play_dialtone, ringing_timeout})` | **YES — provider must support/enable SIP REFER.** LiveKit sends a REFER over the trunk; the carrier re-INVITEs the leg. **Closes the caller's LiveKit session.** | **NONE** — human picks up cold. | **FALLBACK ONLY.** One call, but loses context, ends our session/recording, and **depends on Vobiz honouring REFER (UNVERIFIED — GAP-A1).** Cold-transfer docs are explicit: *"performing a cold transfer closes the caller's LiveKit session"* and *"you must configure your provider trunks to allow call transfers."* |
| **(b)** | **Warm — dial human INTO room (conference)** | `WarmTransferTask(sip_call_to, sip_trunk_id, chat_ctx, hold_audio, …)`  →  internally `create_sip_participant` + `move_participant` | **NO.** Just an outbound INVITE (the earner already does this daily) + LiveKit-internal `MoveParticipant`. **Carrier-agnostic.** | **FULL** — private spoken whisper from `chat_ctx`/`instructions`, hold-audio to the caller, AI stays available. | **★ PRIMARY for Famit.** Native, supported, carrier-agnostic, reuses the proven outbound dial path read-only, keeps our session/recording/metering intact, and the AI can skip-turn as a safety net. |
| **(d)** | **Context pass** | `chat_ctx`/`instructions` (spoken whisper) **+** `whatsapp.send_whatsapp(team_number,"hot_lead_alert",[name,phone,summary,score])` (`whatsapp.py:248`) | n/a | belt-and-braces: spoken brief **and** text drop | **BOTH, simultaneously.** The whisper rides `WarmTransferTask.chat_ctx`; the WhatsApp lands the same payload in the human's chat as a durable backup. |

**Decision: (b) `WarmTransferTask` is PRIMARY; (a) `transfer_sip_participant` (REFER) is the lighter FALLBACK
ONLY if/when Vobiz confirms REFER (GAP-A1).** We are NOT blocked on Vobiz: the primary path never needs REFER.

---

## 3. WHY IT'S GENUINELY ADDITIVE + READ-ONLY (the safety proof)

The human-leg dial reuses the **exact** call + trunk the earner already uses — verified on the box, read-only:

- `famit-agent/bridge.py:29` `TRUNK = os.getenv("LIVEKIT_SIP_TRUNK_ID","ST_fmtVmNJmpzKa")`; `:51`
  `lk.sip.create_sip_participant(api.CreateSIPParticipantRequest(sip_trunk_id=TRUNK, sip_call_to=…, room_name=…))`.
- Same pattern at `caller.py:2059` and `place_call.py:40`. **So `CreateSIPParticipant(sip_trunk_id=ST_fmtVmNJmpzKa,
  sip_call_to=<human>)` is a PROVEN, in-production dial path.** `WarmTransferTask(sip_trunk_id=ST_fmtVmNJmpzKa,
  sip_call_to=<human>)` reuses that **trunk ID as a string** — it never edits the trunk object, the inbound/outbound
  dispatch, or `agent.py`. The new code lives **only** in the new inbound `sales-in` worker as a
  `@function_tool transfer_to_human(reason)` that constructs and `await`s a `WarmTransferTask`.
- Additive surface = (1) the `transfer_to_human` tool in the inbound worker; (2) the per-vendor `handoff{}` block
  on the Business Brain (numbers/roles/hours/priority/rules — `PUT /brain`, no new table); (3) the trigger logic
  (explicit-ask + mid-call hot signal). **Zero edits to the earner / trunks / outbound dispatch.** Gate `G`
  before+after.

---

## 4. THE EXACT BUILD (drop-in shape for the inbound `sales-in` worker)

```python
# inbound sales-in worker only — NEVER in agent.py / the earner
from livekit.agents.beta.workflows import WarmTransferTask
OUTBOUND_TRUNK = "ST_fmtVmNJmpzKa"   # read-only reuse of the earner's trunk ID (env LIVEKIT_SIP_TRUNK_ID)

@function_tool
async def transfer_to_human(self, ctx: RunContext, reason: str):
    hb = vendor_config.get_handoff(self.tenant_id)              # Business Brain handoff{} block
    for num in eligible(hb, now):                               # priority_then_roundrobin, skip out-of-hours
        await ctx.session.say("Bilkul — ek second, main aapko abhi connect karta hoon.")  # bridge line, off-loop
        notify_handoff_team(self.tenant_id, self.lead, self.summary)   # WhatsApp drop, SIMULTANEOUS (belt+braces)
        try:
            res = await WarmTransferTask(
                sip_call_to   = num.phone,                      # the handoff number
                sip_trunk_id  = OUTBOUND_TRUNK,                 # reuse, read-only
                chat_ctx      = self.chat_ctx,                  # whisper/brief to the human
                instructions  = self._whisper_line(),          # "hot on 2BHK, ~80L, Sat site-visit — over to you"
                hold_audio    = self._hold_loop,                # caller never hears silence while ringing
                ringing_timeout = num.ring_timeout_s or 25,     # no-answer -> next number
            )                                                   # -> CreateSIPParticipant -> brief -> MoveParticipant
            return "handed_off"                                 # human merged into caller room; AI skip-turns
        except TransferFailed:                                  # voicemail / no-answer / decline -> next eligible
            continue
    return fallback_callback(ctx)   # nobody answered -> log callback + (already-sent) hot-WA + "team will call you back"
```

- **No-answer ladder** is driven by `ringing_timeout` per number + the `for`-loop over eligible numbers
  (`ring_strategy=priority_then_roundrobin`, skip out-of-hours), then `fallback_callback` — **never a dead drop**
  (reuse `scheduler_loop` `caller.py:4813`; the hot-WA was already fired before the first dial, so speed-to-lead
  wins even on total no-answer).
- **Context (d)** is passed twice: `chat_ctx`+`instructions` (spoken whisper, native to `WarmTransferTask`) AND
  the `hot_lead_alert` WhatsApp (`whatsapp.py:248`) into the human's chat — simultaneous, so a noisy verbal brief
  is backed by text.
- **Fallback path (a)** if Vobiz later confirms REFER: `await lk.sip.transfer_sip_participant(
  api.TransferSIPParticipantRequest(participant_identity=caller_id, room_name=room, transfer_to=f"tel:{num}",
  play_dialtone=True, ringing_timeout=25))` — lighter, but loses context + ends our session, so only as a degrade.

---

## 5. OPEN GAPS / FOUNDER (non-code) BLOCKERS
- **GAP-A1 (carrier, now non-blocking):** does Vobiz honour SIP **REFER**? **Only matters for the fallback (a).**
  The primary `WarmTransferTask` path needs **no REFER** — so the build is NOT blocked on this. Verify only before
  relying on the REFER fallback.
- **GAP-C1 (Meta, founder):** register the `hot_lead_alert` WhatsApp template + finish Meta onboarding so the
  simultaneous text-drop can send cold (no 24h window with the team). WA is dormant until creds land (graceful no-op).
- **UX:** a per-vendor **hold-audio asset** (`hold_audio`) + a Hinglish bridge/whisper line bank; voicemail-detect
  so a machine doesn't burn a human (treat as no-answer → next number).
- **Meter/audit:** wallet-gate the human SIP leg against the resolved tenant; audit every transfer attempt
  (who rung / answered / declined / voicemail / final disposition).

---

## 6. THE 14-LINE RECOMMENDATION (the founder's return value)
1. **Use LiveKit's NATIVE warm transfer — `livekit.agents.beta.workflows.WarmTransferTask` — as the PRIMARY
   method. It is already installed on the box (livekit-agents 1.5.17 + livekit-api 1.1.0, both verified by import).**
2. It performs the attended/warm handoff internally as: **`CreateSIPParticipant`** (dial the human into a staging
   room over the trunk) → **brief the human with `chat_ctx`** → **`MoveParticipant`** (merge the briefed human into
   the caller's room). No conference to hand-roll; no SIP REFER needed.
3. **Exact call:** `await WarmTransferTask(sip_call_to="<human E.164>", sip_trunk_id="ST_fmtVmNJmpzKa",
   chat_ctx=self.chat_ctx, instructions=<whisper line>, hold_audio=<loop>, ringing_timeout=25)`.
4. **It fits our stack because it's CARRIER-AGNOSTIC** — it places a normal OUTBOUND SIP call (which Vobiz already
   does for the earner every day) plus a LiveKit-internal room move; **Vobiz never has to honour REFER.**
5. **It's genuinely additive + read-only:** it reuses the earner's outbound trunk ID `ST_fmtVmNJmpzKa` exactly as
   `bridge.py:51` / `caller.py:2059` / `place_call.py:40` already call `create_sip_participant` — as a string only,
   never editing the trunk, dispatch, or `agent.py`.
6. **All new code lives in the inbound `sales-in` worker** as a `@function_tool transfer_to_human(reason)`; the
   earner, outbound trunks, and outbound dispatch are untouched. Gate `G` runs before+after every step.
7. **Context to the human is passed BOTH ways simultaneously (d):** the private spoken whisper rides
   `WarmTransferTask.chat_ctx`/`instructions`, AND the `hot_lead_alert` WhatsApp (`whatsapp.py:248`) drops
   name+phone+summary+score into the human's chat — belt-and-braces.
8. **`hold_audio` keeps the caller from ever hearing silence** while the human is rung/briefed (never-silent rule,
   built into the task).
9. **The no-answer ladder is native:** `ringing_timeout` per number + a loop over eligible handoff numbers
   (`priority_then_roundrobin`, skip out-of-hours) → on exhaustion, logged callback + the (already-fired) hot-WA +
   "our team will call you back" — never a dead drop.
10. **Keep `transfer_sip_participant` (SIP REFER, cold) ONLY as a lighter FALLBACK** — and only if Vobiz later
    confirms REFER (GAP-A1). It loses context and **closes the caller's LiveKit session/recording**, so it is a
    degrade, never the default.
11. **Triggers (not "AI got confused"):** explicit "talk to a human"; a mid-call **hot/buying-signal** (new
    `lead_is_hot` LLM tool, reuse `_CLOSE_*` banks `agent.py:280-312`); sentiment escalation; policy/expertise gap;
    bounded repeated-confusion.
12. **Per-vendor config lives on the Business Brain `handoff{}` block** (numbers + roles + hours + priority +
    `transfer_on.hot_score_gte`) via `PUT /brain` — no new table, no new auth.
13. **We are NOT blocked on Vobiz** for the headline feature: the primary path is fully self-hosted-LiveKit-native;
    the only true external blocker is the Meta `hot_lead_alert` template for the simultaneous WA (GAP-C1).
14. **Net:** the best handoff for our stack is **LiveKit-native `WarmTransferTask` (CreateSIPParticipant → brief →
    MoveParticipant), reusing the outbound trunk read-only, with a simultaneous hot-lead WhatsApp** — supported,
    carrier-agnostic, context-rich, never-silent, and provably additive to the untouched earner.

---

## 7. EVIDENCE INDEX (verified on box `168.144.153.145`, read-only)
- **Versions:** `pip show` → livekit-api **1.1.0**, livekit-agents **1.5.17** (`/opt/capsy-agent/.venv`).
- **Native warm transfer present:** `from livekit.agents.beta.workflows import WarmTransferTask, WarmTransferResult`
  imports OK; source `…/livekit/agents/beta/workflows/warm_transfer.py` — `:333/:347` `CreateSIPParticipantRequest`
  + `create_sip_participant`; `:181-183` `hold_audio` loop to caller; `:361-365`
  `room.move_participant(MoveParticipantRequest(destination_room=caller_room))`. Constructor exposes
  `sip_call_to, sip_trunk_id, chat_ctx, instructions, hold_audio, ringing_timeout, dtmf, stt/vad/llm/tts`.
- **`MoveParticipant` in livekit-api 1.1.0:** `livekit.protocol.room.MoveParticipantRequest` exists;
  `api.room_service.RoomService.move_participant` exists (both `True`).
- **Cold/REFER primitive present:** `sip_service.py:804 transfer_sip_participant`; proto
  `TransferSIPParticipantRequest{participant_identity, room_name, transfer_to, play_dialtone, headers,
  ringing_timeout}`. Docs: cold transfer **closes the caller's LiveKit session** and **requires provider REFER
  support** ("configure your provider trunks to allow call transfers").
- **Outbound dial path reused read-only:** `bridge.py:29` `TRUNK=ST_fmtVmNJmpzKa`, `:51 create_sip_participant`;
  `caller.py:147 TRUNK`, `:2059 create_sip_participant`; `place_call.py:40 create_sip_participant`;
  env `LIVEKIT_SIP_TRUNK_ID` (redacted). Outbound trunks `ST_fmtVmNJmpzKa` + `ST_LH8ighJJtHSi` frozen.
- **Context-pass + hot:** `whatsapp.py:248 send_whatsapp(to,template,params)` (cold/template);
  `agent.py:155 _summarize_transcript`→interest 0-100; `caller.py:1297 hot=score>=70`; `_CLOSE_*` banks
  `agent.py:280-312`; callback `scheduler_loop caller.py:4813`.
- **Web sources (cited):**
  - LiveKit — *Call forwarding / Cold transfer* (transfer_sip_participant; REFER; provider must enable transfer;
    closes caller session). https://docs.livekit.io/telephony/features/transfers/cold/
  - LiveKit — *Agents telephony integration* (cold REFER vs warm transfer supported).
    https://docs.livekit.io/telephony/agents-integration/
  - LiveKit — *agents/examples/warm-transfer* (CreateSIPParticipant → brief → MoveParticipant; WarmTransferTask
    `target_phone_number`/`sip_trunk_id`/`chat_ctx`). https://github.com/livekit/agents/tree/main/examples/warm-transfer
  - livekit/sip issues #91 (REFER), #234 (cold transfer 603), #237 (custom SIP headers) — REFER is
    provider-dependent + has edge failures, reinforcing "warm is primary, REFER is fallback-only."
    https://github.com/livekit/sip/issues/91 · https://github.com/livekit/sip/issues/234
  - Retell — warm transfer + private whisper + native SIP. https://www.retellai.com/blog/how-ai-voice-agents-are-perfecting-the-warm-transfer
