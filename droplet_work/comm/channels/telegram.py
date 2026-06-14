"""comm.channels.telegram — the Telegram Bot API channel adapter (Wave 1).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §2.1 (the ChannelAdapter contract) + WAVE 1
(Telegram-only: send_text/photo/document/video, dormancy-safe, file_id cache, founder chat_id
from getUpdates) + the W1-P0 build-log (the token is in the LIVE vault).

WHAT THIS DOES (Bot API, async, NEVER raises):
  * send(SendEnvelope) -> SendResult  — routes to sendMessage / sendPhoto / sendVideo /
    sendDocument by the envelope kind+media; renders inline-keyboard URL buttons; returns the
    provider message_id + any file_id to cache (§1.2 #6 — re-send media at ₹0).
  * verify() -> (ok, username)         — a getMe identity check (the channel-setup "Test" button).
  * derive_founder_chat_id()           — read getUpdates, return the chat_id of the user who
    tapped Start to the bot (the hot-lead-alert destination), cached in-process.
  * status()                           — 'configured' (token present) | 'not_configured'.

SECURITY / EARNER LAW:
  * the token is read FRESH from the vault each construction (rotation-safe), NEVER logged,
    NEVER on argv, NEVER persisted on any object beyond this adapter instance,
  * the token is in the Bot API URL path (api.telegram.org/bot<TOKEN>/method) — so we redact
    it from every log line and never echo a URL,
  * every HTTP request carries a short timeout; the engine wraps send() in an outer wait_for,
  * api.telegram.org is the fixed, hard-coded host (no user-supplied base_url -> no SSRF surface
    here; the SSRF guard is for the self-hosted-provider path, not this fixed vendor),
  * import does ZERO I/O and NEVER raises (httpx is imported lazily; absent -> dormant).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .base import Button, MediaItem, SendEnvelope, SendResult

_log = logging.getLogger("comm.channels.telegram")

_API_ROOT = "https://api.telegram.org"
CHANNEL = "telegram"

# In-process cache of the derived founder chat_id, keyed by a token fingerprint (NOT the token)
# so a token rotation invalidates the cache. We never store the token here.
_FOUNDER_CHATID_CACHE: Dict[str, str] = {}


def _token_fp(token: str) -> str:
    """A short, non-reversible fingerprint of the token for cache keys + safe logging.
    NEVER the token itself."""
    import hashlib
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()[:12]


def _redact_url(url: str) -> str:
    """Strip the bot token out of an api.telegram.org URL before it can hit a log."""
    try:
        import re
        return re.sub(r"/bot[^/]+/", "/bot<redacted>/", url or "")
    except Exception:  # noqa: BLE001
        return "<telegram-url>"


# ---------------------------------------------------------------------------
# async HTTP — lazy httpx, NEVER raises, short timeout, token-redacted logs.
# ---------------------------------------------------------------------------
async def _api_call(token: str, method: str, payload: dict, *, timeout: float) -> Tuple[bool, Optional[dict], str]:
    """POST to the Bot API method. Returns (ok, result_dict_or_None, error_code). NEVER raises.
    `ok` reflects the Telegram `ok:true` envelope, not just HTTP 200."""
    if not token:
        return False, None, "no_token"
    try:
        import httpx  # type: ignore
    except Exception:  # noqa: BLE001
        return False, None, "httpx_unavailable"
    url = f"{_API_ROOT}/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            data = None
        if resp.status_code >= 400:
            # Telegram returns a 'description' on errors — surface a short code, never the URL/token.
            desc = ""
            if isinstance(data, dict):
                desc = str(data.get("description", ""))[:120]
            return False, data if isinstance(data, dict) else None, f"http_{resp.status_code}:{desc}"
        if isinstance(data, dict) and data.get("ok") is True:
            return True, data.get("result"), ""
        desc = str(data.get("description", "")) if isinstance(data, dict) else ""
        return False, data if isinstance(data, dict) else None, f"tg_not_ok:{desc[:120]}"
    except Exception as exc:  # noqa: BLE001 — network/timeout -> fail-closed, token-safe log
        code = type(exc).__name__
        _log.warning("telegram._api_call %s failed (%s) url=%s", method, code, _redact_url(url))
        return False, None, f"net_{code}"


def _inline_keyboard(buttons: List[Button]) -> Optional[dict]:
    """Build the reply_markup for inline-keyboard URL buttons (W1: url-only — no callbacks)."""
    rows = []
    for b in buttons or []:
        if b and (b.url or "").strip() and (b.text or "").strip():
            rows.append([{"text": b.text.strip(), "url": b.url.strip()}])
    if not rows:
        return None
    return {"inline_keyboard": rows}


def _extract_file_id(result: Optional[dict], media_kind: str) -> str:
    """Pull the provider file_id out of a sendPhoto/Video/Document result so the engine can
    cache it for a zero-cost re-send (§1.2 #6). Returns '' if absent."""
    if not isinstance(result, dict):
        return ""
    try:
        if media_kind == "photo":
            photos = result.get("photo") or []
            # the largest size is last
            if photos and isinstance(photos, list):
                return str(photos[-1].get("file_id", ""))
        elif media_kind == "video":
            v = result.get("video") or {}
            return str(v.get("file_id", ""))
        elif media_kind == "document":
            d = result.get("document") or {}
            return str(d.get("file_id", ""))
    except Exception:  # noqa: BLE001
        return ""
    return ""


# ---------------------------------------------------------------------------
# The adapter.
# ---------------------------------------------------------------------------
class TelegramAdapter:
    """Implements comm.channels.base.ChannelAdapter for Telegram. Construct with a token
    (read fresh from the vault by the engine). Dormant + never-raises when the token is empty."""

    channel = CHANNEL

    def __init__(self, token: str = "", *, http_timeout_s: float = 6.0,
                 provider_def_id: str = "", provider_name: str = "telegram"):
        # The token lives only on this instance (never persisted elsewhere, never logged).
        self._token = (token or "").strip()
        self._timeout = float(http_timeout_s or 6.0)
        self.provider_def_id = provider_def_id
        self.provider_name = provider_name

    # ---- contract: status / cost ----
    def status(self) -> str:
        return "configured" if self._token else "not_configured"

    def estimate_cost_minor(self, env: SendEnvelope) -> int:  # noqa: ARG002 — Telegram is free
        """Telegram sends are free — always 0 paise (a send still writes ONE wallet row at
        cost 0 in the engine, per the per-message-metering law)."""
        return 0

    # ---- contract: send ----
    async def send(self, env: SendEnvelope) -> SendResult:
        """Route the envelope to the right Bot API method. NEVER raises."""
        if not self._token:
            return SendResult.not_configured(self.channel)
        to = (env.to_ref or "").strip()
        if not to:
            return SendResult.failure(self.channel, "no_destination")

        reply_markup = _inline_keyboard(env.buttons)

        # media path: send the FIRST media item with the text as its caption.
        media = [m for m in (env.media or []) if isinstance(m, MediaItem)]
        if media:
            return await self._send_media(to, media[0], env.text or "", reply_markup)

        # text path.
        return await self._send_text(to, env.text or "", reply_markup)

    async def _send_text(self, chat_id: str, text: str, reply_markup: Optional[dict]) -> SendResult:
        if not (text or "").strip():
            return SendResult.failure(self.channel, "empty_text")
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:4096],                 # Bot API hard cap
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        ok, result, err = await _api_call(self._token, "sendMessage", payload, timeout=self._timeout)
        if not ok:
            return SendResult.failure(self.channel, err)
        mid = str((result or {}).get("message_id", "")) if isinstance(result, dict) else ""
        return SendResult.success(self.channel, external_id=mid, provider=self.provider_name)

    async def _send_media(self, chat_id: str, m: MediaItem, caption: str,
                          reply_markup: Optional[dict]) -> SendResult:
        kind = (m.kind or "photo").lower()
        method = {"photo": "sendPhoto", "video": "sendVideo", "document": "sendDocument"}.get(kind)
        if method is None:
            return SendResult.failure(self.channel, f"bad_media_kind:{kind}")
        field = {"photo": "photo", "video": "video", "document": "document"}[kind]
        # source priority: cached file_id > presigned/public URL (NEVER base64). local_path
        # (multipart) is intentionally NOT implemented in W1 — presigned Spaces URLs are the
        # plan's mandated path; a local_path-only item degrades to a clean failure.
        src = (m.file_id or "").strip() or (m.url or "").strip()
        if not src:
            return SendResult.failure(self.channel, "no_media_source")
        payload: Dict[str, Any] = {"chat_id": chat_id, field: src}
        cap = (caption or m.caption or "").strip()
        if cap:
            payload["caption"] = cap[:1024]      # Bot API caption cap
        if reply_markup:
            payload["reply_markup"] = reply_markup
        ok, result, err = await _api_call(self._token, method, payload, timeout=self._timeout)
        if not ok:
            return SendResult.failure(self.channel, err)
        mid = str((result or {}).get("message_id", "")) if isinstance(result, dict) else ""
        file_id = _extract_file_id(result, kind)
        return SendResult.success(self.channel, external_id=mid, provider=self.provider_name,
                                  file_id_cached=file_id)

    # ---- verify (the channel-setup "Test" button) ----
    async def verify(self) -> Tuple[bool, str]:
        """getMe identity check. Returns (ok, username). NEVER raises, NEVER logs the token."""
        if not self._token:
            return False, ""
        ok, result, _err = await _api_call(self._token, "getMe", {}, timeout=self._timeout)
        if ok and isinstance(result, dict):
            return True, str(result.get("username", ""))
        return False, ""

    # ---- derive the founder chat_id (getUpdates; cached) ----
    async def derive_founder_chat_id(self, *, force: bool = False) -> str:
        """Read getUpdates and return the chat_id of the user who tapped Start to the bot —
        the destination for the founder hot-lead alert. Cached in-process keyed by a token
        fingerprint (so a rotation re-derives). Returns '' if no message has been received yet.
        NEVER raises, NEVER logs the token.

        Picks the MOST RECENT private-chat message's chat id (the founder messaged the bot
        from their own account); a group/channel update is ignored (the alert is a DM)."""
        if not self._token:
            return ""
        fp = _token_fp(self._token)
        if not force and fp in _FOUNDER_CHATID_CACHE:
            return _FOUNDER_CHATID_CACHE[fp]
        ok, result, _err = await _api_call(self._token, "getUpdates",
                                           {"limit": 100, "timeout": 0}, timeout=self._timeout)
        if not ok or not isinstance(result, list):
            return ""
        chat_id = ""
        # walk newest -> oldest; take the first private-chat sender.
        for upd in reversed(result):
            msg = (upd or {}).get("message") or (upd or {}).get("edited_message") or {}
            chat = msg.get("chat") or {}
            if str(chat.get("type", "")) == "private" and chat.get("id") is not None:
                chat_id = str(chat.get("id"))
                break
        if chat_id:
            _FOUNDER_CHATID_CACHE[fp] = chat_id
        return chat_id
