"""comm.engine — the channel-agnostic send engine (Wave 1).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §2.2 ("the resolver + the dispatch seam —
channels are off the voice hot path entirely; post-call, async") + §2.3 (earner-safety:
EVERY contact-facing send is bounded by a per-channel asyncio.wait_for timeout) + WAVE 1.

THE ONE PUBLIC SEAM:
  * `send(tenant_id, env, *, provider_def_id=..., slug=..., named_provider="telegram",
          session_id=..., outcome="") -> SendResult`
    resolves the tenant's channel adapter (token read FRESH from the LIVE vault), sends the
    envelope under a HARD per-channel timeout, and writes ONE comm_send_log row (idempotent
    on comms:{message_id}). Returns the uniform SendResult.

  * `resolve_telegram_adapter(tenant_id, *, provider_def_id, slug, named_provider)`
    -> (TelegramAdapter | None, provider_def_id) — the resolver, exposed so callers (the
    founder-alert / post-call hooks, the channel-setup "Test") can reuse the SAME path.

  * `verify_telegram(tenant_id, ...)`           -> (ok, username) (the setup Test button).
  * `derive_founder_chat_id(tenant_id, ...)`    -> chat_id str (the hot-lead-alert destination).

EARNER LAW (this is the heart of the safety contract):
  * The engine is ASYNC. The dial loop NEVER awaits it — the caller.py hook does
    asyncio.create_task(engine.send(...)). Inside, every adapter call is wrapped in
    asyncio.wait_for(..., config.send_timeout_s()) so a hung / black-holed provider can NEVER
    keep the detached task alive past the bound -> status='timeout', logged, done.
  * NEVER raises. Every failure path returns a SendResult and (best-effort) a send_log row.
  * The flags are checked at CALL time (config.*). A dormant flag -> a 'not_configured'
    SendResult with NO network I/O. Resting byte-identical.
  * This module imports NO agent.py and does ZERO I/O at import.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Tuple

from . import config, send_log, vault_read
from .channels.base import SendEnvelope, SendResult
from .channels.telegram import CHANNEL as TG_CHANNEL, TelegramAdapter

_log = logging.getLogger("comm.engine")


# ---------------------------------------------------------------------------
# resolver — build the tenant's adapter with a freshly-read token (never cached).
# ---------------------------------------------------------------------------
def resolve_telegram_adapter(
    tenant_id: str,
    *,
    provider_def_id: str = "",
    slug: str = "telegram-founder",
    named_provider: str = "telegram",
) -> Tuple[Optional[TelegramAdapter], str]:
    """Resolve the tenant's Telegram adapter (token read FRESH from the vault). Returns
    (adapter | None, resolved_provider_def_id). None when the channel flag is off, no
    provider_def is found, or the token is missing/undecryptable. NEVER raises."""
    if not config.telegram_enabled():
        return None, provider_def_id
    pdid = provider_def_id or vault_read.resolve_provider_def_id(
        tenant_id, named_provider=named_provider, slug=slug
    )
    if not pdid:
        return None, ""
    token = vault_read.get_channel_token(tenant_id, pdid)
    if not token:
        return None, pdid
    adapter = TelegramAdapter(
        token,
        http_timeout_s=config.http_timeout_s(),
        provider_def_id=pdid,
        provider_name=named_provider,
    )
    return adapter, pdid


# ---------------------------------------------------------------------------
# the dispatch seam — send under a hard per-channel timeout + log the result.
# ---------------------------------------------------------------------------
async def send(
    tenant_id: str,
    env: SendEnvelope,
    *,
    provider_def_id: str = "",
    slug: str = "telegram-founder",
    named_provider: str = "telegram",
    channel: str = TG_CHANNEL,
    session_id: str = "",
    outcome: str = "",
    log: bool = True,
) -> SendResult:
    """Resolve -> send (bounded) -> log. The single consumer entrypoint. NEVER raises.

    `env.idempotency_key` (comms:{message_id}) makes a retried create_task safe: the same
    key writes the send_log row once. If absent, the engine mints a fresh message_id."""
    if not config.comm_enabled():
        return SendResult.not_configured(channel, "comm_disabled")
    if channel != TG_CHANNEL:
        # W1 = Telegram only; other channels are dormant (Email W3 / SMS W5).
        return SendResult.not_configured(channel, "channel_not_enabled")

    # a stable message_id for the log + idempotency (reuse the envelope's key if present).
    message_id = (env.idempotency_key or "").replace("comms:", "").strip() or send_log.new_message_id()
    if not env.idempotency_key:
        env.idempotency_key = send_log.idem_key_for(message_id)

    adapter, pdid = resolve_telegram_adapter(
        tenant_id, provider_def_id=provider_def_id, slug=slug, named_provider=named_provider
    )
    if adapter is None:
        res = SendResult.not_configured(channel, "no_channel_or_token")
        if log:
            _safe_log(tenant_id, message_id, env, res, pdid, session_id, outcome)
        return res

    # HARD per-channel timeout — the earner-safety cap. A black-holed provider -> 'timeout'.
    try:
        res = await asyncio.wait_for(adapter.send(env), timeout=config.send_timeout_s())
    except asyncio.TimeoutError:
        res = SendResult.failure(channel, "send_timeout", status="timeout")
    except Exception as exc:  # noqa: BLE001 — adapter promised never to raise, but be paranoid
        res = SendResult.failure(channel, f"engine_{type(exc).__name__}")

    if log:
        _safe_log(tenant_id, message_id, env, res, pdid, session_id, outcome)
    return res


def _safe_log(tenant_id: str, message_id: str, env: SendEnvelope, res: SendResult,
              provider_def_id: str, session_id: str, outcome: str) -> None:
    """Best-effort comm_send_log write. NEVER raises (a log failure must not crash the task)."""
    try:
        media_ref = ""
        if env.media:
            m0 = env.media[0]
            media_ref = (getattr(m0, "file_id", "") or getattr(m0, "spaces_key", "")
                         or getattr(m0, "url", ""))
        send_log.record_send(
            tenant_id,
            message_id=message_id,
            channel=res.channel or TG_CHANNEL,
            status=res.status,
            to_ref=env.to_ref,
            kind=env.kind,
            purpose=env.purpose,
            body_preview=env.preview(),
            provider_def_id=provider_def_id or "",
            session_id=session_id or "",
            media_ref=media_ref,
            cost_minor=res.cost_minor,
            external_id=res.external_id,
            error_code=res.error_code,
            outcome=outcome or "",
            idempotency_key=env.idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.engine._safe_log failed: %r", type(exc).__name__)


# ---------------------------------------------------------------------------
# verify / chat-id derivation — the channel-setup helpers (reuse the resolver).
# ---------------------------------------------------------------------------
async def verify_telegram(
    tenant_id: str,
    *,
    provider_def_id: str = "",
    slug: str = "telegram-founder",
    named_provider: str = "telegram",
) -> Tuple[bool, str]:
    """The channel-setup "Test" — getMe identity check. Returns (ok, username). NEVER raises."""
    adapter, _pdid = resolve_telegram_adapter(
        tenant_id, provider_def_id=provider_def_id, slug=slug, named_provider=named_provider
    )
    if adapter is None:
        return False, ""
    try:
        return await asyncio.wait_for(adapter.verify(), timeout=config.send_timeout_s())
    except Exception:  # noqa: BLE001
        return False, ""


async def derive_founder_chat_id(
    tenant_id: str,
    *,
    provider_def_id: str = "",
    slug: str = "telegram-founder",
    named_provider: str = "telegram",
    force: bool = False,
) -> str:
    """Derive the founder chat_id from getUpdates (cached). The hot-lead-alert destination.
    Returns '' if the founder hasn't messaged the bot yet. NEVER raises."""
    adapter, _pdid = resolve_telegram_adapter(
        tenant_id, provider_def_id=provider_def_id, slug=slug, named_provider=named_provider
    )
    if adapter is None:
        return ""
    try:
        return await asyncio.wait_for(adapter.derive_founder_chat_id(force=force),
                                      timeout=config.send_timeout_s())
    except Exception:  # noqa: BLE001
        return ""


async def set_telegram_webhook(
    tenant_id: str,
    webhook_url: str,
    *,
    provider_def_id: str = "",
    slug: str = "telegram-founder",
    named_provider: str = "telegram",
) -> Tuple[bool, str, str]:
    """Register the inbound webhook with Telegram (setWebhook), binding the per-tenant
    secret_token (comm.webhook.derive_secret_token) so every delivery carries it in the
    X-Telegram-Bot-Api-Secret-Token header. Returns (ok, provider_def_id, error). NEVER raises.

    This is the channel-setup wiring: the panel "Connect webhook" button calls it once; thereafter
    Telegram posts updates to webhook_url with the secret header the fail-closed handler checks."""
    adapter, pdid = resolve_telegram_adapter(
        tenant_id, provider_def_id=provider_def_id, slug=slug, named_provider=named_provider
    )
    if adapter is None or not pdid:
        return False, pdid, "no_channel_or_token"
    if not (webhook_url or "").strip().lower().startswith("https://"):
        # Telegram requires an https webhook URL.
        return False, pdid, "webhook_url_must_be_https"
    try:
        from .webhook import derive_secret_token  # local import (avoid import cycle at module load)
        secret_token = derive_secret_token(tenant_id, pdid)
    except Exception:  # noqa: BLE001
        secret_token = ""
    if not secret_token:
        return False, pdid, "no_signing_secret"
    payload = {
        "url": webhook_url.strip(),
        "secret_token": secret_token,
        "allowed_updates": ["message", "edited_message"],
        "drop_pending_updates": True,
    }
    try:
        from .channels.telegram import _api_call  # the token-redacting Bot API client
        ok, _result, err = await asyncio.wait_for(
            _api_call(adapter._token, "setWebhook", payload, timeout=config.http_timeout_s()),
            timeout=config.send_timeout_s(),
        )
        return bool(ok), pdid, ("" if ok else (err or "setWebhook_failed"))
    except asyncio.TimeoutError:
        return False, pdid, "setWebhook_timeout"
    except Exception as exc:  # noqa: BLE001
        return False, pdid, f"setWebhook_{type(exc).__name__}"


def status() -> dict:
    """Diagnostic — never a secret. Reflects the flags + datastore reachability."""
    return {
        "flags": config.config_snapshot(),
        "vault_available": vault_read.available(),
        "send_log_available": send_log.available(),
    }
