# W1 — RealtimeVoiceKernel v2 — Core Architecture & Service Contracts

> CHIEF ARCHITECT decision log for the `voice_kernel/` package: the kernel core,
> the `ContextPacket` schema, and the `typing.Protocol` service contracts that
> ALL downstream workflows (W2–W8) bind to. This is the foundation everything
> else implements against.
>
> **EARNER LAW (non-negotiable, restated):** the live outbound agent
> `droplet_work/agent.py` (md5 `9150fabe4ff62b4b4470f9a87df346e5`) stays
> byte-identical. This package NEVER edits/imports/restarts the live box during
> the build. It is a NEW git-tracked package, additive, flag-gated default-OFF.
> When `KERNEL_ENABLED=0` (default) the existing prompt assembly path is
> byte-for-byte unchanged. Branch: `fix/realtime-voice-kernel-v2`.

---

## 0. Ground truth (verified file:line, this audit)

The design is anchored to the REAL code, not assumptions:

- **Outbound static-assembly seams** — `agent.py:416` `system_prompt = build_system_prompt(fields)`,
  `agent.py:431` (variant-merge re-render), `agent.py:440` `base_instructions = system_prompt`.
  These three lines are the ONLY seams the kernel adapter must serve for outbound. (We do NOT
  edit them in this wave — they are the future G3 cutover points.)
- **Outbound per-turn seam** — `agent.py:796` `on_user_turn_completed`, `agent.py:820`
  `turn_ctx.add_message(...)` (language note). Async, cache-safe, temporary-per-turn.
- **Inbound seams (SAFE first integration target)** — `aim_voice_agent.py:1436`
  `def _build_sales_instructions(fields, recap, caller_name, is_returning, pending_disambig, campaign_options, grounding="", pg_memory="") -> str`
  (customer persona, line 1652 `super().__init__(instructions=...)`, line 1728/2565 `update_instructions(...)`),
  and `aim_voice_agent.py:581` `def _build_instructions(caller_id, is_manager, role) -> str` (manager persona).
- **The `fields` dict** (the campaign brain) keys, verified at `prompt.py:655` `GODREJ_FIELDS`:
  `company_name, agent_name, product_name, product_summary, location, price_offer, usps[],
  talking_points[], objections[{q,a}], qualifying_questions[], language, past_projects,
  appointment_options[], goal, voice_gender, disclose_ai, ai_disclosure`. The `ContextPacket.card`
  maps 1:1 to these so downstream compilers stay drop-in.
- **L0 safety content** lives at `prompt.py:179` `SHARED_RULES` (speak-in-beats, numbers-in-words,
  language-mirror, curveballs, opt-out/DND, AI-disclosure, guards). The kernel's L0 layer REUSES
  this text verbatim — it is the proven, earner-safe core; we never rewrite it.
- **Flag pattern (codebase-native):** `os.getenv("NAME", "0") in ("1", "true", "True")` —
  e.g. `agent.py:451` (`OPENER_ALREADY_SAID`). The kernel uses the IDENTICAL pattern. No new config
  framework.
- **LLM ground truth:** live model = Groq `meta-llama/llama-4-scout-17b-16e-instruct`
  (`agent.py:173/248`, env `GROQ_LLM_MODEL`). Groq prompt-caching does NOT support llama-4-scout
  today → "context packet" (smaller prompt) and "prompt caching" (a model move) are TWO INDEPENDENT
  levers. The kernel captures lever 1 now (smaller, layered, stable-prefix packet); lever 2 is a
  separate earner-gated model decision (W5/G3), not assumed here.

---

## 1. DECISION — Package location

**`C:\Users\kunal\Desktop\caps\voice_kernel\`** — a NEW, git-TRACKED Python package at repo root.

Rationale:
- **NOT inside `droplet_work/`** — that tree is broadly `.gitignored` (LEARNINGS §2: "curated
  source must be `git add -f`'d file-by-file"). The kernel must be normal tracked source so every
  workflow can commit per-unit, run CI/gitleaks, and review diffs. `voice_kernel/` is tracked
  plainly with no `git add -f` ceremony.
- **Importable at deploy time** — at the future G3 cutover the box gets a copy of `voice_kernel/`
  on its `PYTHONPATH`; the voice agents do `from voice_kernel import ...` ONLY when their flag is
  ON. During THIS build nothing imports the live `agent.py` and the live `agent.py` imports
  nothing new.
- **Pure-Python, dependency-light core** — the `voice_kernel.core` + `voice_kernel.contracts`
  modules import only stdlib (`dataclasses`, `enum`, `typing`) so they can be unit-tested with zero
  infra and can be imported by `aim_voice_agent.py` without dragging in Redis/PG/Qdrant.

### Package layout the Build phase must create

```
voice_kernel/
  __init__.py                 # exports: ContextPacket, KernelConfig, build_kernel, __version__
  contracts.py                # ALL typing.Protocol service interfaces + their dataclasses (no impls)
  packet.py                   # ContextPacket dataclass + the 6 layer dataclasses + token budget + clamps
  config.py                   # KernelConfig (reads env with the codebase-native flag pattern)
  kernel.py                   # RealtimeVoiceKernel: three-speed orchestrator + assemble_prefix/assemble_turn
  fsm.py                      # DialogueMode FSM (states, transitions, per-mode policy table)
  adapter.py                  # instructions-provider adapter: KERNEL_ENABLED OFF -> delegate to legacy
  tokens.py                   # token estimator + per-layer HARD clamp helpers
  errors.py                   # KernelError hierarchy (never silently fail)
  null_impls.py               # safe default/no-op Protocol impls (so the kernel runs before W2-W8 land)
  tests/
    test_packet_budget.py     # asserts total <= budget, per-layer caps, L0 never trimmed
    test_adapter_off_identity.py  # adapter OFF == legacy string byte-for-byte (the earner gate)
    test_fsm.py               # mode transitions + policy lookups
    test_contracts.py         # null_impls satisfy every Protocol (isinstance/structural)
  README.md                   # this contract, condensed, for downstream workflow authors
```

Downstream workflows add their own sub-packages WITHOUT touching the core:
`voice_kernel/context/` (W1 builder + W4 wiring), `voice_kernel/brain_packs/` (W2),
`voice_kernel/vendor_script/` (W3), `voice_kernel/rag/` (W4), `voice_kernel/speech/` +
`voice_kernel/routing/` (W5), `voice_kernel/policy/` (W6), `voice_kernel/memory/` (W7),
`voice_kernel/eventbus/` (W8). Each implements a Protocol from `contracts.py`.

---

## 2. DECISION — The `ContextPacket` schema (6 layers, ~1.5–3k token budget)

The packet REPLACES the ~13k-token single f-string. It is **layered, ordered most-stable-prefix
FIRST → most-volatile LAST** (the universal cache rule). Three render scopes:

- **STABLE PREFIX** = L0+L1+L2+L3 → rendered **ONCE per call**, sent byte-identical every turn.
- **PER-CALL SUFFIX** = L4 (lead memory) → rendered once per call.
- **PER-TURN SUFFIX** = L5 (turn evidence) + the rolling conversation → re-rendered each turn.

Critical rule (fixes a live bug): per-call/per-turn dynamic text (lead_name, recap, opener-said,
lang-lock, timestamps) goes in the SUFFIX, NEVER interleaved into the stable prefix. Today
`agent.py:442/452/459` append these to `base_instructions` — that would bust any prefix cache; the
kernel moves them below the cache boundary.

### Layer budget (target ≤ 2800 tokens stable+memory; +L5/turn ≤ ~400)

| Layer | Name | Scope | Cap (tokens) | Source / owner |
|-------|------|-------|--------------|----------------|
| L0 | IDENTITY + SAFETY | stable | 350 | `prompt.py SHARED_RULES` verbatim + identity (W1) |
| L1 | USE-CASE BRAIN PACK | stable | 250 | BrainPackProvider (W2) |
| L2 | INDUSTRY PACK | stable | 150 | BrainPackProvider (W2) |
| L3 | VENDOR-SCRIPT / CAMPAIGN CARD | stable | 900 | VendorScriptEngine + ContextEngine (W3) |
| L4 | LEAD MEMORY | per-call | 300 | MemoryService (W7) |
| L5 | TURN-SCOPED EVIDENCE | per-turn | 400 | RagRuntime (W4) |

Enforcement is a **HARD clamp in the builder**, not a hope (LEARNINGS §3, §6): cap each list
(`usps<=5, objections<=6, qualifying<=3, rag<=3 @ <=120c`), truncate `product_summary<=600c`,
`lead.last_call_summary<=300c`; assert `total<=budget.max_total_tokens` before send. On overflow:
**drop L5 first, then trim L4, NEVER trim L0**. The 4000-char lossy JSON extract
(`caller.py:1409-1435`) becomes this clean structured card; `GROQ_MAX_TOKENS=90`
(`agent.py:617`, an UNRELATED output guillotine) can be raised to ~160–220 only AFTER the input
packet is small — that is a W5 decision, recorded but not done here.

### The dataclasses (drives `voice_kernel/packet.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class UseCase(str, Enum):
    SALES = "sales"
    SUPPORT = "support"
    AFTER_SALES = "after_sales"
    BOOKING = "booking"
    REMINDER = "reminder"
    FEEDBACK = "feedback"
    COMPLAINT = "complaint"
    RENEWAL = "renewal"
    ONBOARDING = "onboarding"
    INBOUND = "inbound"
    AI_MANAGER = "ai_manager"


class Lifecycle(str, Enum):
    NEW = "new"
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    DEAD = "dead"


class Stage(str, Enum):
    GREET = "greet"
    PERMISSION = "permission"
    INTRO = "intro"
    QUALIFY = "qualify"
    OBJECTION = "objection"
    BOOKING = "booking"
    CLOSE = "close"
    FOLLOWUP = "followup"


@dataclass(frozen=True)
class PacketMeta:
    tenant_id: str
    campaign_id: str
    call_id: str
    room: str
    lead_phone: str = ""
    locale: str = "hi-IN"
    agent_gender: str = "female"
    ts_iso: str = ""
    packet_version: str = "1"
    direction: str = "outbound"          # outbound | inbound


@dataclass(frozen=True)
class IdentityLayer:                       # L0 — static, byte-identical forever
    agent_name: str
    company_name: str
    disclose_ai: bool = True
    ai_disclosure_str: str = ""
    safety_rules: str = ""                 # SHARED_RULES verbatim from prompt.py


@dataclass(frozen=True)
class ModeLayer:                           # L1 — use-case brain pack ref
    use_case: UseCase
    objective_str: str = ""
    success_criteria: str = ""
    brain_pack_id: str = ""                # pointer resolved by BrainPackProvider


@dataclass(frozen=True)
class IndustryLayer:                       # L2
    pack_id: str = ""
    vertical_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Objection:
    q: str
    a: str


@dataclass(frozen=True)
class CampaignCard:                        # L3 — structured persona+facts (NOT raw 4k brief)
    product_name: str = ""
    product_summary: str = ""              # <= 600 chars (clamped)
    location: str = ""
    landmark: str = ""
    price_offer: str = ""
    usps: tuple[str, ...] = ()             # <= 5
    talking_points: tuple[str, ...] = ()   # <= 5
    qualifying_questions: tuple[str, ...] = ()  # <= 3
    objections: tuple[Objection, ...] = () # <= 6
    negotiation_ladder: tuple[str, ...] = ()
    closing_lines: tuple[str, ...] = ()
    escalation_rules: str = ""
    raw_script_ref: str = ""               # POINTER to the full brief, never inlined
    tone: str = ""
    greeting: str = ""
    language: str = "Hinglish"
    do: tuple[str, ...] = ()
    dont: tuple[str, ...] = ()


@dataclass(frozen=True)
class LeadMemory:                          # L4 — structured facts, NOT transcript replay
    name: str = ""
    lifecycle: Lifecycle = Lifecycle.NEW
    last_call_summary: str = ""            # <= 300 chars (clamped)
    open_commitments: tuple[str, ...] = ()
    preferred_callback_ts: str = ""
    do_not_mention: tuple[str, ...] = ()


@dataclass(frozen=True)
class RagSnippet:
    source: str
    text: str                              # <= 120 chars (clamped)


@dataclass(frozen=True)
class TurnLayer:                           # L5 — per-turn, the only thing that changes each turn
    stage: Stage = Stage.GREET
    rag_snippets: tuple[RagSnippet, ...] = ()   # <= 3
    detected_lang: str = ""
    barge_in_hint: str = ""


@dataclass(frozen=True)
class TokenBudget:
    max_total_tokens: int = 2800
    l0_cap: int = 350
    l1_cap: int = 250
    l2_cap: int = 150
    l3_cap: int = 900
    l4_cap: int = 300
    l5_cap: int = 400


@dataclass(frozen=True)
class ContextPacket:
    meta: PacketMeta
    identity: IdentityLayer
    mode: ModeLayer
    industry: IndustryLayer
    card: CampaignCard
    lead: LeadMemory
    turn: TurnLayer
    budget: TokenBudget = field(default_factory=TokenBudget)

    # render scopes — the kernel calls these; downstream never re-implements them
    def render_stable_prefix(self) -> str: ...   # L0..L3, once/call, byte-identical/turn
    def render_call_suffix(self) -> str: ...     # L4, once/call
    def render_turn_suffix(self) -> str: ...      # L5 + dynamic (lead_name/recap/opener/lang)
    def token_estimate(self) -> int: ...
    def clamp(self) -> "ContextPacket": ...       # returns a budget-enforced copy
```

`ContextPacket` is **PURE** (frozen, no global state, same input → same output) so the
double-render at `agent.py:416`+`431` is safe (LEARNINGS: builder must be idempotent).

---

## 3. DECISION — Service Protocols (the contracts W2–W8 implement)

`voice_kernel/contracts.py` defines `typing.Protocol` interfaces ONLY — signatures + dataclasses,
**no implementations**. Downstream workflows ship implementations; the kernel depends only on the
Protocol. `null_impls.py` ships safe defaults so the kernel runs end-to-end before any workflow
lands (LEARNINGS §5: never ship a dormant placeholder that the founder can't run — the null impls
are real, return valid empty layers, and are explicitly logged as "null", never silently `pass`).

```python
from __future__ import annotations
from typing import Protocol, Optional, runtime_checkable
from dataclasses import dataclass

from voice_kernel.packet import (
    ContextPacket, IdentityLayer, ModeLayer, IndustryLayer, CampaignCard,
    LeadMemory, TurnLayer, PacketMeta, UseCase, Stage,
)


# ---- request/result dataclasses shared by the contracts ----------------------

@dataclass(frozen=True)
class CallContext:
    """Everything known at dial time (the WARM-path seed)."""
    meta: PacketMeta
    fields: dict                      # the live campaign `fields` dict (prompt.py shape)
    fields_override: Optional[dict] = None   # A/B variant merge (agent.py:426)
    recap: str = ""                   # legacy recap string (back-compat)


@dataclass(frozen=True)
class TurnContext:
    """Per-turn signal from the HOT path."""
    call_id: str
    user_text: str
    detected_lang: str = ""
    stage: Stage = Stage.GREET
    history_len: int = 0


@dataclass(frozen=True)
class SpeechPlan:
    """Speech Planner output: normalized, beat-segmented text + TTS hints."""
    text: str
    tts_lang: str = ""
    segments: tuple[str, ...] = ()
    normalized: bool = True


@dataclass(frozen=True)
class ProviderChoice:
    stt: str = "sarvam"
    llm: str = "groq"
    tts: str = "elevenlabs"           # provider-lock resolved here
    llm_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    reason: str = ""


@dataclass(frozen=True)
class Event:
    name: str
    call_id: str
    tenant_id: str
    ts_iso: str
    payload: dict


# ---- the nine service contracts ---------------------------------------------

@runtime_checkable
class ContextEngine(Protocol):
    """Compiles the live `fields` dict + variant override into the L3 CampaignCard
    and assembles the full ContextPacket. Owner: W1 (builder) + W3 (card compiler)."""
    def build_card(self, ctx: CallContext) -> CampaignCard: ...
    def build_packet(self, ctx: CallContext) -> ContextPacket: ...


@runtime_checkable
class VendorScriptEngine(Protocol):
    """Treats the vendor script as the authoritative blueprint; returns the
    stage-relevant excerpt for L3. Owner: W3."""
    def stage_excerpt(self, campaign_id: str, stage: Stage, max_chars: int = 600) -> str: ...
    def card_overrides(self, campaign_id: str) -> dict: ...   # script-driven card fields


@runtime_checkable
class BrainPackProvider(Protocol):
    """Resolves use-case (L1) and industry (L2) packs. Owner: W2."""
    def use_case_layer(self, use_case: UseCase, fields: dict) -> ModeLayer: ...
    def industry_layer(self, fields: dict) -> IndustryLayer: ...


@runtime_checkable
class RagRuntime(Protocol):
    """Stage-aware retrieval for L5, injected per-turn (on_user_turn_completed seam).
    Owner: W4. MUST be fast (<50ms hot-cache) and degrade to empty, never block."""
    async def precompute(self, ctx: CallContext) -> None: ...        # WARM: warm the room cache at dial
    async def retrieve(self, turn: TurnContext, k: int = 3) -> TurnLayer: ...


@runtime_checkable
class SpeechPlanner(Protocol):
    """Normalizes numbers/dates/currency, casual Hindi, complete sentences, beats.
    Owner: W5. The mandatory HOT-path step between LLM and TTS."""
    def plan(self, raw_text: str, lang: str, mode_card: CampaignCard) -> SpeechPlan: ...


@runtime_checkable
class ProviderRouter(Protocol):
    """Hard provider routing for STT/LLM/TTS (preview+live+usage+billing, fail-loud).
    Owner: W5. Fixes the Sarvam-silence default and the FallbackAdapter pool."""
    def resolve(self, ctx: CallContext) -> ProviderChoice: ...
    def on_error(self, provider: str, code: int) -> ProviderChoice: ...  # 429 vs 400 aware


@runtime_checkable
class MemoryService(Protocol):
    """Structured lead memory (L4): read ONE row at dial, write summary post-call.
    Owner: W7. Postgres-backed, tenant-RLS-isolated. NOT transcript replay."""
    async def load(self, tenant_id: str, lead_phone: str) -> LeadMemory: ...
    async def persist(self, tenant_id: str, lead_phone: str, summary: LeadMemory) -> None: ...


@runtime_checkable
class EventBus(Protocol):
    """Redis-Streams event backbone. Owner: W8. emit must never block the dial loop
    (fire-and-forget, own timeouts) — LEARNINGS §4."""
    async def emit(self, event: Event) -> None: ...
    async def subscribe(self, stream: str, group: str): ...    # -> async iterator of Event


@runtime_checkable
class DialoguePolicy(Protocol):
    """Per-mode dialogue policy: given the FSM state + turn, return the stage,
    objective nudge, and whether to veto/abort generation. Owner: W6."""
    def next_stage(self, current: Stage, turn: TurnContext, use_case: UseCase) -> Stage: ...
    def turn_directive(self, stage: Stage, use_case: UseCase) -> str: ...
    def should_abort(self, turn: TurnContext) -> bool: ...   # StopResponse() veto hook
```

Every method that touches I/O (RAG, Memory, EventBus) is `async`; the pure compilers
(ContextEngine card build, BrainPack, SpeechPlanner, ProviderRouter, DialoguePolicy) are sync so
they can run on the HOT path without an await. `null_impls.py` provides a structurally-conformant
no-op for each, so `RealtimeVoiceKernel` constructs and runs with zero downstream workflows landed.

---

## 4. DECISION — Three-speed orchestration + Dialogue-mode FSM

### Three-speed shape (`voice_kernel/kernel.py`)

```
HOT  (live speech, per-turn, must be tiny & sync where possible):
     STT-final -> DialoguePolicy.next_stage -> RagRuntime.retrieve (L5) ->
     packet.render_turn_suffix -> LLM -> SpeechPlanner.plan -> TTS -> playback
WARM (parallel, while the user speaks / at dial, never on the critical reply path):
     MemoryService.load (L4) -> ContextEngine.build_card (L3) ->
     VendorScriptEngine + BrainPackProvider (L1/L2) -> RagRuntime.precompute ->
     render_stable_prefix (cache ONCE) + render_call_suffix
COLD (post-call, async, cheap model):
     transcript -> MemoryService.persist (summary) -> RAG index -> EventBus analytics
```

The kernel exposes exactly two assembly entry points (so the agents stay thin):
- `assemble_prefix(ctx: CallContext) -> str` — WARM, once per call. Returns the stable prefix +
  call suffix. This is what the inbound adapter feeds into `instructions=`.
- `assemble_turn(turn: TurnContext) -> str | None` — HOT, per turn. Returns the L5 turn suffix to
  append via `turn_ctx.add_message` (or `None` = nothing to add). This maps onto the existing
  `on_user_turn_completed` seam (`agent.py:820`) and is cache-safe (appended after the cached prefix).

### Dialogue-mode FSM (`voice_kernel/fsm.py`)

States = `Stage` enum (greet → permission → intro → qualify → objection → booking → close →
followup). The FSM is **mode-parameterized by `UseCase`**: each use-case has a policy table giving
(a) the allowed transitions and (b) the per-stage `turn_directive`. Examples:

| UseCase | Skips | Terminal goal |
|---------|-------|---------------|
| SALES | — | booking/close |
| SUPPORT | permission, booking | resolution/followup |
| BOOKING | objection | confirmed slot |
| REMINDER | qualify, objection | acknowledgement |
| INBOUND | permission (they called us) | warmly help → book/transfer |

`DialoguePolicy` (W6) owns the table; the FSM in core just drives transitions and looks up the
directive. The supervisor can `should_abort` a preemptive generation via `StopResponse()` in the
turn node (RESEARCH gotcha: preemptive generation is ON by default in livekit-agents 1.6.1 — the
veto must happen in `on_user_turn_completed` and be FAST).

---

## 5. DECISION — Flag plan + OFF-is-identity adapter

**Flag: `KERNEL_ENABLED`** (default `"0"`), read with the codebase-native pattern
`os.getenv("KERNEL_ENABLED", "0") in ("1", "true", "True")`. Plus per-surface scoping flags so
inbound can be enabled WITHOUT touching the earner:
- `KERNEL_ENABLED` — master switch (default OFF).
- `KERNEL_INBOUND` — enable on `aim_voice_agent.py` only (default OFF).
- `KERNEL_OUTBOUND_SHADOW` — outbound shadow-compute only, never replaces the string (default OFF).

The inbound flag is scoped via the systemd drop-in `Environment=` on `aim-voice-agent.service.d`
so it CANNOT leak to the earner's `.env` (LEARNINGS §2: inbound flags in the shared `.env` leak to
the outbound earner on its next restart — prove via `/proc/<pid>/environ`).

### The adapter (`voice_kernel/adapter.py`) — the byte-identical guarantee

```python
def instructions_provider(legacy_render, ctx: CallContext, *, cfg: KernelConfig) -> str:
    """The ONE seam the voice agents call. When the kernel is OFF it returns the EXACT
    legacy string (the agent's own build_system_prompt/_build_sales_instructions output),
    so the call is byte-for-byte identical. When ON it returns the kernel packet prefix.

    `legacy_render` is a zero-arg callable the AGENT passes that produces today's string,
    so the kernel never imports the agent and the agent never changes its own logic."""
    if not cfg.enabled_for(ctx.meta.direction):
        return legacy_render()                      # <- OFF: identical to today
    try:
        return build_kernel(cfg).assemble_prefix(ctx)
    except Exception as exc:                          # never silently fail (LEARNINGS §1)
        log.warning("kernel assemble failed, falling back to legacy: %r", exc)
        return legacy_render()                       # safe fallback == today's behavior
```

`tests/test_adapter_off_identity.py` asserts `instructions_provider(legacy, ctx, cfg=OFF) ==
legacy()` byte-for-byte across a matrix of fields (default, variant-override, recap-present,
opener-said) — this is the unit-level earner gate. The box-level gate stays the prompt GOLDEN
byte-diff (`_golden/verify_golden.py`) run ON THE BOX at G3 (LEARNINGS §1/§7).

---

## 6. DECISION — Integration plan (inbound first, outbound via shadow + G3)

1. **INBOUND first (lower risk, proves the kernel).** W-integration wave wraps
   `aim_voice_agent.py:1436 _build_sales_instructions` (and `:581 _build_instructions`) by passing
   their existing output as the `legacy_render` callable into `instructions_provider`, gated by
   `KERNEL_INBOUND`. OFF = the inbound agent is byte-identical to today; ON = the kernel packet
   serves the instructions. This NEVER touches `agent.py`, trunks, firewall, or SIP.
2. **OUTBOUND shadow (no behavior change).** Under `KERNEL_OUTBOUND_SHADOW`, a sidecar computes the
   kernel packet for outbound calls and logs the byte-diff vs `build_system_prompt(fields)` for
   observability — but `agent.py:440 base_instructions` keeps using the legacy string. agent.py
   stays byte-identical (we do not edit lines 416/431/440 in this wave; shadow runs in a separate
   tracked sidecar reading dispatch metadata, not inside agent.py).
3. **OUTBOUND live cutover = G3 only (human-gated, one box-change).** Replace `agent.py:416/431`
   with `instructions_provider(...)` ONLY after: inbound proven live + the GOLDEN byte-diff passes
   5/5 flag-OFF on the box + an integrated turn-loop smoke + a founder ring-test. That edit is a
   future, separate, founder-signed deploy — explicitly OUT OF SCOPE for this build wave.

---

## 7. The files the Build phase must create (exhaustive)

| File | Purpose |
|------|---------|
| `voice_kernel/__init__.py` | exports `ContextPacket, KernelConfig, build_kernel, __version__` |
| `voice_kernel/packet.py` | the 6 layer dataclasses + `ContextPacket` + budget + clamp + render scopes |
| `voice_kernel/contracts.py` | the 9 `typing.Protocol` interfaces + their request/result dataclasses |
| `voice_kernel/config.py` | `KernelConfig` (env flags, codebase-native pattern, `enabled_for(direction)`) |
| `voice_kernel/kernel.py` | `RealtimeVoiceKernel` + `build_kernel()` + `assemble_prefix`/`assemble_turn` |
| `voice_kernel/fsm.py` | `DialogueMode` FSM (Stage states, per-UseCase policy table) |
| `voice_kernel/adapter.py` | `instructions_provider` — the OFF-is-identity seam |
| `voice_kernel/tokens.py` | token estimator + per-layer HARD clamp helpers |
| `voice_kernel/errors.py` | `KernelError` hierarchy (never silently fail) |
| `voice_kernel/null_impls.py` | conformant no-op impls of all 9 Protocols (kernel runs before W2–W8) |
| `voice_kernel/tests/test_packet_budget.py` | total<=budget, per-layer caps, L0 never trimmed |
| `voice_kernel/tests/test_adapter_off_identity.py` | OFF == legacy byte-for-byte (unit earner gate) |
| `voice_kernel/tests/test_fsm.py` | transitions + policy lookups per use-case |
| `voice_kernel/tests/test_contracts.py` | null_impls satisfy every Protocol (runtime_checkable) |
| `voice_kernel/README.md` | condensed contract for downstream workflow authors |

**Build DoD:** `python -m pytest voice_kernel/tests -q` green; `test_adapter_off_identity` proves
OFF-identity; zero imports of `droplet_work/agent.py`; `agent.py` md5 unchanged
(`9150fabe4ff62b4b4470f9a87df346e5`); committed per-unit on `fix/realtime-voice-kernel-v2` with
gitleaks 0.

---

## 8. Contract list (the binding surface for W2–W8)

- **ContextEngine** ← W1 builder + W3 card compiler
- **VendorScriptEngine** ← W3
- **BrainPackProvider** ← W2
- **RagRuntime** ← W4
- **SpeechPlanner** ← W5
- **ProviderRouter** ← W5
- **MemoryService** ← W7
- **EventBus** ← W8
- **DialoguePolicy** ← W6

All nine are defined in `voice_kernel/contracts.py`; each downstream wave imports its Protocol,
ships an impl, and registers it via `build_kernel(cfg, **impls)`. Until a wave lands, the kernel
uses the corresponding `null_impls` default (logged as null, never a silent no-op).
