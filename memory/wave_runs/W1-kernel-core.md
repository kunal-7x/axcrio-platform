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
