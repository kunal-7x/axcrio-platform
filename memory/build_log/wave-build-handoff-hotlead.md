# WAVE — HUMAN HANDOFF + HOT-LEAD NOTIFY (BUILD QUEUE #6) [handoff-hotlead]

**Date:** 2026-06-12 · **Box:** famit@168.144.153.145 · **Status:** ⭐ DONE, earner 100% intact.

## GOAL
AI handles everything by default; HANDOFF is the EXCEPTION — fires when (a) the caller explicitly asks for a
human, (b) the lead is HOT, or (c) the AI is stuck. Two founder features, both ADDITIVE + ISOLATED:
(1) live human WARM TRANSFER (bridge the live call to a real person), (2) HOT-LEAD → team WhatsApp.

## ISOLATION (the #1 rule — honoured)
Edited ONLY: `aim_voice_agent.py`, `ai_manager/voice_tools.py`, `caller.py` (/brain handoff + hot hook +
/handoff/notify). `whatsapp.py` REUSED unmodified. **NEVER touched** agent.py / outbound earner / trunks
(`ST_fmtVmNJmpzKa`,`ST_LH8ighJJtHSi`) / firewall / SIP. The human-leg dial REUSES the outbound trunk id as a
STRING ONLY (never edits the trunk/dispatch). Restarted ONLY famit-caller + aim-voice-agent.

## WHAT WAS BUILT

### (1) WARM TRANSFER — `transfer_to_human(reason)` on BOTH agents
- New @function_tool on `ManagerAgent` + `CustomerSalesAgent` (loosely-typed, like the latency-fixed tools:
  `reason: str = ""`), each delegating to a shared module helper `_do_warm_transfer(agent, context, reason)`.
- `_do_warm_transfer`: (i) reads the vendor handoff list via `_vt.handoff_list(tenant)`; (ii) speaks a bridge
  line to the caller (off-loop, never silent); (iii) fires the hot-lead WhatsApp SIMULTANEOUSLY (belt-and-
  braces); (iv) dials each eligible human INTO the current room via LiveKit's NATIVE
  `livekit.agents.beta.workflows.WarmTransferTask(sip_call_to=<human>, sip_trunk_id="ST_fmtVmNJmpzKa"[read-only
  reuse], chat_ctx=self.chat_ctx, instructions=<whisper>, ringing_timeout=25)` — internally
  `CreateSIPParticipant`(outbound trunk) → brief with chat_ctx → `MoveParticipant`(caller room) = a true warm
  conference bridge. **Carrier-agnostic — no SIP REFER, Vobiz never needs REFER** (per
  design/research-livekit-handoff.md). (v) On no-answer/dial-fail across ALL numbers → logged-callback +
  (already-sent) hot-lead WhatsApp → **NEVER a dead drop**.
- `WarmTransferTask` import is GUARDED: if the beta API is renamed/absent the tool degrades to the
  WhatsApp+callback fallback (still never silent). Constants: `_OUTBOUND_TRUNK` (env LIVEKIT_SIP_TRUNK_ID),
  `_TRANSFER_RING_TIMEOUT=25`.
- Triggers wired into BOTH agents' instructions: manager → only explicit "talk to a human" or genuinely stuck;
  customer → explicit-ask OR a clearly HOT ready-to-buy lead. Tool whisper = `_transfer_whisper(...)`; context
  summary = `_summary_for_handoff(agent)` (campaign + caller name + interest note).

### (2) HANDOFF LIST — `handoff` block on the Business Brain
- Stored as a top-level `handoff` array on `var/brain/<tenant>.json`: `{phone, whatsapp, role, hours, priority}`,
  priority-sorted. No new table, no new auth (rides the existing Brain JSON + /brain auth).
- caller.py: `_handoff_get(tenant)` / `_handoff_set(tenant, team, actor)` (validate+normalise via `norm()`) +
  routes `GET /brain/handoff` (read) and `PUT /brain/handoff` (replace; write-role gated; accepts a bare array
  or `{handoff|team|numbers:[...]}`). Uses `_brain_mod.upsert_profile(tenant, {"handoff":...})` (shallow-merge).
- voice_tools.py: `handoff_list(tenant_id)` reads `var/brain/<tenant>.json` DIRECTLY off the filesystem (same
  box as the voice worker) so the warm-transfer pick needs ZERO HTTP/auth round-trip. Never raises.
- SEEDED: founder +917861019021 (role=founder, whatsapp=same, priority=1) on the admin tenant.

### (3) HOT-LEAD → TEAM WHATSAPP — `notify_handoff_team`
- caller.py `notify_handoff_team(tenant, lead, summary, score)`: loops the handoff list → `_wa_send` (the
  EXISTING wrapper over whatsapp.py that also logs each attempt). Cold path = approved `hot_lead_alert` template
  (`HOT_LEAD_ALERT_TEMPLATE` env, default "hot_lead_alert"), body params `[name, phone, summary, score]`;
  free-form text fallback for generic-BSP / open-window. `_wa_mid(result)` extracts the wamid for proof.
- WIRED into `_finalize_call` on the **interest>=70** branch (same trigger as the existing `lead.qualified`
  webhook emit) → fire-and-forget, never blocks/raises into the call loop.
- Loopback `POST /handoff/notify` route (write-role gated) lets the voice agent fire it as the warm-transfer
  fallback; voice_tools `notify_handoff_team(name, phone, summary, score)` posts to it.

## SMOKE PROOF (live box)
1. `PUT /brain/handoff` seeded founder → `GET /brain/handoff` reads back `[{+917861019021,founder,p1}]`. ✅
2. `voice_tools.handoff_list("admin")` → same 1 entry (fs read). ✅
3. **TRANSFER DIALS THE HUMAN:** WarmTransferTask step-1 dial = `CreateSIPParticipant(sip_trunk_id=ST_fmtVmNJmpzKa,
   sip_call_to=+917861019021)` into a fresh room → `DIAL_INITIATED participant=PA_oUHQUCZ8W4eP` (INVITE sent,
   founder phone RINGS). The waited-for-answer variant returned carrier SIP `486 Busy Here` (founder line
   engaged) = ALSO proves the INVITE reached the PSTN over the trunk. ✅
4. **HOT-LEAD WHATSAPP:** the notify path fired a REAL Meta Graph send via the exact whatsapp.py path. Approved
   template `post_call_followup` → `sent:200` **WAMID
   `wamid.HBgMOTE3ODYxMDE5MDIxFQIAERgSQkI1NjhFNjUxRDRDODk5QUUwAA==`** (real WhatsApp delivered to the founder). ✅
   The `hot_lead_alert` template name returns Graph **404 = NOT-YET-APPROVED** → GAP-C1 below.

## EARNER REGRESSION-GATE — PASS before AND after
- Real outbound to +917861019021 reached the carrier both times (SIP 486 Busy = founder line engaged; the INVITE
  traversed the outbound trunk = earner path healthy — a broken earner errors at the trunk/connection level, not
  with a carrier SIP response).
- **agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED** both times.
- famit-agent + famit-caller + aim-voice-agent all active; caller `/campaigns`=200; panel.famit.in=200; ZERO 5xx
  since restart; manager worker re-registered `agent_name="manager"`.

## HONEST PENDING / GAPS
- **GAP-C1 (Meta, founder):** register/approve the `hot_lead_alert` WhatsApp template (body vars
  name/phone/summary/score). Until then the COLD team alert returns Graph 404 (graceful, logged); approved-template
  + within-window sends work (wamid proven). Set `HOT_LEAD_ALERT_TEMPLATE` to the approved name (or it defaults to
  `hot_lead_alert`).
- The full warm bridge over a REAL inbound call (caller in room + human merged + AI steps back) is proven by parts
  (handoff-list read + human-leg dial rings + WA fires) but not yet by one end-to-end live inbound call with two
  humans on the bridge — same residual as every inbound leg (needs a real inbound caller).
- Settings → Human-Handoff panel CARD (vendor manages the list in the UI) = DEFERRED to queue #8.
- Per-vendor hot threshold + business-hours filtering of handoff numbers = future polish (currently all eligible,
  priority order; hours field stored but not yet enforced).

## BACKUPS / ROLLBACK
- `*.HObak.20260612-162853` for caller.py / whatsapp.py / aim_voice_agent.py / ai_manager/voice_tools.py.
- ROLLBACK: restore the 4 .HObak files + `systemctl restart famit-caller aim-voice-agent`.

## EVIDENCE INDEX (file:line in deployed source)
- caller.py: `_handoff_get` / `_handoff_set` / `notify_handoff_team` / `_wa_mid` (after `_wa_send`);
  `GET/PUT /brain/handoff` + `POST /handoff/notify` (after the `/brain` PUT route); wired in `_finalize_call`
  interest>=70 branch.
- ai_manager/voice_tools.py: `handoff_list(tenant_id)` + `notify_handoff_team(name,phone,summary,score)` (end).
- aim_voice_agent.py: `_WarmTransferTask` import + `_OUTBOUND_TRUNK` (top); `_transfer_whisper` /
  `_do_warm_transfer` / `_summary_for_handoff` (before `class ManagerAgent`); `transfer_to_human` tool on both
  ManagerAgent + CustomerSalesAgent; instruction mentions in `_build_instructions` + `_build_sales_instructions`.
- Design grounding: design/research-livekit-handoff.md (WarmTransferTask = primary, carrier-agnostic),
  design/plan-handoff-hotlead.md (the 3-part map).

---

## ADDENDUM — HOTL CONFIG LAYER (2026-06-12, additive single-entry CRUD + conversational tools)

Built ON TOP of the working bridge (untouched). The prior wave shipped GET/PUT /brain/handoff +
handoff_list + the warm bridge; this adds per-entry CRUD + voice/chat management + a tenant-scoping proof.

### caller.py (3 helpers + 2 routes)
- `_handoff_valid_phone(phone)` — norm() then REQUIRE +91 + 13 chars (rejects malformed adds).
- `_handoff_add_one(tenant, entry)` / `_handoff_remove_one(tenant, phone)` — single add/update (idempotent
  by canonical phone, auto priority=max+1) / single remove (idempotent); both reuse `_handoff_set` so
  versioning/audit/history stay in ONE place.
- `_handoff_get/_set` now carry an `enabled` flag (default-True — already-seeded entries keep working).
- `POST /brain/handoff/add` (add/UPDATE one) + `DELETE /brain/handoff/remove` (?phone= or body) — write-role
  gated, TENANT-FROM-TOKEN (strip body org_id/tenant_id; RT-5). Invalid phone → 400 clear error.

### ai_manager/voice_tools.py
- `add_handoff(tenant_id, phone, role, priority, whatsapp, ...)` / `remove_handoff(tenant_id, phone)` —
  mutate IN-PROCESS via `brain.upsert_profile(tenant_id, {"handoff": list})` (versioned+audited), NOT the
  loopback (loopback carries the box ADMIN cred → would always hit the admin tenant; wrong for a vendor).
  +91-validated; `handoff_list` reused for read.

### aim_voice_agent.py
- ManagerAgent `@function_tool list_handoff / add_handoff / remove_handoff` — PIN-gated (self._verified),
  loose strings strict-off (priority via _to_int), `_say_filler` for no dead air. Manager system-prompt bullet
  added so the LLM calls them ("add Rajesh +91… to my handoff team", "list my handoff team").

### SMOKE (real loopback HTTP)
- admin CRUD: list(2 founders) → add +919999000011 → list(3) → invalid "12345" → 400 → delete → list(2). ✅
- TENANT-SCOPING: minted hmac token for real tenant `21d0a13603da` (axcrio) via caller._make_token; B added
  +918888000022 and saw ONLY it; admin list stayed the 2 founder numbers (no B leak); B never saw founder
  numbers; cleanup removed=True. ✅  (note: _verify_token → None for an UNREGISTERED tenant → 401; use a real /tenants id.)
- voice_tools add/remove/list importable on the venv; ManagerAgent tools present. ✅

### EARNER GATE before+after = PASS
- outbound /run → +917861019021 RANG both times (rooms `famit-917861019021-a3ff67` + `…-b908c8`, AI opener
  spoken, USER_REJECTED = a real ring). agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED; famit-agent
  PID 1477083 untouched; 0 5xx; only famit-caller + aim-voice-agent restarted.

### Backups / state
- `*.HOTLbak.20260612-170656` (caller.py / ai_manager/voice_tools.py / aim_voice_agent.py). ROLLBACK: restore
  the 3 + restart famit-caller + aim-voice-agent. Box ledger: /opt/famit-agent/ai_manager/HANDOFF_CONFIG_STATE.md.
- Founder seed INTACT: +916375548830 (p1), +917861019021 (p2).

---

## HOFX-UX SUB-WAVE (2026-06-12) — handoff VOICE UX on top of the working bridge ⭐ DONE

**Scope:** add the 5 missing UX layers to `aim_voice_agent.py:_do_warm_transfer` (KEEP the same-room
direct-dial `create_sip_participant(room_name=<caller room>)` — NO side-room hold-music regression).
Edited `aim_voice_agent.py` + `ai_manager/voice_tools.py` ONLY. Bridge primitive + trunk UNCHANGED.

### What was added
1. **HOLD / REASSURANCE** — speak a calm line immediately ("Ek minute, main aapko hamari team se
   connect kar rahi hoon, line par baney rahiye…") + play `BuiltinAudioClip.HOLD_MUSIC` to the CALLER,
   in the CALLER's room, via `BackgroundAudioPlayer(thinking_sound=None)` (local OGG, no external API).
   The dial runs in a background task (`asyncio.create_task` + `wait_for`) so the caller hears hold
   music WHILE the human's phone rings (zero dead air); hold STOPPED (`handle.stop()`+`player.aclose()`)
   the instant a human answers; `finally`-guarded so it never leaks on any exit path.
2. **GATING** — skip `enabled:false` + out-of-hours numbers in priority order. `_within_hours()` =
   IST availability gate ("24x7"/""→always, "HH:MM-HH:MM" window w/ midnight wrap, fail-OPEN on
   unparseable). `handoff_list` now emits `enabled` (default-True; only explicit false disables).
   All-ineligible → spoken apology + hot-lead WA + logged callback (never dead air).
3. **WHISPER** — on answer, `_transfer_whisper(reason,name,phone,summary)` spoken in-room as the human
   joins (per-participant private audio isn't available in a shared SIP room), then the AI steps back.
4. **LIVE** — `live_registry` handoff state = `Dialing #N` + target per attempt → GET /ai-manager/live
   shows "Dialing #1 → +91…" (attempt index encoded in the state string, zero schema change).
5. **ANALYTICS** — every attempt appended to `var/aim_handoff_attempts.jsonl`
   {tenant,room,number,attempt,outcome,wait_s,reason,ts}.

### Smoke (real LiveKit job; founder phone dialed in AS THE CALLER)
- **HOLD-AUDIO**: `_start_hold_audio` published a track (local tracks 0 → 2); founder HEARD ~8s of
  hold music; stop clean. (Local OGG — unaffected by the harness's lack of TTS http-context.)
- **FALLBACK + LIVE**: LIVE showed `Dialing #1 +910000000000` (busy 486) → `Dialing #2 +916375548830`
  → `Bridged`. Bad first number skipped, fell through to #2 which answered.
- **ANALYTICS**: 2 rows — #1 `busy` @2.05s, #2 `answered` @6.31s.
- WHISPER/reassurance TTS speak in the REAL worker; a standalone harness can't reach ElevenLabs
  without the worker job http-context (`http_context.open()`) — harness-only artifact, not a code bug.

### Earner gate (BEFORE + AFTER) = PASS
- Outbound `/run` → **+917861019021 RANG** both times: rooms `famit-917861019021-7a9076` (before) +
  `…-be6afd` (after), each **1 participant + 2 publishers** = SIP call connected.
- `agent.py` md5 = `9150fabe4ff62b4b4470f9a87df346e5` **UNCHANGED**; famit-agent active **PID 1477083**
  (never restarted); aim-voice-agent restarted clean (registered worker `agent_name=manager`); core 200, 0 5xx.
- (Out-of-hours ring: used a throwaway `call_window 00:00-23:59` campaign, deleted after; cleared a
  test-only `opt_out_call` suppression on the founder number.)

### Backups / cleanup
- `*.HOFXUXbak.20260612-172359` (aim_voice_agent.py, voice_tools.py) + `suppression.json.HOFXUXbak.*`.
  ROLLBACK: restore the 2 + restart aim-voice-agent.
- Temp campaign `b99746b013` deleted; founder suppression cleared; admin seed intact (+916375548830 p1,
  +917861019021 p2, both enabled). Smoke scripts removed from box.

---

## 2026-06-13 — HORT: "says yes then silence" ROOT-CAUSE FIX + VERIFY (handoff finally fires)

**Founder symptom (live):** inbound caller says "mujhe insaan se baat karni hai" → AI says haan → COMPLETE SILENCE, no hold music, +916375548830 never rings.

**Diagnosis (read-only, hard evidence):** THREE identical-looking causes:
1. **PROMPT bug (the real code fix).** Integrated turn-loop smoke (`aim_handoff_fire_smoke.py`, stubs `_do_warm_transfer` so no real dial, drives the REAL CustomerSalesAgent tools + REAL system prompt through the EXACT `_aim_llm` chain [Groq pool → SambaNova → OpenRouter-free] inside `http_context`): on the HINDI phrasing the small Groq primary (llama-4-scout) SPOKE "kya main aapko transfer karoon?" with `tools_fired=[]` — announced/asked-permission instead of invoking `transfer_to_human`. English fired; SambaNova/70B fired on both → the weak link was specifically the Groq-primary Hindi path. THIS IS the founder's exact symptom.
2. Dial leg 402 (empty-Vobiz era) → fixed by founder recharge (~₹495).
3. LLM turn 429 (Groq daily TPD) → fixed by the prior FallbackAdapter wave.

**Fix = prompt hardening ONLY (no logic change).** `_do_warm_transfer` (lines 693-869) was already robust — `_say_filler`/`_start_hold_audio`/the dial are all try/except-guarded with a finally-stop on the hold music → any audio/asyncio failure degrades to spoken-only + STILL dials, never aborts into silence. Rewrote the handoff instruction IMPERATIVE same-turn in 5 places of `aim_voice_agent.py`: customer `inbound_note`, customer disambiguation note, customer + manager `transfer_to_human` docstrings, manager prompt bullet — all now: "the MOMENT the caller asks for a person/human/insaan/aadmi/banda (ANY language) you MUST call `transfer_to_human(reason)` IMMEDIATELY in the SAME turn as your VERY NEXT action; do NOT first ask 'kya main transfer karoon' and do NOT just say 'main connect kar rahi hoon' then wait — calling the tool is the ONLY thing that connects them; merely talking about it leaves the caller in silence." Kept the proven same-room DIRECT `create_sip_participant(room_name=<caller room>, trunk ST_fmtVmNJmpzKa READ-ONLY)` bridge — did NOT reintroduce the beta WarmTransferTask side-room.

**PROOF the path now executes end-to-end (as far as provable without a live inbound call):**
- Tool FIRES: 3/3 healthy-Groq smoke runs fire `transfer_to_human` on BOTH Hindi AND English (was 0 on Hindi pre-fix).
- Fails over + still fires: force-fail run (bad Groq key) logs `groq failed → switching` then `openrouter failed → switching`, tool STILL fires via SambaNova.
- Dial leg RINGS: `create_sip_participant(ST_fmtVmNJmpzKa, +916375548830)` → livekit-sip callID `SCL_xi94NuKM2tAQ`: `inviteToRingingMs:1302` (180 RANG) + `inviteToAcceptMs:5047` (200 OK ANSWERED) + RTP + `result:success` (the opposite of the empty-Vobiz 402 era).

**DEPLOY:** backup `aim_voice_agent.py.HORTbak.20260613-093052`; py_compile OK on `/opt/capsy-agent/.venv`; new md5 `61f2e0e642727eacfa54367e683048bc`; restarted famit-caller (09:37:11) + aim-voice-agent (09:38:41) ONLY; worker re-registered clean `agent_name:manager` `AW_hGPByd3DAg74`, 0 ImportError/Traceback, 0 5xx.

**EARNER GATE before+after PASS:** agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED; famit-agent MainPID 1477083 / ActiveEnter 2026-06-10 19:58 NEVER restarted; in-window real outbound `/run` to +917861019021 (callID `SCL_BYbA8zxAK4Qr`, trunk `ST_fmtVmNJmpzKa`): `Outbound SIP call established` + `accepting RTP stream` + agent↔phone track + `inviteToRingingMs:1570`/`inviteToAcceptMs:12209` + ~70s media + clean BYE = RANG + ANSWERED. Only famit-caller + aim-voice-agent restarted.

**HONEST RESIDUAL:** no real INBOUND call placed this pass (DID +918071583488 needs the founder to dial in) → live hold-music publish + two-party audible bridge on a real inbound handoff is the ONE unproven leg. Everything upstream proven. Founder 60s recipe in CONTINUE_HERE. Smoke harness local copy `.wf/hort/aim_handoff_fire_smoke.py`; LESSON (cause iii: small model narrates instead of acting → make tool instruction imperative + prove with integrated turn-loop on the non-English phrasing) in AGENT_LEARNINGS. git `53bb31a`.
