# 🧠 VOICE BRAIN — the CORE HEART megabuild (state / compaction-proof)

**Founder mandate (2026-06-14):** make the voice pipeline a REAL-HUMAN adaptive telecaller
intelligence. This is the core heart of the product. Day-and-night autonomous build; ultracode
pro-max; do NOT lose this across compaction. Read this + `MASTER_PLAN.md` + `design/VOICE-BRAIN-MASTER-PLAN.md`
(written by the megaplan) after any compaction.

## The 5 intertwined needs (founder's words, decoded)
- **A — DYNAMIC VENDOR SCRIPT.** A vendor supplies a free-form script per campaign (how to greet,
  ask, behave, tone, language); the agent AUTO-ADAPTS its persona/behaviour to it — not today's
  static pre-defined prompt. Needs more Run/campaign UI to author + test it.
- **B — FULL-CONTEXT CAMPAIGN STORE.** Today campaign details are extracted into a fixed ~3-5-field
  JSON that COMPRESSES and LOSES the vendor's full context. Replace with a LOSSLESS full-context
  store in the most optimal form (system-prompt / RAG / Redis-cache / KV — to be decided),
  retrievable at <20-50ms with NO regression to the ~1.1s voice loop. The agent must have the
  ENTIRE campaign context, instantly, whenever needed.
- **C — REAL-HUMAN ADAPTIVE INTELLIGENCE.** Speak like a real 30-yr telecaller: natural Hinglish
  code-switching (today it over-speaks pure complex Hindi), human behaviour / objection handling /
  turn-taking; a retrieval layer of real-telecaller knowledge + behaviour.
- **D — MULTI-CHANNEL MEMORY.** Crazy memory across multi-call + multi-WhatsApp conversations per
  lead — memory types (profile/episodic/semantic), where+how to store, fast retrieval of the entire
  prior-conversation context.
- **E — BLIND-SPOT SWEEP.** Founder + I are blind-spotting. Find EVERYTHING the production-grade
  real-human-telecaller ecosystem is missing across every domain/scope, and add it.

## Approach (earner-safe, founder-rule-compliant)
- **Wave 0 = `voice-brain-megaplan` (read-only):** explore codebase ground-truth → deep web research
  → design per-subsystem → adversarial red-team → phased build roadmap. Writes
  `design/VOICE-BRAIN-MASTER-PLAN.md`. SAFE to run parallel with box-mutating builds.
- **Then build waves:** earner-gated, ONE box-mutating wave at a time, inbound-first
  (`aim_voice_agent.py`/`caller.py`), NEVER `agent.py` (earner) without sign-off + a real ring-test
  (DID currently carrier-resting). Each wave: flag + acceptance gate + rollback.

## Megaplan DONE → master doc + build waves
- `voice-brain-megaplan` (wf_8988e0cb-2cf) COMPLETE → `design/VOICE-BRAIN-MASTER-PLAN.md` (45 agents). Keystone:
  `build_system_prompt(fields)` is a pure fn both agents render through → the brain = enrich fields + fenced
  blocks + RLS tables, NOT a rewrite. Red-team killer catches: (1) agent.py md5 is a FALSE earner-safety
  signal (earner re-renders via SHARED prompt.py → gate on a prompt.py golden byte-diff); (2) an ACTIVE
  cross-tenant lead-memory leak in prod (one tenant reads another's {phone}.json).

## Build sequence (one box-mutating wave at a time; all Opus)
- **W1 ✅ DONE + DEPLOYED + VERIFIED (2026-06-14)** — founder asks A+B: dynamic vendor-script→persona +
  lossless full-context store + Script Studio UI. SHIPPED to box `168.144.153.145` (caller.py + prompt.py v2 +
  aim_voice_agent.py, restart famit-caller + aim-voice-agent only) + Script Studio UI to FORTRESS
  (BUILD_ID `Ykm_1fVt267VDkPib8uVg`). Flag `VENDOR_SCRIPT_INJECT=1` set via systemd drop-in on
  **aim-voice-agent ONLY** (earner env clean). 5/5 verify PASS + full earner gate PASS (golden 5/5
  byte-identical flag off+on, agent.py 9150fabe unchanged, famit-agent PID 1477083 never restarted,
  /health 200, 0 5xx, NO ring). State `design/W1-DEPLOY-STATE.md`; founder recipe `FOUNDER-SCRIPT-STUDIO.md`.
  RESIDUAL: only a real inbound call proves the live mic/voice; outbound earner stays flag-OFF pending sign-off+ring.
- **P0-LEAK (QUEUED, script `.wf/voice-p0-leak.js`)** — close the cross-tenant memory leak on inbound + WA
  only. 🟥 FOUNDER DECISION (2026-06-14): "close safely now, finish on next test" = NO earner restart; the
  outbound earner closes fully on its NEXT deploy+ring (a later founder-signed wave). LAUNCH AFTER W1 (shared
  caller.py — must not collide).
- Then: W2 context-cache, the memory system (C/D), the blind-spot modalities (E) — see the master plan roadmap.
