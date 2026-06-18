"""voice_kernel.memory.continuity — CONVERSATION CONTINUITY builder.

The single highest-ROI piece of cross-call memory: the next call (or WhatsApp)
must START from the prior summary — "kal aapne bola tha aap budget check karke
batayenge..." — and NEVER restart from zero. This module takes a loaded
`LeadMemory` (the WARM L4 row from MemoryService.load) and applies it onto a
`ContextPacket` so the renderer emits the fenced LEAD_MEMORY block above the
vendor brief.

It does NOT touch the prompt position / fencing — that is the FROZEN packet's job
(packet.render_call_suffix wraps L4 in FencedText(SourceTrust.LEAD_MEMORY),
positioned ABOVE CAMPAIGN_BRIEF and BELOW PLATFORM L0). This module only:
  * decides whether continuity applies (a NEW lead with no history => no recap),
  * builds a short, natural-language CONTINUITY OPENER HINT the agent can speak,
  * applies the LeadMemory onto the packet (pure replace + clamp).

Pure-stdlib + voice_kernel only. No droplet_work import, no I/O.
"""
from __future__ import annotations

from dataclasses import replace

from ..packet import ContextPacket, Lifecycle, LeadMemory
from ..tokens import clamp_chars

_OPENER_CHARS = 200


def has_history(mem: LeadMemory) -> bool:
    """True if this lead carries prior context worth surfacing (so we open with a
    recap instead of a cold greeting). A NEW lead with an empty summary has none."""
    if mem is None:
        return False
    if mem.lifecycle == Lifecycle.NEW and not mem.last_call_summary:
        return False
    return bool(
        mem.last_call_summary
        or mem.open_commitments
        or mem.preferred_callback_ts
        or (mem.lifecycle and mem.lifecycle != Lifecycle.NEW)
    )


def continuity_opener_hint(mem: LeadMemory) -> str:
    """A short natural-language hint the agent can weave into its opener so the
    call resumes the relationship ("last time you said..."). Hinglish-friendly,
    derived from the salient memory — NOT the raw transcript. Returns "" for a
    fresh lead (the agent uses its normal cold opener)."""
    if not has_history(mem):
        return ""
    bits: list[str] = []
    who = mem.name.strip()
    if who:
        bits.append(f"You've spoken with {who} before")
    if mem.last_call_summary:
        bits.append(f"last time: {mem.last_call_summary}")
    if mem.open_commitments:
        bits.append(f"they had said they would {mem.open_commitments[0]}")
    if mem.preferred_callback_ts:
        bits.append(f"preferred callback {mem.preferred_callback_ts}")
    hint = ". ".join(bits)
    # PLATFORM-authored control instruction (NOT fenced lead text) — it tells the
    # agent HOW to open. The lead's own words remain fenced inside L4 by the packet.
    return clamp_chars(
        "CONTINUITY: resume the relationship, do NOT restart from zero — " + hint + ".",
        _OPENER_CHARS,
    )


def apply_lead_memory(packet: ContextPacket, mem: LeadMemory) -> ContextPacket:
    """Apply a loaded LeadMemory onto the packet's L4 slot and re-clamp. Pure.

    This is what the kernel's `enrich_prefix` does (kernel.py:148-149) — provided
    here as the named continuity seam so the LATER live splice can call ONE
    function. The packet renderer then fences L4 (LEAD_MEMORY) above the vendor
    brief automatically.
    """
    if mem is None:
        return packet
    return replace(packet, lead=mem).clamp()
