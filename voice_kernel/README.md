# voice_kernel — RealtimeVoiceKernel v2 (kernel core)

The layered **context-packet** kernel that replaces the ~13k-token single
f-string with a budgeted, ordered, cache-friendly `ContextPacket`. This package
is the **foundation contract** every downstream workflow (W2–W8) binds to.

> Full architecture decision log: `design/W1-KERNEL-ARCH.md`.

## EARNER LAW (read first)

- This package **NEVER imports or modifies** `droplet_work/agent.py` (the live
  outbound earner). A test (`test_contracts.py::test_importing_voice_kernel_pulls_no_droplet_modules`)
  asserts this mechanically.
- It is **additive + flag-gated, default OFF**. With `KERNEL_ENABLED=0` (default)
  the existing prompt-assembly path is **byte-for-byte unchanged**.
- Two md5 facts that the earner-gate distinguishes (the design's gate wording was
  internally inconsistent — fixed here):
  - **LIVE-BOX golden** = `9150fabe4ff62b4b4470f9a87df346e5` — the byte-identical
    target for the future **G3** box cutover. Verified ON THE BOX, **never**
    against the repo.
  - **TREE baseline (this branch)** = `98655dbfc71d5c3da36bcfe3f848082c` — what
    `droplet_work/agent.py` is at `HEAD`/working-tree on `fix/realtime-voice-kernel-v2`
    (it was modified by the founder-bug commits; `droplet_work/` is gitignored and
    `agent.py` is force-added). The **Build DoD "agent.py md5 unchanged"** asserts
    the **TREE** value `98655db`, captured at wave-start in `.kernel_baseline_md5`.
    Do NOT "restore" agent.py to `9150fabe` in the tree — that would revert the
    founder-bug commits and is itself an earner-adjacent edit.
- **Wave-start tripwire** (cheap, additive): before committing, run
  `git diff --quiet 98655db -- droplet_work/agent.py droplet_work/prompt.py droplet_work/aim_voice_agent.py || exit 1`
  so any accidental in-wave mutation of the live source fails LOUD, not at DoD.

## The ContextPacket (6 layers, ordered stable→volatile)

| Layer | Name | Scope | Cap | Owner |
|-------|------|-------|-----|-------|
| L0 | IDENTITY + SAFETY | stable | 350 | W1 (`SHARED_RULES` verbatim) |
| L1 | USE-CASE BRAIN PACK | stable | 250 | W2 |
| L2 | INDUSTRY PACK | stable | 150 | W2 |
| L3 | CAMPAIGN CARD | stable | 900 | W3 |
| L4 | LEAD MEMORY | per-call | 300 | W7 |
| L5 | TURN EVIDENCE | per-turn | 400 | W4 |

Render scopes (`packet.py`):
- `render_stable_prefix()` — L0..L3, once/call, **byte-identical every turn**
  (contains ZERO dynamic text — that's the cache rule).
- `render_call_suffix()` — L4, once/call.
- `render_turn_suffix()` — L5 + dynamic, re-rendered each turn, **hard-clamped here**.

`clamp()` enforces the budget: per-field hard clamps → on overflow **drop L5
first, then trim L4, NEVER trim L0** → if L0..L3 alone overflow, raise
`BudgetExceededError` (never silently send an over-budget prompt).

## The 9 service contracts (`contracts.py`)

`typing.Protocol` interfaces only — `ContextEngine, VendorScriptEngine,
BrainPackProvider, RagRuntime, SpeechPlanner, ProviderRouter, MemoryService,
EventBus, DialoguePolicy`. I/O methods are `async`; pure compilers are `sync`
(HOT-path safe). `null_impls.py` ships REAL conformant no-ops so the kernel runs
end-to-end before any workflow lands (logged as "null", never a silent `pass`).

Downstream waves register impls: `build_kernel(cfg, rag=MyRag(), memory=MyMem())`.

## Three-speed orchestration (`kernel.py`) — latency-correct

```
HOT  (per-turn, in-memory, NO await on the reply path):
     assemble_turn(turn, rag_layer=optional)  -> L5 suffix string | None
     retrieve_turn_layer(turn, timeout_s)     -> runs PARALLEL to the preemptive
                                                 LLM; empty on timeout, never blocks
WARM (once/call, opener-independent):
     assemble_prefix_core(ctx) -> (sync L0..L3 text, packet)   # construct Agent + fire opener
     enrich_prefix(ctx, packet) -> packet (L4)                 # background task, AFTER opener
     precompute(ctx)                                           # warm RAG room cache
COLD (post-call): persist_summary(...)
```

**Red-team latency fixes folded in:**
1. RAG is **never awaited before the LLM**. `assemble_turn` is in-memory only;
   `retrieve_turn_layer` carries a hard deadline and returns empty on timeout.
2. The **opener is independent of WARM I/O** — `assemble_prefix_core` is sync/
   await-free; L4 memory is applied via a background `enrich_prefix` task. DoD:
   no await between Agent construction and the first `session.say`.
3. **L5 is hard-clamped inside the per-turn render**, not only in the builder.

## Flags (`config.py`) — codebase-native, default OFF

`os.getenv("NAME","0") in ("1","true","True")`. Three scoped flags:
- `KERNEL_ENABLED` — master (default OFF).
- `KERNEL_INBOUND` — `aim_voice_agent.py` only (default OFF).
- `KERNEL_OUTBOUND_SHADOW` — shadow compute+log only, **never** substitutes.

`cfg.enabled_for(direction)` is the single gate. **With no env set, every
direction returns False** (`test_flags.py`).

> **Inbound flag MUST NOT go in the shared `.env`** (LEARNINGS §2: it leaks to
> the outbound earner on its next restart). Use the tracked systemd drop-in
> `systemd/aim-voice-agent.service.d-kernel.conf` (scopes `KERNEL_INBOUND=1` to
> the inbound unit only). Verify via `/proc/<pid>/environ` — see that file.

## The OFF-is-identity adapter (`adapter.py`) — the unit earner gate

```python
instructions_provider(legacy_render, ctx, *, cfg)  # OFF -> legacy_render() byte-for-byte
```
`legacy_render` is a zero-arg callable the AGENT passes (its OWN existing output)
— the kernel never imports the agent. `test_adapter_off_identity.py` runs the
**REAL** `droplet_work/prompt.py build_system_prompt(fields)` through the adapter
with `cfg=OFF` across a field matrix and asserts byte-equality. ON-failure falls
back to legacy AND logs a warning (never silently fails).

## Outbound shadow sidecar (`shadow/runner.py`)

Standalone, **never imports `droplet_work`** (`test_shadow_isolation.py`). Reads
out-of-band dispatch metadata, computes the packet for observability ONLY, never
substitutes the live string.

## Integration plan (out of scope for THIS build wave)

1. **Inbound first** — wrap `aim_voice_agent.py:1436 _build_sales_instructions`
   via `instructions_provider`, gated `KERNEL_INBOUND`. Never touches `agent.py`.
2. **Outbound shadow** — `KERNEL_OUTBOUND_SHADOW`, compute+log diff only.
3. **Outbound live cutover = G3 only** — human-gated, after the box GOLDEN
   byte-diff passes 5/5 flag-OFF + integrated turn-loop smoke + founder ring-test.

## Run the tests

```
python -m pytest voice_kernel/tests -q
```
