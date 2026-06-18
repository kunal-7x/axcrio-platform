"""voice_kernel.packet — the ContextPacket schema + the layered builder.

This REPLACES the ~13k-token single f-string with a layered, ordered, budgeted
packet (W1-KERNEL-ARCH §2). Ordered most-stable-prefix FIRST → most-volatile
LAST (the universal prompt-cache rule):

    STABLE PREFIX = L0+L1+L2+L3   -> rendered ONCE per call, byte-identical/turn
    PER-CALL SUFFIX = L4          -> rendered once per call (lead memory)
    PER-TURN SUFFIX = L5 + dynamic -> re-rendered each turn (turn evidence)

Critical rule (fixes a live cache bug): per-call/per-turn dynamic text
(lead_name, recap, opener-said, lang-lock) goes in the SUFFIX, NEVER interleaved
into the stable prefix.

The packet is PURE (frozen dataclasses, same input → same output) so the
double-render at agent.py:416+431 is idempotent.

Pure-stdlib only (dataclasses/enum/typing) — import-safe for aim_voice_agent.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional

from .errors import BudgetExceededError, ClampError
from .tokens import clamp_chars, clamp_list, estimate_tokens


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# C3 — ONE TRUST BOUNDARY (structural, by position)
# --------------------------------------------------------------------------- #
# Every text source that reaches the prompt has a trust level. PLATFORM text
# (identity + safety rules we author) is trusted. EVERYTHING ELSE — the campaign
# brief a vendor uploads, knowledge retrieved from RAG/PDF, lead memory written
# by a prior (possibly poisoned) call, and the live caller utterance — is
# UNTRUSTED and must be carried as FencedText so the renderer can wrap it in a
# typed fence and keep the PLATFORM safety/identity layer ABOVE it BY POSITION.
# This replaces "safety is a stated priority sentence" with "safety is the first
# thing in the prompt and untrusted content is structurally fenced below it".


class SourceTrust(str, Enum):
    """Trust level of a text source, highest → lowest. Ordering is by position:
    PLATFORM renders FIRST (top, most authoritative); everything below it is
    fenced and explicitly marked data-not-instructions."""

    PLATFORM = "platform"  # we authored it (identity + SHARED_RULES safety) — trusted
    CAMPAIGN_BRIEF = "campaign_brief"  # vendor-uploaded brief/card text — UNTRUSTED
    RETRIEVED_KNOWLEDGE = "retrieved_knowledge"  # RAG / PDF snippets — UNTRUSTED
    LEAD_MEMORY = "lead_memory"  # prior-call summary — UNTRUSTED (may be poisoned)
    CALLER_UTTERANCE = "caller_utterance"  # live mic / STT — UNTRUSTED


# The fence tag each untrusted trust level renders inside. PLATFORM is never
# fenced (it is the authority); the rest are wrapped so the model treats their
# contents as DATA, never as instructions (W18 C3 / H12).
_FENCE_TAG: dict[SourceTrust, str] = {
    SourceTrust.CAMPAIGN_BRIEF: "campaign_brief",
    SourceTrust.RETRIEVED_KNOWLEDGE: "retrieved_knowledge",
    SourceTrust.LEAD_MEMORY: "lead_memory",
    SourceTrust.CALLER_UTTERANCE: "caller_utterance",
}


@dataclass(frozen=True)
class FencedText:
    """A typed fence wrapper around an UNTRUSTED text source (W18 C3).

    Downstream layers (W3 campaign brief, W4 RAG, W7 lead memory, live mic) MUST
    carry untrusted text as FencedText so it cannot be forgotten — the type
    itself is the reminder. `render()` wraps the content in its typed fence tag;
    the packet renderer guarantees the PLATFORM safety layer sits ABOVE every
    FencedText by prompt position.
    """

    trust: SourceTrust
    content: str
    label: str = ""  # optional human label, e.g. the RAG source name

    def render(self) -> str:
        body = (self.content or "").strip()
        if not body:
            return ""
        tag = _FENCE_TAG.get(self.trust, "untrusted")
        head = f"<{tag}>" if not self.label else f"<{tag} source=\"{self.label}\">"
        # The fence body is DATA, never instructions — say so once, structurally.
        return f"{head}\n{body}\n</{tag}>"


def fence(trust: SourceTrust, content: str, label: str = "") -> FencedText:
    """The helper W3/W4/W7 (and the live-mic seam) call so they CANNOT forget to
    fence untrusted text. Always returns a FencedText; refuses to fence PLATFORM
    content (that is the authority and is never wrapped)."""
    if trust == SourceTrust.PLATFORM:
        raise ClampError("fence(): PLATFORM text is the authority and is never fenced")
    return FencedText(trust=trust, content=content or "", label=label or "")


# --------------------------------------------------------------------------- #
# Layer dataclasses
# --------------------------------------------------------------------------- #
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
    direction: str = "outbound"  # outbound | inbound


@dataclass(frozen=True)
class IdentityLayer:  # L0 — static, byte-identical forever
    agent_name: str
    company_name: str
    disclose_ai: bool = True
    ai_disclosure_str: str = ""
    safety_rules: str = ""  # SHARED_RULES verbatim from prompt.py


@dataclass(frozen=True)
class ModeLayer:  # L1 — use-case brain pack ref
    use_case: UseCase = UseCase.SALES
    objective_str: str = ""
    success_criteria: str = ""
    brain_pack_id: str = ""


@dataclass(frozen=True)
class IndustryLayer:  # L2
    pack_id: str = ""
    vertical_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Objection:
    q: str
    a: str


@dataclass(frozen=True)
class CampaignCard:  # L3 — structured persona+facts (NOT the raw 4k brief)
    product_name: str = ""
    # product_summary is the in-prompt summary (kept small for latency). H13:
    # RETRIEVAL-OVER-TRUNCATION — we no longer LOSE the overflow. The full text
    # lives in `full_product_summary` (carried losslessly) and `summary_overflow`
    # flags that more is retrievable via `raw_script_ref` (W3/W4 recall on demand).
    product_summary: str = ""  # the small in-prompt summary (soft cap, NOT lossy)
    full_product_summary: str = ""  # LOSSLESS full text (never clamped); W4 indexes it
    summary_overflow: bool = False  # True if product_summary was shortened for the prompt
    usps_overflow: bool = False  # True if some USPs were held back for retrieval
    location: str = ""
    landmark: str = ""
    price_offer: str = ""
    usps: tuple[str, ...] = ()  # in-prompt subset (soft cap); full set retrievable
    full_usps: tuple[str, ...] = ()  # LOSSLESS full list (never clamped)
    talking_points: tuple[str, ...] = ()  # <= 5
    qualifying_questions: tuple[str, ...] = ()  # <= 3
    objections: tuple[Objection, ...] = ()  # <= 6
    negotiation_ladder: tuple[str, ...] = ()
    closing_lines: tuple[str, ...] = ()
    escalation_rules: str = ""
    raw_script_ref: str = ""  # POINTER to the full brief, never inlined
    tone: str = ""
    greeting: str = ""
    language: str = "Hinglish"
    do: tuple[str, ...] = ()
    dont: tuple[str, ...] = ()


@dataclass(frozen=True)
class LeadMemory:  # L4 — structured facts, NOT transcript replay
    name: str = ""
    lifecycle: Lifecycle = Lifecycle.NEW
    last_call_summary: str = ""  # <= 300 chars (clamped)
    open_commitments: tuple[str, ...] = ()
    preferred_callback_ts: str = ""
    do_not_mention: tuple[str, ...] = ()


@dataclass(frozen=True)
class RagSnippet:
    source: str
    text: str  # <= 120 chars (clamped)


@dataclass(frozen=True)
class TurnLayer:  # L5 — per-turn, the only thing that changes each turn
    stage: Stage = Stage.GREET
    rag_snippets: tuple[RagSnippet, ...] = ()  # <= 3
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


# Per-field char clamps (from the arch doc §2). Centralised so both the WARM
# builder and the per-turn assembler use the SAME caps.
_PRODUCT_SUMMARY_CHARS = 600
_LAST_CALL_SUMMARY_CHARS = 300
_RAG_TEXT_CHARS = 120
_USPS_MAX = 5
_TALKING_MAX = 5
_QUALIFYING_MAX = 3
_OBJECTIONS_MAX = 6
_RAG_MAX = 3


# --------------------------------------------------------------------------- #
# The packet
# --------------------------------------------------------------------------- #
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

    # -- per-layer renderers (composed by the scopes below) ---------------- #
    #
    # C3 trust boundary: L0 (identity + SHARED_RULES safety) is PLATFORM — it is
    # rendered FIRST, at the very top, and is the authority. L3 campaign card,
    # L4 lead memory and L5 RAG/turn are UNTRUSTED — they are wrapped in typed
    # fences (FencedText) and ALWAYS positioned BELOW the platform layer. Safety
    # is established by PROMPT POSITION, not by a "this is high priority" line.

    def _render_platform_layer(self) -> str:
        """L0 — IDENTITY + SAFETY (PLATFORM, trusted, never fenced, never trimmed,
        ALWAYS first). This is the structural safety boundary (C3/H12)."""
        ident = self.identity
        out: list[str] = [
            f"You are {ident.agent_name}, calling on behalf of {ident.company_name}."
        ]
        if ident.disclose_ai and ident.ai_disclosure_str:
            out.append(ident.ai_disclosure_str)
        if ident.safety_rules:
            out.append(ident.safety_rules)
        return "\n\n".join(p for p in out if p)

    def _render_mode_industry(self) -> str:
        """L1 + L2 — use-case objective + industry vertical terms. PLATFORM-tier
        (we author these from the brain packs) and CAMPAIGN-STABLE, so they sit
        ABOVE the cache boundary with L0 (H13)."""
        out: list[str] = []
        m = self.mode
        if m.objective_str:
            out.append(f"OBJECTIVE: {m.objective_str}")
        if m.success_criteria:
            out.append(f"SUCCESS: {m.success_criteria}")
        ind = self.industry
        if ind.vertical_terms:
            out.append("VERTICAL TERMS: " + ", ".join(ind.vertical_terms))
        return "\n\n".join(p for p in out if p)

    def _render_card_body(self) -> str:
        """L3 campaign-card fields as a single block (NO fence tag here — the
        caller fences it). This is the VOLATILE, vendor-supplied content that
        sits BELOW the cache boundary (H13)."""
        c = self.card
        card_lines: list[str] = []
        if c.product_name:
            card_lines.append(f"PRODUCT: {c.product_name}")
        if c.product_summary:
            card_lines.append(f"ABOUT: {c.product_summary}")
            if c.summary_overflow and c.raw_script_ref:
                card_lines.append(
                    f"(More product detail is available on request — recall from {c.raw_script_ref}.)"
                )
        if c.location:
            loc = c.location + (f" (near {c.landmark})" if c.landmark else "")
            card_lines.append(f"LOCATION: {loc}")
        if c.price_offer:
            card_lines.append(f"OFFER: {c.price_offer}")
        if c.usps:
            card_lines.append("USPS: " + "; ".join(c.usps))
            if c.usps_overflow and c.raw_script_ref:
                card_lines.append(
                    f"(Additional USPs are available on request — recall from {c.raw_script_ref}.)"
                )
        if c.talking_points:
            card_lines.append("TALKING POINTS: " + "; ".join(c.talking_points))
        if c.qualifying_questions:
            card_lines.append("QUALIFY: " + " | ".join(c.qualifying_questions))
        if c.objections:
            obj = " | ".join(f"Q:{o.q} A:{o.a}" for o in c.objections)
            card_lines.append("OBJECTIONS: " + obj)
        if c.negotiation_ladder:
            card_lines.append("NEGOTIATION: " + " -> ".join(c.negotiation_ladder))
        if c.closing_lines:
            card_lines.append("CLOSE: " + "; ".join(c.closing_lines))
        if c.do:
            card_lines.append("DO: " + "; ".join(c.do))
        if c.dont:
            card_lines.append("DON'T: " + "; ".join(c.dont))
        if c.escalation_rules:
            card_lines.append(f"ESCALATE: {c.escalation_rules}")
        if c.language:
            card_lines.append(f"LANGUAGE: speak in {c.language}.")
        return "\n".join(card_lines)

    def _render_card_fenced(self) -> str:
        """L3 — campaign card wrapped in a CAMPAIGN_BRIEF fence (untrusted, C3)."""
        body = self._render_card_body()
        if not body:
            return ""
        return FencedText(SourceTrust.CAMPAIGN_BRIEF, body).render()

    # -- render scopes ----------------------------------------------------- #
    def render_stable_prefix(self) -> str:
        """L0..L3 — the full per-call instruction block (back-compat scope).

        Contains ZERO per-call/per-turn dynamic text (no lead_name, no recap,
        no opener flag, no timestamp). L0 (PLATFORM safety/identity) is rendered
        FIRST by position; the L3 campaign card is fenced below it (C3).

        NOTE (H13): for prompt-cache reuse use `render_cache_split()` — only
        L0+L1+L2 are CAMPAIGN-STABLE; the L3 card is volatile and lives below the
        cache boundary there. `render_stable_prefix` keeps the legacy L0..L3
        grouping for callers that send the whole block at once.
        """
        parts = [
            self._render_platform_layer(),   # L0 — PLATFORM, top, never fenced
            self._render_mode_industry(),     # L1 + L2
            self._render_card_fenced(),       # L3 — fenced untrusted, below L0
        ]
        return "\n\n".join(p for p in parts if p)

    def render_cache_split(self) -> tuple[str, str]:
        """H13 — return (stable_prefix, volatile_suffix) for prompt-cache reuse.

        stable_prefix  = L0 (identity+safety) + L1 (use-case) + L2 (industry).
                         CAMPAIGN-STABLE: byte-identical for EVERY call/turn of a
                         campaign, so it is the natural cache breakpoint.
        volatile_suffix = L3 (campaign card volatile fields, fenced) + L4 (lead
                         memory, fenced) + L5 (turn, fenced). Everything that can
                         change per-campaign-card-edit / per-call / per-turn.

        The PLATFORM safety layer is the FIRST thing in stable_prefix, so it is
        positionally above ALL fenced/untrusted content in the assembled prompt.
        """
        stable_parts = [
            self._render_platform_layer(),   # L0
            self._render_mode_industry(),     # L1 + L2
        ]
        stable = "\n\n".join(p for p in stable_parts if p)

        volatile_parts = [
            self._render_card_fenced(),       # L3 (volatile card, fenced)
            self.render_call_suffix(),         # L4 (lead memory, fenced)
            self.render_turn_suffix(),         # L5 (turn, fenced)
        ]
        volatile = "\n\n".join(p for p in volatile_parts if p)
        return stable, volatile

    def render_call_suffix(self) -> str:
        """L4 — lead memory (UNTRUSTED, fenced), rendered ONCE per call, below
        the cache boundary. A prior-call summary can be poisoned, so it is wrapped
        in a LEAD_MEMORY fence (C3/H3)."""
        l = self.lead
        parts: list[str] = []
        if l.name:
            parts.append(f"LEAD NAME: {l.name}")
        if l.lifecycle and l.lifecycle != Lifecycle.NEW:
            parts.append(f"LIFECYCLE: {l.lifecycle.value}")
        if l.last_call_summary:
            parts.append(f"LAST CALL: {l.last_call_summary}")
        if l.open_commitments:
            parts.append("OPEN COMMITMENTS: " + "; ".join(l.open_commitments))
        if l.preferred_callback_ts:
            parts.append(f"PREFERRED CALLBACK: {l.preferred_callback_ts}")
        if l.do_not_mention:
            parts.append("DO NOT MENTION: " + "; ".join(l.do_not_mention))
        if not parts:
            return ""
        body = "LEAD MEMORY:\n" + "\n".join(parts)
        return FencedText(SourceTrust.LEAD_MEMORY, body).render()

    def render_turn_suffix(self) -> str:
        """L5 + dynamic — re-rendered each turn, appended after the cached prefix.

        This is the ONLY scope that changes per turn. It is also hard-clamped
        here (the red-team fix): we never trust the caller to have pre-clamped.

        C3: RAG snippets are RETRIEVED_KNOWLEDGE — untrusted — so the relevant
        block is wrapped in a retrieved_knowledge fence. Stage/language are
        PLATFORM-authored control text and stay unfenced.
        """
        t = self.turn
        parts: list[str] = []
        if t.stage:
            parts.append(f"STAGE: {t.stage.value}")
        if t.detected_lang:
            parts.append(f"USER LANGUAGE: {t.detected_lang} — mirror it.")
        # hard per-turn clamp on RAG snippets (cap count + per-item chars)
        if t.rag_snippets:
            snips = t.rag_snippets[:_RAG_MAX]
            rendered = "; ".join(
                f"[{s.source}] {clamp_chars(s.text, _RAG_TEXT_CHARS)}" for s in snips if s.text
            )
            if rendered:
                parts.append(FencedText(SourceTrust.RETRIEVED_KNOWLEDGE, "RELEVANT: " + rendered).render())
        if t.barge_in_hint:
            parts.append(t.barge_in_hint)
        if not parts:
            return ""
        return "\n".join(parts)

    # -- budget ------------------------------------------------------------ #
    def _layer_text(self) -> dict[str, str]:
        return {
            "prefix": self.render_stable_prefix(),
            "call": self.render_call_suffix(),
            "turn": self.render_turn_suffix(),
        }

    def token_estimate(self) -> int:
        return sum(estimate_tokens(v) for v in self._layer_text().values())

    def clamp(self) -> "ContextPacket":
        """Return a budget-enforced COPY (pure — never mutates self).

        Order of operations (arch §2):
          1. Hard per-field clamps on every layer (lists capped, chars trimmed).
          2. If still over budget: drop L5, then trim L4 — NEVER trim L0.
          3. If L0..L3 alone are still over budget -> BudgetExceededError (a
             campaign-config bug; we refuse to silently send an over-budget
             prompt — LEARNINGS §1).
        """
        b = self.budget

        # 1. per-field clamps ------------------------------------------------------
        # H13 RETRIEVAL-OVER-TRUNCATION: the campaign card no longer LOSES the
        # overflow. The full product summary + full USP list are carried
        # losslessly (full_product_summary / full_usps) so W4 can index them and
        # recall on demand; the in-prompt copy is shortened for latency and an
        # overflow flag tells the renderer to advertise "more on request". We
        # populate full_* only if the caller didn't already (idempotent — a
        # second clamp() is a no-op, preserving the double-render invariant).
        src = self.card
        full_summary = src.full_product_summary or src.product_summary
        in_prompt_summary = clamp_chars(src.product_summary, _PRODUCT_SUMMARY_CHARS)
        summary_overflow = src.summary_overflow or (len(src.product_summary) > len(in_prompt_summary))

        full_usps = src.full_usps or src.usps
        in_prompt_usps = clamp_list(src.usps, _USPS_MAX)
        usps_overflow = src.usps_overflow or (len(src.usps) > len(in_prompt_usps))

        card = replace(
            src,
            product_summary=in_prompt_summary,
            full_product_summary=full_summary,
            summary_overflow=summary_overflow,
            usps=in_prompt_usps,
            full_usps=full_usps,
            usps_overflow=usps_overflow,
            talking_points=clamp_list(src.talking_points, _TALKING_MAX),
            qualifying_questions=clamp_list(src.qualifying_questions, _QUALIFYING_MAX),
            objections=tuple(src.objections[:_OBJECTIONS_MAX]),
        )
        lead = replace(
            self.lead,
            last_call_summary=clamp_chars(self.lead.last_call_summary, _LAST_CALL_SUMMARY_CHARS),
        )
        turn = replace(
            self.turn,
            rag_snippets=tuple(
                replace(s, text=clamp_chars(s.text, _RAG_TEXT_CHARS))
                for s in self.turn.rag_snippets[:_RAG_MAX]
            ),
        )
        pkt = replace(self, card=card, lead=lead, turn=turn)

        if pkt.token_estimate() <= b.max_total_tokens:
            return pkt

        # 2a. drop L5 (turn evidence) first ----------------------------------------
        pkt = replace(pkt, turn=replace(pkt.turn, rag_snippets=()))
        if pkt.token_estimate() <= b.max_total_tokens:
            return pkt

        # 2b. trim L4 (lead memory) ------------------------------------------------
        pkt = replace(
            pkt,
            lead=LeadMemory(name=pkt.lead.name, lifecycle=pkt.lead.lifecycle),
        )
        if pkt.token_estimate() <= b.max_total_tokens:
            return pkt

        # 3. L0..L3 alone are over budget -> loud failure --------------------------
        raise BudgetExceededError(
            f"stable prefix (L0..L3) alone exceeds budget "
            f"({pkt.token_estimate()} > {b.max_total_tokens} tokens) — "
            f"campaign {pkt.meta.campaign_id} card is too large; trim it."
        )
