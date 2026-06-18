"""voice_ops.whatsapp — W16 WhatsApp Media Library + Campaign Send + Delivery (tracked, droplet-free).

The founder's WhatsApp follow-up upgrade, beyond plain templates:

  1. MEDIA LIBRARY (`media.py`)      — upload / store / preview / reuse / replace / organize a
     banner, image, video, or PDF brochure. Tenant-scoped FORCE-RLS rows (`wa_media`) + object
     bytes on the W9 ObjectStorage tier under `wa_media/<tenant>/`. A brochure (PDF) is its own
     `kind='brochure'` asset — first-class, because PDFs are critical in real estate.

  2. AUDIENCE RESOLVER (`audience.py`) — resolve a target lead set from a rich segment spec:
     hot / warm / cold / dead (W7 lifecycle), a named custom segment, leads from campaign-X,
     leads handled by agent-Y, `requested_brochure` (behavioural), `follow_up_pending` (callback
     lifecycle). NOT "send to all". Reads the W14 reporting read-model — never re-classifies.

  3. SEND ORCHESTRATOR (`send.py`)    — assemble template + media -> resolve audience -> dispatch.
     FUTURE-READY: DORMANT until WhatsApp creds land (W13 `WhatsAppConfig.is_active`). Wired but
     never sends blind — a dormant run records `skipped_no_config` rows so the panel shows exactly
     what WOULD be sent. Every dispatch emits the W8 delivery events.

  4. DELIVERY TRACKING (`delivery.py`)— one tenant-scoped row per message (`wa_delivery`), advanced
     latest-wins through the funnel sent -> delivered -> read, or failed / opted_out, fed by the
     Meta status webhook. The panel delivery view + KPIs read this.

IMPORT ISOLATION: imports ONLY from voice_ops.{config,recording,reporting,callback} + voice_kernel,
all of which are themselves droplet-free with lazy heavy deps. Importing this package pulls ZERO
boto3 / sqlalchemy / livekit / droplet code at module load — safe on any host (CI included).
"""
from __future__ import annotations

from .model import MediaAsset, MediaKind, DeliveryRow, DeliveryStatus, AudienceSpec, SendPlan, SendResult
from .store import MediaStore, DeliveryStore, InMemoryMediaBackend, InMemoryDeliveryBackend
from .media import MediaLibrary
from .audience import AudienceResolver
from .delivery import DeliveryTracker
from .send import SendOrchestrator

__all__ = [
    "MediaAsset", "MediaKind", "DeliveryRow", "DeliveryStatus",
    "AudienceSpec", "SendPlan", "SendResult",
    "MediaStore", "DeliveryStore", "InMemoryMediaBackend", "InMemoryDeliveryBackend",
    "MediaLibrary", "AudienceResolver", "DeliveryTracker", "SendOrchestrator",
]
