"""comm.webhook — the FAIL-CLOSED inbound Telegram webhook handler (Wave 1/2 seam).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §4 S2 (webhook FAIL-CLOSED, secret bound to
the PATH tenant, GUC set only AFTER verify) + §2.3 (earner-safe) + WAVE 2 (the inbound webhook).

THE SECURITY CONTRACT (S2 — the catastrophic per-tenant surface; every clause is a gate):
  * The route is POST /comm/webhook/telegram/{tenant_id} — UNAUTHENTICATED (Telegram, a machine,
    calls it). The PATH tenant_id is UNTRUSTED until the secret proves it.
  * FAIL-CLOSED: a tenant with NO webhook secret configured (dormant) -> 403, NOT 200. (The live
    Meta webhook fails-OPEN when dormant — acceptable single-tenant, CATASTROPHIC per-tenant. We
    do the opposite here.)
  * The secret_token is bound to (PATH tenant, that tenant's bot provider_def): it is
    HMAC-SHA256(signing_secret, "telegram-webhook||{tenant_id}||{provider_def_id}"), hex. Telegram
    echoes it in the X-Telegram-Bot-Api-Secret-Token header on EVERY webhook delivery (it is set on
    setWebhook). We constant-time compare (hmac.compare_digest) the header against the value derived
    for THIS path tenant. A header that matches tenant B's secret on tenant A's path -> 403.
  * BOT-IDENTITY CROSS-CHECK: the secret already binds to the tenant's specific provider_def (its
    bot). We additionally resolve the tenant's bot via the registry so a webhook can only land for a
    tenant that actually has a Telegram bot configured (no bot -> 403).
  * The RLS tenant GUC is set ONLY AFTER the secret verify passes (inside handle()'s DB work) — a
    forged/wrong secret never reaches a DB row.
  * IDEMPOTENT on update_id: Telegram re-delivers on a non-200; we store inbound turns idempotently
    per (tenant, update_id) so a retry is a no-op.
  * W1 = REPLY-DISABLED. The LLM brain is W2 (comm/brain.py). In W1 the handler VERIFIES (the full
    fail-closed gate), stores the inbound turn into comm_sessions, and acks 200 fast — no reply, no
    Groq call. This ships the S2 security surface now; W2 flips on the brain reply.

EARNER LAW: this module rides caller.py (a separate process), imports NO agent.py, does ZERO I/O
at import, and NEVER raises out of handle() (it returns a (status_code, body) tuple the route emits).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import config, sessions, vault_read

_log = logging.getLogger("comm.webhook")

# The header Telegram sends on every webhook delivery (set via setWebhook secret_token).
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

# The HMAC domain-separation label (so this derivation can never collide with another use of
# the same signing secret — JWT/firewall/hmac-tokens).
_WEBHOOK_LABEL = "telegram-webhook"

# In-process idempotency cache of seen (tenant, update_id) — best-effort de-dup on top of the
# DB upsert (cheap fast-path; bounded). A restart re-allows a retry (harmless — append is small).
_SEEN_UPDATES: Dict[str, float] = {}
_SEEN_CAP = 4096


# ---------------------------------------------------------------------------
# signing-secret resolution — the SAME secret the setup endpoint uses to set the webhook.
# ---------------------------------------------------------------------------
def _signing_secret() -> str:
    """Resolve the webhook signing secret. Precedence (so the setup endpoint and the webhook
    handler ALWAYS derive the same secret_token for a given tenant):
      1. COMM_WEBHOOK_SIGNING_SECRET env (explicit override),
      2. the box's var/secret file (the SAME secret caller.py uses for hmac/JWT/firewall) —
         tried at the canonical box path,
      3. '' (no secret -> derive_secret_token returns '' -> the webhook FAILS CLOSED).
    NEVER raises."""
    env = (os.environ.get("COMM_WEBHOOK_SIGNING_SECRET") or "").strip()
    if env:
        return env
    # the box path caller.py writes (var/secret under the app dir). Best-effort read; '' if absent.
    for p in (os.environ.get("FAMIT_SECRET_FILE", "").strip(),
              "/opt/famit-agent/var/secret"):
        if not p:
            continue
        try:
            f = Path(p)
            if f.exists():
                s = f.read_text(encoding="utf-8").strip()
                if s:
                    return s
        except Exception:  # noqa: BLE001
            continue
    return ""


def derive_secret_token(tenant_id: str, provider_def_id: str, *, signing_secret: str = "") -> str:
    """The per-tenant Telegram webhook secret_token, bound to (tenant, that tenant's bot def).

    = HMAC-SHA256(signing_secret, "telegram-webhook||{tenant}||{provider_def_id}").hexdigest().

    This is the value passed to setWebhook(secret_token=...) AND the value Telegram echoes in the
    SECRET_HEADER on every delivery. It is deterministic (so the setup endpoint and the webhook
    agree without a DB column), bound to the PATH tenant + the bot, and never stored in plaintext
    anywhere queryable. Returns '' when no signing secret / no def id is available (-> fail-closed).
    NEVER raises. Telegram constrains secret_token to 1-256 chars of [A-Za-z0-9_-]; a hex digest
    (64 chars, [0-9a-f]) satisfies that."""
    sec = (signing_secret or _signing_secret()).strip()
    if not sec or not tenant_id or not provider_def_id:
        return ""
    msg = f"{_WEBHOOK_LABEL}||{tenant_id}||{provider_def_id}".encode("utf-8")
    try:
        return hmac.new(sec.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    except Exception:  # noqa: BLE001
        return ""


def _verify_secret(tenant_id: str, provider_def_id: str, header_value: str) -> bool:
    """Constant-time check the inbound SECRET_HEADER against THIS tenant's derived secret_token.
    FAIL-CLOSED: a missing header, a missing signing secret, or a missing provider_def -> False."""
    expected = derive_secret_token(tenant_id, provider_def_id)
    if not expected:                       # no signing secret OR no bot def -> dormant -> FAIL CLOSED
        return False
    if not header_value:                   # Telegram always sends it once configured; absence -> reject
        return False
    try:
        return hmac.compare_digest(str(header_value), expected)
    except Exception:  # noqa: BLE001
        return False


def _seen(tenant_id: str, update_id: Any) -> bool:
    """Best-effort in-process de-dup of (tenant, update_id). Returns True if ALREADY seen."""
    if update_id is None:
        return False
    key = f"{tenant_id}:{update_id}"
    import time
    if key in _SEEN_UPDATES:
        return True
    if len(_SEEN_UPDATES) >= _SEEN_CAP:     # crude bound: drop the oldest half
        for k in list(_SEEN_UPDATES.keys())[: _SEEN_CAP // 2]:
            _SEEN_UPDATES.pop(k, None)
    _SEEN_UPDATES[key] = time.time()
    return False


def _parse_inbound(update: dict) -> Optional[Dict[str, str]]:
    """Pull the inbound text + sender chat_id from a Telegram Update. Returns
    {chat_id, text, from_kind} or None if there's nothing to handle. Tolerant, never raises."""
    try:
        msg = (update or {}).get("message") or (update or {}).get("edited_message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return None
        text = msg.get("text") or msg.get("caption") or ""
        return {"chat_id": str(chat_id), "text": str(text or ""),
                "from_kind": str(chat.get("type", ""))}
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# THE HANDLER — verify (fail-closed) -> set GUC (only after) -> store -> ack.
# ---------------------------------------------------------------------------
async def handle(tenant_id: str, header_value: str, raw_body: bytes) -> Tuple[int, dict]:
    """Process one inbound Telegram webhook delivery for the PATH tenant. Returns (status_code,
    body_dict) the FastAPI route emits verbatim. NEVER raises.

    The ORDER is the security contract:
      1. master flag off -> 404-shaped dormant (handled at the route mount; here we still 403 if
         called) — resting byte-identical when COMM_ENABLED is off.
      2. resolve the tenant's bot provider_def (the bot-identity binding). No bot -> 403.
      3. VERIFY the secret_token against THIS path tenant (constant-time). Wrong/missing -> 403.
         >>> only past this line is tenant_id trusted; only now do we touch a DB row. <<<
      4. parse + idempotency (update_id) + store the inbound turn into comm_sessions (RLS GUC set
         inside sessions.* — AFTER verify).
      5. ack 200 fast. (W1: no reply. W2: the brain reply is added here.)
    """
    # (1) dormant master flag -> fail-closed (the route also self-gates; defense in depth).
    if not config.comm_enabled() or not config.telegram_enabled():
        return 403, {"ok": False, "error": "not_configured"}
    if not tenant_id:
        return 403, {"ok": False, "error": "no_tenant"}

    # (2) bot-identity binding: resolve THIS tenant's Telegram bot provider_def (RLS-scoped read).
    #     A tenant with no configured bot can receive no webhook (and there is no secret to derive).
    provider_def_id = vault_read.resolve_provider_def_id(
        tenant_id, named_provider="telegram", slug="telegram-founder"
    ) or ""
    if not provider_def_id:
        return 403, {"ok": False, "error": "no_channel"}

    # (3) FAIL-CLOSED secret verify, bound to the PATH tenant + that tenant's bot def.
    if not _verify_secret(tenant_id, provider_def_id, header_value):
        return 403, {"ok": False, "error": "bad_secret"}

    # ---- past here tenant_id is TRUSTED (the secret proved it). Only now do we touch a DB row. ----
    try:
        import json
        update = json.loads((raw_body or b"").decode("utf-8") or "{}")
    except Exception:  # noqa: BLE001
        update = {}
    if not isinstance(update, dict):
        update = {}

    update_id = update.get("update_id")
    # (4a) idempotency: a Telegram retry re-delivers the same update_id -> no-op ack.
    if _seen(tenant_id, update_id):
        return 200, {"ok": True, "dedup": True}

    parsed = _parse_inbound(update)
    if not parsed:
        # nothing actionable (a non-message update) — ack so Telegram stops retrying.
        return 200, {"ok": True, "handled": False}

    # (4b) store the inbound turn (RLS GUC bound to tenant_id INSIDE sessions.*; best-effort).
    stored = False
    try:
        sid = sessions.get_or_create(
            tenant_id, channel="telegram", external_chat_id=parsed["chat_id"],
            provider_def_id=provider_def_id,
        )
        if sid:
            stored = sessions.append_turn(
                tenant_id, sid, role="user", text_body=parsed["text"]
            )
    except Exception as exc:  # noqa: BLE001 — never raise out of the webhook
        _log.warning("comm.webhook.handle store failed: %r", type(exc).__name__)

    # (5) ack. W1 is reply-disabled (the brain is W2); we acknowledge fast so Telegram is happy.
    return 200, {"ok": True, "handled": True, "stored": bool(stored), "reply": False}
