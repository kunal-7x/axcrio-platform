# ROUND-5 VOICE-FIX — STATE (crash-safe scratch)

EARNER-CRITICAL. Voice byte-identical. P0 brain LIVE (`KERNEL_OUTBOUND=0`, `build_system_prompt`).
Box: `ssh -i ~/.ssh/do-blr-test/id_ed25519 -o StrictHostKeyChecking=no famit@168.144.153.145`, `/opt/famit-agent/`.

## GROUND TRUTH (verified on box 2026-06-19 this session)
- agent.py md5 `48bc2b5a54261a85846f715ba731ef35` == repo (line numbers trustworthy).
- **TTS LOCKED region agent.py:885-957 md5 = `ee9d18935437b67aabc3d9fec14d0eeb`** (MUST be unchanged after deploy).
- prompt.py md5 `635d8205f0ed8ce324809f2a1a62a95c`.
- .env: EL_STABILITY=0.55, ELEVENLABS_VOICE_ID=QTKSa2Iyv0yoxvXY2V8a, LLM_CLOSE=1, LANG_MIRROR_V2=1.
- drop-in: KERNEL_OUTBOUND=0, W5_SPEECH=0, OPENER_IN_CTX=1, OPENER_ALREADY_SAID=1, OPENER_DELAY_S=0.8.
- caller.py listens on 0.0.0.0:8209 (uvicorn) — booking contract target reachable. `grep booking/book caller.py` = NONE yet (backend agent building in parallel; code to contract).
- BOOKING_TOOL_ENABLED NOT in env → existing in-proc booking tool OFF (and gated behind KERNEL_OUTBOUND=1 → dead on P0).

## THE LAW
NEVER touch agent.py:885-957 / .env (EL_STABILITY=0.55) / language. One box-mutating deploy, off-hours, golden armed, rollback on any fail. Back up every file `*.R5VFbak.<ts>`.

## ROOT CAUSES (read from live source)
- **BUG1 (outbound framed as inbound):** spoken opener = `agent.py:_llm_opener` line 377 `कहो कि '{product}' के बारे में call किया था` → ambiguous past tense → LLM said "आपने ... कॉल किया था" (YOU called). prompt.py `_flow_block` step2 (338-340) already correct but the SPOKEN opener (`_llm_opener`, said via session.say) is the live source. FIX = make `_llm_opener` explicit first-person outbound; reinforce prompt.py opener_section + add top-priority anti-inbound-framing rule. Kernel path: add outbound-framing to `delivery.py`.
- **BUG2 (repetitive ending):** LLM_CLOSE=1 IS live so close is "LLM-generated" — BUT `agent.py:_llm_close` sysmsg lines 561-562 literally steer it: `उसके बजाय शुक्रिया कहकर 'आपका दिन अच्छा रहे' जैसी ... line से बात ख़त्म करो` + temp 0.4 → same phrase every call. FIX = rewrite sysmsg to mandate VARIED + contextual close referencing the actual outcome; remove the canned-phrase steer; bump temp; keep अलविदा ban as pure ban. P1 `delivery.py closing_directive` already varied ✓.
- **BOOKING:** existing `book_appointment` (agent.py:1244-1292) gated behind KERNEL_OUTBOUND=1 (dead on P0) + uses in-proc booking.core (not the HTTP contract). NEW = a P0-compatible tool POSTing to `http://127.0.0.1:8209/booking/book` {phone,lead_name,datetime_iso,campaign_id,notes}, NEW flag independent of KERNEL_OUTBOUND, default OFF, staged.

## CAMPAIGN FINDING (verified on box this session)
Live Codename Joy campaigns (80a939941d, b690f78cab, c17e55e9f3, d52d4ea111) have CLEAN OUTBOUND
raw_script + talking_points. BUG1 source = `_llm_opener` line 377 ambiguous "call किया था" → LLM
said "आपने ... कॉल किया था". NO campaign JSON edit needed (guide the LLM, not hardcode). prompt.py
reframe rule covers the defense-in-depth case (some eval-only Surat campaigns DO have inbound talking_points).

## EDITS DONE (file:region)
- T1 BUG1 P0: agent.py `_llm_opener` (~377-383) explicit first-person outbound framing + inbound ban.
  prompt.py opener_section `_opener_already_said` branch (+ outbound framing + inbound ban).
- T1 BUG1 P1: voice_kernel/brain_packs/delivery.py `single_greeting_directive` (+ outbound framing).
- T2 BUG2 P0: agent.py `_llm_close` sysmsg (~550-571) — removed canned 'आपका दिन अच्छा रहे' steer,
  mandate VARIED+contextual close referencing actual outcome, temp 0.4→CLOSE_TEMP default 0.8.
  P1: delivery.py `closing_directive` already varied/principle-only (no change).
- T3 BOOKING: agent.py NEW `booking_http_tool_enabled()` (flag BOOKING_HTTP_ENABLED, default OFF,
  INDEPENDENT of KERNEL_OUTBOUND → attaches on P0) + `_do_booking_http()` (POST 127.0.0.1:8209/booking/book
  {phone,lead_name,datetime_iso,campaign_id,notes}, reuses resolve_slot_start for natural→ISO, fully
  wrapped) + `book_site_visit` function-tool attached when flag on + a gated prompt nudge.

## VOICE-SAFE PROOF (local, pre-deploy)
- py_compile OK (agent.py, prompt.py, delivery.py).
- TTS construct block (content-anchored `tts=elevenlabs.TTS(` → `turn_detection="vad"`) md5
  = `f0d8e332673f3fbc07c0359772469fa1` on BOTH live box AND edited repo → byte-identical. ✓
- All my edits are OUTSIDE the TTS/voice region. .env NOT touched. KERNEL_OUTBOUND stays 0.

## TASKS — ALL DONE
- [x] T1 BUG1  - [x] T2 BUG2  - [x] T3 BOOKING  - [x] T4 py_compile
- [x] T5 DEPLOYED 2026-06-19 ~15:23 UTC. Backups `*.R5VFbak.20260619-205238`. New md5s agent.py
  `c33c03e2`, prompt.py `c60b30f4`, delivery.py `2b704ea4`. TTS block byte-identical
  `f0d8e332673f3fbc07c0359772469fa1` (pre==post). .env golden. KERNEL_OUTBOUND=0. Worker "capsy"
  re-registered (PID 162145), NRestarts=0, 0 errors on new PID. BOOKING_HTTP_ENABLED OFF (staged).
- [x] T6 ROUND-5 VOICE-FIX block recorded at TOP of EARNER-LIVE-STATE.md.

DONE. Founder tests one call (outbound framing + varied ending). Booking: flip BOOKING_HTTP_ENABLED=1
once /booking/book is live on caller.py (8209).

## DEPLOY FLAGS (default OFF → staged; founder flips to test booking)
- BOOKING_HTTP_ENABLED=1 (drop-in) to attach the booking voice-tool on the P0 brain.
- Optional: BOOKING_HTTP_URL, BOOKING_HTTP_TOKEN, CLOSE_TEMP. BUG1+BUG2 fixes are LIVE on deploy (no flag).

## ROLLBACK
Golden: `agent.py.PERFECTgolden.20260618-210445` + `_GOLDEN_ROUND5_20260619-140341/`. Per-file: `*.R5VFbak.<ts>`.
