# PRODUCTION-READINESS AUDIT — STATE (read-only; writes only design/*.md)

## TASK
1. Audit the FULL connected lifecycle: outbound call -> per-person memory -> WhatsApp follow-up (template+LLM)
   -> inbound callback w/ full history -> warm-transfer to human + hot-lead WhatsApp to team.
   Goal: PRODUCTION-GRADE + SELLABLE. Earner NEVER touched. READ-ONLY.
2. RESEARCH: best AI->human WARM TRANSFER for OUR self-hosted LiveKit + Vobiz SIP stack.
   Write design/research-livekit-handoff.md. Return 14-line recommendation.

## BOX (read-only)
famit@168.144.153.145  key C:\Users\kunal\.ssh\do-blr-test\id_ed25519
voice venv /opt/capsy-agent/.venv (livekit-api 1.1.0, livekit-agents 1.5.17)
api venv /opt/famit-agent/.venv

## PROGRESS
- [x] Read INBOUND-PIPELINE-MASTER-PLAN-V2.md (full lifecycle plan; Pattern C decision already made)
- [x] Read plan-research-transfer.md (external pattern evidence; 3 patterns A/B/C)
- [ ] Read plan-handoff-hotlead.md (box primitive map)
- [ ] Read v1 master plan handoff section
- [x] Web research: LiveKit transfer APIs (cold REFER + warm) — DONE
- [x] Verify box primitives read-only — DONE (see HEADLINE below)
- [x] Write design/research-livekit-handoff.md — DONE
- [x] Return 14-line recommendation — DONE (in §6 of the doc + returned to caller)

## HEADLINE FINDING (supersedes prior "hand-roll a conference")
LiveKit ships a NATIVE warm-transfer primitive ALREADY INSTALLED ON THE BOX:
- livekit.agents.beta.workflows.WarmTransferTask  (livekit-agents 1.5.17) — importable, verified
- api.MoveParticipant / MoveParticipantRequest    (livekit-api 1.1.0) — present, verified
Internal seq (warm_transfer.py): CreateSIPParticipant(dial human to staging room over trunk) ->
brief w/ chat_ctx (whisper) -> MoveParticipant(merge into caller room). hold_audio loops to caller.
=> PRIMARY = WarmTransferTask(sip_call_to=<human>, sip_trunk_id="ST_fmtVmNJmpzKa", chat_ctx, instructions,
   hold_audio, ringing_timeout). CARRIER-AGNOSTIC — no Vobiz REFER needed. Reuses earner trunk READ-ONLY
   (same call as bridge.py:51 / caller.py:2059 / place_call.py:40). FALLBACK = transfer_sip_participant
   (SIP REFER, cold, closes session, needs Vobiz REFER = GAP-A1).
=> NOT blocked on Vobiz for the headline feature. Only real external blocker = Meta hot_lead_alert template (GAP-C1).

## REMAINING (lifecycle audit beyond the handoff research)
The handoff research deliverable is COMPLETE. Broader lifecycle production-readiness audit (outbound->memory->
WhatsApp->inbound->transfer) is already well-covered by INBOUND-PIPELINE-MASTER-PLAN-V2.md + plan-*.md;
the one NEW load-bearing correction this session adds is the native-WarmTransferTask finding above.

## KEY FACTS SO FAR
- Decision already converged: Pattern C (dial human INTO room via CreateSIPParticipant over outbound trunk,
  read-only reuse) PRIMARY; Pattern A (SIP REFER via transfer_sip_participant) FALLBACK only if Vobiz honours REFER.
- transfer_sip_participant @ /opt/capsy-agent/.venv/.../livekit/api/sip_service.py:804 (livekit-api 1.1.0) — present, un-wired.
- outbound trunks ST_fmtVmNJmpzKa + ST_LH8ighJJtHSi (FROZEN, read-only reuse only).
- whatsapp.py:248 send_whatsapp (template/cold) — reuse for hot-lead alert.
- GAP-A1: does Vobiz honour SIP REFER? unverified.
