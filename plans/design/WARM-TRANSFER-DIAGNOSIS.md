# WARM-TRANSFER / HUMAN-HANDOFF REGRESSION — DIAGNOSIS

> READ-ONLY diagnosis. Zero box mutations made. 2026-06-15.
> Earner gate verified UNCHANGED: `agent.py` md5 = `9150fabe4ff62b4b4470f9a87df346e5`; `famit-agent` active; box reachable.
> Box: `famit@168.144.153.145` (key `C:\Users\kunal\.ssh\do-blr-test\id_ed25519`).

---

## TL;DR (decision-ready)

The warm-transfer **code is correct and IS firing** — tool called, hold music started, both
handoff numbers dialed in priority order, AI exits after bridge. The regression is **purely the
SIP trunk**: the live inbound-agent process is dialing the human over the **OLD spam-blocked
trunk `ST_fmtVmNJmpzKa`**, so every dial leg returns **`486 Busy Here` / `408 timeout` / `500`**
and no human is ever bridged in.

The DID swap (`.env` → `ST_bpGqmc9TL9Ph`) was applied at **11:19 today and ONLY restarted
`famit-caller`. The voice agents were NOT restarted**, so the running inbound process still holds
the old trunk in memory (env captured at module import). **The fix is a single service restart of
`aim-voice-agent` — NO code edit, NO `agent.py` touch.**

---

## 1. WHERE the transfer tool lives

- **`aim_voice_agent.py`** (box md5 `1614be09`, the INBOUND / AI-Manager agent) — this is the ONLY
  file with warm-transfer. Service: `aim-voice-agent.service` → `/opt/famit-agent/aim_voice_agent.py`.
- Tool defined on **both** agent classes, both delegating to one shared impl:
  - `CustomerSalesAgent.transfer_to_human` — **`aim_voice_agent.py:1854`** (the lead/customer-facing one)
  - `ManagerAgent.transfer_to_human` — `aim_voice_agent.py:1324`
  - Shared impl **`_do_warm_transfer()` — `aim_voice_agent.py:779`**
- **`agent.py` (OUTBOUND earner) has ZERO transfer/handoff/function_tool** (grep count = 0). So warm
  transfer works on **INBOUND calls only**. An outbound call has no transfer tool at all (relevant for
  the live test — see §7).
- `caller.py` holds only the handoff-list CRUD + hot-lead WhatsApp (`_handoff_get` `caller.py:1785`,
  `notify_handoff_team` `caller.py:1911`), not the in-call bridge.

## 2. HOW it warm-transfers (mechanism — correct, matches founder spec)

`_do_warm_transfer` (`aim_voice_agent.py:779`):
1. Reads handoff team, filters enabled + in-hours (priority order).
2. Speaks **ONE short line** via `_say_filler` (`:817`): `"Ek second, main aapko {name} se connect kar rahi hoon."`
3. Fires hot-lead WhatsApp simultaneously.
4. Starts **HOLD music** in the caller's room (`_start_hold_audio`, `:872`).
5. **Dials each human INTO THE SAME room** via `CreateSIPParticipantRequest` (`:911`):
   `sip_trunk_id=_OUTBOUND_TRUNK`, `room_name=<caller room>`, `wait_until_answered=True`,
   `ringing_timeout=25s` → a warm conference, no REFER, carrier-agnostic.
6. On answer: stops hold, whispers one context line, then **`session.aclose()` (`:970`) — the AI exits**
   while caller + human stay in the room. Correct per spec.

So mechanism = exactly what the founder described (one line → hold music → dial handoff number into the
same SIP room → AI exits). **Nothing in the logic is broken.**

## 3. HANDOFF LIST — POPULATED ✅

- Source: Business Brain block `handoff` in `var/brain/<tenant>.json`, read by `_handoff_get`
  (`caller.py:1785`); the agent fetches it via `_vt.handoff_list` (`aim_voice_agent.py:798`).
- **Founder tenant `admin` IS populated**: `/opt/famit-agent/var/brain/admin.json` has **2 entries**,
  both `enabled=True`, `hours=24x7`, priorities 1 (`…9021`) and 2 (`…8830`), role `founder`.
- (Other tenant `21d0a13603da` has no handoff block — irrelevant to the founder.)
- **Handoff list is NOT the problem.**

## 4. WHICH TRUNK the transfer dials — THE BUG

- `_OUTBOUND_TRUNK` = **module-level** capture at import: `aim_voice_agent.py:172`
  `_OUTBOUND_TRUNK = os.getenv("LIVEKIT_SIP_TRUNK_ID", "ST_fmtVmNJmpzKa")`.
- **Live `.env` (on disk) NOW = `ST_bpGqmc9TL9Ph`** (the new DID trunk; `.env` mtime `2026-06-15 11:19:36`).
- **BUT the running inbound process still holds the OLD trunk.** Proof from `/proc/<pid>/environ`:
  `LIVEKIT_SIP_TRUNK_ID=ST_fmtVmNJmpzKa` (the OLD spam-blocked trunk).
- Timeline (the regression):
  - `aim-voice-agent` ActiveEnter = **2026-06-14 15:51:05 UTC** (≈20h BEFORE the swap).
  - `.env` trunk swap = **2026-06-15 11:19:36 UTC**.
  - `famit-caller` restarted **11:19:49 UTC** (picked up new trunk) — **voice agents were NOT restarted.**

## 5. ROOT CAUSE (ranked, with evidence)

**(a) #1 — Transfer dial fails on the OLD spam-blocked outbound trunk `ST_fmtVmNJmpzKa`** because the
running `aim-voice-agent` process never reloaded `.env` after the DID swap. **CONFIRMED by live logs**
(`journalctl -u aim-voice-agent`):
  - `10:10:42  dialing #1 +91…21 … 486: Busy Here (status 429 resource_exhausted)` ← carrier spam-block signature
  - `10:10:57  dialing #2 +91…30 … update room failed: could not connect after timeout, status=500`
  - `06:51:47  +91…30 … sip request timed out, status=408`
  → every dial leg fails at SIP, falls through to the WhatsApp+callback fallback → **no human bridged, no
    music heard past the failed ring**. This is the founder's "no transfer happens."

**(b) NOT a factor — the AI does NOT actually ramble.** Tool is called immediately and correctly
(`10:10:17  transfer_to_human (customer) reason='caller explicitly asked to talk to a human'`),
followed instantly by `REQUESTED → dialing #1`. The single reassurance line is one short Hinglish
sentence (`:817`). The "says a lot of unnecessary things" the founder perceived is the **fallback
return-string** the LLM reads aloud AFTER both dials fail (e.g. `no_human_answered: … reassure the
caller … team will call back …` at `:981`) — i.e. a SYMPTOM of (a), not a separate prompt bug. Once the
trunk works and the human bridges in, that fallback never plays.

**(c) Tool not called** — ruled out (logs show it called).
**(d) Hold-music / SIP move-participant API** — ruled out (dial fails before any move; bridge logic is sound).
**(e) Handoff list empty** — ruled out (§3, 2 enabled entries).

## 6. DID THE DID SWAP ALREADY FIX IT?

**Partially — on disk yes, in the running process NO.** `.env` already points at the good trunk
`ST_bpGqmc9TL9Ph`, and `famit-caller` already runs on it. But the **inbound voice agent process must be
restarted to pick it up.** Until then, transfers keep dialing the dead trunk. So the dial leg is **one
restart away from fixed**, not already fixed.

## 7. MINIMAL EARNER-SAFE FIX

**No code edit. No `agent.py` touch. Restart ONE non-earner service so it reloads `.env`:**

```
sudo systemctl restart aim-voice-agent      # reloads .env -> _OUTBOUND_TRUNK = ST_bpGqmc9TL9Ph
```

- This restarts ONLY the **inbound** voice agent (additive, NOT the outbound earner). `famit-agent`
  (the earner, `agent.py`) is **untouched** — md5 stays `9150fabe`, no restart, no ring risk.
- Verify after restart: `sudo cat /proc/$(systemctl show aim-voice-agent -p MainPID --value)/environ | tr '\0' '\n' | grep LIVEKIT_SIP_TRUNK_ID` → must read `ST_bpGqmc9TL9Ph`.
- Earner gate (before+after): `agent.py` md5 `9150fabe` unchanged; `famit-agent` active & not restarted;
  `curl -s localhost:8209/health` 200.
- Optional hardening (later, code change — do NOT block the fix): drop the hardcoded fallback default at
  `aim_voice_agent.py:172` so a missing env can never silently dial a stale/dead trunk. Not required for
  the fix; the restart alone resolves the regression.
- **Outbound transfer gap (separate, larger):** if the founder also wants warm transfer on OUTBOUND
  calls, that needs the tool added to `agent.py` (the sacred earner) — flag as a future earner-gated wave
  (backup + ONE change + live real-call smoke + revert). NOT part of this fix.

## 8. LIVE TEST PLAN (after the restart)

Founder said we can call HIM outbound on the new trunk. **Caveat:** the warm-transfer tool exists ONLY on
the INBOUND agent. Two clean options:

- **Preferred (tests the real fix): INBOUND.** Founder calls the inbound DID; on the AI call he says
  *"transfer me to a human."* Expect: ONE short line → hold music → handoff `…9021` (priority 1) dialed
  in → on answer, AI exits, founder + human keep talking.
- **If only outbound is available:** an outbound earner call will NOT offer transfer (no tool in
  `agent.py`) — so use the outbound call only to confirm the new trunk dials clean, then do the inbound
  call above to prove the transfer.

Evidence to capture (proves each step) from `sudo journalctl -u aim-voice-agent -f`:
1. `transfer_to_human (customer) reason=…`  → tool called
2. `handoff lifecycle: REQUESTED … eligible=2`  → list read
3. `dialing #1 human +91…21 … INTO caller room`  → correct number, same room
4. **`BRIDGED +91…21 into room … (#1, N.Ns)`**  → human actually connected (the win; was `486` before)
5. `AI-EXITED (session.aclose) after bridge`  → AI stepped back
6. on hangup: `handoff lifecycle: HUMAN-HANGUP … ending caller call`

A `486 Busy Here` / `408` / `500` at step 4 (instead of `BRIDGED`) = the restart didn't take the new
trunk → re-check `/proc/<pid>/environ`.

---

### Read-only earner gate at diagnosis time
`agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` (UNCHANGED) · `famit-agent` active · no box mutation made.
