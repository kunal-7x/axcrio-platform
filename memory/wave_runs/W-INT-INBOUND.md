# W-INT-INBOUND — flag-gated INBOUND kernel integration

Branch `fix/realtime-voice-kernel-v2`. Plan: `design/W-INT-INBOUND-PLAN.md`.
Patch doc: `design/W-INT-INBOUND-PATCH.md`. EARNER LAW: outbound `agent.py` md5
`98655dbf` FROZEN — never touched. Inbound target `aim_voice_agent.py` (box golden
`1614be09`). KERNEL_INBOUND default OFF ⇒ inbound byte-identical to today. NO box
deploy in this wave.

## Phase: BUILD

Built the TRACKED, git-revertable integration façade + tests. No box mutation; no
outbound/agent.py touched; `aim_voice_agent.py` left unmodified (patch is doc-only
— see drift note below).

### Deliverables (tracked)
- `voice_kernel/integrations/__init__.py` — package (droplet-free at import).
- `voice_kernel/integrations/inbound.py` — the agent-facing façade. Public API:
  `kernel_inbound_enabled, build_for_call, assemble_inbound_instructions, on_turn,
  plan_speech, choose_tts, on_tts_error, persist_post_call` (+ `bind_box_memory`
  box-startup memory seam). No `voice_kernel.*` type crosses into the agent. Every
  function is fail-safe (error ⇒ legacy-equivalent, never raises into a live call).
  Wires the REAL W2–W7 impls via `build_kernel(cfg, context=, vendor_script=,
  brain_packs=, rag=, speech=, router=, memory=)`; EventBus left Null.
- `voice_kernel/integrations/tests/` — `conftest.py` (isolated legacy-prompt
  loader) + `test_inbound_integration.py` (28 tests).
- `design/W-INT-INBOUND-PATCH.md` — the exact ~40-line flag-gated `aim_voice_agent.py`
  hook (Patches A–G), every hunk OFF-gated with the verbatim legacy `else`.

### API-name reconciliation (the façade is the single adaptation point)
Real exported factories (verified against the kernel source), which differ from
the plan's guesses — only `inbound.py` adapts, never the agent:
- W2 brain packs: `build_brain_packs()` (not `BrainPackProvider()`).
- W3 context: `compile_campaign(...)` + `ContextEngineImpl({cid: compiled},
  vendor_script=vs, safety_rules="")` + `VendorScriptEngineImpl().register(cid,
  raw, variables=)`.
- W4 rag: `build_rag_runtime()` (not `RagRuntime.from_env()`); degrades to empty
  with no backend wired.
- W5: `build_provider_router()` + `build_speech_planner()` ✓.
- W7: `LeadMemoryService(asession=None)` by default (droplet-free); box injects
  the RLS asession via `bind_box_memory()` at box startup.
- `MemoryService.extract_and_persist` has NO `outcome` param ⇒ façade accepts
  `outcome=` for forward-compat but does not pass it down.

### Design calls made (deviations from the plan, with reasons)
1. ON instructions path calls `ik.kernel.assemble_prefix(ctx)` DIRECTLY (the
   per-call WIRED kernel), NOT `adapter.instructions_provider` — the adapter
   builds a FRESH Null-impl kernel, so routing ON through it would lose all W2–W7
   impls. The OFF path (`ik is None`) returns `legacy_render()` — the same
   byte-identical guarantee `test_adapter_off_identity` proves.
2. Did NOT fold the legacy `prompt.py SHARED_RULES` into `safety_rules`. That text
   contains the legacy disclosure-honesty lines that include the spoken phrase
   "AI assistant"; folding it would undo the W2 banned-phrase fix and fail the "no
   banned self-label" gate. The kernel's own W2 structural disclosure
   (`build_structural_identity`) is authoritative — its SPOKEN self-label is
   guaranteed banned-phrase-free; the GUARDRAIL meta-instruction legitimately
   NAMES the phrase as a prohibition (tested via `strip_guardrail`).
3. W7 memory constructed `asession=None` (droplet-free) so calling the ON path in
   CI never lazily imports `droplet_work.db.engine` (which would pollute the
   global `sys.modules` and break the kernel-isolation tests that scan it). Live
   persistence is wired ON THE BOX ONLY via `bind_box_memory()` (Patch G).

### Tests — GREEN
- New: 28 tests in `voice_kernel/integrations/tests/test_inbound_integration.py`:
  import isolation (zero droplet at load); OFF flag ⇒ `build_for_call` None; OFF ⇒
  `assemble_inbound_instructions` byte-identical to the REAL `prompt.py
  build_system_prompt` (matrix); ON ⇒ valid packet prefix (not legacy); honors
  vendor script (hook word present); NO banned 'AI assistant' SPOKEN self-label;
  FENCES the untrusted brief (`<campaign_brief>…</campaign_brief>`, injection
  marker INSIDE the fence); fail-closed (blank tenant ⇒ None; tenant mismatch ⇒
  None; kernel refuses no-session assembly with `TenantIdentityError`; internal
  error ⇒ legacy fallback); `choose_tts` lean⇒SARVAM (the fix), premium⇒EL,
  explicit override wins, cached per call, `on_tts_error` fail-loud named swap;
  HOT `on_turn` returns a plain dict (no kernel types); COLD `persist_post_call`
  never raises without a DB; `plan_speech` returns a SpeechPlan ON / None OFF.
- Full suite: `python -m pytest voice_kernel/` ⇒ **240 passed** (212 prior + 28
  new). Verified the full ON exercise (build + assemble + choose_tts + on_turn +
  persist) leaves `sys.modules` droplet-free.

### Drift note (why the smoke patch is doc-only)
Local `droplet_work/aim_voice_agent.py` md5 `8335d4ba` ≠ box golden `1614be09`
(`droplet_work/aim_voice_agent.LIVEBOX.py`). The EARNER LAW permits applying the
smoke hook to the local copy only if OFF stays byte-identical vs the golden; with
the local copy drifted, that guarantee can't be made, so the patch is left
doc-only (the plan's documented fallback). The deploy wave applies Patches A–G to
the GOLDEN on the box (runbook backs up + asserts md5 `1614be09` first).

### Deploy-readiness statement
The integration is BUILT, fully tested, and inert by default. `KERNEL_INBOUND`
unset ⇒ the façade is never imported by the agent and `build_for_call` returns
None ⇒ inbound behaves byte-identical to the `1614be09` golden. NO box deploy was
performed (founder-gated, separate wave). The deployable = the box golden
`1614be09` + the §2 patch hunks from `design/W-INT-INBOUND-PATCH.md` applied on
top + ship the tracked `voice_kernel/integrations/` to the box venv (inert without
the flag). Deploy order is flag-OFF smoke (prove inert) → flag-ON synthetic canary
on a LEAN/STANDARD tenant (prove Sarvam audio + kernel prompt + tenant-scoped
memory write), restart ONLY `aim-voice-agent`, agent.py/famit-agent NEVER touched,
one-command rollback (`KERNEL_INBOUND=0` + restart). The earner gate (outbound
agent.py md5 `98655dbf`, PIDs, /health, no ring) is unaffected by this wave because
nothing outbound was changed.
