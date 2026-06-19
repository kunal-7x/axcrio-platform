> **Synthesized by the 18-agent ROUND-5 planning workflow on 2026-06-19.**
> Source: 6 Explore agents · 4 Research agents · 4 Architect agents · 3 Red-Team agents · 1 Synthesis agent.
> This is GROUND TRUTH / THE LAW for all execution workflows. Do not edit without re-running the planning workflow.

---

# ROUND-5 PRODUCTION SHIP — ONE EXECUTABLE PLAN (synthesized, edged, earner-safe)

## GROUND TRUTH (resolved — trust the box, supersedes stale notes)

**The live earner is running the BROKEN kernel brain RIGHT NOW.** All four architectures + all four red-teams independently SSH-verified this and it overrides `EARNER-LIVE-STATE.md` lines 6-22:
- Live drop-in `kernel-outbound.conf`: `KERNEL_OUTBOUND=1`, `W5_SPEECH=0`, `OPENER_IN_CTX=1`, `OPENER_ALREADY_SAID=1`, `OPENER_DELAY_S=0.8`. Live PID env confirms `KERNEL_OUTBOUND=1`.
- Live `agent.py` md5 = **`48bc2b5a`** (== repo `droplet_work/agent.py`, byte-identical → repo line numbers are trustworthy). NOT `5c055a31`.
- `.env`: `EL_STABILITY=0.55`, `ELEVENLABS_VOICE_ID=QTKSa2Iyv0yoxvXY2V8a`, `LLM_CLOSE=1`, `LANG_MIRROR_V2=1`. **`.env` does NOT set `EL_SPEED`/`EL_SIMILARITY`/`GROQ_MAX_TOKENS`/`PREEMPTIVE_GEN`** → those run on CODE DEFAULTS (the EL_STABILITY default `0.65` is the broken value — the golden `0.55` is set explicitly in `.env`, so any `.env` drift silently breaks the voice; md5 of agent.py alone does NOT catch it).
- `EARNER-LIVE-STATE.md` line 43 (A4 flip → `KERNEL_OUTBOUND=1`) + line 105 (md5 `48bc2b5a`) are the truth; lines 6-22 predate them.

**Root cause of "RAG broke the brain" (code-proven, deeper than the label — verified this session):**
1. **Prefix-swap is the primary break.** `agent.py:761-766`: when kernel ON, `instructions = _vk.assemble_outbound_instructions(...)` renders the layered L0-L3 packet and **discards the entire `build_system_prompt(fields)` BRAIN-V2 body** (the brain the founder confirmed perfect). `base_instructions` (`agent.py:736`) is only the unused fallback lambda on the ON path.
2. **`safety_rules=""` on the live build** — `outbound.py:234` passes empty; `packet.py` only emits the slot if non-empty → SHARED_RULES (the "ONE reply THEN STOP / never exit while buying" engagement discipline) is **GONE, not lean.** This is the deepest cause of premature closure.
3. **Dual unguarded closing directive** — `delivery.py:105 closing_directive()` bakes a ready-to-speak farewell example with NO "only when outcome clear" gate; `agent.py` `_FAREWELL_MARKERS` then matches "दिन अच्छा" and converts the baited line into a real hangup.
4. **Card-script leak (independent door)** — `packet.py:350-353` renders campaign `negotiation_ladder`/`closing_lines` verbatim (`NEGOTIATION:`, `CLOSE:`) when present in the on-box campaign JSON → LLM parrots scripted closings. This is "scripts in RAG" via the campaign card.
5. **The literal 188-chunk RAG is mostly INERT** on the live path: `on_turn` passes no `stage` → defaults `Stage.GREET` → `is_retrieval_stage(GREET)=False` → empty in <1ms; hot-cache never warmed. So "disable RAG only" would NOT restore the brain. **BUT** the RAG wire at `outbound.py:273 build_rag_runtime(corpus=KbCorpusBackend())` is **unconditional (no env gate)** — verified this session — so it must still be gated for P1's facts-only re-architecture.

**Net:** the brain is restored by turning the kernel prefix OFF (P0). The target = rebuild a lean ≤1-2k prompt that KEEPS the proven brain body, RAG-as-facts-only behind a gate, dual-closing fixed, async strategy token, behavioral memory — all on the kernel path, each gated + founder-tested.

**Latency reality (measured live, sets the guardrail):** the turn floor is `eou_delay 0.82-1.55s + llm_ttft 0.22-2.05s + tts_ttfb ~0.18s` = **1.2-3.7s perceived**, none of which this plan touches. "≤700ms/turn" is unreachable with hosted Groq+eou regardless of brain design. The correct guardrail = **"adds ≤50ms p99 to an already-1.2-3.7s turn"**, and prompt SIZE (TTFT) is the only lever we own. `on_turn` is a real `await` capped at 30ms (`asyncio.wait_for`) — keep it there.

---

## THE LAW (every phase obeys; never propose touching these)
Voice/TTS constructors (`agent.py:885-957`), `.env` prosody (`EL_STABILITY=0.55`, voice_id, speed/similarity), `language` logic, `safe_tts_language_code()` clamp (sending `gu`/`pa` kills the TTS socket → silent call). **Proof contract for EVERY brain change:** (a) `agent.py:885-957` textually unchanged AND (b) resolved `.env` values feeding them unchanged — assert BOTH after every deploy (`grep -E 'EL_STABILITY|EL_SPEED|EL_SIMILARITY|ELEVENLABS_VOICE_ID' .env` == golden + md5 of the constructor region). Never `npm run build` on the panel box (OOM). One box-mutating step → founder real-call test → keep or one-command rollback. Golden always armed: `agent.py.PERFECTgolden.20260618-210445` + the A4bak chain.

**caller.py has ONE OWNER at a time** (P4 is sequenced, never parallel with another caller.py editor). `famit-agent` is NEVER restarted by panel/backend work — only by an explicit, gated, off-hours earner deploy.

---

# PHASE 0 — IMMEDIATE REVERT: restore the working brain (BLOCKING, one box step)

**Goal:** stop mid-call premature closure/hangups NOW by routing back through `build_system_prompt`. This is the proven-safe revert (verified: `agent.py:766` returns `base_instructions` byte-identical to the perfect-voice brain when `_ik is None`).

- **P0.1 — CHANGE:** in the live drop-in `kernel-outbound.conf`, flip **`KERNEL_OUTBOUND=1` → `0`**. KEEP all other lines. Surface: **earner brain** (box drop-in only, NOT a source edit, NOT `.env`).
  - Mechanism: `KERNEL_OUTBOUND=0` → `agent.py:601 kern=False` → `_ik=None` → `agent.py:766 instructions = base_instructions` = full `build_system_prompt` brain (engagement-gated, the 2:21PM-perfect body) + the A1/A2/A3a/VP3/VSE prompt fixes that live in `prompt.py`/`delivery.py` and are ALSO on the OFF path.
  - **Earner-safety gate:** off-hours, JOBS queue empty (an agent.py-adjacent restart drops active calls). This is a drop-in + `systemctl restart famit-agent`.
  - **Byte-identical proof:** TTS region `agent.py:885-957` untouched (no source edit at all); `grep EL_STABILITY .env == 0.55`; worker "capsy" re-registers, NRestarts=0, 0 errors in journal.
  - **Rollback:** flip the drop-in back to `KERNEL_OUTBOUND=1` + restart (returns to current state). Ultimate: the PERFECTgolden cp one-liner.
  - **FOUNDER-TEST GATE #1 (blocking):** one real outbound call — confirm NO mid-call goodbye, no repeat-intro, engaged user not dropped, voice still perfect. Only on PASS proceed to P1.

**Note on staging:** all of P1-P3 below is built on the kernel path but stays `KERNEL_OUTBOUND=0` until the lean rebuild is founder-validated, so the earner stays on the restored brain the entire time the new brain is built and offline-gated.

---

# PHASE 1 — LEAN ≤1-2k PROMPT + RAG-AS-FACTS-ONLY + closure/repeat/framing/two-step-greeting (brain-only, gated, founder-tested)

All P1 edits are to `voice_kernel/*` + `prompt.py` (NOT the TTS region). They take effect only when `KERNEL_OUTBOUND=1`; until the final P1 flip the earner runs the P0 brain. Each edge is independently env-toggleable.

- **P1.1 — RESTORE the engagement discipline (THE premature-closure root): populate `safety_rules`.**
  - CHANGE: `voice_kernel/integrations/outbound.py:234` — replace `safety_rules=""` with the SHARED_RULES engagement block (`prompt.py:485-495` content: "ONE assistant turn = ONE reply THEN STOP", "say ONE clean closing line and stop", "NEVER exit while the user is buying/asking", "outcome साफ़ हो तो ही close"). Surface: **earner brain.**
  - Guardrail: this slot already renders via `packet.py:299-300` only when non-empty — additive, no other path changes.
- **P1.2 — Kill the baited farewell (dual-closing fix).**
  - CHANGE: `voice_kernel/brain_packs/delivery.py:105 closing_directive()` — remove the ready-to-speak example string; make it a PRINCIPLE only ("close with ONE natural line ONLY when the outcome is clearly resolved; never mid-engagement"). Surface: **earner brain.** This removes the string that `agent.py` `_FAREWELL_MARKERS` was matching into a real hangup.
- **P1.3 — Stop the card-script leak.**
  - CHANGE: `voice_kernel/packet.py:350-353` — do NOT render `negotiation_ladder`/`closing_lines` as `NEGOTIATION:`/`CLOSE:` lines (these are behavioral SCRIPTS the LLM parrots → premature closure/repeat). Either drop these card fields from the prefix or gate them behind a `CARD_SCRIPTS=0` default-off flag. Surface: **earner brain.** (Campaign DESCRIPTIONS/facts stay; only the closing/objection/negotiation SCRIPT fields are stripped — this IS "RAG-as-facts-not-scripts" at the card door.)
- **P1.4 — Shrink the prefix to ≤1-2k tokens (KEEP the brain).**
  - CHANGE: the L0-L3 assembly (`packet.py render_stable_prefix` + `outbound.py assemble_outbound_instructions`) must carry the `build_system_prompt(fields)` engagement body (or its distilled equivalent) as the spine, not replace it with a thin layered packet. Target ≤1-2k tokens (VERIFY actual on-box token count first via the eval harness, not founder estimate). Surface: **earner brain.**
  - Correctness guardrail (red-team): do NOT lose the recency FINAL-OVERRIDE mirror rule, the no-recording rule, name-confirm, or the stay-engaged gate while shrinking — these are the exact guards the kernel dropped originally.
- **P1.5 — RAG-as-FACTS-ONLY behind a gate.**
  - CHANGE: `voice_kernel/integrations/outbound.py:273` — wrap the unconditional `build_rag_runtime(corpus=KbCorpusBackend())` in `if RAG_INJECT_ENABLED (default 0)`. Add a doc_type filter in `kb/core.py`/`rag/runtime.py` so retrieval returns ONLY FACTS (campaign descriptions, lead/chat/WhatsApp/call history, conversation context) and EXCLUDES behavioral chunks (objection/closing/greeting scripts). Surface: **earner brain.**
  - Guardrail: keep the hot read cache-only with the 30ms hard-deadline + degrade-to-None (a cache miss is never a stall, never re-greets). Pass a real `stage` from `on_turn` so retrieval can actually fire at PITCH/OBJ — but only for FACTS, default OFF until P1 validated.
- **P1.6 — Two-step greeting + outbound framing + repeat-intro (brain-only).**
  - Greeting: enforce "good morning/afternoon/evening + hello sir" → name-confirm ("क्या मेरी बात {name} से हो रही है?") → THEN pitch (two-step). Already largely live in `delivery.py`/`prompt.py` (VP3/VSE) on the OFF path; re-assert inside the lean kernel prefix so it survives `KERNEL_OUTBOUND=1`. Surface: **earner brain.**
  - Outbound framing: ban "आपने कॉल किया था" (inbound framing); mandate "we're calling about your interest in X".
  - Repeat-intro: keep `OPENER_ALREADY_SAID=1`/`OPENER_IN_CTX=1` (the spoken opener IS in LLM ctx) so the LLM never re-greets.
- **P1.7 — Drop-in alignment:** keep `W5_SPEECH=0` (prosody/filler planner FORCE-OFF — it broke the voice once). Prove `plan_speech()` returns None when kernel ON.

**Earner-safety gate (whole P1):** build + edit `voice_kernel/*`/`prompt.py` while `KERNEL_OUTBOUND=0` (earner on the P0 brain). Run BOTH offline gates GREEN before any flip: `voice_ops/eval/regression_gates.py run_all_gates()` (R1-R15, drives the real kernel prompt with `KERNEL_OUTBOUND` flipped in-proc) + `droplet_work/eval/gate.py evaluate()` (paired baseline-vs-candidate: latency p95 ceiling, guard==0, language/monologue no-regress).

**Byte-identical proof:** TTS region `agent.py:885-957` untouched (P1 edits none of agent.py's TTS); `.env` untouched; md5 the constructor region + assert EL_STABILITY=0.55.

**Rollback:** `KERNEL_OUTBOUND=0` drop-in flip (instant return to P0 brain); per-edge env toggles (`RAG_INJECT_ENABLED`, `CARD_SCRIPTS`) for granular off; box backups `voice_kernel/*.R5P1bak.*`.

**FOUNDER-TEST GATE #2 (blocking):** flip `KERNEL_OUTBOUND=1` (now the LEAN brain) → one real call → confirm: no premature closure, no repeat-intro, outbound framing, two-step greeting, engaged user driven to site-visit, voice perfect. Only on PASS does the lean kernel become the new baseline and P2-P3 build on it.

**Parallelism:** P1 is SEQUENCED (single earner brain surface, one founder gate). P4/P5 below are parallel-safe with P1 (different surfaces) EXCEPT P4 must respect caller.py single-owner.

---

# PHASE 2 — ASYNC INTELLIGENCE LAYER (strategy token; 0ms added to the hot path)

Two-turn pipeline: turn N replies immediately (lean sync core); an off-loop asyncio task analyzes turn N and writes a tiny strategy token to Redis; turn N+1's `on_turn` reads it in ~0ms and folds it into the WORDS the LLM is told to use. Analysis is always one turn behind the mouth — exactly a human telecaller.

- **P2.1 — Hook (NO new hot-loop call site):** extend the existing `agent.py:1174 _kt = await _vk.on_turn(...)`. Inside `voice_kernel/integrations/outbound.py on_turn`: (a) `asyncio.create_task(...)` to fire the analyzer fire-and-forget (NO await/`.result()` on the hot path — red-team correction: the live `on_turn` is itself an awaited 30ms-bounded call, so the analyzer must NOT inherit that await); (b) one sync `RedisHotCache.get` of the token turn N wrote (same class as the existing cache read, `socket_timeout` bounded, degrade-to-None). Surface: **earner brain.**
  - **AGENT DELTA = +1 line** at `agent.py:1178`: after the existing `turn_ctx.add_message(role="user", content=_rag)`, append `_kt.get("strategy_suffix")` the same way. Verified this session: `:1176-1180` is exactly this shape.
- **P2.2 — Strategy token schema:** tiny JSON (<512B, clamped), key `vk:strat:{tenant}:{call}`. WORD/STRATEGY hints ONLY (intent, temperature, objection-type, buying-signal, suggested reframe). **NO TTS/prosody field, NO `role="system"` command, NO literal line to speak** (a literal line = the reverted bug). Injected as a SOFT `role="user"` suffix, like the language hint.
- **P2.3 — Analyzer:** off-loop; may use a HOSTED reasoning model (never the sync loop, never self-hosted). Reads the running `agent.py:790 turns[]` window. Hard-bounded; on any failure → no token → turn proceeds exactly as P1.

**Guardrails (red-team):** (1) the sync RedisHotCache GET is a ≤50ms socket call inside the event loop — keep the bounded timeout + degrade-to-None so a miss/slow-Redis is never a stall and never re-greets. (2) Redis on the box has ~287MB free + `noeviction` — set an explicit `maxmemory` + `allkeys-lru` (or TTL all `vk:strat:*` keys) so the token store can never OOM the box. (3) A token miss (analyzer not done) → `strategy_suffix=None` → byte-identical to a P1 turn.

**Earner-safety / proof / rollback:** gate behind `ASYNC_STRATEGY=0` default-off; when OFF, `on_turn` returns no `strategy_suffix` → byte-identical to P1 (and identity when kernel OFF). Both eval gates GREEN (assert p99 turn delta ≤50ms). **FOUNDER-TEST GATE #3:** flip `ASYNC_STRATEGY=1` → real call → adaptive without latency regression.

**Parallelism:** SEQUENCED after P1 (same earner brain seam, builds on the lean core).

---

# PHASE 3 — BEHAVIORAL MEMORY + CLOSED-LOOP SELF-LEARNING (gated)

**Root finding (verified):** W7 WRITE is live (`agent.py:868 persist_post_call → extract_and_persist` fills PG every call) but the dial-time READ still uses the LEGACY file recap (`agent.py:710 mem.build_recap(mem.load_memory(phone))`), NOT `LeadMemoryService.load`. The WARM L4 loader (`kernel.py enrich_prefix`) + `continuity_opener_hint` exist with NO live caller. **The behavioral-memory feature IS the missing READ leg** — and the legacy file recap mis-firing is BRAIN RECON #1 ("पिछली बात हुई थी on FRESH leads").

- **P3.1 — Per-lead behavioral profile (the moat read path).** Add a SECOND narrow frozen `LeadProfile` (in `packet.py` near `:222`; do NOT widen the deliberately-narrow `LeadMemory` L4): `verbosity`, `language_pref`, `objection_pattern` (≤4 tags), `buying_pattern`, `best_contact_window`, `call_count`, `avg_conversion_prob`. Computed by RULES from `lead_memory_summary` + head row (like the deterministic `conversion_probability()` FSM) — **no new LLM on any hot path.** Surface: **earner brain.**
- **P3.2 — Storage:** extend the EXISTING `lead_memory` head row (keeps the WARM load a single PK read = the latency contract) via additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (new `voice_kernel/memory/ddl_lead_profile.sql`, idempotent, applied to box PG as a zero-code step BEFORE the read is wired — else finalize/load throws + silently drops the write).
- **P3.3 — Fix the broken read leg:** replace the legacy `agent.py:710` file recap with the WARM `LeadMemoryService.load` (5-min cache, 1 PK read, RLS) AND **gate recap on ACTUAL prior-call memory** (call_count>0) → kills the "पिछली बात" hallucination on fresh leads. Push the profile to Redis at call-start (0ms during turns). Surface: **earner brain** (the one P3 agent.py touch — outside the TTS region).
- **P3.4 — Closed-loop self-learning (OFFLINE/async + GATED):** a periodic background routine consumes the already-emitted outcome events (`events/taxonomy.py`: `LEAD_HOT/WARM/COLD/DEAD`, `SITE_VISIT_BOOKED`, `CALLBACK_SCHEDULED`, stream `vk:events:{tenant}`), clusters win/loss → synthesizes strategy hints **surfaced as eval-gated SUGGESTIONS in the panel, NEVER auto-mutating the live prompt** (earner-safety). A suggestion only reaches the brain after a founder approves it + it passes `run_all_gates()`.

**Guardrails:** profile computation is deterministic (drift-free, like `lifecycle.py`); the new column read is additive (a NULL profile → no behavior change). Self-learning writes nothing to the live path automatically.

**Earner-safety / proof / rollback:** gate behind `LEAD_PROFILE=0` default-off; agent.py P3.3 touch leaves TTS region untouched (assert md5 + EL_STABILITY). DDL is idempotent. Rollback = flag off + restore `agent.py.R5P3bak.*`. **FOUNDER-TEST GATE #4:** returning-lead call primed correctly + a FRESH lead gets NO "पिछली बात".

**Parallelism:** P3.2 DDL is parallel-safe (PG only). P3.1/P3.3/P3.4 SEQUENCED after P2 (earner brain). The self-learning routine (P3.4) is a separate worker — parallel-safe once events flow.

---

# PHASE 4 — BACKEND WIRING (caller.py — SINGLE OWNER, sequenced; earner never restarted)

All P4 is `famit-caller`/`caller.py`/endpoints — NEVER `famit-agent`. caller.py is ONE owner at a time: P4 fully completes + ships before any other caller.py editor runs. (Note: STREAM C already flipped EVENTBUS/RECORDING_FINALIZE/REPORTING/LEAD_LIFECYCLE live via drop-in; P2-data read-model split-brain already fixed via `_w14_hydrate`. P4 closes the REMAINING wiring gaps below.)

| Edge | Root cause (verified) | CHANGE (file:line) | Surface |
|---|---|---|---|
| P4.1 callbacks fire | `RETRY_SCHEDULER_ENABLED=0` (built, correctly not flipped) → due-fire dial loop never runs; the enqueue path (`caller.py:3059-3066`) + T0-retry-fix + TRAI DND clamp are present | flip `RETRY_SCHEDULER_ENABLED=1` after one signed live test; T0 verify (no source change) | caller.py drop-in |
| P4.2 warm-lead auto-schedule | finalize only branches at score≥70 (HOT handoff); no warm band | new branch ~`caller.py:3091` for score 40-69 → "Warm-Lead Schedule" | caller.py |
| P4.3 CRM "unknown number" | `crm.upsert_contact()` (`crm/core.py:247`) has ZERO callers; finalize writes only leads.json; reporting serves `name or "(unknown)"` | wire `upsert_contact` into `_finalize_call` | caller.py |
| P4.4 AI-Mgr add-number | `register_number` route exists; gap = response-shape/list-refresh | `endpoints.py:136` + return shape | endpoints |
| P4.5 PIN-reset 422 | panel calls `POST /ai-manager/pin/set` but NO such route exists → FastAPI 422 | NEW `POST /ai-manager/pin/set` | endpoints |
| P4.6 "Try it" hardcoded + jargon leak | deterministic closed-schema driver; leaks `analytics.read`/tool labels | NEW free-form `/ask` route + natural-language driver (LLM-driven, reads DB, no jargon) | endpoints |
| P4.7 booking real-time | router mounted + `/booking/book`+`calendar_sync` un-stubbed; the safe half = finalize-side booking persist | wire finalize booking + GCal sync (the in-call voice-TOOL half is earner-gated, DEFERRED to a separate earner wave) | caller.py |
| P4.8 KB ingest real-time | already synchronous off-loop upsert (`caller.py:/kb`) | verify-only | — |

**Earner-safety gate:** `caller.py af64ab4d` unchanged where possible (prefer drop-in flags); every source edit additive + flag-gated; `famit-caller` restart only; box backup `caller.py.R5P4bak.*`; each flag flip gated by a real-call WIRE-OPS smoke. **FOUNDER actions flagged:** GCal OAuth creds; AIM OTP backend; flip `RETRY_SCHEDULER` after one signed live test.

**Parallelism:** P4 runs in PARALLEL with P1-P3 (different surface: famit-caller, never famit-agent) — but is INTERNALLY sequenced (one caller.py owner). P5 frontend can start against P4's new routes once their contracts are fixed.

---

# PHASE 5 — FRONTEND OVERHAUL (panel; reuse Core_2; ship pre-built `.next`)

Surface: `famit-panel` only. NEVER `npm run build` on the panel box (OOM — Next 15 mmaps ~50GB virtual; even 4GB swap OOM-kills). WORKING deploy = ship the pre-built LOCAL `.next` (runs on Linux because `next.config.ts images:{unoptimized:true}` → no `sharp` at runtime → pure JS/JSON, platform-independent — red-team's "Windows-.next-won't-run" is mitigated). Reuse Core_2 templates; NEVER build UI from scratch; NEVER delete a page's code (IA/UI only; restore any removed page).

Scope (much already deployed per EARNER-LIVE-STATE commits `9f6a379`/`960035b` — P5 closes remainders + wires P4 data):
- **AI-Manager:** add-number works (P4.4); PIN-reset works (P4.5); "Try it" → LLM-driven free-form (P4.6, no jargon leak); home cards match dashboard style; calls list lazy-load; collapse 7→3 tabs.
- **Speed:** pagination/lazy-load EVERY load-all list (call-logs [worst], CRM, ai-mgr calls, super-admin spending, image library). Column-header sort across ALL records everywhere there's a table.
- **Dashboard:** wire lead-temperature + hot-leads (P4 data); fill space beside Recent Calls (2 analytics cards + AI-recommendation card from P3.4 suggestions); DATE-PICKER (single date → that day's real-time data, forward GlobalFilters range to the P2-fixed backend); varied premium charts.
- **Report:** temperature fix; real top-to-bottom conversion FUNNEL diagram (uploaded→…→converted, hover=numbers), restore the reverted real funnel; varied analytics.
- **CRM:** name-link persist (P4.3); temperature column + All/Hot/Warm/Cold/Dead filters; dustbin delete.
- **Callbacks/Warm-lead:** in-call "call me at 5pm" appears in Callbacks (P4.1); "Warm-Lead Schedule" section (P4.2); booking real-time (P4.7).
- **Polish:** brand-kit spacing/save/real-time; WhatsApp banner/video preview; payment UI consistency + per-call cost; real vendor logos (ElevenLabs/Sarvam/Vobiz/Groq); library image/video filter; KB real-time ingest verify; transparent-tab consistency.

**Earner-safety / proof / rollback:** panel-only, earner untouched; build LOCAL → ship `.next` + source → chown deployuser → restart famit-panel; backup `.next.R5P5bak.*`; public 200 + BUILD_ID check. Rollback = restore prior `.next` backup.

**Parallelism:** PARALLEL with P1-P4 (panel surface) — but data-dependent items (temperature, funnel, callbacks, warm-lead, CRM name) need their P4 routes live first. P5 is the one place a frontend specialist owns nav/IA + `app/*` + `lib/{events,report,query-client}.ts`; backend owns flags/DDL/routes.

---

# PHASE 6 — SECURE GITHUB PUSH + DEPLOY (final, after all gates green)

- **P6.1 — Secure push:** `kunal-7x/axcrio-platform`. gitleaks/secret-scan == 0; `.gitignore` hardened (NO `.env`/keys/`.env.local`); selective `git add` (NO `-A`). Use the box `gh` OAuth (the `.env.local` PAT lacked `Contents:write` → 403 last time) OR have the founder grant the PAT `axcrio-platform`+Contents:write. Commit messages end with the Co-Authored-By trailer.
- **P6.2 — Deploy:** earner = the gated drop-in/source flips already founder-tested per phase (no big-bang); panel = ship pre-built `.next`. Verify end-to-end: real call lights dashboard+CRM in seconds, recording on the lead profile, correct timestamps, brain behavior correct, voice perfect.
- **Earner-safety:** `droplet_work`/box-secrets never committed; golden backups remain on box; final earner state = the founder-validated lean kernel (P1) + gated P2/P3 layers.

**FOUNDER-TEST GATE #5 (final, blocking):** one end-to-end real call + dashboard/CRM/recording check before declaring shipped. Only the founder's live call proves it.

---

## SEQUENCING / PARALLELISM SUMMARY
- **P0** blocks everything (restore brain first).
- **P1 → P2 → P3** are SEQUENCED on the single earner-brain surface, each behind its own founder gate (#2/#3/#4).
- **P4 (caller.py, single owner)** and **P5 (panel)** run in PARALLEL with the P1-P3 stream (different surfaces; famit-agent never restarted by them); P5 data-items depend on their P4 routes.
- **P3.2 DDL** is parallel-safe (PG). **P3.4 self-learning worker** is a separate parallel worker.
- **P6** is last, after all five founder gates pass.
- **Founder-test gates (all blocking):** #1 P0 revert · #2 P1 lean kernel flip · #3 P2 async strategy · #4 P3 behavioral memory · #5 P6 end-to-end ship.

## Critical Files for Implementation
- `C:/Users/kunal/Desktop/caps/droplet_work/agent.py` (kernel seam :761-766, on_turn :1174-1178, TTS region :885-957 LOCKED, legacy recap :710)
- `C:/Users/kunal/Desktop/caps/voice_kernel/integrations/outbound.py` (safety_rules="" :234, unconditional RAG wire :273, on_turn analyzer hook)
- `C:/Users/kunal/Desktop/caps/voice_kernel/packet.py` (lean prefix render, card-script leak :350-353, LeadProfile near :222)
- `C:/Users/kunal/Desktop/caps/voice_kernel/brain_packs/delivery.py` (closing_directive :105, greeting/closing principles)
- `C:/Users/kunal/Desktop/caps/droplet_work/caller.py` (P4 wiring: finalize CRM upsert, warm-lead branch ~:3091, callback fire, booking) + `endpoints.py` (PIN/ask/register routes)
