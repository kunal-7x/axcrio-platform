# W6 — Cross-Vertical AI Telecaller Research/Synthesize (wave run log)

Compaction-proof per-phase log. Each phase appends as it finishes.

## Phase: SYNTHESIZE

**Date:** 2026-06-18 · **Mode:** DOC-ONLY (no code, no droplet_work/agent.py, no box mutation).

**Inputs consumed:**
- `request1.md` + `request2.md` (founder vision) — extracted the hard laws: never self-label as AI; never hardcode words (behavior not scripts); vendor-script overrides default; preserve FULL campaign context (no lossy JSON); dynamic objection handling over full brief/RAG (no 2–3 canned pairs); casual Hinglish never literary Hindi (banned "mahatvapurn"); complete every sentence (no "batana chahti…" truncation); cross-vertical mandate (sales+support+after-sales+booking+reminder+feedback+complaint+renewal+inbound); lead intelligence + conversation continuity + sensible retry cadence; behaviorally-correct one-line human handoff.
- `VOICE_ARCHITECTURE_RESEARCH.md` — architecture grounding (per-stage state layer on native LiveKit not Pipecat; semantic turn-detector; pre-loaded/cached campaign context; RAG as fallback not hot-path).
- RESEARCH input (opening/rapport/identity-confirm/reason/permission deep techniques + EN/Hinglish example lines).
- EXISTING input (inventory of prompt.py shared rules + 10-step flow + negotiation ladder + objection bank + escalation + cross-vertical gaps).
- On-disk per-topic brain packs already present in `design/` (identity-confirm, discovery-qualification, objection-price, objection-* trust/notinterested, closing-booking, push-without-pushy, callback-cadence, ethical-urgency, support-mode, aftersales-nps, reminder-renewal-payment, inbound-receptionist) — unified/indexed rather than duplicated.

**Output:** `C:\Users\kunal\Desktop\caps\design\W6-TELECALLER-PLAYBOOK.md`

**Structure delivered (matches the ask a–e):**
- §0 — 6 non-negotiable laws (gate everything).
- §A — universal behavior principles (tone/warmth, brevity/altitude, listen>talk, language mirroring, prosody-not-typos, guardrails, memory/continuity).
- §B — DEFAULT outbound-sales framework as DYNAMIC structure (greet→confirm→intro→reason→permission→qualify→pitch→objections→close/book→callback) with intent/dynamic-fills/exit table + branch behaviors + tested-opener notes; vendor-script-overridable.
- §C — per-USE-CASE brain-pack draft for ALL 9 modes (sales, support, after-sales, booking, reminder, feedback, complaint, renewal, inbound) — each with goal, caller role, opening style, data to collect, push/stop/handoff, success criteria, memory fields, EN+Hinglish example lines; plus C-Handoff cross-mode law (the one-line transfer fix).
- §D — objection handling as PRINCIPLES (acknowledge→isolate→reframe-from-full-context→honest→re-close) + business-context hooks pointing to existing deep packs; NO canned reply pairs.
- §E — casual-Hindi guidance: BANNED literary/Sanskritised words (mahatvapurn, atyant, etc.) + PREFERRED casual Hinglish phrasing + rendering rules.
- §F — handoff to W2: how this becomes brain-pack content (laws+universals = always-on layer; §B = default flow; each §C = per-mode pack; §D = stance+hooks; §E = language layer), earner-safe/additive/regression-gated, no agent.py mutation.

**Key synthesis decisions:**
- Made the doc a UNIFYING INDEX over the already-rich `design/` per-topic packs (don't duplicate; W2 expands those as source-of-record).
- Everything framed as behavior + runtime dynamic fills; example lines explicitly labeled ILLUSTRATIVE-only to honor the "never hardcode" law.
- Cross-vertical gap from EXISTING inventory (prompt.py was 100% real-estate-hardcoded) is filled by the 9 §C mode blocks + the C-Handoff law.

**Status:** SYNTHESIZE COMPLETE. Next (future wave): W2 implements these as brain packs; architecture per VOICE-BRAIN-MASTER-PLAN.
