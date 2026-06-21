> 🧭 **READ `MASTER-INDEX.md` FIRST** (repo root) — the single read-first orchestration index (compaction protocol + running-now + done+live + the complete pending build queue + gated/founder actions + file map + laws). THEN read `MASTER_DNA_PLAN.md` for the full DNA. This file is the night-loop.

> 🧬 **READ-FIRST → `MASTER_DNA_PLAN.md`** for the FULL DNA (vision · every subsystem with why-it-was-born · ✅done · 🏗️pending runlist · ⛔gated · 📏laws · 📖read-order). This file is the night-loop; that file is the brain.

# 🌙 AUTONOMOUS NIGHT-BUILD — founder away, laptop ON (2026-06-14)

Founder left the laptop running: "build everything we discussed + the pending list, most important
first, then move and move and move — full autonomous; when I'm back I need everything done."
Read this + `MASTER_PLAN.md` + `design/VOICE-BRAIN-MASTER-PLAN.md` + `design/RUN-PLATFORM-MASTER-PLAN.md`
(once written) + `NEXT-BIG-BUILDS.md` after any compaction, then continue the loop.

## 🔁 THE LOOP (how the night keeps building)
Each wave completion fires a notification that re-invokes me → I launch the NEXT wave. NEVER end a turn
with zero waves running while the queue remains. ONE box-mutating wave at a time (sequential); read-only
research may run in parallel. On each completion: commit, update the ledgers + this file, launch next.

## 🟥 RULES (every wave)
- EARNER-SAFE: never edit/restart agent.py (md5 9150fabe…, PID 1477083); prompt.py is SHARED → gate on a
  golden byte-diff (flag OFF = byte-identical render); NO outbound test calls (DID resting); restart only
  famit-caller / aim-voice-agent / famit-panel. Verify md5/PID/health + golden diff, never a ring.
- MODEL ROUTING by task (memory `model-routing-by-task.md`): Haiku=explore/mechanical, Sonnet=research/
  web-search/compress/tests, Opus=design/red-team/earner-surgery/synthesis. Decide routing at AUTHOR time;
  never change a model on already-run phases (forces a wasteful re-run); reuse cache.
- Granular/resumable waves; flag + acceptance + rollback each; commit per unit; keep ledgers current.

## 🟢 LIVE NOW
- **W1** `wf_17dcce28-47c` (box-mutating, BUILDING) — dynamic vendor-script→persona + lossless full-context store + Script Studio UI.
- **P0-LEAK** `.wf/voice-p0-leak.js` (QUEUED → launch when W1 done) — close cross-tenant memory leak (inbound + WA only, NO earner restart, founder's choice).
- **run-platform-megaplan** `wf_eefea3fb-378` (read-only, FINISHING) — writes `design/RUN-PLATFORM-MASTER-PLAN.md`: real pricing, preview fix, provider-lock, feature-bucket table, crazy Run UI.

## 🏗️ PRIORITY ORDER (most important first; sequence the box-mutating ones)
1. **W1** (running) — script + full-context store. [founder asks A+B]
2. **P0-LEAK** — close the memory leak (inbound/WA).
3. **RUN-PLATFORM waves — founder's hot bugs (`design/RUN-PLATFORM-MASTER-PLAN.md` DONE). Build B→A→C:**
   - **B — PREVIEW FIX (hottest, do FIRST):** REAL cause = EL bytes served `Content-Type: text/plain` → Safari/iOS refuse `<audio>` → silence (the 307 theory was WRONG; the earlier "200 audio/mpeg curl proof" was fabricated). Fix: backend full-buffer the ≤32KB clip + FORCE `audio/mpeg` (both EL hosts: GCS + signed `api.us`) + 502-on-empty; FE real `.catch`+`onError`+caption, no `preload="none"`; byte-sniff (`ID3`/`\xFFxFB`/`RIFF`) not size>10000. Files: `caller.py` voice-preview route + `_voice-providers.tsx`. No flag.
   - **A — env billing + inbound provider-lock + funnels mount:** fix `USD_INR=1→95.2` (Groq ~95× undercharged), `EL_RATE=1.5→4.76`, Sarvam v2/v3 split; pure `resolve_providers(fields)` leaf in prompt.py drives plugin build + the metering `vendor` label (inbound, flag `INBOUND_PROV_LOCK=1`); mount funnels router (security). 🟥 CAVEAT: lock fixes the cost-LEDGER/dashboard, NOT the bill (wallet `_charge_call` is flat-rate → real billing = F4-wallet wiring, deferred). 🟥 EARNER GATE: golden `verify_golden.py` exit 0 + FRESH box md5 (the `9150fabe` literal is the BOX value — re-baseline, never trust the constant) + PID 1477083 + never edit/restart agent.py.
   - **C — Run UI + REAL cost meter (FE):** provider-lock banner, sourced cost breakdown, exclude-already-called toggle, pacing-defaults chip, inline voice-compare. `app/run/*`. 🟥 PRICING HONESTY: Vobiz ₹0.65/min is FABRICATED → needs founder's real CDR; Premium ₹8/min is BELOW COGS (platform-fee loss-leader); show ONLY sourced numbers, never fabricated.
   - DEFERRED (gated): D OB-PROV outbound + per-provider REAL billing (DID un-rest + sign-off + ring), E DID pool/rotation, F inbound metering, G F4-wallet→calls, H compliance+eval+KB.
4. **W2** — full-context cache + pooled httpx (voice-brain).
5. **Voice-brain memory system** — real-telecaller Hinglish RAG + multi-channel cross-call/WhatsApp memory (needs C/D).
6. **THE FULL BACKLOG — `NEXT-BIG-BUILDS.md` items 1–50 (canonical queue). Grind TOP-DOWN, every SAFE one, FE control UI each. Concrete order:**
   - #7 Funnels/Media MOUNT-BLOCKER security fix (body-tenant→token `build_router`) — before/with Workflow.
   - #6 AIM Access + PIN (`.wf/aim-access-and-pin.js` staged) → #8 Workflow/Funnel execution (human labels + wire Trigger→leads→campaign→/run + a working template).
   - #12 RAG populate + wire (BGE-M3 + campaign KB + grounding) → #13 Per-person memory inbound + WA-reply (keystone) → feeds the voice-brain memory system (C/D).
   - #9 Video Studio · #10 Vault · #15 ai_asset go-wide · #14 Hardening pt2 (sellable).
   - Gold-mine SAFE: #29 never-silent guard · #30 inbound Egress · #31 inbound metering · #33 DPDP delete · #34 inbound analytics · #35 mid-call `lead_is_hot` · #36 warm-transfer fallback · #37 post-call events · #38 sales-in inbound worker · #42 semantic turn-detector · **#44 eval/replay harness (HIGHEST leverage — makes voice changes provable)** · #47 warm-cache + pooled HTTP.
   - #5 Switcher P1 polish · #16 the 6 Creative sub-products · #20 Switcher P2 · #43 flow layer · #17 Control C10 · #18/#19 AIM+WhatsApp residuals · #27 media-gen flag-on.
   - Each: explore(haiku)→research(sonnet)→design/build(opus where it matters)→verify on the real flow, earner-safe, FE control UI, autonomously add the sellable bits he didn't name.

## ⛔ GATED — do NOT build without the founder (flag, don't ask)
Outbound provider-lock (agent.py edit + ring-test + DID un-rested + sign-off), WhatsApp delivery (Meta WABA),
Credits/Razorpay (on hold), Ads (OAuth), ModelScope (Alibaba bind), outbound dialing (DID/Vobiz carrier block).
