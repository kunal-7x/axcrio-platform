"""voice_kernel.memory.cards — AI SUMMARY card (per lead) + NEXT-BEST-ACTION.

Two COLD artifacts the panel renders per lead. Both are generated OFF the hot
path (post-call, async-allowed). Both have a deterministic baseline (so they
work with ZERO model cost) and an optional async LLM-assist hook (so they read
better when a model is available). Neither widens the FROZEN LeadMemory; the
summary lands in `last_call_summary` (already a field), the NBA is advisory and
the service persists it in the `next_best_action` column.

Pure-stdlib + voice_kernel only. No droplet_work import.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from ..packet import Lifecycle, LeadMemory
from ..tokens import clamp_chars

_CARD_CHARS = 300
_NBA_CHARS = 160


@dataclass(frozen=True)
class LeadCard:
    """The AI summary card the panel shows for a lead (read model, not stored as
    a new table — derived from the LeadMemory head row + its history)."""

    name: str
    lifecycle: Lifecycle
    badge: str            # human business badge text
    summary: str          # <= 300 chars
    conversion_prob: int  # 0..100 internal score
    open_commitments: tuple[str, ...]
    preferred_callback_ts: str
    next_best_action: str


# Founder-facing business badge text per lifecycle (the simple badge he asked for).
_BADGE: dict[Lifecycle, str] = {
    Lifecycle.NEW: "New lead",
    Lifecycle.HOT: "Hot — ready to convert",
    Lifecycle.WARM: "Warm — follow up",
    Lifecycle.COLD: "Cold — re-warm needed",
    Lifecycle.DEAD: "Dead — do not call",
}


def build_summary_card(mem: LeadMemory, conversion_prob: int = 0, next_best_action: str = "") -> LeadCard:
    """Deterministic AI SUMMARY CARD from a LeadMemory head row. Pure."""
    return LeadCard(
        name=mem.name,
        lifecycle=mem.lifecycle,
        badge=_BADGE.get(mem.lifecycle, "New lead"),
        summary=clamp_chars(mem.last_call_summary, _CARD_CHARS),
        conversion_prob=max(0, min(100, conversion_prob)),
        open_commitments=mem.open_commitments,
        preferred_callback_ts=mem.preferred_callback_ts,
        next_best_action=next_best_action or next_best_action_rules(mem),
    )


def next_best_action_rules(mem: LeadMemory) -> str:
    """DETERMINISTIC next-best-action from the lead state. Cheap, no model.

    A single, concrete instruction for the NEXT touch — what the agent/telecaller
    should do. Derived from lifecycle + open signals.
    """
    lc = mem.lifecycle
    if lc == Lifecycle.DEAD:
        return "Do not contact — lead opted out. Suppress from all campaigns."
    if lc == Lifecycle.HOT:
        if mem.preferred_callback_ts:
            return f"Call back at {mem.preferred_callback_ts} to confirm the booking."
        return "Call now to confirm the appointment while interest is high."
    if lc == Lifecycle.WARM:
        if mem.open_commitments:
            return f"Follow up on: {mem.open_commitments[0]}"
        if mem.preferred_callback_ts:
            return f"Call back at {mem.preferred_callback_ts} as the lead requested."
        return "Follow up within 24h with a value point; ask for the booking."
    if lc == Lifecycle.COLD:
        return "Send a WhatsApp re-warm (offer/social proof) before calling again."
    return "First-contact call: qualify need and budget, build rapport."


async def next_best_action_llm(
    mem: LeadMemory,
    *,
    llm: Optional[Callable[[str], Awaitable[str]]] = None,
    timeout_s: float = 6.0,
) -> str:
    """OPTIONAL async LLM-assist NBA. Falls back to the deterministic rule on any
    error/timeout. Never raises."""
    import asyncio

    base = next_best_action_rules(mem)
    if llm is None:
        return base
    try:
        prompt = (
            "Given this lead state, give ONE concrete next-best-action for the "
            f"sales agent in <={_NBA_CHARS} chars.\n"
            f"Lifecycle: {mem.lifecycle.value}\n"
            f"Last call: {mem.last_call_summary}\n"
            f"Open commitments: {'; '.join(mem.open_commitments)}\n"
            f"Preferred callback: {mem.preferred_callback_ts}"
        )
        out = (await asyncio.wait_for(llm(prompt), timeout=timeout_s) or "").strip()
        return clamp_chars(out, _NBA_CHARS) if out else base
    except Exception:
        return base
