"""comm.channels.base — the channel-neutral contract every channel adapter implements.

Spec: communication/COMMUNICATION-MASTER-PLAN.md §2.1 ("ONE ABC every channel implements —
ChannelAdapter, NEVER raises, mirrors creative/.../providers/base.py") + the universal
SendEnvelope / SendResult shapes.

THE CONTRACT (mirrors providers/base.py house rules):
  * read the token fresh via the vault (so a rotation takes effect without an import restart),
  * DORMANT when unconfigured: status() -> "not_configured", send() returns a non-ok
    SendResult, NEVER raises, NEVER calls out,
  * a short timeout on every outbound HTTP request (the engine ALSO wraps the whole call in
    asyncio.wait_for as the outer cap — defense in depth),
  * NEVER log a secret/token.

A SendEnvelope is channel-NEUTRAL (the same object routes to Telegram now, Email/SMS later);
the adapter translates it to the provider's wire format. A SendResult is the uniform return
the engine logs into comm_send_log. Both are pure dataclasses (stdlib only) so importing this
module does ZERO I/O and NEVER raises (the resting-byte-identical guarantee).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# The universal value objects (§2.1).
# ---------------------------------------------------------------------------
@dataclass
class MediaItem:
    """One media attachment to send. `kind` selects the Bot API method (photo/document/
    video). EXACTLY ONE source is used, in this priority: file_id (cached, re-send at ₹0)
    > url (presigned Spaces / CDN URL — NEVER base64) > local_path. caption is optional."""
    kind: str = "photo"               # photo | document | video
    file_id: str = ""                 # a cached provider file_id (reuse = zero re-upload)
    url: str = ""                     # a presigned/public URL the provider fetches
    local_path: str = ""              # a local file path (last resort; multipart upload)
    caption: str = ""                 # optional caption rendered with the media
    spaces_key: str = ""              # provenance: the source object key (for file_id cache)


@dataclass
class Button:
    """An inline-keyboard button. Telegram supports url buttons (W1 — no callback/firewall).
    `url` opens a link (e.g. the Call-Now panel URL); `callback_data` is reserved for W5."""
    text: str = ""
    url: str = ""
    callback_data: str = ""           # reserved (W5 war-room); unused in W1


@dataclass
class SendEnvelope:
    """The channel-NEUTRAL outbound message. The engine resolves the channel + adapter and
    hands the SAME envelope to whichever adapter serves the tenant's channel.

      * to_ref         — the destination on this channel (TG chat_id / email / phone).
      * kind           — text | photo | document | video | alert | summary (audit/metering).
      * purpose        — marketing | service | transactional (the consent (channel x purpose)).
      * text           — the message body (also a media caption when media is present).
      * media          — zero+ attachments (banner / PDF / video).
      * buttons        — inline-keyboard buttons (W1: url-only).
      * lang           — BCP-47-ish hint for the brain (W1 unused by the adapter).
      * idempotency_key — comms:{message_id}; makes a retried create_task safe (UNIQUE in DB).
      * meta           — free-form provenance the engine copies into the send_log
                         (session_id / call_id / provider_def_id / lead_id / contact_phone).
    """
    to_ref: str = ""
    kind: str = "text"
    purpose: str = "service"
    text: str = ""
    media: List[MediaItem] = field(default_factory=list)
    buttons: List[Button] = field(default_factory=list)
    lang: str = ""
    idempotency_key: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def preview(self, n: int = 280) -> str:
        """First ~n chars of the body — what the send_log stores (never the full PII blob)."""
        t = (self.text or "").strip()
        return t[:n]


@dataclass
class SendResult:
    """The uniform adapter return the engine logs. NEVER carries a token. `ok` is the only
    field a caller branches on; `status` is the comm_send_log status value."""
    ok: bool = False
    status: str = "failed"            # sent | failed | not_configured | blocked_* | timeout
    channel: str = ""                 # telegram | email | sms | whatsapp
    external_id: str = ""             # the provider message id (TG message_id)
    error_code: str = ""              # a short machine code (never a secret / full trace)
    cost_minor: int = 0               # INR paise charged (Telegram = 0)
    provider: str = ""               # the named provider (telegram)
    file_id_cached: str = ""          # a file_id the engine should cache for re-use (§1.2 #6)

    @classmethod
    def not_configured(cls, channel: str = "", reason: str = "not_configured") -> "SendResult":
        return cls(ok=False, status="not_configured", channel=channel, error_code=reason)

    @classmethod
    def failure(cls, channel: str, error_code: str, status: str = "failed") -> "SendResult":
        return cls(ok=False, status=status, channel=channel, error_code=(error_code or "")[:160])

    @classmethod
    def success(cls, channel: str, *, external_id: str = "", cost_minor: int = 0,
                provider: str = "", file_id_cached: str = "") -> "SendResult":
        return cls(ok=True, status="sent", channel=channel, external_id=external_id,
                   cost_minor=int(cost_minor or 0), provider=provider,
                   file_id_cached=file_id_cached)


# ---------------------------------------------------------------------------
# The adapter Protocol (§2.1). NEVER raises. Dormant when unconfigured.
# ---------------------------------------------------------------------------
@runtime_checkable
class ChannelAdapter(Protocol):
    """What every channel (Telegram now; Email/SMS later) implements. The engine depends on
    THIS shape only — adding a channel is one new adapter behind this contract."""

    channel: str                      # 'telegram' | 'email' | 'sms'

    def status(self) -> str:
        """'configured' | 'not_configured' | 'error'. NEVER raises, NEVER calls out unless
        a cheap identity check is explicitly requested elsewhere (verify())."""
        ...

    def estimate_cost_minor(self, env: SendEnvelope) -> int:
        """Estimated INR paise for this send (Telegram = 0). NEVER raises."""
        ...

    async def send(self, env: SendEnvelope) -> SendResult:
        """Send the envelope. NEVER raises — returns a non-ok SendResult on any failure.
        Applies its OWN per-request HTTP timeout; the engine adds the outer wait_for cap."""
        ...
