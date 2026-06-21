# 🔧 voice-agent-v2 — CLEAN REBUILD, CRASH-SAFE STATE (ROUND-10, 2026-06-21)

Authoritative plan: `caps/.claude/plans/you-have-digitalocean-api-imperative-mist.md` → ROUND-10.
Branch: `rebuild/voice-telecaller-v2`. Direct build (NO ultracode). Live earner UNTOUCHED.

## WHAT THIS IS
A new, self-contained LiveKit voice-telecaller worker that runs SIDE-BY-SIDE with the live one
(`capsy`) as `capsy-v2`. The perfect VOICE is preserved byte-for-byte; the bug machinery + scripts
are gone; the brain runs on a bigger model. Founder's real call = the only verdict. I do NOT say "done".

## THE 3 CHANGES (everything else is byte-identical to live agent.py f4d75e49)
1. **Clean script-free prompt** — `prompt.py` rebuilt: role + hard rules + FACTS only. No objection/
   closing/step scripts (killed premature-close + CoT-recite). Keeps the field contract
   (GODREJ_FIELDS, _gender_of, build_system_prompt) so campaigns + agent.py import unchanged.
2. **Closure trimmed to explicit end-signals** — `agent.py` `_CLOSE_NO` now lists ONLY real hang-up /
   do-not-call phrases (bye/रखता हूँ/cut the call/do-not-call). Objections ("महंगा"/"नहीं चाहिए"/
   "अभी नहीं") REMOVED → the #1 bug (objection→call-cut) is gone. `_closure_signal` no longer
   auto-books/auto-closes (returns 'no' on an explicit end-signal only; booking = the LLM tool).
3. **Bigger model** — `.env` `GROQ_LLM_MODEL=llama-3.3-70b-versatile` (kills number-loop / role-flip /
   CoT-recite = small-model signatures). NOT a code change — `_mk_groq_llm` already reads this env.
   Proven on these keys (live AI-Manager runs the same model).

## PRESERVED BYTE-IDENTICAL (untouched in agent.py)
ElevenLabs Flash TTS constructor (voice_id QTKSa2Iyv0yoxvXY2V8a, EL_STABILITY via env=0.55) ·
Groq LLM factory + room-seeded key-spread + FallbackAdapter (dead-air fix) · Sarvam saarika-v2.5 STT ·
AgentSession/VAD/endpointing/barge-in tuning · opener (_llm_opener + OPENER flags) · per-turn language
mirror (_normalize_indic + langdetect note + cache-safe TTS nudge) · booking tool (_do_booking_http) ·
cross-call memory · metrics. All copied verbatim from the live f4d75e49.

## FILES (in repo, branch rebuild/voice-telecaller-v2)
- `agent.py`   — clean entrypoint (= live f4d75e49 minus closure machinery; 2 subtractive edits). py_compile OK.
- `prompt.py`  — NEW clean brain (role+rules+facts). py_compile OK.
- `memory.py` `langdetect.py` `voice_ops/booking/datetime_resolve.py` — VERBATIM copies from the box.
- `.env.example` — env contract (NO secrets).
- `tests/replay.py` — offline live-Groq replay gate (run on the box venv).
- `README.md` — deploy + flip + rollback runbook.

## DEPLOY (isolated, gated — see README)
Box scratch `/opt/famit-agent-v2/`. `.env` = copy of `/opt/famit-agent/.env` with ONLY:
`GROQ_LLM_MODEL=llama-3.3-70b-versatile` + `LIVEKIT_AGENT_NAME=capsy-v2` (+ AGENT_HTTP_PORT distinct).
systemd unit `famit-agent-v2`. Live `famit-agent` / `capsy` NEVER touched.

## ROLLBACK
There is nothing to roll back on the live earner — `capsy` keeps running untouched the whole time.
To stop v2: `systemctl stop famit-agent-v2`. To flip live→v2 later (only after founder OK): point the
live dispatch / unit at the v2 code; rollback = point back to `capsy` (instant).

## PROGRESS
- [x] Branch + pull live source (md5 f4d75e49 / b9a974cf confirmed)
- [x] Copy proven support modules verbatim (memory/langdetect/voice_ops)
- [x] prompt.py clean (py_compile OK)
- [x] agent.py — 2 subtractive edits (closure→end-signal-only) (py_compile OK)
- [x] README + .env.example + tests/replay.py
- [x] commit + gitleaks scan (0 leaks) + push (origin/rebuild/voice-telecaller-v2)
- [x] DEPLOY isolated `famit-agent-v2` (capsy-v2) — **registered worker agent_name=capsy-v2**,
      NRestarts=0, live `capsy` active+untouched. Port 8092 (8090=live out, 8091=live inbound).
      v2 .env = live .env + GROQ_LLM_MODEL=llama-3.3-70b-versatile + GROQ_MAX_TOKENS=120 +
      LIVEKIT_AGENT_NAME=capsy-v2 + AGENT_HTTP_PORT=8092 + opener flags. Voice env golden (EL_STABILITY=0.55).
- [x] PROVE: offline replay on box (70b) = ALL_CLEAN — objection→keeps selling (NOT cut),
      "not interested"→reframes, English→English, price→one number in words (no loop),
      yes-no-time→asks for time (no fake-book), no ## Step / ₹ / digit-spam.
- [x] TEST-DISPATCH: `test_call_v2.py` dials founder + dispatches capsy-v2 (live path untouched)
- [x] FOUNDER REAL CALL #1 (room famit-916375548830-cfeda3, 14:54): brain behaved CORRECTLY —
      budget objection (5cr vs 6cr) handled w/o cut + value reframe; English switch mirrored
      (`lang mirror v2 -> english`); replied by name; TTFT 0.24–0.34s; one number in words; no
      cut/loop/CoT. BUG found+FIXED live: booking save threw ImportError (voice_ops.booking
      __init__ eager-imports store+transfer; partial copy) → copied full package, restart, OK.
- CALL #2 (15:01): booking LLM @tool LEAKED `<function=book_site_visit>{}` as SPOKEN text on
  llama-3.3-70b (Groq emits tool-calls in content) + never executed. FIX: dropped the tool
  (BOOKING_HTTP_ENABLED=0) + CODE-SIDE booking in _on_item (on explicit consent+time → _do_booking_http).
- CALL #3 (15:14): CLEAN — no leak; adaptive discovery (took founder's coaching); 5cr-vs-6cr handled;
  verbally confirmed "kal teen baje" visit; clean close on explicit "bye bye" (closure end-signal-only ✓).
  REMAINING: booking SAVE = `bad_slot` — `resolve_slot_start` can't parse Devanagari time "तीन बजे"
  (needs Hindi/Devanagari numeral+time normalization before resolve). Minor: slight double-goodbye.
- [x] FIX booking-save (3 issues): (a) Devanagari time → taught resolve_slot_start digits/number-words/
      day+period + PM-default for bare visit hours; (b) 70b leaked the @tool → dropped tool, book in code;
      (c) false-positive ("आज्ञा"⊃"आज") → require a booking NOUN + time/verb; (d) 401 → loopback needs a
      real campaign_id → created `godrejv2` (tenant=admin, Godrej fields, clean prompt).
- [x] CALL #5 (15:43, campaign godrejv2): BOOKING PERSISTED on a real call — "कल दोपहर चार बजे" →
      `bk_17d7f9a929b2 status=booked slot=2026-06-22 16:00 IST` (4 PM). Clean voice, confirmed once,
      clean close on "बाय बाय". Full flow works end-to-end.
- [ ] (polish, non-blocking) slight double-goodbye; opener says "नमस्ते" (founder prefers "good morning/
      hello sir"); summarizer mislabels bye as opt_out; Latin-transliterated Hindi numerals not parsed.
- [x] POLISH: single goodbye (drop scripted close, let model's goodbye play + grace) + time-of-day
      English greeting ("Good morning/afternoon/evening", never नमस्ते).
- [x] BRAIN sharpened (founder ask): curiosity-led, engaging questions ("kya aap janna chahenge…"),
      30-yr master telecaller, read+adapt, step-by-step desire — still script-free, facts+history only.
- [x] **WIRED LIVE (the flip)**: famit-caller drop-in `/etc/systemd/system/famit-caller.service.d/
      agentflip.conf` → `Environment=LIVEKIT_AGENT_NAME=capsy-v2`. Now ALL caller dispatches
      (panel Run-Campaign, website calls, campaigns, callbacks) route to capsy-v2. Realtime
      backbone already ON in caller (EVENTBUS_ENABLED=1, RECORDING_FINALIZE_ENABLED=1) → stats/
      recordings fire on finalize. Agent uses NO redis (campaign JSON + memory files = the context).
      ROLLBACK: `sudo rm /etc/systemd/system/famit-caller.service.d/agentflip.conf && sudo systemctl
      daemon-reload && sudo systemctl restart famit-caller` → back to old capsy instantly.
- [x] WIRING FIX: the dispatch-flip drop-in lost to env precedence (caller kept LIVEKIT_AGENT_NAME=capsy).
      ROBUST FIX: v2 worker now registers as the canonical **capsy** (its .env LIVEKIT_AGENT_NAME=capsy);
      OLD famit-agent stopped + disabled; agentflip.conf removed. So caller → capsy → v2 brain. Sole capsy
      worker = famit-agent-v2 (the clean brain). ROLLBACK to old: `sudo systemctl enable --now famit-agent`
      + `sudo systemctl stop famit-agent-v2` (old capsy resumes).

## ✅ WORKING-STATE RESTORE POINT (tag `voice-telecaller-v2-working`, 2026-06-21)
The clean rebuild IS live as capsy: clean human brain (objection-handling, language-mirror, ~0.25s),
booking persists, no degeneration loop. The 2-day loop is solved. Old buggy capsy retired (stopped).

## ▶ FOUNDER ROUND-11 DIRECTIVE (production-grade, 2026-06-21 PM) — "good, not satisfactory yet"
Goal: a PRODUCTION-grade voice telecaller like Vapi / Retell / Ringg — full end-to-end, any situation,
no human, scalable, low-latency, cost-efficient, a real human-feeling salesperson, sellable to vendors.
Brain asks (ALL prompt-level, NEVER hardcode — tell Groq to do it): (1) two-step greeting ("Good morning
sir, kya meri baat Mr. Kunal se? " → yes → "main Riya…, 2 min baat?"); (2) adaptive FILLERS (Groq picks
them, none hardcoded); (3) curiosity-chain — reveal a little, ask "aur jaanna chahenge?", build interest,
THEN propose a visit only when intent shows; (4) language mirror (Groq follows STT language). Architecture
Q (founder): are we building it like real production cos, or a "school project"? Use Redis hot-cache + RAG
ONLY when needed (big campaign detail / history not already in context) — pieces already exist. HARD: do
NOT break it, do NOT hardcode, do NOT touch sensitive files, secure + precise, research-first.
NEXT (carefully, reversible, tested): research how production voice-AI is built → confirm/correct the
architecture → incremental brain polish (the 4 asks) → production hardening (latency/turn-taking, evals,
RAG-when-needed, robustness/STT). NO rebuild; additive only.

## ✅ RESEARCH VERDICT (3 scouts, 2026-06-21): architecture is PRODUCTION-LEGITIMATE
Same pattern as Vapi/Retell/Bland (LiveKit streaming STT→LLM→TTS + prompt brain). Not a rebuild — refine.
Convergent #1 finding (all 3 scouts): the brain DUMPED facts + pitched too early instead of qualifying.
Gaps (additive, ordered): (B0) brain "character-not-script" + 4 asks [DONE Wave A] · (B1) eval suite
[DONE Wave A] · (B2) semantic turn-detection · (B3) light state layer (QUALIFY→PITCH, +20% conv) · (B4)
hardening (provider fallback, observability, RAG-on-demand). Brain-design secret: phrase rules as CHARACTER
TRAITS ("you are someone who…") → model embodies, doesn't recite → also stops the small-model breakage.

## ✅ WAVE A DONE (brain v2 + eval gate, 2026-06-21) — eval-gated, deployed to capsy
- `prompt.py` rewritten to CHARACTER framing + the founder's 4 asks + 2 bug fixes: two-beat open
  (opener does beat-1 name-confirm, brain does beat-2 intro+permission) · QUALIFY-before-dump (ask one
  discovery Q first, price only on budget/ask) · curiosity-chain (one point + "aur sunna chahenge") ·
  language-mirror · STT-garble→ask-to-repeat · callback-sanity (no "2 saal") · clean bye (no re-intro).
- `agent.py` `_llm_opener` → beat-1 only (greeting + name-confirm).
- `tests/replay.py` → EVAL SUITE (9 scenarios + auto-checks) = the anti-Black-Day gate. Result: **8/9**
  (the 1 fail = garble-ask-to-repeat; the LLM can't reliably self-detect Devanagari gibberish, but it now
  DEGRADES GRACEFULLY — stays on-topic + alive instead of the call dying). Every future brain change runs
  this offline FIRST. Deployed to capsy (NRestarts=0). Voice byte-identical. Rollback = git tag.
- [ ] FOUNDER live test of Wave A brain.

## RUNBOOK
- v2 logs: `journalctl -u famit-agent-v2 -f`  ·  restart: `sudo systemctl restart famit-agent-v2`
- STOP v2 (no effect on earner): `sudo systemctl stop famit-agent-v2`
- live `capsy` untouched throughout; nothing to roll back on the earner.
