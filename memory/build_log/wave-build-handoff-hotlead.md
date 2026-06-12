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
