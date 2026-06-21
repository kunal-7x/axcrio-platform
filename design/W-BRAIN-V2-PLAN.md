# W-BRAIN-V2 — BRAIN-ONLY UPGRADE (prompt.py text only; voice UNTOUCHED)

**Date:** 2026-06-19 · **Scope:** `droplet_work/prompt.BRAINv2.py` ONLY.
**Hard guarantee:** this wave changes ONLY the brain TEXT (the system prompt the
LLM reads). It does **not** touch `agent.py`, the TTS/STT plugins, voice_id,
`EL_STABILITY`, `KERNEL_OUTBOUND`, or any decoding/turn-detection code. The
founder's perfect voice (timbre, prosody, latency) is **byte-identical** before
and after. Deploy = copy one `.py` and restart.

---

## 1. WHAT THE RED-TEAM FOUND (and what a prompt CAN vs CANNOT fix)

Three adversarial lenses agreed on one structural truth: **the worst live
failures are RUNTIME/ARCHITECTURE bugs in `agent.py`, not prompt-content bugs.**
A system prompt is persuasion, not a mechanism — it cannot raise its own token
ceiling or suppress a second `session.say()`.

| # | Failure | Real root cause | Fixable in THIS file? |
|---|---------|-----------------|------------------------|
| a | Double / ghost goodbye (T9+T10, T7+T8) | `agent.py` `_confirm_then_hangup` fires on the **assistant** turn (≈line 776) + closure heuristic on a stale tail → a SECOND independent `session.say()` | **NO** (agent.py) — prompt only reduces in-completion self-answering |
| c/g | Hard mid-word truncation ("3 BH", "25 एकड़…", "बहुत अच्छा! मैं") | `agent.py` `max_completion_tokens=90` (GROQ_MAX_TOKENS) guillotines the stream after generation; Devanagari is token-expensive in llama BPE | **NO at the cap** — but prompt CAN make the model self-police length so it rarely reaches the cap |
| d | Language-mirror lag (English turn answered in Hindi) | `agent.py` pipeline race: the Hindi turn was queued before lang-detect flipped | **Prompt-side already strong**; runtime race persists |
| b | Name overuse ("कुणाल जी… कुणाल जी…") | soft cap | **YES (mitigated)** — already capped in SHARED_RULES |
| e | Recording disclaimer + double-question + "इच्छा" | content | **YES — closed** (banned by name) |
| h | Roman Hindi instead of Devanagari | content | **YES — closed** (Devanagari-only rule) |
| f | Hallucinated "previous call" | content | **YES — closed** (no-PICHHLI-BAAT rule) |

**Verdict the founder must hear honestly:** failures **a, c, g, d** can only be
*fully* closed by an `agent.py` change (raise `max_completion_tokens` to ~160–180
for Devanagari + a sentence-boundary trim before TTS; gate the hangup `say()` on
the **latest USER turn**; pass the freshest lang to the turn). Those are a
SEPARATE, voice-touching wave and are explicitly OUT of this brain-only scope.
This wave installs the **prompt-side backstops** the red-team recommended so the
model rarely *reaches* the truncation cap and never *starts* an enumeration it
cannot finish.

---

## 2. SURGICAL EDITS APPLIED (this file only — 3 targeted edits)

All edits are additive text inside the existing rules; no function signature, no
render structure, no resolver, no vendor-injection logic changed. v2-OFF output
stays byte-identical to base render (verified).

**EDIT 1 — Rule 2: countable HARD BUDGET + no-enumeration backstop** (the #1
red-team ask across all three lenses). Added after the "✂️ ALWAYS FINISH YOUR
SENTENCE" bullet:
> 🔢 HARD BUDGET — COUNT BEFORE YOU SPEAK: entire reply ≤ ~30 words (~200 chars),
> a HARD ceiling (line is cut mid-word if exceeded). Nearing the limit → end the
> sentence with a full stop immediately; never open a clause/list/number you
> can't finish. NEVER begin "दो BHK, तीन BHK, और तीन BHK duplex…" / "85 lakh से
> शुरू, फिर…" — give ONE option/number, finish, then "...और बताऊँ?".

*Why:* "land a complete thought" gave the model no countable target; a hard word
cap it can self-check beats the cap it cannot see. This is the strongest
prompt-only hedge against (c)/(g). **The token cap is still the disease — the
real cure is the agent.py wave.**

**EDIT 2 — "numbers in words" conflict resolution** (lens 2: spelling every
number in words while under a 90-token Devanagari cap is a collision course).
Kept the words-not-symbols rule (correct for TTS pronunciation) but added: spelled
numbers are long → **one number per turn, never a price+size+floor list.**

**EDIT 3 — Flow step 5 (KEY DETAILS)** anti-enumeration: "give ONE relevant
point + ONE number, then pause; never count out a list of configs/numbers in one
turn (it gets cut in half)."

No change to rule 1 (language/Devanagari — already excellent), the OPENER strict
rules (greeting-once, no-recording, no-double-question, no-hallucinated-history —
already closed), or the name cap (already present).

---

## 3. py_compile + invariants (verified locally)

- `python -m py_compile prompt.BRAINv2.py` → **PY_COMPILE_OK**
- `resolve_providers({}) == _DEFAULT_PROVIDERS` → **PASS** (resolver undrifted)
- `build_system_prompt_v2(GODREJ_FIELDS) == build_system_prompt(GODREJ_FIELDS)`
  (vendor feature OFF) → **PASS** (byte-identical; golden oracle stays green)
- Render len 18259; HARD BUDGET rule present; anti-enumeration present.
- **Local md5 of prompt.BRAINv2.py: `17ad3e0d133721c4a673f258f6420df5`**

---

## 4. BRAIN-ONLY DEPLOY PLAN (READY — NOT executed)

Box: `famit-livekit` / voice box, app dir `/opt/famit-agent/`. One file changes.

```bash
# 0) timestamp
TS=$(date +%Y%m%d-%H%M%S)

# 1) backup the LIVE brain on the box
ssh <voice-box> "cp /opt/famit-agent/prompt.py /opt/famit-agent/prompt.py.BRAINv2bak.$TS && echo BACKED_UP $TS"

# 2) ship the new brain (local -> box)
scp C:/Users/kunal/Desktop/caps/droplet_work/prompt.BRAINv2.py <voice-box>:/opt/famit-agent/prompt.py

# 3) compile on the box (must be clean BEFORE restart)
ssh <voice-box> "cd /opt/famit-agent && python3 -m py_compile prompt.py && echo BOX_PY_COMPILE_OK"

# 4) restart the agent
ssh <voice-box> "systemctl restart famit-agent && echo RESTARTED"

# 5) ASSERT — voice byte-identical + healthy (ALL must pass)
ssh <voice-box> '
  systemctl show famit-agent -p NRestarts --value;            # expect 0
  journalctl -u famit-agent -n 40 --no-pager | grep -i "registered worker\|capsy";  # worker "capsy" re-registers
  md5sum /opt/famit-agent/agent.py;     # MUST equal 5c055a31...  (voice UNCHANGED)
  grep -E "^EL_STABILITY=" /opt/famit-agent/.env;   # MUST be EL_STABILITY=0.55  (UNCHANGED)
  grep -E "^KERNEL_OUTBOUND=" /opt/famit-agent/.env; # MUST be KERNEL_OUTBOUND=0 (UNCHANGED)
'
```

**GO criteria (all true):** `py_compile` clean on box · worker **capsy**
re-registers in logs · `NRestarts=0` · `agent.py` md5 == **5c055a31** (voice
byte-identical) · `.env` `EL_STABILITY=0.55` UNCHANGED · `KERNEL_OUTBOUND=0`
UNCHANGED. If ANY fails → ROLLBACK immediately (§5).

Then: **founder places ONE real outbound test call** and runs the checklist (§6).

---

## 5. ONE-COMMAND ROLLBACK (restore prior brain + restart)

```bash
ssh <voice-box> 'cp $(ls -t /opt/famit-agent/prompt.py.BRAINv2bak.* | head -1) /opt/famit-agent/prompt.py && systemctl restart famit-agent && echo ROLLED_BACK'
```

(Restores the most-recent `prompt.py.BRAINv2bak.<ts>` and restarts. Since only the
brain text changed, rollback is fully sufficient — nothing else was mutated.)

---

## 6. FOUNDER REAL-CALL TEST CHECKLIST (the only truth)

Place ONE real outbound call. Watch/listen for:

1. **Opener** — ONE greeting only (no "नमस्ते… नमस्ते", no half-greeting that
   restarts). No "call is being recorded" line. ONE question (name-confirm OR
   "दो minute?"), not both. No "हमारी पिछली बात हुई थी".
2. **No mid-word cut** — no reply ends like "3 BH…" / "25 एकड़ में फैला…" /
   "बहुत अच्छा! मैं". Each reply is a COMPLETE short sentence.
3. **No number-list dump** — when asked configs/price, it gives ONE option + asks
   "...और बताऊँ?" rather than reeling off "2, 3, 4 BHK… price… floors".
4. **Language mirror** — answer it in English mid-call → it should reply in
   English on that turn (NOTE: a one-turn lag here is the agent.py race, not the
   brain — flag it but it is the next wave).
5. **Devanagari only** — Hindi replies are in देवनागरी, never "Haan bilkul".
6. **No double goodbye** — at the end it says ONE closing line and stops (NOTE: a
   second goodbye = the agent.py hangup `say()`, not the brain — flag for the
   agent.py wave).
7. **Name** — your name said at most once or twice total, not every turn.
8. Voice itself **sounds identical** to before (timbre/speed/warmth).

If 1,2,3,5,7 are good → the brain wave succeeded. If 4 or 6 still show → that is
the KNOWN agent.py residue, queued as the next (voice-touching) wave.

---

## 7. KNOWN RESIDUE → NEXT (separate) VOICE-TOUCHING WAVE

Not in this brain-only scope; queued for an `agent.py` wave under full
earner-gate (one box-mutating change + integrated smoke + revert):
- Raise `GROQ_MAX_TOKENS` 90 → ~160–180 (Devanagari headroom) **+** sentence-
  boundary trim before TTS so a partial final sentence is dropped, never spoken
  mid-word. (closes c/g at the mechanism)
- Gate `_confirm_then_hangup` on the **latest USER turn's** affirm/no signal
  (never the assistant's own tail); suppress any second generation with no
  intervening user STT; drop any canned appended farewell. (closes a)
- Pass the freshest detected language to the turn so rule-1 can't be bypassed by
  a stale queued turn. (closes d)
