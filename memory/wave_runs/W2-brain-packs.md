# W2 — Brain Packs (voice_kernel/brain_packs/)

Branch: fix/realtime-voice-kernel-v2. EARNER LAW: never edit/import droplet_work/agent.py,
caller.py, aim_voice_agent.py. New disjoint files only under voice_kernel/brain_packs/.
Binds FROZEN BrainPackProvider Protocol (contracts.py:170): use_case_layer + industry_layer.

## Plan (one verifiable unit each)
- [ ] model.py        — UseCasePack + IndustryPack data model (encodes W6 §0/§A/§C/§D/§E)
- [ ] disclosure.py   — Tier-0/1/2 structural disclosure + banned-phrase block-list (W26)
- [ ] packs_data.py   — the 11 use-case packs + N industry packs as DATA (behavior, no campaign content)
- [ ] objection.py    — §D objection PRINCIPLES (stance + hooks, NOT canned replies)
- [ ] language.py     — §E casual-Hinglish rules (banned literary words -> preferred)
- [ ] registry.py     — version store: draft/test/publish/rollback + campaign->version binding
- [ ] provider.py     — BrainPackProvider impl (mode-aware objective engine) + identity_layer helper
- [ ] __init__.py     — public surface + build_brain_packs() factory for build_kernel(brain_packs=...)
- [ ] tests           — support!=push, no cross-vertical leak, no banned phrase, swappable,
                        versioning transitions, 0 droplet imports, flag-OFF byte-identity

## Phase: BUILD
Status: DONE — green. `python -m pytest voice_kernel/ -q` = 169 passed (28 new in
test_brain_packs.py). 0 droplet_work imports (asserted in test). Flag-OFF byte-
identity holds (adapter unchanged; test proves OFF returns legacy verbatim).

Files created (all DISJOINT, under voice_kernel/brain_packs/):
- model.py        — UseCasePack + IndustryPack + Stance data model (orthogonal L1/L2 axes)
- disclosure.py   — Tier 0/1/2 structural disclosure + BANNED_PHRASES block-list + strip_guardrail (W26)
- language.py     — casual-Hinglish rules: BANNED_LITERARY -> preferred, RENDERING_RULES, language_directive (W6 §E)
- objection.py    — §D objection PRINCIPLES (5-step stance + context hooks; NO canned replies); mode-tilted (support=de-escalate)
- packs_data.py   — the 11 use-case packs (1 per UseCase enum) + 6 seed industry packs as DATA (behavior, zero campaign content)
- registry.py     — BrainPackStore + JsonBrainPackStore: draft/test/publish/rollback + campaign->version pin/binding
- provider.py     — BrainPacks (BrainPackProvider impl): mode-aware objective engine (goal layered-in, not replaced) + identity_layer disclosure helper
- __init__.py     — public surface + build_brain_packs() factory
- tests/test_brain_packs.py — 28 tests

Key decisions:
- TWO orthogonal axes compose (UseCase L1 x Industry L2) — N+M packs, not N*M.
- Pack = DATA resolved by registry lookup, never code-per-pack. objective_template
  is abstract behavior; fields["goal"] is LAYERED IN (Law 2, never replaced).
- Stance.pushes_sale is the load-bearing flag: support/complaint/feedback/
  after_sales = False -> no sales-advance directive, objection stance flips to
  de-escalation. (Proven: support has no "advance the lead"/"purchase intent".)
- Cross-vertical leak guard: vertical vocab lives ONLY in IndustryPack; NEUTRAL
  default carries no vocabulary; language/objection layers were genericized to
  not enumerate vertical-specific examples (caught 'BHK'/'site visit' leaks in test).
- Disclosure is STRUCTURAL (always rendered in L0, above the C3 fence; vendor
  cannot weaken it). Default Tier 0 = brand+purpose+record-cue, NO banned phrase.
  Vendor-script-compatible: clean override honoured, banned override rejected.

Registered via: build_kernel(cfg, brain_packs=build_brain_packs()) — or with a
store: build_kernel(cfg, brain_packs=build_brain_packs(store=JsonBrainPackStore(path))).

LATER (not this wave): wire identity_layer/SHARED_RULES into NullContextEngine's
build_packet at the integration seam (flag-gated); PG-back the store; W4 consumes
behavior_pack_ids for micro-pack RAG.

## Phase: VERIFY+COMMIT (2026-06-18)

RECONCILE-FIRST (crash-safe RESUME): the W2 brain_packs package was already in HEAD
via prior sessions — `39304ba` (BUILD: swappable use-case + industry packs binding
BrainPackProvider), `ce5eddc` (RED-TEAM: stop sales-coaching hooks leaking into the
9 no-push modes — `hooks_for(use_case)` drops price/competitor/urgency for
pushes_sale=False), `637bb86` (order-independent droplet-isolation test), and the
disclosure red-team `build_structural_identity` (in `6db7dcf`, disclosure.py +
context_engine.py + null_impls.py + test_redteam_injection.py). This VERIFY phase
re-ran every gate against that committed tree — NO test weakened, NO re-build.

GATES (all GREEN on clean HEAD tree):
- `python -m pytest voice_kernel/` = **212 passed / 0 failed**.
- `test_adapter_off_identity` ran for REAL (NOT skipped) = **12/12 PASSED**
  (>=10 required) — flag-OFF kernel render byte-identical to droplet_work prompt.
- Droplet isolation: `import voice_kernel` + `voice_kernel.brain_packs` +
  `voice_kernel.contracts` from a clean interpreter pulls **0** agent / droplet_work
  / caller modules.
- W2 brain_packs files (provider/registry/model/packs_data/objection/language/
  disclosure/__init__) all committed, clean vs HEAD.

EARNER LAW HELD: `droplet_work/agent.py` md5 `98655dbfc71d5c3da36bcfe3f848082c`
(branch-baseline snapshot) UNCHANGED — `git diff --quiet -- droplet_work/agent.py`
clean; NOT edited/imported; `caller.py` / `aim_voice_agent.py` NOT touched.

gitleaks: `detect --no-git --source voice_kernel/brain_packs` (164 KB) = **0 leaks**;
`protect --staged` = **0**.

Red-team verdict folded: SHIP. The one cross-vertical leak (sales-coaching hooks in
no-push modes) was FIXED + regression-locked in `ce5eddc`; the disclosure
break-out/injection fence was sealed via `build_structural_identity` (`6db7dcf` /
`6fa3f09`). The W3 `Stage.PITCH` AttributeError the red-team reported is a concurrent
W3 wave's file (context_engine.py) and is resolved in HEAD (full suite green) — not a
brain_packs defect.

Staged ONLY memory/wave_runs/W2-brain-packs.md + WORKFLOW_LEDGER.md for this VERIFY
commit (brain_packs already committed). NEVER `git add -A`.
