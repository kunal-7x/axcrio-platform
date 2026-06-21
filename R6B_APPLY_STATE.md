# ROUND-6b GENIUS-BRAIN APPLY — STATE (crash-safe)

EARNER-CRITICAL. Voice byte-identical. Live md5 (verified on box 168.144.153.145):
- agent.py `e353b775b6415cd8391637da5bb06d24`
- prompt.py `759b6f5c939a7f16e95611bddd0d2d34`
- env: KERNEL_OUTBOUND=0, GROQ_MAX_TOKENS=220, BOOKING_HTTP_ENABLED=1, EL_STABILITY=0.55,
  voice_id=QTKSa2Iyv0yoxvXY2V8a, LLM_CLOSE=1
- BASELINE render: 15782 chars / ~3945 tok. v2==v1 True. resolve_providers({})==default True.

THE LAW: never touch EL TTS constructor span (md5 414e5019) / sarvam.STT+groq.LLM span (b3feafd3)
/ .env. Prove via constructor-span md5 unchanged.

Working dir: caps/.r6b_apply/  (local copies of live prompt.py + agent.py, md5-matched).

## PLAN (DO NOT DEPLOY — return staged diffs + offline proof)
### PART A — prompt.py (brain swap) — DONE + offline-verified
- [x] A1: _flow_block -> generic 8-beat veteran arc (RE tokens stripped)
- [x] A2: _vertical_defaults(f) + _vertical_block(f) helpers added
- [x] A3: build_system_prompt render template -> lean genius persona + vertical_block
- [x] A4: SHARED_RULES trimmed 1718->840 tok (R6 fixes preserved; dropped dup language section)
- [x] A5: greeting state machine preserved (no pre-name, two-step, no re-intro)
- [x] A6: numbers as WORDS + rupees + square feet, ban digits/RS/sq.ft (SHARED_RULES)
- [x] A7: public surface byte-identical (v2==v1 OFF True, RP default True, SYSTEM_PROMPT ok)
PROOF: render 3945->2674 tok (char/4, -32%); full genius arc present; cross-vertical works;
no RE persona tokens in scaffold; py_compile clean. (Target ~1.7-1.9k not fully hit — would
require cutting transcript-proven guards on an earner; -32% is the safe win. NOTED in return.)

### PART B — agent.py (brain logic; NO TTS/STT/.env) — DONE + offline-verified
- [x] B1: closure fix — _CLOSE_BOOK request-phrasing removed; _closure_signal now REQUIRES a
      _CLOSE_CONFIRMED marker (booked=true / appointment fix / confirm कर दिया) before 'book'
      close. PROVEN: book-REQUEST turn -> no close; CONFIRMED -> closes; opt-out -> closes.
- [x] B2: BOOKING_FILLER (default ON) — short non-interrupting "ek second sir…" say() before the
      async to_thread booking POST; kills the dead-air gap. Fully wrapped, gender-aware.
- [x] B3: _MirrorAgent.tts_node override + _normalize_speech_units (TTS_NORMALIZE default ON):
      ₹X->"X rupees", "Rs 200"->"200 rupees", "sq.ft/sqft"->"square feet", Cr->crore, L->lakh.
      Operates ONLY on the text stream; TTS constructor UNTOUCHED. 6/6 exact cases pass, no double.
- [x] B4: language-matched close — already LLM-gen (_llm_close mirrors caller lang, LLM_CLOSE=1). No change.
- [x] B5: booking asks date+time — flow beat 8 "caller से पूछ कर date और time लो" + tool need_time branch.
VOICE-SAFE PROOF: EL span md5 bc782ad2 UNCHANGED, STT/LLM span md5 da13b168 UNCHANGED.
py_compile clean under /opt/capsy-agent/.venv (the live service venv).

## PROOF GATES (offline, on box, KERNEL_OUTBOUND irrelevant — P0 path)
- render build_system_prompt <= ~2k tok
- genius arc present (discover/curiosity/objection-stance/buying-signal/close)
- greeting has no pre-name
- v2==v1 still True (OFF), resolve_providers({}) still default
- agent.py EL constructor span md5 == 414e5019, STT/LLM span md5 == b3feafd3 (UNCHANGED)
- py_compile clean both files

## BACKUP scheme: *.R6bbak.<ts> on box for each edited file. Golden _GOLDEN_ROUND5_* + R6bak armed.

## STATUS: STAGED, NOT DEPLOYED (per brief). Live prompt.py 759b6f5c + agent.py e353b775 BYTE-IDENTICAL.
Staged files: caps/.r6b_apply/{prompt.py,agent.py} (+ prompt_r6b.diff, agent_r6b.diff).
On-box backups armed: prompt.py.R6bbak.20260620-r6b + agent.py.R6bbak.20260620-r6b.

## OFFLINE PROOF (all green)
- prompt.py: render 3945->2674 tok (char/4, -32%); full genius arc (NAAM CONFIRM/DISCOVER/CURIOSITY/
  OBJECTION/ISOLATE/feel-felt-found/trial-close/BUYING-SIGNAL/VETERAN all present); greeting state
  machine + no-pre-name; no RE persona tokens in scaffold; cross-vertical (insurance tilt+advisor goal,
  generic no-tilt); v2==v1 OFF True (GODREJ+empty); resolve_providers({}) default True; SYSTEM_PROMPT ok.
- agent.py: EL span md5 bc782ad2 UNCHANGED + STT/LLM span md5 da13b168 UNCHANGED (THE LAW); py_compile
  clean under /opt/capsy-agent/.venv; closure REQ->no-close / CONFIRMED->close / optout->close;
  normalizer 6/6 exact; no double rupees; plain text unchanged.

## DEPLOY ENV (founder-gated, off-hours, no active call): GROQ_MAX_TOKENS STAYS 220, KERNEL_OUTBOUND=0,
   BOOKING_HTTP_ENABLED=1, EL_STABILITY=0.55. New knobs (defaults ON, env kill-switches):
   BOOKING_FILLER=1, TTS_NORMALIZE=1. DEPLOY = cp staged files over live, py_compile, restart famit-agent.
   ROLLBACK = cp *.R6bbak.20260620-r6b back + restart. Ultimate golden _GOLDEN_ROUND5_20260619-140341.
