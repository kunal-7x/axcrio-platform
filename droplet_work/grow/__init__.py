"""Haptica Grow — autonomous Ad → Lead → AI-qualify → SCORE → Revenue-Truth signal loop.

The "ElevateX / Growth-OS" engine, implemented as an ADDITIVE, FLAG-GATED module inside
the existing modular monolith (NOT a separate microservices monorepo). W1 ships the moat:
L5 lead scoring + the L7 CAPI/Enhanced-Conversions Signal Loop (GROWTH-OS-BUILD-SPEC §11),
shadow-safe by default. Mounted only when FEATURE_GROW=1; the earner (agent.py) is never
touched. Convenience re-exports keep the caller.py hook a one-liner:

    import grow
    grow.on_call_outcome(tenant_id, lead_id, phone=..., call_answered=True, ...)

Import is stdlib-only (FastAPI lives behind grow.endpoints.build_router, imported lazily
by caller.py); a broken sub-import here can never crash the spine.
"""
from __future__ import annotations

__version__ = "0.7.0"  # W1-W6 + W7 all-ads-platforms + W8 advisor/chat (Famit Growth)

from .config import GrowConfig            # noqa: E402,F401
from .model import (CapturedLead, Journey, Ladder, LeadTier, Orchestration,  # noqa: E402,F401
                    ScoredLead, ScoringInput, SignalEvent, SignalStatus)
from .loop import GrowLoop, get_loop, reset_loop  # noqa: E402,F401
from .adapters import (register_voice_caller, register_whatsapp_sender,  # noqa: E402,F401
                       set_main_loop)


def on_lead_captured(tenant_id: str, lead_id: str, **kw) -> dict:
    """Fire-and-forget L3 speed-to-lead hook (used by the L1 ingest webhook behind
    FEATURE_GROW): consent-clean lead -> compliance gate -> WhatsApp + AI call <60s."""
    return get_loop().on_lead_captured(tenant_id, lead_id, **kw)


async def acapture(tenant_id: str, lead_id: str, **kw) -> dict:
    """Async-safe speed-to-lead capture for an async request context (auto_lead webhook /
    the ingest endpoint): binds the running loop (so the live voice dial can schedule
    run_job on it) and runs the sync loop off-thread (so a blocking WhatsApp POST never
    stalls the event loop). NEVER raises."""
    import asyncio  # noqa: PLC0415
    try:
        set_main_loop(asyncio.get_running_loop())
    except Exception:  # noqa: BLE001
        pass
    try:
        return await asyncio.to_thread(on_lead_captured, tenant_id, lead_id, **kw)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"acapture_error:{exc!r}"[:160]}


def on_call_outcome(tenant_id: str, lead_id: str, **kw) -> dict:
    """Fire-and-forget post-call hook (used by caller._finalize_call behind FEATURE_GROW)."""
    return get_loop().on_call_outcome(tenant_id, lead_id, **kw)


def on_booking(tenant_id: str, lead_id: str, **kw) -> dict:
    return get_loop().on_booking(tenant_id, lead_id, **kw)


def on_sale(tenant_id: str, lead_id: str, *, value: int, **kw) -> dict:
    return get_loop().on_sale(tenant_id, lead_id, value=value, **kw)
