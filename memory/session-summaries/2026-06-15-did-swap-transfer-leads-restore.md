# SESSION SUMMARY — 2026-06-15 — DID swap → outbound restored · warm-transfer restored · leads-mgmt LIVE · Telegram ecosystem diagnosis

> **What was happening:** The founder personally tested the live product (the HOLD from the Telegram
> build) and surfaced real gaps: outbound calls weren't ringing (carrier-spam-flagged DID), warm/human
> transfer wasn't connecting, Telegram follow-ups weren't firing after inbound calls, and the leads
> screen lacked basic management. This session was a **preservation + restore wave** — diagnose each
> real-world complaint against the live box, fix the earner-safe ones (no `agent.py` edit), and write
> durable state so nothing is lost across the next compaction. Earner gate held all night:
> `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED, famit-agent never restarted.

---

## 1. OUTBOUND RESTORED — DID swap (Vobiz carrier-spam rotation)
**Problem:** the old outbound DID `+91…488` was carrier-spam-flagged since ~2026-06-13 — every
outbound INVITE returned **SIP 486 / 480 / 603 with only `inviteToTryingMs`** (carrier-rejected
pre-ring, NOT a real ring). Outbound earner was effectively dead. The founder bought a **NEW DID on
the SAME Vobiz account/trunk** to rotate off the flagged number.

**Root cause of where the caller-ID lives:** it is NOT a `.env` number var and NOT hardcoded in any
`.py`. It lives in the **LiveKit SIP OUTBOUND trunk's `numbers` field**. The box LiveKit (v1.8) does
**not** support `UpdateSIPOutboundTrunk` (twirp `bad_route`), so the swap was done by **creating a new
outbound trunk with the new DID** and **repointing the env trunk-id**.

**Change set (minimal — no pipeline/code rewrite):**
- Created new outbound trunk **`ST_bpGqmc9TL9Ph`** (`vobiz-outbound-new-did`, same Vobiz host
  `2c24f731.sip.vobiz.ai`, same auth user `capsy-project`, same pass, TCP) carrying the NEW DID.
- Edited `/opt/famit-agent/.env` line 13 `LIVEKIT_SIP_TRUNK_ID`: `ST_fmtVmNJmpzKa` → **`ST_bpGqmc9TL9Ph`**.
  All outbound dial paths (`place_call.py`, `bridge.py`, `caller.py`, `aim_voice_agent.py`) read this
  ONE env line via `os.getenv("LIVEKIT_SIP_TRUNK_ID", …)`, so the swap propagates with no `.py` edit.
- Old trunks `ST_fmtVmNJmpzKa` (TCP) and `ST_LH8ighJJtHSi` (UDP) LEFT INTACT for instant rollback.
  INBOUND untouched (separate trunk `ST_K785ASpNh5ow` / aim-inbound).
- Restarted **only famit-caller** (PID 3022373). famit-agent (earner) NOT restarted.
- Placed **exactly ONE** founder-authorized outbound test call via `place_call.py`; retry_queue left PAUSED.

**Ring proof (concrete SIP evidence):** call `SCL_8QpqwzW6SU4T`, via trunk `ST_bpGqmc9TL9Ph`:
- **`inviteToRingingMs: 3463`** → IT RANG (3.46s; was SIP 486 / no ring before).
- `inviteToAcceptMs: 21083` → answered; `Outbound SIP call established`; two-way RTP; earner agent
  ran ~27s and saved transcript `outcome=answered`.

**Backups (box):** `.env.VOBIZbak.20260615-164935`; trunk JSON snapshot
`var/did_swap_backup/outbound_trunks.20260615-164817.json`. State: `design/W-DID-SWAP-STATE.md`.

> NOTE: a fresh DID does NOT escape the carrier spam-flag long-term — the block follows BEHAVIOUR
> (velocity / near-zero answer / un-DLT 10-digit MSISDN), not the digits. It buys days, not immunity.
> The legal non-negotiable is a 140-series DID on a DLT-registered route (telephony-independence plan).

---

## 2. WARM-TRANSFER / HUMAN-HANDOFF RESTORED — same DID swap, missed restart
**Complaint:** human/warm transfer stopped connecting.

**Diagnosis (READ-ONLY, zero box mutation):** the warm-transfer **code is correct and WAS firing** —
tool called, hold music started, both handoff numbers dialed in priority order, AI exits after bridge.
The regression was **purely the SIP trunk**: the live INBOUND agent process was still dialing the human
over the **OLD spam-blocked trunk `ST_fmtVmNJmpzKa`** → every leg returned 486/408/500, no human bridged.

**Root cause = the missed restart.** The DID swap edited `.env` and restarted **only famit-caller**.
The **voice agent process captured the env at module import**, so the running `aim-voice-agent` still
held the OLD trunk in memory.

**Fix:** a single service restart of **`aim-voice-agent`** to reload the new trunk-id — NO code edit,
NO `agent.py` touch.

**Key facts:** warm transfer lives ONLY in `aim_voice_agent.py` (`_do_warm_transfer()` :779; tool on
`CustomerSalesAgent.transfer_to_human` :1854 and `ManagerAgent.transfer_to_human` :1324). The OUTBOUND
earner `agent.py` has ZERO transfer/handoff/function_tool — **warm transfer is INBOUND-ONLY** (an
outbound call has no transfer tool at all). State: `design/WARM-TRANSFER-DIAGNOSIS.md`.

---

## 3. ⭐ KEY LEARNING (blood-written this session)
**An `.env` change only reaches the processes you restart.** `caller.py`/`aim_voice_agent.py` read
`LIVEKIT_SIP_TRUNK_ID` once at import. Restarting **famit-caller ≠ reloading the voice agent.** Any env
mutation that affects the voice path must restart the **SPECIFIC** process that holds it
(`aim-voice-agent`), not just the caller. (Earner `agent.py` is NEVER restarted without founder sign-off
+ a real ring — but for inbound-only env changes, restart `aim-voice-agent`.)
→ logged to `AGENT_LEARNINGS.md` + `PLAYBOOK.md`.

---

## 4. LEADS MANAGEMENT FEATURE — LIVE on the panel
**Founder ask:** basic CRUD/management on the leads screen (he could not delete or sort his leads).

**Shipped (panel, FORTRESS `143.110.247.249`):**
- **`/leads`** — delete + sort.
- **`/run`** — sort.
- **BUILD_ID `xF8YUvBmTwYj_yP4w7WY4`** (panel rebuilt + deployed).
- Side effect of this deploy: the **Communication tab and Video Studio** are now VISIBLE in the panel.

---

## 5. TELEGRAM ECOSYSTEM — DIAGNOSIS (planned vs delivered vs missing)
The founder tested the Telegram system built earlier on 2026-06-15 and found gaps. READ-ONLY diagnosis
written to **`design/TELEGRAM-ECOSYSTEM-DIAGNOSIS.md`**. Live facts at diagnosis: caller.py md5
`ccf9715b`, agent.py `9150fabe` UNCHANGED, all comm flags ON for tenant `admin`, founder chat_id
`1862240811` persisted, `comm-poll.service` running.

**Headline:** the comm package is well-built and LIVE, but **wired into the WRONG finalize**
(outbound-only) and it **never seeds the brain's session with the real call facts**:
- **Complaint 1 — no Telegram follow-up after an INBOUND call.** ROOT CAUSE: the W1-P3 post-call hook
  (`caller.py:2796-2818`) lives inside `_finalize_call`, which is called from ONE place — the OUTBOUND
  dialer (`run_job`). The INBOUND path is a separate process (`aim_voice_agent.py`,
  `_AimSessionLogger.finish()`) that does NOT import `comm.post_call`/`comm.engine`/`comm.founder_alert`
  (grep = 0 hits). The founder's real test was an inbound call → no Telegram seam at all.
- **#1 fix = grounding:** seed `comm_sessions` post-call with the real call facts so the conversation
  brain stops hallucinating (explains complaints 1, 2, 4). Complaints 3, 5, 6 are mostly-present and
  need small additive work.

> This diagnosis is the input for the NEXT comm wave (move/duplicate the post-call hook onto the inbound
> finalize + seed the session) — earner-safe, additive, caller.py/comm only, never `agent.py`.

---

## 6. THIS WHOLE PRESERVATION / RESTORE WAVE
The founder is about to compact and start fresh and does NOT want to lose the chronological story.
This session = restore the live earner (outbound + transfer), ship the leads-mgmt UI, diagnose the
Telegram gaps, and write durable state (`design/W-DID-SWAP-STATE.md`, `design/WARM-TRANSFER-DIAGNOSIS.md`,
`design/TELEGRAM-ECOSYSTEM-DIAGNOSIS.md`, this summary, `RESTORE/04-SESSION-HISTORY.md`) so the next
session resumes with zero loss.

## EARNER GATE (held the entire session)
`agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED · famit-agent NEVER restarted · caller
`/health` 200 · 0 5xx · the ONLY ring was the ONE founder-authorized DID-swap verification call.

## STANDING ORDER AFTER THIS SESSION
- Outbound + warm-transfer RESTORED and proven. Leads-mgmt LIVE.
- Telegram needs the inbound-finalize hook + session-grounding fix (next comm wave) before it satisfies
  the founder's real test.
- Remember the new DID is a clock-reset, not immunity → 140-series + DLT is the real fix (founder action).
