"""voice_ops.whatsapp.model — the canonical W16 records + taxonomies.

Pure stdlib dataclasses, no droplet import. These are the flat, cheap rows the
media library, audience resolver, send orchestrator, and delivery tracker pass
around — mirrors the voice_ops.reporting.model posture (flat + (de)serializable).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Optional


# --------------------------------------------------------------------------- #
# Media library
# --------------------------------------------------------------------------- #
class MediaKind(str, Enum):
    """The four media kinds the founder asked for. `brochure` is its OWN kind (PDF
    is first-class — critical in real estate), never lumped under 'image'."""

    BANNER = "banner"
    IMAGE = "image"
    VIDEO = "video"
    BROCHURE = "brochure"

    @classmethod
    def coerce(cls, value) -> "MediaKind":
        try:
            return cls((value or "image").lower())
        except Exception:
            return cls.IMAGE

    @property
    def media_type(self) -> str:
        """Meta media category for this kind (image|video|document)."""
        return {
            MediaKind.BANNER: "image",
            MediaKind.IMAGE: "image",
            MediaKind.VIDEO: "video",
            MediaKind.BROCHURE: "document",
        }[self]


# Per-kind allowed MIME prefixes + size ceilings (Meta-aligned, generous floors).
_KIND_RULES = {
    MediaKind.BANNER: (("image/",), 5 * 1024 * 1024),
    MediaKind.IMAGE: (("image/",), 5 * 1024 * 1024),
    MediaKind.VIDEO: (("video/",), 16 * 1024 * 1024),
    MediaKind.BROCHURE: (("application/pdf",), 100 * 1024 * 1024),
}


def kind_rules(kind: MediaKind) -> tuple[tuple[str, ...], int]:
    """(allowed_mime_prefixes, max_bytes) for a kind."""
    return _KIND_RULES.get(kind, (("image/",), 5 * 1024 * 1024))


_EXT = {
    "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp",
    "image/gif": "gif", "video/mp4": "mp4", "video/quicktime": "mov", "application/pdf": "pdf",
}


def ext_for(content_type: str) -> str:
    return _EXT.get((content_type or "").split(";")[0].strip().lower(), "bin")


@dataclass
class MediaAsset:
    """One media-library row (latest-wins by (tenant, id))."""

    tenant_id: str
    id: str = ""
    kind: MediaKind = MediaKind.IMAGE
    title: str = ""
    storage_key: str = ""
    content_type: str = ""
    size_bytes: int = 0
    width: int = 0
    height: int = 0
    duration_s: int = 0
    page_count: int = 0
    source: str = "uploaded"               # uploaded|generated
    tags: list = field(default_factory=list)
    used_count: int = 0
    status: str = "ready"                   # ready|archived
    created_by: str = ""
    created_at: float = field(default_factory=time.time)

    @property
    def media_type(self) -> str:
        return self.kind.media_type

    def to_doc(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex

    def copy(self) -> "MediaAsset":
        return replace(self)


# --------------------------------------------------------------------------- #
# Audience
# --------------------------------------------------------------------------- #
@dataclass
class AudienceSpec:
    """A rich targeting spec — NOT "send to all". Any subset of signals composes
    with AND between groups, OR within a group (temps OR-match; a temp set AND a
    campaign filter both apply). An empty spec resolves to NOTHING (fail-closed:
    you must positively select an audience), unless `include_all` is set."""

    temps: tuple = ()                       # ("hot","warm","cold","dead")
    campaign_id: str = ""                   # leads touched by campaign X
    agent: str = ""                         # leads handled by agent Y
    segment: str = ""                       # a named saved segment (resolved by callback hook)
    requested_brochure: bool = False        # behavioural: lead asked for the brochure
    follow_up_pending: bool = False         # callback/follow-up lifecycle pending
    lead_ids: tuple = ()                    # explicit hand-picked ids (union)
    exclude_opted_out: bool = True          # always drop opted-out numbers
    include_all: bool = False               # escape hatch (must be explicit)

    def is_empty(self) -> bool:
        return not (self.temps or self.campaign_id or self.agent or self.segment
                    or self.requested_brochure or self.follow_up_pending
                    or self.lead_ids or self.include_all)


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #
class DeliveryStatus(str, Enum):
    """The per-message delivery funnel. Monotone for the happy path
    (queued->sent->delivered->read); failed / opted_out / skipped are terminal."""

    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    OPTED_OUT = "opted_out"
    SKIPPED_NO_CONFIG = "skipped_no_config"   # dormant run — WA creds not present

    @classmethod
    def coerce(cls, value) -> "DeliveryStatus":
        try:
            return cls((value or "queued").lower())
        except Exception:
            return cls.QUEUED


# Funnel ordinals — a status only advances forward (a late 'delivered' webhook
# must never overwrite a 'read'). Terminal states have high ordinals.
_STATUS_ORDER = {
    DeliveryStatus.QUEUED: 0,
    DeliveryStatus.SKIPPED_NO_CONFIG: 1,
    DeliveryStatus.SENT: 2,
    DeliveryStatus.DELIVERED: 3,
    DeliveryStatus.READ: 4,
    DeliveryStatus.FAILED: 5,
    DeliveryStatus.OPTED_OUT: 6,
}


def status_order(s: DeliveryStatus) -> int:
    return _STATUS_ORDER.get(s, 0)


@dataclass
class DeliveryRow:
    """One dispatched message's delivery state (latest-wins by (tenant, message_id))."""

    tenant_id: str
    message_id: str
    campaign_id: str = ""
    template: str = ""
    phone_masked: str = ""
    lead_id: str = ""
    status: DeliveryStatus = DeliveryStatus.QUEUED
    reason: str = ""                         # Meta failure message verbatim
    media_count: int = 0
    sent_at: float = 0.0
    delivered_at: float = 0.0
    read_at: float = 0.0
    failed_at: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def to_doc(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def copy(self) -> "DeliveryRow":
        return replace(self)


# --------------------------------------------------------------------------- #
# Send plan / result
# --------------------------------------------------------------------------- #
@dataclass
class SendPlan:
    """What a campaign send will dispatch: a template + attached media -> a resolved
    audience. The orchestrator builds this, then either dispatches (creds present)
    or records it dormant (creds absent)."""

    tenant_id: str
    campaign_id: str = ""
    template: str = ""
    media_ids: tuple = ()                    # ordered: banner, images…, video, brochure
    audience_lead_ids: tuple = ()
    audience_phones: dict = field(default_factory=dict)   # lead_id -> masked phone (PII-light)


@dataclass
class SendResult:
    """Outcome of a send run. `dispatched` is the count actually handed to Meta;
    `skipped_no_config` is the dormant count. `active` is whether WA creds were
    present (the future-ready gate)."""

    tenant_id: str
    campaign_id: str = ""
    active: bool = False                     # WA creds present -> really sent
    queued: int = 0                          # rows created
    dispatched: int = 0                      # handed to Meta (active runs)
    skipped_no_config: int = 0               # dormant rows (creds absent)
    message_ids: tuple = ()
    reason: str = ""                         # why dormant / why nothing sent
