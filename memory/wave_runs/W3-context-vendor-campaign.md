# W3 — context / vendor-script / campaign-compiler wave

Branch: `fix/realtime-voice-kernel-v2`. Built DISJOINT new files under
`voice_kernel/context/`. EARNER LAW held: `agent.py` md5 = `98655dbf` (unchanged);
`caller.py` / `aim_voice_agent.py` NOT edited.

## Phase: BUILD

Built the W3 campaign-context subsystem that fixes the two Founder complaints:
(a) vendor script ignored → now AUTHORITATIVE; (b) campaign brief lossy-compressed
→ now DUAL-LAYER (full raw preserved verbatim + structured metadata + compact card).

### Files (new, DISJOINT under voice_kernel/context/)
- `voice_kernel/context/text_hygiene.py` — self-contained NFKC normalize + zero-width
  strip + forged-fence defang (mirrors prompt.py hardening, imports nothing from
  droplet). LOSSLESS (no truncation) — `sanitize/normalize/defang_fences`.
- `voice_kernel/context/understanding.py` — Campaign Understanding Engine. Pure/sync
  keyword classifier → `CampaignUnderstanding(use_case, industry, objective,
  needs_booking/handoff/whatsapp, scores, confidence, source)`. EDITABLE: vendor
  explicit field wins over inference; `with_overrides(...)`. No GPU/embeddings (V1).
- `voice_kernel/context/campaign_compiler.py` — DUAL-LAYER `compile_campaign(...)
  -> CompiledCampaign`. T0 raw lossless (fenced CAMPAIGN_BRIEF, `raw_script_ref`
  pointer) + T1 full_* lossless + T2 compact card (H13 fields, overflow flags set
  by the compiler so packet.clamp stays idempotent). Injected `Distiller` (default
  heuristic, no key) for later LLM swap. Vendor-authored fields win.
- `voice_kernel/context/vendor_script.py` — `VendorScriptEngineImpl`. Vendor script
  = authoritative stage-by-stage blueprint (greet→permission→intro→qualify→
  objection→close), inline + standalone heading detection, `{{variable}}`
  substitution (unknown placeholders left intact; values sanitized), injection-fenced,
  falls back to "" when absent (default flow runs). `stage_excerpt` / `card_overrides`
  / `full_blueprint` are pure hot reads.
- `voice_kernel/context/context_engine.py` — `ContextEngineImpl` (ContextEngine
  Protocol). Assembles the ContextPacket from compiled campaign + understanding +
  vendor script, fences ALL untrusted text, renders L0 safety FIRST by position.
  Folds vendor greeting + opening blueprint into the card (authoritative flow).
  Compiles legacy/un-migrated campaigns on the fly (drop-in for NullContextEngine).
- `voice_kernel/context/__init__.py` — public surface.

### Edited (additive, kernel file — NOT a live earner file)
- `voice_kernel/kernel.py` — `build_kernel` now accepts the FROZEN registration
  spec `context=`/`vendor_script=` via an alias map (`context`→`context_engine`).
  Existing `rag=`/`memory=` field-name overrides unchanged.

### Tests — `voice_kernel/tests/test_w3_context.py` (15 tests, all green)
- full brief preserved verbatim (no loss) + full_usps lossless + in-prompt overflow flags
- packet.clamp idempotent on the compiled card (double-render invariant safe)
- vendor script overrides default opening + drives flow; falls back when absent
- ContextEngine folds vendor greeting + blueprint into the card
- fences present + PLATFORM safety ABOVE the fence by position (C3)
- vendor script cannot break out of its fence (forged-tag defang)
- Understanding Engine classifies real-estate vs support correctly; editable override wins
- `build_kernel(cfg, context=, vendor_script=)` registers correctly
- impls conform to their Protocols (isinstance runtime_checkable)
- zero droplet_work imports

### Verification
- `pytest voice_kernel/tests/test_w3_context.py` → 15 passed.
- `pytest voice_kernel/` → 82 passed (no regression).
- OFF byte-identity matrix → 10/10 (5 field variants × 2 directions) + 2 OFF guards, all PASSED.
- `md5sum droplet_work/agent.py` → `98655dbf...` (EARNER LAW value, unchanged).
- live files untouched (caller.py / aim_voice_agent.py not in my diff).

### Design note (no live edit)
- `design/W3-INTEGRATION-SEAM.md` — the LATER flag-gated wiring: `/extract` save-time
  compile (caller.py:4031 / extract_fields caller.py:1409), `run_job` engine build
  (caller.py:2852), recap seam (caller.py:2180/2216), persistence options. Single
  flag `KERNEL_W3_CONTEXT` (default OFF). No caller.py edits.

## Phase: VERIFY (red-team fixes folded)

Red-team verdict on W3 found claim (b) full-brief-lossless PASSES, but claim (a)
"vendor script is authoritative" was only HALF true — the back half of the
vendor's flow never reached any prompt. Two BLOCKERS + one quality bug, all fixed
in-scope (only `voice_kernel/context/context_engine.py`), still flag-OFF/additive.

- **BLOCKER 1 (vendor flow truncated):** `_apply_vendor_overrides` previously folded
  ONLY GREET/PERMISSION/INTRO into talking_points; QUALIFY/PITCH/OBJECTION/CLOSE were
  parsed but never surfaced. FIX — fold the FULL ordered flow into each stage's
  NATURAL card slot, which the packet renderer already prints (`_render_card_body`):
  GREET+PERMISSION+INTRO → talking_points, QUALIFY → qualifying_questions (carries the
  pitch/value-prop content when the vendor writes it under qualify/reason), OBJECTION
  → objections (as a leading Objection), CLOSE → closing_lines. The whole blueprint
  now reaches `render_stable_prefix()`. (PITCH has no Stage enum member; vendors write
  it under intro/reason → INTRO, or it rides the QUALIFY segment — either way it lands
  in the prompt.) C3 holds: every fold lands inside the CAMPAIGN_BRIEF fence below the
  PLATFORM safety layer — authoritative-on-flow never means authoritative-over-safety.
- **BLOCKER 2 (vendor content evicted):** the old `blueprint + talking_points)[:5]`
  raw-sliced away the vendor's own authored talking points (VENDOR-TP-4 dropped at the
  cap-5 boundary). FIX — new `_merge_unique(lead, existing)` keeps the authoritative
  flow FIRST then the vendor's authored content, dedupes (case/space-insensitive,
  substring-aware), and lets `packet.clamp()` (not a raw slice) apply the final per-
  field cap so the authoritative head always survives.
- **QUALITY (duplicate opener):** an unsegmented script returned the whole GREET text
  for GREET *and* INTRO → "Namaste ji" appeared duplicated. `_merge_unique` dedup
  collapses it to one. New test asserts exactly one opener talking point.

### VERIFY tests added (`test_w3_context.py`, now 18 total, all green)
- `test_full_vendor_flow_reaches_rendered_prompt_blocker1` — QUALIFY/PITCH/OBJECTION/
  CLOSE excerpts (`2BHK` / `metro ke paas` / `EOI offer` / `site visit book`) all
  present in `render_stable_prefix()`.
- `test_vendor_blueprint_does_not_evict_vendor_talking_points_blocker2` — vendor flow
  leads AND a vendor-authored `VENDOR-TP*` point survives the merge+clamp.
- `test_unsegmented_vendor_script_does_not_duplicate_opener` — opener appears once.

### VERIFY results
- `pytest voice_kernel/tests/test_w3_context.py` → 18 passed.
- `pytest voice_kernel/` → 212 passed (no regression; full kernel suite green).
- OFF byte-identity / isolation / shadow subset → 27 passed.
- zero `droplet_work` imports in `voice_kernel/context/` (real import lines = 0).
- `md5sum droplet_work/agent.py` → `98655dbf` (EARNER LAW, unchanged).
- caller.py / aim_voice_agent.py NOT in diff.
- NOTE: this commit also carries one orphaned W2 working-tree line in `context_engine.py`
  — `identity = build_structural_identity(f, ...)` (from the already-committed
  `brain_packs/disclosure.py`) — folded in to keep the tree consistent; it is the W2
  structural-AI-disclosure wiring the W2 wave built but left un-integrated. Tested green.
