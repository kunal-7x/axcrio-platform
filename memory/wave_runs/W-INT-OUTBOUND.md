# W-INT-OUTBOUND — flag-gated OUTBOUND kernel integration (wave run log)

> Branch `fix/realtime-voice-kernel-v2`. ONE BRAIN: the same kernel serves inbound
> + outbound; only the dial direction differs. This wave MIRRORS the proven inbound
> façade (`voice_kernel/integrations/inbound.py`) 1:1.
> 🚨 EARNER LAW (SACRED): the OUTBOUND earner is `droplet_work/agent.py`, LIVE box
> md5 `98655dbfc71d5c3da36bcfe3f848082c`. This wave does NOT edit the box, does NOT
> change agent.py, does NOT deploy. Flag `KERNEL_OUTBOUND` DEFAULT OFF ⇒ outbound
> byte-identical to today. The agent.py edit + deploy is a SEPARATE founder-gated
> step (PLAN §5).

## Phase: BUILD

Built/verified the TRACKED outbound integration as git-revertable code; wrote the
agent.py hook as a DOC-ONLY patch (no box file or gitignored agent.py edited).

### Files (all absolute under `C:\Users\kunal\Desktop\caps\`)
- `voice_kernel/integrations/outbound.py` — TRACKED façade (already present, green).
  Near-mirror of `inbound.py`; outbound deltas: flag `KERNEL_OUTBOUND`, session
  `direction="outbound"`, tenant source = the CAMPAIGN RECORD's owner
  (`camp["tenant_id"]`, server-written by `caller.py:save_campaign`), NO
  `is_manager` kwarg. Public API: `kernel_outbound_enabled`, `build_for_call`,
  `assemble_outbound_instructions`, `on_turn`, `plan_speech`, `choose_tts`,
  `on_tts_error`, `persist_post_call`, `bind_box_memory`. Lazy imports ⇒ importing
  the module pulls ZERO `droplet_work` modules (proven).
- `voice_kernel/config.py` — `KERNEL_OUTBOUND` flag (additive, default-OFF, the
  outbound twin of `KERNEL_INBOUND`); `enabled_for("outbound") = enabled OR
  outbound`. Locked by `test_outbound_flag_enables_outbound_only` in
  `voice_kernel/tests/test_flags.py`.
- `voice_kernel/integrations/tests/test_outbound_integration.py` — NEW this wave.
  33 tests mirroring the inbound integration gate + outbound deltas.
- `design/W-INT-OUTBOUND-PATCH.md` — DOC-ONLY agent.py hook (5 flag-gated sites,
  each with the verbatim legacy line as the OFF `else`; anchored to `98655dbf`).
- `design/W-INT-OUTBOUND-PLAN.md` — the design + super-gated deploy runbook.

### Tests (what the new file proves)
- OFF earner gate: `assemble_outbound_instructions(None, legacy_render=…)` delegates
  to the REAL `droplet_work/prompt.py:build_system_prompt` BYTE-IDENTICAL across the
  FIVE outbound field shapes (`default_godrej`, `variant_override`, `recap_present`,
  `minimal`, `empty`) — the same matrix the off-identity harness
  (`voice_kernel/tests/test_adapter_off_identity.py`, both directions) exercises.
- ON: valid kernel packet prefix honoring a vendor script (`VENDORHOOKWORD`
  present), NO "AI assistant" banned self-label (W2 fix, spoken-portion scan),
  untrusted brief fenced inside `<campaign_brief>` (C3, injection cannot escape),
  session `direction="outbound"` + `stamped_by="server"`.
- Fail-closed KernelSession: blank tenant ⇒ `None` ⇒ legacy (lead call NOT dropped);
  owner mismatch ⇒ `None`; kernel itself raises `TenantIdentityError` with no
  session; internal kernel error ⇒ falls back to `legacy_render` (never a broken
  prompt on the earner).
- `choose_tts` returns the SELECTED provider: lean tier ⇒ `sarvam`, premium ⇒
  `elevenlabs`, explicit `provider_pref` wins, cached per call; OFF ⇒ `elevenlabs`
  default; `on_tts_error` = fail-loud named swap.
- Import isolation: zero `droplet_work` leak at import AND via `bind_box_memory`.
- Outbound delta guards: `build_for_call` has NO `is_manager` kwarg (TypeError);
  `__all__` is exactly the documented surface.

### Verification (evidence, run this wave)
- `python -m pytest voice_kernel/integrations/tests/test_outbound_integration.py -q`
  ⇒ **33 passed**.
- `python -m pytest voice_kernel/ -q` ⇒ **274 passed** (was 241 collected pre-wave;
  +33 new = 274; well above the ≥240 floor). 0 failures.
- Smoke (KERNEL_OUTBOUND=1): import leaks 0 droplet modules; `build_for_call`
  returns a façade with `direction="outbound"`; rendered prompt 3585 chars, no
  legacy sentinel, vendor hook present, brief fenced, no "AI assistant",
  `choose_tts().tts == "sarvam"` for lean tier.
- `git status` ⇒ only the new test file changed under `voice_kernel/`; `agent.py`
  absent from git status (gitignored, untouched). No box mutation.

### Deploy readiness
NOT deployed in this wave — by EARNER LAW the agent.py edit + deploy is a SEPARATE,
super-gated founder step (PLAN §5: backup `98655dbf` + record md5, drift-check,
compute intended-new-closure md5, ship tracked `voice_kernel/` INERT, deploy patched
agent FLAG-OFF first with golden-campaign render-equality + real-ring smoke, then
flag-ON canary = FOUNDER REAL OUTBOUND RING on his own number only, restart
`famit-agent` ONLY, instant rollback = `KERNEL_OUTBOUND=0` + restart or restore the
`98655dbf` backup). `aim-voice-agent` (inbound) is NEVER touched by any outbound
step. With `KERNEL_OUTBOUND` unset the integration is fully inert and the earner is
byte-identical to today.

## Phase: VERIFY (2026-06-18)

Independent re-verification before the VERIFY+COMMIT. Red-team verdict on this wave =
**SHIP, no earner-safety blockers** (two non-blocking notes folded — see below).

### Tests (re-run this session)
- `python -m pytest voice_kernel/integrations/tests/test_outbound_integration.py -q`
  ⇒ **33 passed** in 0.23s.
- `python -m pytest voice_kernel/ -q` ⇒ **318 passed / 0 failed** in 2.19s. (The 3
  `voice_kernel/events/` failures the red-team flagged as pre-existing + unrelated are
  now GREEN too — the W8 events subsystem was fixed since; the only uncommitted
  kernel.py delta is the additive W8 `event_bus`→`events` impl-alias, NOT part of this
  outbound wave and left for its own unit.)

### Earner-safety invariants (all PROVEN this session)
- **Box/local `droplet_work/agent.py` md5 = `98655dbfc71d5c3da36bcfe3f848082c`** —
  EXACT match to the SACRED EARNER LAW hash. Earner byte-identical, untouched, not in
  git (gitignored). This wave wrote NO box file and NO local agent.py.
- **Import isolation:** `import voice_kernel.integrations.outbound` pulls **0**
  `droplet_work`/`agent` modules (measured via `sys.modules` diff). All droplet seams
  are lazy + flag-gated.
- **OFF = byte-identical:** `kernel_outbound_enabled()` default `False`;
  `build_for_call(...)` returns `None` (legacy path); `assemble_outbound_instructions(
  None, legacy_render=…)` returns the legacy render BYTE-FOR-BYTE (content + length,
  incl. unicode). Earner OFF behaves exactly as today.
- **Flag scoping:** `KERNEL_OUTBOUND=1` enables outbound ONLY (inbound stays `False`,
  no leak); `KERNEL_OUTBOUND_SHADOW=1` alone does NOT enable live replacement
  (`enabled_for('outbound')==False`). Default both `False`.
- **PATCH anchors valid:** the agent.py hook sites the DOC-ONLY patch targets exist in
  the local `98655dbf` copy at the cited lines — `instructions = base_instructions`
  `:461`, `ctx.add_shutdown_callback(_persist_memory)` `:553`, `elevenlabs.TTS(` `:563`.
- **gitleaks:** staged scan = 0 findings (committed below).

### Non-blocking notes folded (do not gate ship)
1. Doc nuance: outbound.py's module top-level is stdlib-only, but `voice_kernel/__init__.py`
   eagerly imports `.adapter`/`.kernel`/`brain_packs`, so importing the façade loads the
   kernel CORE (still 100% droplet-free). Identical to the shipped inbound pattern;
   irrelevant to the OFF earner (the agent never imports the façade when OFF).
2. The intended-new-closure md5 must be computed locally and asserted against the box
   file BEFORE the founder-gated deploy (PLAN §5) — deterministic gate, already specified.

### Commit
VERIFY+COMMIT staged ONLY this wave's wave-run log + the ledger VERIFY entry (the
outbound code + PLAN/PATCH docs were already committed in `1a2492b` + `cd24434`).
NEVER `git add -A`; the dirty `kernel.py` (W8) + the W-DEPLOY-INBOUND ledger line +
the broad untracked tree were left untouched for their own waves.
