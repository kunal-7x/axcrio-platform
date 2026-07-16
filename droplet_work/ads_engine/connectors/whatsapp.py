"""ads_engine.connectors.whatsapp — WhatsApp Cloud API (Graph v23.0) via the 360dialog BSP.

Design: vault-connectors.md §5 + india-compliance-channels.md §6. This connector owns *how* to
call WhatsApp; campaign/leads own *what* to send. It speaks two backends behind ONE method surface,
chosen by the decrypted cred blob's `channel` field:

  * "360dialog" (default, recommended): base `https://waba-v2.360dialog.io`, auth header
    `D360-API-KEY: {api_key}` — zero per-message markup, ~EUR49/mo flat (research §6).
  * "cloud"     (Cloud-API direct):     base `https://graph.facebook.com/v23.0/{phone_number_id}`,
    auth `Authorization: Bearer {access_token}`.

Capabilities built here (the W2 task):
  1. send_template(...) — the first business-initiated message MUST be a pre-approved template
     (research §6). Bulk marketing is flagged to route via the Marketing Messages API to dodge the
     ~7% standard-endpoint surcharge.
  2. send_text(...)     — free-text, ONLY valid inside an open session window:
       * the 72h CTWA "Free Entry Point" window (click-to-WhatsApp ad / Page CTA), OR
       * the 24h customer-service window after a user reply.
     Outside any window the connector REFUSES (returns invalid_request) — it will not silently spend
     on a template-shaped text. send_ctwa_followup(...) is the within-72h convenience wrapper.
  3. metering hook — every accepted send increments a per-message paise cost into the ledger via an
     INJECTED `meter` closure (the connector owns no ledger; it just emits the cost event). India
     rates: Marketing ~Rs0.86, Utility/Auth ~Rs0.12 (per-message model since 2025-07-01).

HARD invariants (inherited from base.py + the redteam rules):
  * Auth ONLY via vault_adapter.get_secret_json — NEVER os.environ/.env, never a `*_key` constant.
    The api_key/access_token lives on the repr-suppressed ConnectorCreds.secret_json; never logged.
  * Every network error is RETURNED as ConnectorResult(ok=False, error=...) — never raised into tick.
  * SSRF host allowlist + backoff are the base's; this subclass only sets base_url + auth headers +
    request bodies. httpx stays lazy (the package imports on an httpx-less box).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from .base import BaseConnector, ConnectorError, ConnectorResult

_log = logging.getLogger("ads_engine.connectors.whatsapp")

# Backends.
_BACKEND_360 = "360dialog"
_BACKEND_CLOUD = "cloud"

# Base URLs (vault-connectors.md §5 / research §6). Cloud-API uses the pinned Graph version.
_BASE_360 = "https://waba-v2.360dialog.io"
_BASE_CLOUD = "https://graph.facebook.com"

# Per-message India rates in PAISE (minor units) by template category. Research §6 / config EOL row.
# Marketing ~Rs0.86, Utility/Authentication ~Rs0.12, Service replies free in-window.
_RATE_PAISE = {
    "marketing": 86,
    "utility": 12,
    "authentication": 12,
    "auth": 12,
    "service": 0,
}

# The 72h CTWA Free-Entry-Point window + the 24h customer-service window, in seconds.
_CTWA_FREE_WINDOW_S = 72 * 3600
_SERVICE_WINDOW_S = 24 * 3600

# A WhatsApp recipient is an E.164-ish msisdn (digits, optional leading +). Belt-and-suspenders.
_MSISDN = re.compile(r"^\+?[1-9]\d{6,14}$")


def _category_rate_paise(category: str) -> int:
    """Per-message cost (paise) for a template category. Unknown -> marketing rate (conservative)."""
    return _RATE_PAISE.get((category or "").strip().lower(), _RATE_PAISE["marketing"])


class WhatsAppConnector(BaseConnector):
    """WhatsApp Cloud API over the shared async base. 360dialog default; Cloud-API-direct fallback.

    Construction reads the backend + ids from the decrypted cred blob (`creds.secret_json`). The
    `meter` closure is OPTIONAL and injected (the connector emits a cost event; the host writes the
    ledger). `now_fn` is injectable for deterministic window math in tests.
    """

    channel = "whatsapp"

    def __init__(
        self,
        creds: Any = None,
        *,
        version: str = "",
        http: Any = None,
        now_fn: Optional[Callable[[], float]] = None,
        meter: Optional[Callable[[dict], None]] = None,
        **kw: Any,
    ) -> None:
        blob = getattr(creds, "secret_json", None) or {}
        self._backend = str(blob.get("channel") or _BACKEND_360).strip().lower()
        if self._backend not in (_BACKEND_360, _BACKEND_CLOUD):
            self._backend = _BACKEND_360
        self._phone_number_id = str(blob.get("phone_number_id") or "").strip()
        # secrets — held transiently for per-request auth ONLY; never logged, never persisted.
        self._api_key = str(blob.get("api_key") or "").strip()        # 360dialog: D360-API-KEY
        self._access_token = str(blob.get("access_token") or "").strip()  # cloud: Bearer
        # pin the version (cloud path embeds it in the URL).
        version = version or "v23.0"
        # resolve base_url BEFORE super().__init__ so the SSRF allowlist locks to the right host.
        base_url = _BASE_360 if self._backend == _BACKEND_360 else _BASE_CLOUD
        super().__init__(creds, version=version, base_url=base_url, http=http,
                         now_fn=now_fn, **kw)
        self._meter = meter

    # -- auth: per-request header injection; the token is NEVER stored on the client/logged --------
    def _auth_headers(self) -> dict:
        if self._backend == _BACKEND_360:
            return {"D360-API-KEY": self._api_key} if self._api_key else {}
        return {"Authorization": f"Bearer {self._access_token}"} if self._access_token else {}

    # -- the messages path differs per backend ----------------------------------------------------
    def _messages_path(self) -> Optional[str]:
        """The POST .../messages path. None when a required id/token is missing (=> not_configured)."""
        if self._backend == _BACKEND_360:
            # 360dialog terminates on the WABA; no phone_number_id in the path.
            return "/messages" if self._api_key else None
        # Cloud-API-direct: /{version}/{phone_number_id}/messages
        if not (self._access_token and self._phone_number_id):
            return None
        return f"/{self.version}/{self._phone_number_id}/messages"

    @staticmethod
    def _clean_to(to: str) -> Optional[str]:
        """Normalize a recipient msisdn; None if it is not a plausible E.164 number."""
        t = str(to or "").strip().replace(" ", "").replace("-", "")
        if t.startswith("+"):
            t = t[1:]
        return t if _MSISDN.match("+" + t) else None

    def _config_error(self) -> Optional[ConnectorResult]:
        """Fail-closed envelope if creds/backend are unusable. None when good to send."""
        if not getattr(self.creds, "ok", False):
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="whatsapp: creds not ok")
        if self._messages_path() is None:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail=f"whatsapp: {self._backend} missing api_key/token/id")
        return None

    # -- metering hook: emit a per-message paise cost event (host writes the ledger) --------------
    def _meter_send(self, *, to: str, kind: str, category: str, message_id: str) -> int:
        """Increment the per-message paise cost via the injected meter closure. Returns the paise.

        NEVER raises — a metering failure must not fail the send (the message already went). The
        emitted event is secret-free: recipient is a bare msisdn (already non-secret PII the lead
        store holds), no token, no api_key.
        """
        cost = _category_rate_paise(category)
        if self._meter is None:
            return cost
        try:
            self._meter({
                "channel": "whatsapp",
                "kind": kind,                 # "template" | "text"
                "category": (category or "").strip().lower() or "marketing",
                "to": to,
                "message_id": message_id,
                "cost_minor": cost,           # paise
                "backend": self._backend,
            })
        except Exception as exc:  # noqa: BLE001 — meter is best-effort, never fails the send
            _log.warning("ads_engine.connectors.whatsapp meter failed: %r", type(exc).__name__)
        return cost

    @staticmethod
    def _extract_message_id(data: Any) -> str:
        """Pull the wamid from a WhatsApp send response. '' when absent (never raises)."""
        try:
            msgs = (data or {}).get("messages") or []
            if msgs and isinstance(msgs[0], dict):
                return str(msgs[0].get("id") or "")
        except Exception:  # noqa: BLE001
            return ""
        return ""

    # =========================================================================================
    # 1. TEMPLATE SEND — the only valid first business-initiated message.
    # =========================================================================================
    async def send_template(
        self,
        to: str,
        template: str,
        lang: str = "en",
        *,
        category: str = "marketing",
        components: Optional[list] = None,
        via_marketing_api: bool = True,
    ) -> ConnectorResult:
        """POST a pre-approved template message. Meters per-message cost on a 2xx.

        `via_marketing_api` (default True for marketing) flags routing through the Marketing Messages
        API to avoid the ~7% standard-endpoint surcharge (research §6); recorded on the result.data
        so the host/analytics can see which path was taken. The connector still posts to /messages
        (the BSP routes by category) — the flag is the cost-aware signal, not a different host.
        """
        err = self._config_error()
        if err is not None:
            return err
        clean = self._clean_to(to)
        if clean is None or not str(template or "").strip():
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="whatsapp: bad recipient or empty template")

        body: dict = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean,
            "type": "template",
            "template": {
                "name": str(template).strip(),
                "language": {"code": str(lang or "en").strip()},
            },
        }
        if components:
            body["template"]["components"] = components

        res = await self._request("POST", self._messages_path(), json=body)
        if res.ok:
            mid = self._extract_message_id(res.data)
            cost = self._meter_send(to=clean, kind="template", category=category, message_id=mid)
            # surface non-secret send metadata for the host/ledger/analytics.
            res.data = {
                "message_id": mid,
                "category": (category or "marketing").strip().lower(),
                "cost_minor": cost,
                "via_marketing_api": bool(via_marketing_api),
                "backend": self._backend,
            }
        return res

    # =========================================================================================
    # 2. FREE-TEXT SEND — valid ONLY inside an open session window.
    # =========================================================================================
    async def send_text(
        self,
        to: str,
        body: str,
        *,
        window_opened_at: Optional[float] = None,
        window: str = "service",
    ) -> ConnectorResult:
        """POST a free-text message — REFUSED unless an open window is proven by `window_opened_at`.

        `window` ∈ {"ctwa","service"}: ctwa => 72h Free-Entry-Point window (click-to-WhatsApp ad);
        service => 24h customer-service window after the user replied. `window_opened_at` is the unix
        ts the window started; None or an expired window => invalid_request (we will NOT spend on a
        text that platform policy would reject — template-only outside a window).
        """
        err = self._config_error()
        if err is not None:
            return err
        clean = self._clean_to(to)
        if clean is None or not str(body or "").strip():
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="whatsapp: bad recipient or empty text")

        span = _CTWA_FREE_WINDOW_S if (window or "").strip().lower() == "ctwa" else _SERVICE_WINDOW_S
        if window_opened_at is None or (self._now() - float(window_opened_at)) > span:
            return ConnectorResult.fail(
                ConnectorError.INVALID_REQUEST,
                detail=f"whatsapp: outside {window} window (template-only)")

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean,
            "type": "text",
            "text": {"body": str(body), "preview_url": False},
        }
        res = await self._request("POST", self._messages_path(), json=payload)
        if res.ok:
            mid = self._extract_message_id(res.data)
            # free-text inside a window is free (service category) — meter at 0 for the audit trail.
            cost = self._meter_send(to=clean, kind="text", category="service", message_id=mid)
            res.data = {"message_id": mid, "category": "service", "cost_minor": cost,
                        "window": (window or "service").strip().lower(), "backend": self._backend}
        return res

    async def send_ctwa_followup(
        self,
        to: str,
        body: str,
        *,
        click_ts: float,
    ) -> ConnectorResult:
        """Convenience: a free-text follow-up to a click-to-WhatsApp lead, within the 72h FEP window.

        `click_ts` = when the user clicked the CTWA ad (the window start). Delegates to send_text with
        window="ctwa"; outside 72h it fails closed to invalid_request (the caller should template)."""
        return await self.send_text(to, body, window_opened_at=click_ts, window="ctwa")
