# ROUND-5 P1 — voice_kernel lean brain (STAGED / DORMANT, KERNEL_OUTBOUND stays 0)

THE LAW: never touch TTS constructors (agent.py:885-957) / .env / language clamp.
Do NOT flip KERNEL_OUTBOUND. Do NOT restart famit-agent. Edits are INERT while flag=0.
Box: ssh -i ~/.ssh/do-blr-test/id_ed25519 -o StrictHostKeyChecking=no famit@168.144.153.145 ; code /opt/famit-agent/
Repo (line-number-trustworthy, agent.py md5 48bc2b5a == box): C:/Users/kunal/Desktop/caps/

## STATUS: ✅ COMPLETE — STAGED/DORMANT (KERNEL_OUTBOUND stays 0; earner untouched, NRestarts=0)
TS for all backups: 20260619-142001. 6 files edited on box+repo (md5s in EARNER-LIVE-STATE P1 block).
- [x] P1.1 outbound.py — safety_rules="" -> SHARED_RULES_ENGAGEMENT constant -> ContextEngineImpl(safety_rules=…). PRESENT:True.
- [x] P1.2 delivery.py closing_directive() — removed ready-to-speak farewell EXAMPLE; principle-only (अलविदा ban kept). baited:False.
- [x] P1.3 packet.py _render_card_body — NEGOTIATION:/CLOSE: gated behind CARD_SCRIPTS (default OFF); facts still render. card-script:False.
- [x] P1.4 shrink: pack-select already 1+1 (no 11+6 concat). Compressed objection(482->377)/language(253->176)/delivery dirs;
        dropped redundant pack CLOSING: in provider.py. 2295 -> 1974 tok (<=2000). 14/14 guards + 19/19 invariants PASS.
- [x] P1.5 outbound.py — build_rag_runtime gated behind w4_rag_inject_enabled() (RAG_INJECT_ENABLED default OFF) -> NullRagRuntime;
        no corpus RELEVANT: block at GREET or QUALIFY. PROVEN.

OFFLINE PROOF: 2295->1974 tok; safety PRESENT; no baited farewell; no card-script; no corpus RAG. py_compile all 6 clean.
EARNER-SAFE: agent.py md5 48bc2b5a unchanged; .env EL_STABILITY=0.55 + voice_id unchanged; KERNEL_OUTBOUND=0 (drop-in+PID); active; NRestarts=0.
FLIP-TEST + REVERT commands recorded in EARNER-LIVE-STATE.md "ROUND-5 P1 STAGED" block.

## VERIFY (offline, subprocess w/ KERNEL_OUTBOUND=1 for THAT proc only)
assemble_outbound_instructions(...) on sample campaign+lead; assert:
  - assembled prompt <= ~2000 tokens
  - safety_rules engagement block PRESENT
  - NO baited farewell line
  - NO NEGOTIATION:/CLOSE: card-script
py_compile all edited files.

## RECORD
EARNER-LIVE-STATE.md "ROUND-5 P1 STAGED (dormant)" block: file:line changes, offline proof (token before/after,
safety present, no-baited-closing, no card-script), founder-gated FLIP-TEST cmd + one-command REVERT.

## PROGRESS LOG
(append per unit)
