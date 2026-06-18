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
