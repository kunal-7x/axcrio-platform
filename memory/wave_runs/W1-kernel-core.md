# W1 — RealtimeVoiceKernel v2 Core — Wave Run Log

Branch: `fix/realtime-voice-kernel-v2`. EARNER LAW: `droplet_work/agent.py` md5
`9150fabe4ff62b4b4470f9a87df346e5` stays byte-identical; this wave builds ONLY new git-tracked
files under `voice_kernel/`, flag-gated default-OFF, additive. Never imports/edits the live agent.

## Phase: ARCHITECT

**Status:** DONE. Output = `design/W1-KERNEL-ARCH.md` (full decision log + Protocol signatures).

**Decisions recorded:**
1. **Package** = NEW git-tracked `voice_kernel/` at repo root (NOT inside gitignored
   `droplet_work/`). Pure-stdlib core so it imports clean and unit-tests with zero infra.
2. **ContextPacket** = 6 layers, stable-prefix-first, ≤2800 tok stable+memory (+≤400 turn):
   L0 IDENTITY+SAFETY (350, reuses `prompt.py SHARED_RULES` verbatim) · L1 USE-CASE (250) ·
   L2 INDUSTRY (150) · L3 CAMPAIGN CARD (900, replaces the lossy 4000-char extract) ·
   L4 LEAD MEMORY (300, structured facts not transcript) · L5 TURN RAG (400, per-turn). HARD
   per-layer clamps; overflow drops L5→L4, never L0. Frozen/pure (safe for the double-render at
   agent.py:416+431). Dynamic text (lead_name/recap/opener/lang) moves to the SUFFIX, never the
   cached prefix.
3. **9 Protocols** in `contracts.py`: ContextEngine(W1+W3), VendorScriptEngine(W3),
   BrainPackProvider(W2), RagRuntime(W4), SpeechPlanner(W5), ProviderRouter(W5),
   MemoryService(W7), EventBus(W8), DialoguePolicy(W6). I/O methods async; HOT-path compilers sync.
   `null_impls.py` = conformant no-op for each so the kernel runs before any downstream wave (logged
   null, never silent `pass`).
4. **Three-speed** HOT/WARM/COLD + Stage FSM (greet→...→followup) parameterized by UseCase; W6
   owns the policy table. Two assembly entry points: `assemble_prefix` (WARM, once/call) +
   `assemble_turn` (HOT, per-turn, maps to the on_user_turn_completed seam).
5. **Flags** `KERNEL_ENABLED` / `KERNEL_INBOUND` / `KERNEL_OUTBOUND_SHADOW` (default "0", native
   `os.getenv(...) in ("1","true","True")`). Inbound flag scoped via systemd drop-in so it can't
   leak to the earner .env. `adapter.instructions_provider` returns the EXACT legacy string when
   OFF (byte-for-byte) — unit earner gate = `test_adapter_off_identity`.
6. **Integration**: INBOUND first (wrap `aim_voice_agent.py:1436 _build_sales_instructions` +
   `:581 _build_instructions`, gated `KERNEL_INBOUND`) → OUTBOUND shadow (sidecar, agent.py
   byte-identical) → OUTBOUND live cutover at agent.py:416/431 is G3-only, human-gated, OUT OF
   SCOPE this wave.

**Ground truth verified (file:line):** agent.py:416/431/440 (outbound seams), agent.py:796/820
(per-turn seam), aim_voice_agent.py:1436/581/1652/1728/2565 (inbound seams), prompt.py:179
SHARED_RULES (L0 source), prompt.py:655 GODREJ_FIELDS (the `fields` key set the card maps 1:1 to),
flag pattern agent.py:451, live LLM = Groq llama-4-scout (no prompt-cache support today → packet
and caching are independent levers).

**Next phase (BUILD) must create:** the 15 files in §7 of `design/W1-KERNEL-ARCH.md`
(`voice_kernel/{__init__,packet,contracts,config,kernel,fsm,adapter,tokens,errors,null_impls}.py`
+ 4 tests + README). DoD: pytest green, OFF-identity proven, agent.py md5 unchanged, per-unit
commits + gitleaks 0.

---

## Phase: BUILD (2026-06-18, commit a1a3c58, branch fix/realtime-voice-kernel-v2)

STATUS: DONE — package built, 50/50 tests green, committed per-unit, gitleaks 0.

### Files created (24, all git-TRACKED at repo root, NOT under droplet_work/)
Core:
- `voice_kernel/__init__.py` — public surface export (ContextPacket, KernelConfig, build_kernel, contracts, fsm, prompt_cache, errors).
- `voice_kernel/packet.py` — 6 layer dataclasses + ContextPacket + TokenBudget + render scopes (stable_prefix/call_suffix/turn_suffix) + clamp (drop L5 -> trim L4 -> NEVER L0; BudgetExceededError on L0..L3 overflow).
- `voice_kernel/contracts.py` — 9 typing.Protocol interfaces (ContextEngine, VendorScriptEngine, BrainPackProvider, RagRuntime, SpeechPlanner, ProviderRouter, MemoryService, EventBus, DialoguePolicy) + shared dataclasses (CallContext, TurnContext, SpeechPlan, ProviderChoice, Event).
- `voice_kernel/config.py` — KernelConfig, codebase-native flag pattern, enabled_for(direction), default OFF.
- `voice_kernel/kernel.py` — RealtimeVoiceKernel + build_kernel + KernelServices (DI w/ null defaults); HOT/WARM/COLD entry points.
- `voice_kernel/fsm.py` — DialogueFSM + per-UseCase ModePolicy table + policy_for.
- `voice_kernel/adapter.py` — instructions_provider, the OFF-is-identity earner seam.
- `voice_kernel/tokens.py` — estimate_tokens (conservative chars/3.5) + clamp_chars/clamp_list.
- `voice_kernel/prompt_cache.py` — Groq prompt-cache helper (scout NOT cacheable encoded; split_for_cache shape-ready for lever 2).
- `voice_kernel/errors.py` — KernelError hierarchy (never silently fail).
- `voice_kernel/null_impls.py` — 9 REAL conformant null impls (NullContextEngine does the real fields->card compile).
Sidecar + infra:
- `voice_kernel/shadow/__init__.py`, `voice_kernel/shadow/runner.py` — standalone outbound shadow, NEVER imports droplet_work.
- `voice_kernel/systemd/aim-voice-agent.service.d-kernel.conf` — drop-in template scoping KERNEL_INBOUND off the shared .env (LEARNINGS §2) + /proc/<pid>/environ verify recipe.
- `voice_kernel/README.md` — condensed contract for W2-W8 authors.
Tests (7 files):
- `tests/conftest.py` — repo-root sys.path + isolated loader for droplet_work/prompt.py (no agent.py, no droplet package).
- `tests/test_adapter_off_identity.py` — EARNER GATE: OFF == REAL build_system_prompt(fields) byte-for-byte across a field matrix x both directions; ON-failure logs+falls-back.
- `tests/test_packet_budget.py` — budget/clamp/L0-never-trimmed/drop-L5-first/per-turn-L5-clamp/no-dynamic-in-prefix.
- `tests/test_fsm.py` — per-UseCase transitions, skips, objection routing, terminal hard-stop.
- `tests/test_flags.py` — default OFF every direction, inbound-only scoping, shadow never enables replacement.
- `tests/test_contracts.py` — null impls conform to Protocols; kernel runs e2e; ZERO droplet imports (mechanical).
- `tests/test_shadow_isolation.py` — shadow computes-not-substitutes; ZERO droplet imports.
- `tests/__init__.py`.
Wave-start tripwire artifact:
- `.kernel_baseline_md5` — captured md5 of the 3 live source files at wave start (agent.py 98655db, prompt.py fb87ea56, aim_voice_agent.py 8335d4ba).

### Test result
`python -m pytest voice_kernel/tests -q` -> **50 passed in 0.15s**.

### Red-team fixes folded (load-bearing)
1. EARNER-GATE wording fixed: DoD asserts TREE baseline md5 `98655db` (this branch's agent.py, modified by founder-bug commits); LIVE-BOX golden `9150fabe` stays the G3 box target, verified on the box never the repo. agent.py NOT restored (would revert founder commits). Wave-start tripwire `git diff --quiet HEAD -- droplet_work/{agent,prompt,aim_voice_agent}.py` = PASS.
2. RAG off the critical reply path: assemble_turn is in-memory only (no await); retrieve_turn_layer runs PARALLEL to the preemptive LLM w/ a hard timeout, empty on timeout.
3. Opener independent of WARM I/O: assemble_prefix_core is sync/await-free (constructs Agent + fires opener); enrich_prefix applies L4 via a background task AFTER the opener.
4. L5 hard-clamped INSIDE render_turn_suffix (+ standalone _render_turn_layer), not only in the WARM builder.
5. test_adapter_off_identity proves OFF-identity against the ACTUAL production build_system_prompt strings (prompt.py is stdlib-only/import-safe), not a stub.
6. Mechanical isolation: import voice_kernel + shadow => 0 droplet_work modules in sys.modules (tested).
7. Inbound flag-leak guard shipped as a tracked systemd drop-in, not prose.
8. voice_kernel/ at repo ROOT confirmed NOT gitignored (`git check-ignore` exit 1).

### Earner-safety verification
- Live source byte-identical vs HEAD: PASS (git diff --quiet clean for agent.py/prompt.py/aim_voice_agent.py).
- agent.py md5 = 98655dbfc71d5c3da36bcfe3f848082c (== tree baseline, unchanged).
- gitleaks protect --staged = 0 leaks (pre-commit hook also green).

### Follow-ups for the VERIFY phase
- VERIFY should run `python -m pytest voice_kernel/tests -q` (expect 50 green) + re-assert the tree tripwire + gitleaks.
- Confirm `import voice_kernel` on a clean interpreter pulls zero third-party deps (core is stdlib-only) — relevant for importing into aim_voice_agent.py at integration.
- The integration wave (NOT this one) wires instructions_provider into aim_voice_agent.py:1436 under KERNEL_INBOUND via the systemd drop-in, then verifies /proc/<pid>/environ shows the earner clean.
- Downstream W2-W8 each implement one Protocol from contracts.py and register via build_kernel(cfg, <name>=impl); until then the null impls run (logged as null).
- NOTE for VERIFY: test_adapter_off_identity SKIPS if droplet_work/prompt.py is absent (CI checkout w/o the gitignored tree) — on this box it is present and the gate runs for real.

## Phase: VERIFY

**Status:** DONE. Commit `718f569` (`feat(kernel): W1 RealtimeVoiceKernel v2 core + service contracts (flag-OFF, earner-safe)`) on branch `fix/realtime-voice-kernel-v2`. The kernel core landed earlier in `a1a3c58`; `718f569` adds `design/W1-KERNEL-ARCH.md` (the binding architecture/decision log) and this VERIFY log.

**Gate results (all GREEN):**
1. **Branch** = `fix/realtime-voice-kernel-v2` (confirmed via `git rev-parse --abbrev-ref HEAD`).
2. **Tests** = `python -m pytest voice_kernel/` -> **50 passed, 0 failed** (0.40s). No tests weakened/skipped to pass.
3. **OFF-is-identity** = `test_adapter_off_identity` ran for REAL (NOT skipped): 10/10 parametrized cases PASSED (outbound+inbound × default_godrej/variant_override/recap/minimal/empty), each asserting the flag-OFF kernel render is byte-identical to the actual `droplet_work/prompt.py build_system_prompt(fields)`.
4. **Flag default OFF** = `KernelConfig.from_env()` with no env -> `enabled=False`, `inbound=False`.
5. **Zero earner import** = `import voice_kernel` pulls **0** `droplet_work`/`agent` modules AND **0** third-party top-level deps (stdlib-only core) — proven at runtime, not just by grep. The only `agent.py`/`droplet_work` textual references in the package are comments, docstrings, and NEGATIVE test assertions (`test_contracts.py` asserts no `droplet_work` module is imported).
6. **Earner byte-identical** = `droplet_work/agent.py` shows ZERO changes vs HEAD (`git status` clean, `git diff --quiet` clean). md5 of the tracked tree copy = `98655dbf...` (the branch baseline snapshot from `683b0e5`); the EARNER-LAW md5 `9150fabe` is the BOX-truth md5 (LEARNINGS §1: local disk agent.py is a stale snapshot, the box is live truth). The real gate — agent.py UNTOUCHED by this build — holds. We did NOT "restore" the tree to `9150fabe` (that would revert the founder-bug commits — LEARNINGS §2-tree-tripwire).
7. **gitleaks** = `gitleaks protect --staged` = **0 leaks**; `gitleaks detect --no-git` over `voice_kernel/` (321 KB) and `design/W1-KERNEL-ARCH.md` = **0 leaks**; pre-commit hook gitleaks scan also clean. Staged ONLY the three required paths — never `git add -A`.

**Contract surface now FROZEN for W2-W8** (public API in `voice_kernel/__init__.py`, contracts in `contracts.py`):
- `ContextPacket` + 6 layers (`IdentityLayer` L0, `ModeLayer` L1, `IndustryLayer` L2, `CampaignCard` L3, `LeadMemory` L4, `TurnLayer` L5) + `TokenBudget`, `Stage`, `UseCase`, `Lifecycle`, `Objection`, `RagSnippet`, `PacketMeta`.
- 9 `@runtime_checkable` Protocols + owner waves: `ContextEngine` (W1+W3), `VendorScriptEngine` (W3), `BrainPackProvider` (W2), `RagRuntime` (W4, async, timeout-bounded, degrade-to-empty), `SpeechPlanner` (W5, sync HOT-path), `ProviderRouter` (W5, fail-loud), `MemoryService` (W7, async, PG/RLS), `EventBus` (W8, async, fire-and-forget), `DialoguePolicy` (W6, sync).
- Shared request/result dataclasses: `CallContext`, `TurnContext`, `SpeechPlan`, `ProviderChoice`, `Event`.
- Wiring: `build_kernel(cfg, <name>=impl)` + `KernelServices`; `RealtimeVoiceKernel`; `instructions_provider` (the OFF-is-identity seam); `DialogueFSM`/`ModePolicy`/`policy_for`; prompt-cache helpers (`split_for_cache`, `cache_breakpoint`, `is_cacheable_model`). `null_impls.py` ships a conformant logged-null for each Protocol so the kernel runs end-to-end before any W2-W8 lands.
- **How W2-W8 plug in:** each implements ONE Protocol from `contracts.py` and registers it via `build_kernel(cfg, <name>=impl)`; until a real impl lands, the null impl runs (logged as null, never silent). Integration into `aim_voice_agent.py:1436` is a LATER wave, gated `KERNEL_INBOUND` via a systemd drop-in — `agent.py` (the earner) is NEVER touched.

---

## Phase: AMEND (W1.5)

**Status:** DONE (2026-06-18). The three W18 red-team CRITICALs (C2/C3/H13) folded into the FROZEN W1
contracts, additively, BEFORE W2–W8 bind. Branch `fix/realtime-voice-kernel-v2`. EARNER LAW held:
`droplet_work/agent.py` md5 = `98655dbfc71d5c3da36bcfe3f848082c` (unchanged); agent.py/prompt.py/
aim_voice_agent.py byte-identical vs HEAD (`git diff --quiet` clean). OFF earner gate
`test_adapter_off_identity` = **10/10 byte-identical, STILL passing** (the OFF path delegates to
`droplet_work/prompt.py build_system_prompt` and does NOT require a tenant_id — the session is enforced
only on the kernel ON path, which the adapter never reaches when OFF).

### Files changed (6 source + 2 test + 2 doc)
- `voice_kernel/errors.py` — NEW `TenantIdentityError` (fail-closed tenant violation).
- `voice_kernel/contracts.py` — NEW frozen `KernelSession` (mandatory non-empty `tenant_id`+`call_id`,
  `__post_init__` raises, `assert_matches_campaign` cross-check); `CallContext` gains optional
  `session` field.
- `voice_kernel/packet.py` — C3: `SourceTrust` enum + `FencedText` + `fence()` helper; renders L0
  PLATFORM first, L3 card / L4 lead / L5 RAG wrapped in typed fences (safety-above-by-POSITION). H13:
  `render_cache_split()` → (L0+L1+L2 stable, L3+L4+L5 volatile); `CampaignCard` gains
  `full_product_summary`/`full_usps`/`summary_overflow`/`usps_overflow`; `clamp()` does
  retrieval-over-truncation (full text kept losslessly + overflow flag, NEVER dropped) and stays
  idempotent.
- `voice_kernel/kernel.py` — `_require_session(ctx)` fail-closed precondition at the top of
  `assemble_prefix_core`; `_render_turn_layer` fences RAG identically to the packet renderer.
- `voice_kernel/__init__.py` — export `KernelSession`, `SourceTrust`, `FencedText`, `fence`,
  `TenantIdentityError`.
- `voice_kernel/shadow/runner.py` — stamps a `KernelSession` from the SERVER-SIDE dispatch metadata
  (out-of-band, never a caller body) so the shadow ON path satisfies C2.
- `voice_kernel/tests/test_contracts.py` — `_ctx()` now stamps a matching `KernelSession`.
- `voice_kernel/tests/test_amend_w18.py` — NEW: 17 tests (C2 required/mismatch/immutable/fail-closed;
  C3 fenced layers present + safety-above-by-position + caller-utterance fence + PLATFORM-refused;
  H13 cache stable/volatile split + retrieval-over-truncation lossless + overflow flag + idempotent).

### Test result
`python -m pytest voice_kernel/` → **67 passed** (was 50; +17 new). OFF-identity 10/10 ran for REAL
(not skipped). `import voice_kernel` pulls **0** droplet modules (clean-interpreter check).

### New public surface (binding for W2–W8)
- `KernelSession` (server-stamped tenant identity; ON path REQUIRES it) · `CallContext.session`
  (NEW optional) · `TenantIdentityError`.
- `SourceTrust` {PLATFORM, CAMPAIGN_BRIEF, RETRIEVED_KNOWLEDGE, LEAD_MEMORY, CALLER_UTTERANCE} ·
  `FencedText` · `fence(trust, content, label)` (refuses PLATFORM) — W3/W4/W7 carry untrusted text
  through this so they can't forget to fence.
- `ContextPacket.render_cache_split() -> (stable, volatile)` (H13) · `CampaignCard.full_product_summary
  /full_usps/summary_overflow/usps_overflow` (retrieval-over-truncation — W4 indexes the full text).
- `RealtimeVoiceKernel.assemble_prefix_core/assemble_prefix` now fail-closed without a matching session.

## Phase: VERIFY (W1.5) (2026-06-18, commit 05cb505, branch fix/realtime-voice-kernel-v2)

Independent VERIFY of the W1.5 contract amendment (the BUILD/AMEND was committed by a prior
session as `05cb505`; this phase re-ran every gate against that commit's tree — no re-commit,
no test weakened, crash-safe RESUME).

### Gates (all GREEN)
- **Branch:** `fix/realtime-voice-kernel-v2` ✓.
- **Tests:** `python -m pytest voice_kernel/` → **67 passed / 0 failed**. `test_adapter_off_identity`
  ran for REAL (not skipped): the 10 `test_off_is_byte_identical_to_real_legacy` params (outbound +
  inbound × {default_godrej, variant_override, recap_present, minimal, empty}) = **10/10 PASS**, plus
  `test_off_does_not_invoke_kernel` + `test_on_failure_falls_back_to_legacy_not_silent`. Flag-OFF
  byte-identity invariant intact after the amendment.
- **Earner law:** `droplet_work/agent.py` byte-identical vs HEAD (`git diff --quiet` clean); NOT in
  the `05cb505` file list; tree md5 `98655dbfc71d5c3da36bcfe3f848082c` == the EARNER-LAW box truth.
  Import isolation: `import voice_kernel` from a clean interpreter pulls **0** `agent`/`droplet_work`
  modules (146 new modules, 0 leaked).
- **gitleaks:** `detect --no-git --source voice_kernel/` (≈416 KB) = **0 leaks**; `protect --staged` = 0;
  diff scan of `05cb505~1..05cb505` (37.8 KB) = **0 leaks**.

### FINAL FROZEN PUBLIC SURFACE (binding for W2/W3/W4/W5/W7/W8)
Re-exported from `voice_kernel/__init__.py` (`__all__`, version 0.1.0). Downstream waves implement
ONE `@runtime_checkable` Protocol and register via `build_kernel(cfg, <name>=impl)`.

- **9 service Protocols** (`contracts.py`): `ContextEngine` (W1/W3) · `VendorScriptEngine` (W3) ·
  `BrainPackProvider` (W2) · `RagRuntime` (W4) · `SpeechPlanner` (W5) · `ProviderRouter` (W5) ·
  `MemoryService` (W7) · `EventBus` (W8) · `DialoguePolicy` (W6).
- **Request/result dataclasses** (`contracts.py`): `CallContext{meta,fields,fields_override,recap,session}` ·
  `TurnContext` · `SpeechPlan` · `ProviderChoice` · `Event`.
- **C2 tenant identity:** `KernelSession{tenant_id,call_id,direction,stamped_by}` (frozen, fail-closed
  `__post_init__` + `assert_matches_campaign`) · `CallContext.session` (Optional; ON path REQUIRES it
  via `RealtimeVoiceKernel._require_session`) · `TenantIdentityError`.
- **C3 trust fences:** `SourceTrust` {PLATFORM, CAMPAIGN_BRIEF, RETRIEVED_KNOWLEDGE, LEAD_MEMORY,
  CALLER_UTTERANCE} · `FencedText{trust,content,label}.render()` · `fence(trust, content, label="")`
  (refuses PLATFORM). W3/W4/W7 + live-mic seam carry untrusted text through `fence()`.
- **Packet + layers** (`packet.py`): `ContextPacket` (+ `render_stable_prefix`, `render_call_suffix`,
  `render_turn_suffix`, `render_cache_split() -> (stable, volatile)` H13, `clamp`, `token_estimate`) ·
  `PacketMeta` · `IdentityLayer` (L0) · `ModeLayer` (L1) · `IndustryLayer` (L2) · `CampaignCard` (L3,
  with **H13 lossless** `full_product_summary` / `full_usps` / `summary_overflow` / `usps_overflow`) ·
  `Objection` · `LeadMemory` (L4) · `RagSnippet` · `TurnLayer` (L5) · `TokenBudget` · enums `UseCase` /
  `Lifecycle` / `Stage`.
- **Kernel + factory** (`kernel.py`): `RealtimeVoiceKernel` (entry points `assemble_prefix_core` /
  `assemble_prefix` / `enrich_prefix` / `precompute` / `assemble_turn` / `retrieve_turn_layer` /
  `persist_summary`; both prefix entries now fail-closed without a matching `KernelSession`) ·
  `KernelServices` (9 fields, each defaulting to its null impl) · `build_kernel(cfg, services, **impls)`.
- **Adapter / FSM / cache / config / errors:** `instructions_provider` (the OFF-is-identity seam) ·
  `DialogueFSM` / `ModePolicy` / `policy_for` · `CacheSplit` / `cache_breakpoint` / `is_cacheable_model`
  / `split_for_cache` · `KernelConfig` (default OFF) · errors `KernelError` / `BudgetExceededError` /
  `ClampError` / `ContractViolationError` / `ConfigError` / `TenantIdentityError`.
