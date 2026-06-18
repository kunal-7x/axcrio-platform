"""voice_ops.ai_manager_live.delivery — WhatsApp-ready report delivery (W14).

Founder pain #4 + #5: the daily executive summary (and on-demand "send today's
report") must be deliverable to the tenant's REGISTERED WhatsApp number. The
delivery surface is built NOW but DORMANT until Meta WhatsApp creds are wired — it
NEVER sends blind. A sender is INJECTED:

  * `NullWhatsAppSender` (default) — returns {"status":"not_configured"}; the
    resting build + CI never attempt a real send.
  * a real sender (the live box's WhatsApp client) can be injected later via a
    structural `.send(to, body) -> dict`; this module imports ZERO droplet/HTTP.

`ReportDelivery.deliver(...)` resolves the tenant's registered number (also
injected — a `number_resolver(tenant_id) -> str`), refuses to send to an empty
number (fail-closed), and returns a structured envelope (queued / sent /
not_configured / no_recipient) so the caller always knows what happened.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, Protocol, runtime_checkable

log = logging.getLogger("voice_ops.ai_manager_live.delivery")


@runtime_checkable
class WhatsAppSender(Protocol):
    """Structural sender contract. A real impl wraps the box's WA client."""

    def send(self, to: str, body: str) -> dict: ...


class NullWhatsAppSender:
    """The dormant default — never sends, always reports not_configured."""

    def send(self, to: str, body: str) -> dict:
        return {"status": "not_configured", "reason": "whatsapp_sender_unwired"}


# tenant_id -> registered E.164 number ("" if none). Injected by the seam.
NumberResolver = Callable[[str], str]


class ReportDelivery:
    """Deliver a rendered report/summary to a tenant's registered WhatsApp number."""

    def __init__(self, sender: Optional[WhatsAppSender] = None,
                 number_resolver: Optional[NumberResolver] = None):
        self.sender: WhatsAppSender = sender or NullWhatsAppSender()
        self.number_resolver = number_resolver

    def _resolve_number(self, tenant_id: str, override: str = "") -> str:
        if (override or "").strip():
            return override.strip()
        if self.number_resolver is None:
            return ""
        try:
            return (self.number_resolver(tenant_id) or "").strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("number_resolver failed (non-fatal): %r", exc)
            return ""

    def deliver(self, tenant_id: str, body: str, *, to: str = "") -> dict:
        """Send `body` to the tenant's WhatsApp number. Fail-closed:
          * empty tenant -> error
          * no resolvable recipient -> no_recipient (never broadcast)
          * NullSender -> not_configured (dormant build)
        Returns a structured envelope; NEVER raises."""
        if not (tenant_id or "").strip():
            return {"status": "error", "reason": "empty_tenant"}
        recipient = self._resolve_number(tenant_id, to)
        if not recipient:
            return {"status": "no_recipient", "reason": "no_registered_number", "tenant_id": tenant_id}
        try:
            result = self.sender.send(recipient, body)
        except Exception as exc:  # noqa: BLE001 — a sender failure must not crash the manager
            log.warning("whatsapp send failed (non-fatal): %r", exc)
            return {"status": "error", "reason": "send_failed", "detail": repr(exc)[:160],
                    "to": _mask(recipient)}
        out = dict(result or {})
        out.setdefault("status", "sent")
        out["to"] = _mask(recipient)
        return out


def _mask(number: str) -> str:
    """Mask a phone for logs/envelopes: keep country + last 2 digits."""
    s = (number or "").strip()
    if len(s) <= 4:
        return "***"
    return s[:3] + "*" * (len(s) - 5) + s[-2:]
