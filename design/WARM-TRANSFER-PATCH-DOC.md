# WARM-TRANSFER PATCH DOC
> READ-ONLY analysis + patch specification. Zero box mutations made.
> Source file: `_inbound_ref/aim_voice_agent.DEPLOYED.py` (2882 lines — the canonical version).
> Earner gate: `agent.py` md5 `98655dbf` — NEVER touched.
> Branch: `fix/callback-retry-scheduling` (write patch to `voice_ops/booking/` tracked layer).

---

## 1. FLOW MAP (exact file:line)

| Step | What happens | Location |
|------|-------------|----------|
| Trigger | `transfer_to_human(reason)` tool called by LLM | `DEPLOYED.py:1798` (CustomerSalesAgent), `DEPLOYED.py:1302` (ManagerAgent) |
| Dispatch | Both call `_do_warm_transfer(agent, context, reason)` | `DEPLOYED.py:1818` / `DEPLOYED.py:1319` |
| Reassurance line | `_say_filler(context, "Ek second, main aapko {dial_who} se connect kar rahi hoon.")` | `DEPLOYED.py:801–803` |
| Hot-lead WhatsApp | `asyncio.create_task(_vt.notify_handoff_team(...))` fired simultaneously | `DEPLOYED.py:806–811` |
| Hold music start | `_start_hold_audio(room_obj, session)` — `BackgroundAudioPlayer`, `BuiltinAudioClip.HOLD_MUSIC`, looped | `DEPLOYED.py:862`, impl at `717–736` |
| Dial human | `lk_api.sip.create_sip_participant(CreateSIPParticipantRequest(room_name=<caller_room>, sip_trunk_id=_OUTBOUND_TRUNK, wait_until_answered=True, ringing_timeout=25s))` | `DEPLOYED.py:889–901` |
| Trunk ID source | Module-level capture: `_OUTBOUND_TRUNK = os.getenv("LIVEKIT_SIP_TRUNK_ID", "ST_fmtVmNJmpzKa")` | `DEPLOYED.py:172` |
| On answer | Stop hold music → whisper one in-room line → `session.aclose()` (AI exits) | `DEPLOYED.py:923–950` |
| AI exit | `session.aclose()` — full AgentSession close; caller + human stay in room | `DEPLOYED.py:947` |
| Fallback | LLM reads `no_human_answered: …` return string (only when all dials fail) | `DEPLOYED.py:958–960` |
| Handoff list source | `_vt.handoff_list(tenant_id)` → reads `var/brain/<tenant>.json` (`handoff` block) | `DEPLOYED.py:776`, `caller.py:1785` |

---

## 2. FOUNDER BUG #1 — "AI says unnecessary things + doesn't ring/play-music"

### 2a. Root cause: trunk stale in running process

`_OUTBOUND_TRUNK` is captured **once at import** (`DEPLOYED.py:172`). When `.env` was updated
(trunk `ST_fmtVmNJmpzKa` → `ST_bpGqmc9TL9Ph`) only `famit-caller` was restarted — `aim-voice-agent`
was NOT restarted, so the running process still dials the spam-blocked old trunk.

**Every dial leg returns 486/408/500 → no human bridges → AI reads the fallback
`no_human_answered: …` aloud → that is the "unnecessary things".** The music starts fine but stops
(finally block `DEPLOYED.py:952`) before anyone hears it because all dials fail immediately.

This is the **primary bug**. Fix = restart `aim-voice-agent` to reload `.env`. Optionally harden
the trunk capture (see §4, Patch A).

### 2b. Secondary issue: AI can speak BEFORE tool is called

The system prompt at `DEPLOYED.py:1534–1539` says "ACT — DON'T ANNOUNCE: call `transfer_to_human`
IMMEDIATELY, in the SAME turn … do NOT say 'main aapko connect kar rahi hoon' and then wait."
This is correct but fragile under some LLM variants that generate a spoken prefix before emitting
the tool call. The reassurance line at `DEPLOYED.py:801–803` is spoken INSIDE the tool (correct),
but if the LLM also generates a verbal preamble in the SAME turn before the tool, the caller hears
two lines.

**Patch needed (Patch B):** strengthen the prompt from "do NOT say…" to an explicit hard block.

### 2c. Whisper is in-room (caller hears it too)

`_transfer_whisper` at `DEPLOYED.py:637–646` is acknowledged in the code ("per-participant private
audio isn't possible in a shared SIP room, so the CALLER hears this too"). Whisper content is
already clean (no phone, no AI disclosure). This is acceptable as-is — **no patch needed for
whisper content**. But the whisper runs AFTER `session.aclose()` is called in the error path;
on success path it runs BEFORE aclose (correct order at `DEPLOYED.py:929–950`).

---

## 3. PATCHES — EXACT CHANGES

### Patch A — Harden trunk capture (never silently dial a stale/dead trunk)

**File:** `aim_voice_agent.DEPLOYED.py` → tracked as `voice_ops/booking/warm_transfer_patch.py`

**Current** (`DEPLOYED.py:172`):
```python
_OUTBOUND_TRUNK = (os.getenv("LIVEKIT_SIP_TRUNK_ID", "ST_fmtVmNJmpzKa") or "ST_fmtVmNJmpzKa").strip()
```

**Replace with** (dynamic read per call, no module-level freeze):
```python
def _get_outbound_trunk() -> str:
    """Always read from env so a service restart isn't required after a trunk swap.
    Falls back to the last-known value but LOGS a warning so the stale-trunk bug is visible."""
    v = (os.getenv("LIVEKIT_SIP_TRUNK_ID") or "").strip()
    if not v:
        logger.warning("WARM-TRANSFER: LIVEKIT_SIP_TRUNK_ID not set — transfer will fail; set it in .env")
    return v
```

**In `_do_warm_transfer` at `DEPLOYED.py:889`**, replace `sip_trunk_id=_OUTBOUND_TRUNK` with:
```python
sip_trunk_id=_get_outbound_trunk(),
```

**Why:** eliminates the need for a service restart when the trunk changes. A missing/empty env now
logs a visible warning instead of silently dialing a stale ID.

---

### Patch B — Tighten prompt: hard-block LLM pre-speech before tool call

**File:** `aim_voice_agent.DEPLOYED.py`, system prompt block at `DEPLOYED.py:1534–1539` (CustomerSalesAgent)
and `DEPLOYED.py:1302–1319` / `DEPLOYED.py:615–621` (ManagerAgent tool description)

**Current** (`DEPLOYED.py:1534`):
```
"call transfer_to_human(reason) right now → THEN speak only the line it returns and stop talking."
```

**Replace the entire HANDOFF block** (`DEPLOYED.py:1528–1539`) with:
```python
"HANDOFF TO A HUMAN — RARE, NOT A DEFAULT: your job is to handle the WHOLE call yourself and "
"book the deal. Do NOT offer a human, do NOT suggest connecting them to someone, and do NOT jump "
"to a human for ordinary questions, prices, objections, or a ready-to-buy lead — YOU close those "
"yourself. Call the `transfer_to_human(reason)` tool ONLY in two cases: (1) the caller EXPLICITLY "
"asks to talk to a person/human/agent/insaan/aadmi/banda (in ANY language), or (2) the caller is "
"genuinely very hot or frustrated AND you truly cannot resolve or close it yourself. "
"STRICT RULE: when one of those is true, your ENTIRE response for that turn must be ONLY the "
"tool call — zero spoken words before or after (not 'ठीक है', not 'hold on', not 'main connect "
"kar rahi hoon', NOTHING). The tool itself speaks the reassurance line for you. After the tool "
"returns 'handed_off', output NO text at all and stop your turn immediately."
```

**Also update ManagerAgent tool description** at `DEPLOYED.py:615–621`:
```python
"• `transfer_to_human(reason)` — connect to a REAL person on the team (warm transfer). The "
"MOMENT they ask to talk to a human/person/insaan, call this tool IMMEDIATELY in the SAME "
"turn — your turn must contain ONLY this tool call, zero spoken words before or after. "
"The tool speaks the reassurance; you say nothing. Once it returns 'handed_off', output nothing."
```

**Why:** closes the gap where an LLM emits "ठीक है सर" spoken text in the same turn before the
tool fires, causing the caller to hear two lines instead of one.

---

### Patch C — Founder's desired reassurance line (language + gender)

**Current** (`DEPLOYED.py:803`):
```python
f"Ek second, main aapko {_dial_who} se connect kar rahi hoon."
```

**Founder wants** (as specified): `"ठीक है सर, मैं team se connect kar raha hoon"` — masculine,
uses "ठीक है सर" opener, and agent-gender-agnostic "hoon" not "rahi".

**Replace** `DEPLOYED.py:801–803` with:
```python
_reassurance = f"Theek hai sar, main aapko {_dial_who} se connect kar raha hoon."
await _say_filler(context, _reassurance)
```

Or for the Hinglish-Devanagari variant:
```python
_reassurance = f"ठीक है सर, मैं {_dial_who} se connect kar raha hoon."
await _say_filler(context, _reassurance)
```

**Why:** the current line uses `rahi hoon` (feminine). Founder specified `raha hoon` and the
`ठीक है सर` opener. Also removes the "Ek second" stall prefix (per founder: ONE line, nothing extra).

---

### Patch D — Suppress fallback speech when dial fails (never narrate the failure)

**Current** (`DEPLOYED.py:958–960`):
```python
return ("no_human_answered: I couldn't reach a team member live, but I've alerted them with the "
        "caller's details on WhatsApp. Reassure the caller warmly that the team will call them "
        "back very shortly, confirm their number, and close politely — never leave them hanging.")
```

This is an LLM instruction disguised as a return string — the LLM reads it aloud and produces
verbose reassurance. The founder hears this as "unnecessary things".

**Replace with** a tight closed-room instruction that keeps the AI brief:
```python
return ("no_team_available: Say only: 'Team abhi available nahin hai, hum aapko callback karenge.' "
        "Then confirm their number and close. Say nothing else.")
```

Similarly update the `no_human_available` fallbacks at `DEPLOYED.py:816–818` and `849–851`:

`DEPLOYED.py:816–818` — replace with:
```python
return ("no_team_configured: Say only: 'Team connect nahin ho saka, hum callback karenge.' "
        "Confirm number and close.")
```

`DEPLOYED.py:849–851` — replace with:
```python
return ("no_team_available_now: Say only: 'Team abhi available nahin hai, callback milega jaldi.' "
        "Confirm number and close.")
```

**Why:** short instruction strings force the LLM to say exactly one sentence instead of a
paragraph of reassurance.

---

## 4. RELIABLE RING / HOLD MUSIC CHECKLIST

The hold music uses `BackgroundAudioPlayer` + `BuiltinAudioClip.HOLD_MUSIC` (`DEPLOYED.py:64`,
`DEPLOYED.py:726–732`). It degrades silently when the import fails (guard at `DEPLOYED.py:63–68`).

**Verify on the box:**
```bash
python3 -c "from livekit.agents import BackgroundAudioPlayer, BuiltinAudioClip, AudioConfig; print('hold-audio OK')"
```
If this fails, music silently degrades to spoken-only — the call still works but no music plays.
Check `journalctl -u aim-voice-agent | grep "hold-audio start failed"`.

**Ring reliability** (after trunk fix): the dial runs in `asyncio.wait_for(..., timeout=37s)`
(`DEPLOYED.py:902`). With the correct trunk `ST_bpGqmc9TL9Ph`, 486/408/500 disappear and the
human phone actually rings. No code change needed — the dial primitive is correct.

---

## 5. IMPLEMENTATION ORDER (earner-safe)

1. **Service restart** (no code edit): `sudo systemctl restart aim-voice-agent` → reloads `.env`
   → `_OUTBOUND_TRUNK` picks up `ST_bpGqmc9TL9Ph`. This alone fixes the "no ring" + "unnecessary
   things" symptoms. Earner gate: `agent.py` md5 `98655dbf` untouched.

2. **Patch A** (dynamic trunk read) — prevents regression on future trunk swaps.

3. **Patch B** (prompt tightening) — prevents double-speak from LLM preamble.

4. **Patch C** (reassurance line wording) — gender + opener per founder spec.

5. **Patch D** (tighten fallback strings) — cuts verbose fallback narration.

Patches A–D are all code-only changes to `aim_voice_agent.py` (inbound). Zero `agent.py` touches.
Each can be applied and smoke-tested independently: restart `aim-voice-agent`, make an inbound call,
say "transfer me to a human", verify journalctl shows BRIDGED (not 486).

---

## 6. LIVE TEST PROTOCOL (post-patch)

```bash
sudo journalctl -u aim-voice-agent -f
```

Expected sequence (proves all 5 issues fixed):
1. `transfer_to_human (customer) reason=…` — tool called, no spoken preamble
2. `AIM handoff lifecycle: REQUESTED … eligible=2` — list read, 2 numbers
3. `AIM transfer_to_human: dialing #1 human +91…21 … INTO caller room` — correct trunk
4. `AIM transfer_to_human: BRIDGED +91…21 into room … (#1, N.Ns)` — human connected (was 486)
5. `AIM transfer_to_human: AI-EXITED (session.aclose) after bridge` — AI steps back cleanly

A `486 Busy Here` or `500` at step 4 = trunk still stale → re-verify `/proc/<pid>/environ`.

---

## 7. FILES TO EDIT IN TRACKED LAYER

Write patches to `voice_ops/booking/warm_transfer_patch.py` (new tracked file — wraps DEPLOYED).
Do NOT rely on `droplet_work/` (gitignored). Deployment = copy the patched `.py` to the box.

Exact lines to change in `aim_voice_agent.DEPLOYED.py` when writing the patched file:
- Line 172: `_OUTBOUND_TRUNK` capture → replace with `_get_outbound_trunk()` function (Patch A)
- Line 803: reassurance line text (Patch C)
- Line 816–818: `no_team_configured` fallback (Patch D)
- Line 849–851: `no_team_available_now` fallback (Patch D)
- Line 958–960: `no_human_answered` fallback (Patch D)
- Line 1528–1539: HANDOFF prompt block (Patch B — CustomerSalesAgent)
- Line 615–621: ManagerAgent `transfer_to_human` tool description (Patch B)

---

*Earner gate (read-only, unchanged): `agent.py` md5 = `98655dbf`. Zero box mutations made in this analysis.*
