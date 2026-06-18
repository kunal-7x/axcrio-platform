# W-INT — Flag-Gated OUTBOUND Kernel Integration PLAN

> Status: **DESIGN + TRACKED MODULE — no box file edited, no box restart by this wave.**
> Branch: `fix/realtime-voice-kernel-v2`.
> 🚨 EARNER LAW (SACRED): the OUTBOUND earner is `droplet_work/agent.py`, LIVE box
> md5 = **`98655dbfc71d5c3da36bcfe3f848082c`** (= the founder's already-live voice
> fixes; NEVER restore an older hash). **This wave does NOT edit the box and does
> NOT change the box `agent.py`.** It builds the integration as TRACKED code in
> `voice_kernel/integrations/outbound.py` (git-revertable) + writes the `agent.py`
> hook as a **PATCH DOC only** (`design/W-INT-OUTBOUND-PATCH.md`; `droplet_work/` is
> gitignored). The actual `agent.py` edit + deploy is a **SEPARATE, super-gated
> founder step** (§5). Flag **`KERNEL_OUTBOUND` DEFAULT OFF** ⇒ outbound behaves
> **byte-identical to today**.

> ONE BRAIN: the SAME kernel serves inbound + outbound; only the dial direction
> differs. This plan MIRRORS the proven inbound integration
> (`voice_kernel/integrations/inbound.py` + `design/W-INT-INBOUND-PLAN.md` +
> `W-INT-INBOUND-PATCH.md`) — same `instructions_provider` OFF-is-identity seam,
> same `KernelSession` fail-closed pattern, `direction='outbound'`. Outbound differs
> ONLY in: the base agent file (`agent.py` vs `aim_voice_agent.py`), the flag
> (`KERNEL_OUTBOUND`), the **campaign-driven tenant/lead source**, and
> `direction='outbound'`.

The kernel is built + green (185 kernel tests, +1 new outbound-flag test = 186).
This plan wires W2–W7 into outbound via ONE tracked façade module so `agent.py`
gains only ~5 call sites, each `if _KERNEL_OUTBOUND:` with the existing legacy line
as the unchanged `else`.

---

## 0. Why a façade module (the design choice — identical rationale to inbound)

`agent.py` is box-only/gitignored AND is THE live earner (the single most
dangerous file in the product). Putting the wiring (build_kernel, all W2–W7 impl
construction, the per-hook glue) inside it would be (a) un-revertable via git and
(b) a large diff on the most sensitive file in the system. Instead:

- **TRACKED** `voice_kernel/integrations/outbound.py` holds ALL the bulk: it builds
  the kernel once per call, constructs every W2–W7 impl, stamps the fail-closed
  `direction="outbound"` session, and exposes a small set of functions the agent
  calls. Reverting the integration code = `git revert` of that one tracked module.
- The agent hook is a **few lines**, each gated by `_KERNEL_OUTBOUND`, with the
  legacy expression preserved verbatim as the OFF branch. The agent NEVER imports
  `voice_kernel.*` at module top-level — every import is lazy, INSIDE the `if`, so
  OFF pays nothing (not even an import).
- This is the EXACT shape that passed for inbound; outbound reuses it 1:1.

---

## 1. THE TRACKED MODULE API — `voice_kernel/integrations/outbound.py`

A thin, stateful-per-call façade. It owns kernel construction + impl wiring and
hides every `voice_kernel.*` type from the agent. All functions are **fail-safe**:
any internal error logs a WARNING and returns the legacy-equivalent so a kernel
fault can never break or drop a live LEAD call (the earner). **This module already
exists, is tracked, and is green (smoke + 186 kernel tests).** API surface:

### 1.1 `kernel_outbound_enabled() -> bool`
Single source of truth for the flag (config-native). Reads
`KernelConfig.from_env().enabled_for("outbound")`, which is `True` iff
`KERNEL_OUTBOUND` (the outbound twin of `KERNEL_INBOUND`) OR the master
`KERNEL_ENABLED` is set. Default ⇒ `False`. Wrapped in try/except → any config
error treats the flag as OFF (never crashes the earner).

### 1.2 `build_for_call(...) -> OutboundKernel | None`  (once per call, after the campaign + tenant resolve)
```python
def build_for_call(
    *,
    tenant_id: str,            # the CAMPAIGN RECORD's owning tenant (camp["tenant_id"]) — NOT a body value
    call_id: str,             # = room_name (the outbound room id)
    lead_phone: str,          # parsed from the room name (mem.parse_phone(room_name))
    campaign_id: str,         # from dispatch metadata (meta["campaign_id"])
    campaign_tenant_id: str,  # the campaign record's owner (same source) — fail-closed cross-check
    fields: dict | None = None,   # the live campaign `fields` dict (prompt.py shape)
    recap: str = "",
    pg_memory: str = "",
    locale: str = "hi-IN",
) -> Optional[OutboundKernel]: ...
```
Returns `None` on the OFF flag OR ANY failure ⇒ the agent uses its legacy path
unchanged. C2 fail-closed: stamps `KernelSession(tenant_id=<campaign-record owner>,
call_id=room_name, direction="outbound", stamped_by="server")` and cross-checks via
`session.assert_matches_campaign(campaign_tenant_id)`; a blank/mismatch raises
`TenantIdentityError` → caught → `None` → legacy path (the call still proceeds,
kernel disengaged, logged LOUD). **Note vs inbound:** there is NO `is_manager`
parameter — an outbound LEAD dial is never a manager persona (inbound's
manager/attendant branch has no outbound analog).

`_build_kernel_with_impls(cfg, tenant_id, campaign_id, fields)` is the ONE place
registering the W2–W7 concretes (`ContextEngineImpl` + `VendorScriptEngineImpl` +
`compile_campaign`, `build_brain_packs`, `build_rag_runtime`, `build_provider_router`
+ `build_speech_planner`, `LeadMemoryService`). It is **byte-for-byte the same
wiring as `inbound._build_kernel_with_impls`** (one brain). A missing/disabled wave
degrades to its Null impl automatically.

### 1.3 The functions the agent hook calls (identical signatures to inbound, outbound-named)
| Function | Path | OFF / None ik returns |
|---|---|---|
| `assemble_outbound_instructions(ik, *, legacy_render, fields, recap, grounding, pg_memory) -> str` | one-time prefix | `legacy_render()` (byte-identical) |
| `async on_turn(ik, *, user_text, detected_lang, stage, history_len) -> dict` | HOT, per turn | inert `{"reply_lang": detected_lang, "rag_suffix": None, "speech_plan": None}` |
| `plan_speech(ik, *, raw_text, lang) -> SpeechPlan \| None` | HOT, pre-TTS | `None` (agent uses raw text) |
| `choose_tts(ik, *, provider_pref) -> ProviderChoice` | once, TTS init | `ProviderChoice(tts="elevenlabs")` (today's hard-coded default) |
| `on_tts_error(ik, provider, code) -> ProviderChoice` | on TTS fault | `ProviderChoice(tts="elevenlabs")` |
| `async persist_post_call(ik, *, lead_phone, turns, name, raw_summary, outcome) -> None` | COLD, post-call | no-op (legacy save still runs) |
| `bind_box_memory(asession) -> None` | box startup | n/a (wires RLS memory ON BOX only) |

**Public API surface (what the agent imports):** `kernel_outbound_enabled`,
`build_for_call`, `assemble_outbound_instructions`, `on_turn`, `plan_speech`,
`choose_tts`, `on_tts_error`, `persist_post_call`, `bind_box_memory`. Nothing else.
No `voice_kernel.*` type crosses into the agent.

### 1.4 Config flag added (additive, default-OFF) — `voice_kernel/config.py`
`KERNEL_OUTBOUND` is the outbound twin of `KERNEL_INBOUND`:
`enabled_for("outbound") = self.enabled or self.outbound`. This lets the G3 cutover
flip ONLY `KERNEL_OUTBOUND` (in the famit-agent systemd drop-in) WITHOUT turning on
the master `KERNEL_ENABLED` (which would also enable inbound). The shadow flag
`KERNEL_OUTBOUND_SHADOW` is untouched and still never enables replacement. New test
`test_outbound_flag_enables_outbound_only` locks the contract; all 186 pass.

---

## 2. THE MINIMAL `agent.py` HOOK (exact hunks → `W-INT-OUTBOUND-PATCH.md`)

The full, copy-paste hunks live in `design/W-INT-OUTBOUND-PATCH.md`. Summary of the
five flag-gated sites in `entrypoint()` (line anchors against the FROZEN `98655dbf`),
each with the verbatim legacy line preserved as the OFF branch:

| Patch | Site (agent.py) | Legacy expr (OFF branch, unchanged) | ON branch |
|---|---|---|---|
| **A** flag + slot | top of `entrypoint`, ~`:404` after `lead_name` | — | `_KO = os.getenv("KERNEL_OUTBOUND",...)`; `_OK = None` |
| **B** build façade | after prompt+recap assembled, ~`:461` (after `instructions = base_instructions`) | — | `_OK = outbound.build_for_call(tenant_id=camp_owner, ...)` |
| **C** instructions | `instructions =` assignment, `:461` | the whole `base_instructions` block (system_prompt + lead-name + OPENER_ALREADY_SAID + recap) wrapped as a zero-arg `_legacy` lambda | `assemble_outbound_instructions(_OK, legacy_render=_legacy, ...)` |
| **D** TTS provider | TTS init, `:563`–`:567` (`voice_id`/`language`) | `elevenlabs.TTS(... voice_id=fields.get("voice_id") or env ...)` | `choose_tts(_OK, provider_pref=fields.get("tts_provider",""))` decides EL vs Sarvam; EL path unchanged |
| **F** post-call | `_persist_memory()` shutdown cb, `:537` after `_summarize` | `summ = _summarize(turns)` + the transcript write | ADD `persist_post_call(_OK, ...)` AFTER the legacy write (additive) |

Optional **Patch E** (per-turn HOT, SHADOW-safe): register an `on_user_turn_completed`
/ `_on_item` shadow that calls `await on_turn(_OK, ...)` to compute+log the L5 RAG
suffix with NO behavior change until a pre-LLM inject hook lands (the documented W5
deferral). The **closure seam** (`_confirm_then_hangup`, `:695`) is a candidate for a
later `generate_outbound_closing` but is OUT OF SCOPE for the first cutover (the
legacy `_llm_close` / `_goodbye_line` is already env-gated and proven); the patch
leaves it byte-identical.

**Total agent edit:** flag line + façade build + 1 instruction wrap + 1 TTS-provider
branch + 1 post-call add (+ optional shadow turn listener) ≈ **~35 lines, every one
OFF-gated.** No closure rewrite, no opener rewrite in the first cutover — the OFF
default keeps both identical.

---

## 3. HOW `KERNEL_OUTBOUND=0` STAYS BYTE-IDENTICAL

1. **No import on the OFF path.** Every `from voice_kernel.integrations import
   outbound` sits INSIDE an `if _KERNEL_OUTBOUND` (Patches B–F). With the flag off,
   `voice_kernel` is never imported by the earner — an import-time bug in the kernel
   cannot reach `agent.py`. (Verified: the module is droplet-free; importing it
   pulls ZERO `droplet_work` modules.)
2. **`_OK is None` ⇒ legacy.** `build_for_call` returns `None` when the flag is off
   (it checks `kernel_outbound_enabled()` first). Every helper short-circuits on
   `ik is None` and returns the legacy-equivalent (proven by the smoke:
   `assemble_outbound_instructions(None, legacy_render=…) == legacy`,
   `choose_tts(None).tts == "elevenlabs"`).
3. **Instructions = the legacy renderer when OFF.** `assemble_outbound_instructions`'
   OFF branch is `return legacy_render()`, where `legacy_render` is the verbatim
   `base_instructions` builder (system_prompt + lead-name append +
   `OPENER_ALREADY_SAID` block + recap). The **W1 off-identity test
   (`test_adapter_off_identity`) covers outbound** — it exercises the
   `instructions_provider` OFF==legacy invariant against the legacy renderer, the
   same byte-for-byte guarantee. The kernel's `instructions_provider` delegates to
   the legacy build for outbound field shapes when OFF.
4. **No per-turn kernel calls when OFF.** The optional shadow `on_turn` listener is
   registered only under `if _KERNEL_OUTBOUND`. OFF ⇒ no extra event handler, no
   RAG, no speech plan — the hot path is unchanged.
5. **Provider default preserved.** OFF branch of Patch D is the verbatim
   `elevenlabs.TTS(...)` exactly as today (the earner has always spoken EL on
   outbound).
6. **Post-call.** OFF ⇒ only the legacy `mem.save_memory` + `_summarize` +
   transcript write run. No kernel write.

**DoD for the OFF claim:** with `KERNEL_OUTBOUND` unset, the rendered system-prompt
(for a GOLDEN CAMPAIGN — see §5 render-equality gate), the constructed TTS provider
(`elevenlabs`), the opener, the closure, and the post-call write set are identical
to the `98655dbf` golden — verified by an md5 of the rendered prompt + a flag-OFF
real-ring smoke (§5 Step 1).

---

## 4. WHERE `tenant_id` COMES FROM ON AN OUTBOUND CAMPAIGN CALL (fail-closed)

This is the KEY outbound-vs-inbound difference. On **inbound** the tenant is
server-resolved from the DID / contact lookup (no trusted body). On **outbound**
there is a dispatch, but the dispatch metadata must NOT be trusted to carry the
tenant. Ground truth from the live code:

| Fact | File:line | Implication |
|---|---|---|
| The campaign record is written by the caller WITH its owning tenant | `caller.py:1458` `rec = {"id": cid, "tenant_id": tenant_id, ...}` | the campaign file IS the server-stamped tenant source |
| Dispatch metadata carries ONLY `{campaign_id, lead_name}` (+ optional `fields_override`) | `caller.py:2931` `md_obj = {"campaign_id": cid, "lead_name": ...}` | the metadata does NOT (and must not) carry a tenant |
| The agent loads the campaign by id | `agent.py:407` `camp = _load_campaign(meta.get("campaign_id",""))` | the agent already reads the campaign record per call |
| The agent today writes `tenant_id: ""` in usage and lets the caller join by room | `agent.py:506` `"tenant_id": ""  # caller joins tenant/call_id by room` | the agent has no tenant of its own TODAY — the kernel adds one, sourced correctly |

**The fail-closed source:** the tenant for the outbound `KernelSession` is
`camp["tenant_id"]` — **the campaign record's OWNING tenant**, which `caller.py`
wrote under that tenant's authenticated request (`save_campaign(fields, tenant_id)`).
It is NOT taken from the dispatch metadata body. A forged `campaign_id` in a
dispatch body cannot smuggle a tenant: either the campaign file does not exist
(`_load_campaign` → `None` → no kernel build → legacy path), or it exists and
carries its TRUE owner (the only tenant the kernel will ever stamp for that call).

**The cross-check (armed):** `build_for_call` is passed `tenant_id=camp["tenant_id"]`
AND `campaign_tenant_id=camp["tenant_id"]`; `session.assert_matches_campaign(...)`
fail-closes on a blank tenant or any future path where the two diverge (e.g. a
campaign resolved from `fields_override` whose owner differs). On the
returning-lead/normal path they are the same value (a consistency assertion); its
TEETH are on any future code path that resolves an owner independently. A raise is
caught → `_OK = None` → **the call still runs on the legacy path** (kernel
disengaged, logged LOUD) — fail-closed for the KERNEL but never a dropped lead call.

> Net: outbound tenant = the campaign record's owner (server-written by
> `caller.py:save_campaign`), stamped immutably with `direction="outbound"`, never a
> dispatch-body value; blank/mismatch ⇒ kernel disengages (legacy), never serves a
> cross-tenant packet. (Verified by smoke: blank tenant → None; owner mismatch →
> None.)

---

## 5. THE SUPER-GATED DEPLOY RUNBOOK (the MOST DANGEROUS deploy in the product)

> 🚨 This is the SINGLE most dangerous deploy: it mutates the LIVE EARNER `agent.py`.
> **ONE box-mutating change at a time. Earner gate before AND after every step. The
> `98655dbf` backup is the one-command revert. The revert path is ALWAYS ready
> before any change.** NOT executed in this design wave. The `aim-voice-agent`
> service is NEVER touched here; ONLY `famit-agent` is restarted, and ONLY at the
> flag-OFF deploy + the canary step.

### Pre-flight (READ-ONLY — abort on any mismatch)
1. **Earner gate BEFORE:** SSH the voice box. Confirm the LIVE `agent.py` md5 ==
   `98655dbfc71d5c3da36bcfe3f848082c`. `famit-agent` worker PIDs running; caller
   `/health` == 200; a real outbound ring still connects (the LIVE baseline).
   **ABORT** if md5 ≠ `98655dbf` — do NOT "restore baseline" to any older hash; that
   hash IS the founder's live fixes.
2. **Backup the earner:** `cp /opt/famit-agent/agent.py
   /opt/famit-agent/agent.py.WOUTbak.<ts>`; **record its md5** (must be `98655dbf`).
   This backup is the instant rollback artifact — verify it reads back at `98655dbf`
   before proceeding.
3. **Box→local drift check:** md5 of box `agent.py` == local
   `droplet_work/agent.py` (`98655dbf`). They MATCH today (unlike inbound, which had
   drifted) — so the local copy is byte-representative and the patch hunks in
   `W-INT-OUTBOUND-PATCH.md` apply cleanly. If the box ever differs, STOP and
   reconcile first.
4. **Compute the INTENDED-NEW md5 locally FIRST.** Apply the `W-INT-OUTBOUND-PATCH.md`
   hunks to a COPY of the local `98655dbf` `agent.py`, syntax-check it
   (`python -m py_compile`), and record the resulting md5 = the **intended-new
   closure** hash. The box deploy will assert the deployed file equals THIS exact
   hash (no accidental extra edits).
5. **Ship the TRACKED module:** copy `voice_kernel/` (incl. `integrations/outbound.py`
   + the `config.py` flag) into the famit-agent venv's import path. It is INERT
   without the flag (import is droplet-free + the flag is OFF).

### Step 1 — deploy the patched agent FLAG-OFF FIRST (byte-identical smoke)
6. Deploy the patched `agent.py` with `KERNEL_OUTBOUND` UNSET (or `=0`). The flag
   goes in the **`famit-agent.service.d` drop-in** (`Environment=`), **NOT** the
   shared `.env` (LEARNINGS §2: a shared-.env flag leaks across services on the next
   restart). Assert the deployed file md5 == the **intended-new closure** hash from
   pre-flight step 4.
7. **Render-equality gate (the byte-identical proof, BEFORE any restart):** on the
   box, render the system prompt for a **GOLDEN CAMPAIGN** (a fixed campaign id) with
   `KERNEL_OUTBOUND` unset, via both the OLD backup and the NEW patched file; assert
   the rendered prompt strings are **md5-identical**. (The OFF branch is
   `legacy_render()` → `build_system_prompt(fields)` + appends, so this MUST match.)
8. **Restart ONLY `famit-agent`** (`systemctl restart famit-agent`). `aim-voice-agent`
   untouched.
9. **FLAG-OFF real-ring smoke:** place a real outbound test call (the founder's test
   number). Assert: opener + language + flow + closure identical to pre-deploy; TTS
   still ElevenLabs; transcript + summary + memory written as before; no new errors.
   **Earner gate AFTER:** md5 on box still == the intended-new closure hash; PIDs
   healthy; `/health` 200. This proves the patch is INERT when OFF.

### Step 2 — flag-ON canary (still synthetic, founder-only)
10. Set `KERNEL_OUTBOUND=1` in the **`famit-agent.service.d` drop-in ONLY**. Verify
    via `/proc/<famit-agent-pid>/environ` that `KERNEL_OUTBOUND=1` is present on the
    famit-agent process AND **ABSENT** from the `aim-voice-agent` process env (the
    cross-service isolation check).
11. **Restart ONLY `famit-agent`.**
12. **FLAG-ON canary (founder real outbound ring-test):** run a campaign configured
    with **ONLY the founder's own test number** as the lead list. The founder ANSWERS
    the call and JUDGES it live (a green per-component report is NOT success — only
    the founder's real call is truth). Assert: (a) the persona/flow is coherent and
    at least as good as today; (b) the correct TTS engine speaks (lean/standard →
    Sarvam Bulbul actually heard; growth/premium → EL) with `selected==actual` (any
    swap NAMED at INFO, never silent); (c) the kernel packet prefix is present in the
    debug log yet the call is natural; (d) the post-call lead-memory row is written
    under the CORRECT tenant (RLS-visible only under that tenant — NO cross-tenant
    bleed); (e) latency is within budget (RAG hard-deadline respected, no per-turn
    stall); (f) **earner gate AFTER:** md5 unchanged, PIDs healthy, `/health` 200.
13. **Hold** on the single founder canary; widen to real leads ONLY after the founder
    signs off on the real ring-test.

### Rollback (INSTANT, ready at every step)
- **Fastest:** set `KERNEL_OUTBOUND=0` in the drop-in + `systemctl restart
  famit-agent` ⇒ byte-identical to today (all helpers no-op, EL default, legacy
  prompt/opener/closure/memory). One env flip.
- **If the patched file itself is suspect:** restore `agent.py.WOUTbak.<ts>` (the
  `98655dbf` golden) + `systemctl restart famit-agent`. Re-assert md5 == `98655dbf`.
  The tracked `voice_kernel/` is inert without the flag, so it can stay.
- `aim-voice-agent` is NEVER part of any step here ⇒ inbound cannot be affected.

**Invariants enforced at every step:** one box-mutating change at a time; earner
gate (md5 `98655dbf` / PIDs / `/health` / real ring) BEFORE and AFTER; flag in the
famit-agent systemd drop-in, NOT the shared `.env`; restart ONLY `famit-agent`; the
`98655dbf` backup is the one-command revert; the founder's REAL outbound ring is the
only acceptance truth.

---

## 6. Acceptance (this design wave)

- [x] Tracked module `voice_kernel/integrations/outbound.py` written + green
  (`build_for_call` w/ `direction="outbound"` + `assemble_outbound_instructions` +
  `on_turn` + `plan_speech` + `choose_tts` + `on_tts_error` + `persist_post_call` +
  `bind_box_memory`), all fail-safe, no kernel type leaks to the agent. Mirrors the
  inbound façade 1:1.
- [x] `KERNEL_OUTBOUND` flag added to `config.py` (additive, default-OFF, outbound
  twin of `KERNEL_INBOUND`); locked by `test_outbound_flag_enables_outbound_only`;
  186 kernel tests pass.
- [x] OFF byte-identity argued (no-OFF-path-import + `instructions_provider`
  OFF==legacy invariant the W1 test covers for outbound + no per-turn calls when
  OFF) AND smoke-verified (OFF returns legacy/None, droplet-free).
- [x] Minimal agent patch specified as exact hunks (`W-INT-OUTBOUND-PATCH.md`),
  every one OFF-gated with the verbatim legacy `else`.
- [x] Outbound tenant source mapped to GROUND TRUTH: the campaign record's owner
  (`camp["tenant_id"]`, `caller.py:1458`), NOT the dispatch body; fail-closed,
  smoke-verified (blank → None, mismatch → None).
- [x] Super-gated deploy runbook for the EARNER: backup `98655dbf` + record md5,
  drift-check, intended-new-closure md5 computed first, ship voice_kernel + patched
  agent FLAG-OFF (golden-campaign render-equality + real-ring smoke), then flag-ON
  canary = FOUNDER REAL OUTBOUND RING-TEST (founder's number only, he answers +
  judges), restart `famit-agent` ONLY at deploy + canary, instant rollback
  (`KERNEL_OUTBOUND=0` + restore backup + restart). Emphasized as the MOST dangerous
  deploy; one box-mutating change; revert path always ready.

_Branch `fix/realtime-voice-kernel-v2`. No box deploy in this wave; the `agent.py`
edit + deploy is the separate founder-gated step (§5)._
