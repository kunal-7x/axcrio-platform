# W-BRAIN-V2 — BRAIN-ONLY red-team hardening (per-wave run log)

**Date:** 2026-06-19 · **Status:** BUILD COMPLETE + verified · **Deploy:** READY, founder-gated (NOT executed)
**File:** `droplet_work/prompt.BRAINv2.py` ONLY · **Voice:** byte-identical (no agent.py / .env / voice_id change)
**Plan:** `design/W-BRAIN-V2-PLAN.md` · **Ledger:** `WORKFLOW_LEDGER.md` (W-BRAIN-V2)

## Goal
Apply the three lenses' red-team fixes that are *closable in the prompt layer* to
the campaign brain, re-verify py_compile + byte-identity, and produce a
ready-but-unexecuted brain-only deploy + rollback plan. Voice stays perfect.

## The harsh red-team truth (recorded so we don't relitigate)
All 3 lenses agreed: the worst failures live in `agent.py`, not the prompt.
- (c)/(g) hard mid-word truncation ← `max_completion_tokens=90` cuts the stream
  AFTER generation; Devanagari is token-expensive. A prompt cannot raise its own
  cap → can only make the model self-police so it rarely hits the cap.
- (a) double/ghost goodbye ← `_confirm_then_hangup` fires on the **assistant**
  turn (≈agent.py:776) → a SECOND independent `session.say()`. A prompt cannot
  suppress an orchestrator-issued say().
- (d) language lag ← pipeline race (Hindi turn queued before lang-detect flips).
- Already closed at prompt level: (e) recording/double-Q/"इच्छा", (h) Roman→
  Devanagari, (f) hallucinated previous call, (b) name overuse (capped).

## Edits applied (3, additive, no structure change)
1. **Rule 2 — HARD BUDGET (countable):** ≤ ~30 words / ~200 chars, "count before
   you speak", stop at a full stop when nearing the limit, NEVER start an
   enumeration/number you can't finish. (the #1 cross-lens ask; the strongest
   prompt-only hedge vs truncation)
2. **"numbers in words" conflict fix:** keep words-not-symbols (TTS correctness)
   but ONE number per turn, no price+size+floor list (spelled numbers are long).
3. **Flow step 5 KEY DETAILS:** ONE point + ONE number then pause; never a config
   /number list in one turn (it gets cut in half).

## Verification (local, all PASS)
- `python -m py_compile prompt.BRAINv2.py` → PY_COMPILE_OK
- `resolve_providers({}) == _DEFAULT_PROVIDERS` → PASS (resolver undrifted)
- `build_system_prompt_v2(GODREJ_FIELDS) == build_system_prompt(GODREJ_FIELDS)`
  (vendor OFF) → PASS (byte-identical; golden oracle green)
- render len 18259; HARD BUDGET + anti-enumeration present
- **local md5(prompt.BRAINv2.py) = `17ad3e0d133721c4a673f258f6420df5`**

## Deploy (READY — NOT run) — brain text only
backup live `/opt/famit-agent/prompt.py` → `prompt.py.BRAINv2bak.<ts>` · scp
prompt.BRAINv2.py → `/opt/famit-agent/prompt.py` · `py_compile` on box ·
`systemctl restart famit-agent` · ASSERT worker "capsy" re-registers + NRestarts=0
+ **agent.py md5 == 5c055a31 (UNCHANGED)** + `.env EL_STABILITY=0.55` UNCHANGED +
`KERNEL_OUTBOUND=0` UNCHANGED · founder ONE real test call (checklist in plan §6).
Full commands: `design/W-BRAIN-V2-PLAN.md` §4.

## Rollback (one command)
`cp $(ls -t /opt/famit-agent/prompt.py.BRAINv2bak.* | head -1) /opt/famit-agent/prompt.py && systemctl restart famit-agent`

## Residue → NEXT separate voice-touching wave (earner-gated, NOT this wave)
- raise GROQ_MAX_TOKENS 90→~160-180 + sentence-boundary trim before TTS (c/g)
- gate `_confirm_then_hangup` on the latest USER turn; suppress 2nd generation w/o
  intervening user STT; drop any canned appended farewell (a)
- feed freshest detected language to the turn (d)
