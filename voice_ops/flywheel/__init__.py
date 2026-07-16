"""voice_ops.flywheel — Haptica Flywheel: the RLHF/RLAIF self-improvement engine.

Every voice call becomes fuel. This side-pipeline package joins the streams Haptica
already emits — the voice_kernel.events outcome facts (site_visit_booked, callback_scheduled,
lead_hot..dead, summary_ready) + the Famit Research per-turn affect trace (arousal/friction) +
the policy arm that was live (model/voice/variant) — into one canonical RL trajectory, scores a
fused & provenance-stamped reward, distributes the terminal outcome across turns (credit
assignment → "which MOVE was positive/negative"), mines a proprietary (chosen,rejected)
preference dataset (the moat), and proposes GATED challengers that must pass the existing
eval + shadow harness with HUMAN APPROVAL before promotion.

DESIGN LAWS (mirror voice_ops/research + grow): SIDE-PIPELINE (never on the live turn loop),
FLAG-GATED + DORMANT-SAFE (a cheap no-op unless FLYWHEEL_ENABLED + ClickHouse configured;
every entrypoint swallows errors → WARNING, never raises into a call), MULTI-TENANT, HONEST
SCIENCE (no fused number without its components), COMPLIANCE AS A HARD GATE (never a reward).

Public surface kept tiny so callers (the droplet finalize hook, the worker, the router) import
exactly what they need. Heavy submodules (judge/optimizer/credit) are imported LAZILY inside the
functions that use them, so importing this package can NEVER crash startup even mid-build.
"""
from __future__ import annotations

import logging

from . import config as _config

logger = logging.getLogger("flywheel")

__version__ = "0.1.0"


def active() -> bool:
    """Master dormancy gate — True only when FLYWHEEL_ENABLED + a ClickHouse url are set."""
    try:
        return _config.active()
    except Exception:  # noqa: BLE001
        return False


def status() -> dict:
    try:
        return _config.status()
    except Exception:  # noqa: BLE001
        return {"enabled": False, "active": False}


def on_call_finalized(tenant_id: str, call_id: str, rec: dict, transcript=None) -> None:
    """The fire-and-forget post-call hook (mirrors grow.on_call_outcome).

    Called from caller._finalize_call via asyncio.to_thread (OFF the event loop). Captures
    the call's trajectory seed (the live arm + outcome + per-turn affect already in
    famit_research_turns) and persists it so the dataset compounds immediately. The HEAVY
    enrichment (RLAIF judge, credit assignment, preference mining) is the worker's job over the
    warehouse — this hook stays light. No-op when dormant. NEVER raises (a flywheel error must
    never break the call-finalize path).

    `rec` is the droplet call record (id, tenant_id, campaign_id, variant_id, outcome, interest,
    duration_s, chosen_model, chosen_voice, ...). `transcript` is the optional turn list.
    """
    try:
        if not active():
            return
        # Lazy import so a half-built package or absent CH lib can't crash the caller.
        from . import trajectory
        trajectory.capture_finalized(tenant_id, call_id, rec or {}, transcript)
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel on_call_finalized error (non-fatal): %r", exc)


__all__ = ["active", "status", "on_call_finalized", "__version__"]
