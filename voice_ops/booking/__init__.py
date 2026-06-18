"""voice_ops.booking — TRACKED, droplet-free booking layer (W11).

Three founder fixes live under voice_ops (this package + voice_ops.gcal):

  1. BOOKING from the call (founder bug 2): `BookingService.book_site_visit(...)` is the AI
     @function_tool impl — resolve the loose time the prospect gave, claim a REAL appointment via
     the booking engine (no double-book — that invariant is owned by droplet_work/booking/core.py,
     inherited unchanged through the lazy `store` wrapper), emit ONE W8 `site_visit_booked` event
     (dashboard/CRM react instantly), and return ONE short spoken confirmation. Plus the full
     manual + AI-driven lifecycle (Scheduled/Confirmed/Completed/NoShow/Cancelled/Rescheduled).

  2. WARM TRANSFER hardening (founder bug 1): `transfer.plan_transfer(...)` is the pure planner
     that yields the EXACT choreography — ONE short ack line + hold music + same-room dial +
     AI-exit — and `TransferLog` records requested/started/connecting/completed/failed (W8
     handoff_requested/handoff_done). The LIVE aim_voice_agent is NOT edited here; the edits are a
     PATCH DOC (design/W11-TRANSFER-BOOKING-GCAL-SEAM.md) that calls into this tested brain.

WRAPS (never edits / never imports at load) agent.py / caller.py / aim_voice_agent.py / the
gitignored droplet_work/booking engine. IMPORT ISOLATION: `import voice_ops.booking` pulls ZERO
droplet_work, ZERO sqlalchemy, ZERO livekit, ZERO redis — the engine is loaded lazily inside
`store`, and the EventBus is injected. Inert until BOOKING_OPS_ENABLED flips (default OFF).
"""
from __future__ import annotations

from . import store, transfer
from .config import BookingOpsConfig
from .datetime_resolve import humanize_slot, resolve_slot_start
from .service import BookingService
from .transfer import (
    TransferLog,
    TransferPlan,
    TransferState,
    detect_transfer_intent,
    plan_transfer,
)

__all__ = [
    "BookingOpsConfig",
    "BookingService",
    "store",
    "resolve_slot_start",
    "humanize_slot",
    # transfer
    "transfer",
    "plan_transfer",
    "detect_transfer_intent",
    "TransferPlan",
    "TransferState",
    "TransferLog",
]
