"""voice_kernel.contracts — the typing.Protocol service interfaces (no impls).

These are the BINDING SURFACE that downstream workflows W2–W8 implement. The
kernel depends ONLY on these Protocols; it never imports a concrete service.
`null_impls.py` ships structurally-conformant no-ops so the kernel runs
end-to-end before any workflow lands.

Async vs sync (deliberate, arch §3): everything that touches I/O (RagRuntime,
MemoryService, EventBus) is `async`. The pure compilers (ContextEngine card
build, BrainPackProvider, SpeechPlanner, ProviderRouter, DialoguePolicy) are
SYNC so they can run on the HOT path without an await.

All Protocols are `@runtime_checkable` so `test_contracts.py` can assert the
null impls conform via `isinstance`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Optional, Protocol, runtime_checkable

from .errors import TenantIdentityError
from .packet import (
    CampaignCard,
    ContextPacket,
    IndustryLayer,
    LeadMemory,
    ModeLayer,
    PacketMeta,
    Stage,
    TurnLayer,
    UseCase,
)


# --------------------------------------------------------------------------- #
# C2 — TENANT IDENTITY (fail-closed, server-stamped, immutable)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class KernelSession:
    """The immutable, SERVER-STAMPED tenant identity for one call (W18 C2).

    `tenant_id` + `call_id` are MANDATORY and non-empty — the kernel refuses to
    run a call without them. This object is stamped server-side from the resolved
    campaign owner (`get_campaign_for(cid, tenant)` shape), NEVER from a
    caller-supplied dispatch body — that is the whole point: a guessed/forged
    `campaign_id` in the body cannot smuggle in a tenant.

    Frozen = immutable: once stamped it cannot be mutated downstream. Every
    service Protocol that needs tenant scoping (RagRuntime, MemoryService,
    EventBus, ContextEngine, BrainPackProvider) receives this session, so none of
    them can operate cross-tenant by accident.

    Fail-closed: an empty/missing `tenant_id` or `call_id` raises
    TenantIdentityError at construction. The orchestrator additionally asserts
    `session.tenant_id == campaign.tenant_id` before assembling — a mismatch is a
    hard hang-up, not a warning.
    """

    tenant_id: str
    call_id: str
    direction: str = "outbound"  # outbound | inbound (mirrors PacketMeta.direction)
    stamped_by: str = "server"  # provenance marker; never "caller_body"

    def __post_init__(self) -> None:
        if not (self.tenant_id or "").strip():
            raise TenantIdentityError("KernelSession.tenant_id is required (server-stamped, fail-closed)")
        if not (self.call_id or "").strip():
            raise TenantIdentityError("KernelSession.call_id is required (server-stamped, fail-closed)")

    def assert_matches_campaign(self, campaign_tenant_id: str) -> None:
        """Fail-closed cross-check: the session tenant MUST equal the campaign's
        owning tenant. A mismatch (or a missing campaign tenant) is a hard
        refusal — the call must hang up, never serve a cross-tenant packet."""
        ct = (campaign_tenant_id or "").strip()
        if not ct:
            raise TenantIdentityError(
                f"campaign has no tenant_id to verify against session "
                f"{self.tenant_id!r} — refusing (fail-closed)"
            )
        if ct != self.tenant_id:
            raise TenantIdentityError(
                f"tenant mismatch: session={self.tenant_id!r} != campaign={ct!r} — "
                f"refusing cross-tenant assembly (call must hang up)"
            )


# --------------------------------------------------------------------------- #
# request/result dataclasses shared by the contracts
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CallContext:
    """Everything known at dial time (the WARM-path seed).

    `session` (C2) is the server-stamped tenant identity. It is OPTIONAL on the
    dataclass ONLY so the OFF / shadow / legacy paths that never enter the kernel
    orchestrator can still construct a CallContext. The kernel's ON entry points
    REQUIRE it (fail-closed) — see RealtimeVoiceKernel._require_session.
    """

    meta: PacketMeta
    fields: dict  # the live campaign `fields` dict (prompt.py shape)
    fields_override: Optional[dict] = None  # A/B variant merge (agent.py:426)
    recap: str = ""  # legacy recap string (back-compat)
    session: Optional[KernelSession] = None  # C2 server-stamped tenant identity


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
    tts: str = "elevenlabs"
    llm_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    reason: str = ""


@dataclass(frozen=True)
class Event:
    name: str
    call_id: str
    tenant_id: str
    ts_iso: str
    payload: dict


# --------------------------------------------------------------------------- #
# the nine service contracts
# --------------------------------------------------------------------------- #
@runtime_checkable
class ContextEngine(Protocol):
    """Compiles the live `fields` dict + variant override into the L3
    CampaignCard and assembles the full ContextPacket. Owner: W1 + W3."""

    def build_card(self, ctx: CallContext) -> CampaignCard: ...

    def build_packet(self, ctx: CallContext) -> ContextPacket: ...


@runtime_checkable
class VendorScriptEngine(Protocol):
    """Treats the vendor script as the authoritative blueprint; returns the
    stage-relevant excerpt for L3. Owner: W3."""

    def stage_excerpt(self, campaign_id: str, stage: Stage, max_chars: int = 600) -> str: ...

    def card_overrides(self, campaign_id: str) -> dict: ...


@runtime_checkable
class BrainPackProvider(Protocol):
    """Resolves use-case (L1) and industry (L2) packs. Owner: W2."""

    def use_case_layer(self, use_case: UseCase, fields: dict) -> ModeLayer: ...

    def industry_layer(self, fields: dict) -> IndustryLayer: ...


@runtime_checkable
class RagRuntime(Protocol):
    """Stage-aware retrieval for L5, injected per-turn. Owner: W4.

    MUST be fast and degrade to empty, never block. `retrieve` carries an
    explicit `timeout_s` and the documented guarantee: on timeout / error it
    returns an EMPTY TurnLayer rather than raising. The kernel NEVER awaits this
    before starting the LLM (red-team latency fix) — it runs parallel to the
    preemptive LLM start and is appended only if it returns within deadline.
    """

    async def precompute(self, ctx: CallContext) -> None: ...  # WARM: warm room cache at dial

    async def retrieve(self, turn: TurnContext, k: int = 3, timeout_s: float = 0.03) -> TurnLayer: ...


@runtime_checkable
class SpeechPlanner(Protocol):
    """Normalizes numbers/dates/currency, casual Hindi, complete sentences,
    beats. Owner: W5. The mandatory HOT-path step between LLM and TTS."""

    def plan(self, raw_text: str, lang: str, mode_card: CampaignCard) -> SpeechPlan: ...


@runtime_checkable
class ProviderRouter(Protocol):
    """Hard provider routing for STT/LLM/TTS (fail-loud). Owner: W5."""

    def resolve(self, ctx: CallContext) -> ProviderChoice: ...

    def on_error(self, provider: str, code: int) -> ProviderChoice: ...  # 429 vs 400 aware


@runtime_checkable
class MemoryService(Protocol):
    """Structured lead memory (L4): read ONE row at dial, write summary
    post-call. Owner: W7. Postgres-backed, tenant-RLS-isolated."""

    async def load(self, tenant_id: str, lead_phone: str) -> LeadMemory: ...

    async def persist(self, tenant_id: str, lead_phone: str, summary: LeadMemory) -> None: ...


@runtime_checkable
class EventBus(Protocol):
    """Redis-Streams event backbone. Owner: W8. `emit` must never block the
    dial loop (fire-and-forget, own timeouts) — LEARNINGS §4."""

    async def emit(self, event: Event) -> None: ...

    async def subscribe(self, stream: str, group: str) -> AsyncIterator[Event]: ...


@runtime_checkable
class DialoguePolicy(Protocol):
    """Per-mode dialogue policy. Owner: W6. Pure + sync (HOT-path safe)."""

    def next_stage(self, current: Stage, turn: TurnContext, use_case: UseCase) -> Stage: ...

    def turn_directive(self, stage: Stage, use_case: UseCase) -> str: ...

    def should_abort(self, turn: TurnContext) -> bool: ...  # StopResponse() veto hook
