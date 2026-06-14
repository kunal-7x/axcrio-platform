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

# The Telegram /start deep-link prefix. A tapped t.me/<bot>?start=<payload> link is delivered
# to the bot as a message whose text is "/start <payload>". We parse + verify the payload
# (comm.deeplink) to bind the contact's chat_id to (tenant, phone) + write a consent row.
_START_PREFIX = "/start"

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
# /start deep-link binding (S5) — verify the signed single-use payload, bind the contact's
# chat_id to (tenant, phone), and write a telegram_start consent row. Best-effort; never raises.
# ---------------------------------------------------------------------------
def _maybe_handle_start(tenant_id: str, provider_def_id: str, parsed: Dict[str, str]) -> Dict[str, Any]:
    """If the inbound text is a `/start <payload>` deep-link, verify it (signed, single-use, not
    expired, bound to THIS path tenant) and — on success — bind the chat_id + write a consent row.
    Returns {"is_start": bool, "bound": bool, "error": str}. NEVER raises."""
    out: Dict[str, Any] = {"is_start": False, "bound": False, "error": ""}
    text = (parsed.get("text") or "").strip()
    if not text.startswith(_START_PREFIX):
        return out
    out["is_start"] = True
    parts = text.split(None, 1)
    payload = parts[1].strip() if len(parts) > 1 else ""
    if not payload:
        out["error"] = "no_payload"          # a bare /start (no deep-link) — nothing to bind.
        return out
    try:
        from . import deeplink
        ok, phone, err = deeplink.verify(tenant_id, payload)
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.webhook start verify failed: %r", type(exc).__name__)
        return {"is_start": True, "bound": False, "error": "verify_error"}
    if not ok:
        out["error"] = err or "bad_deeplink"
        return out
    chat_id = (parsed.get("chat_id") or "").strip()
    # bind the chat_id <-> (tenant, phone) on the session, and write the consent artifact.
    try:
        sid = sessions.get_or_create(
            tenant_id, channel="telegram", external_chat_id=chat_id,
            provider_def_id=provider_def_id, contact_phone=phone,
        )
        out["bound"] = bool(sid)
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.webhook start bind failed: %r", type(exc).__name__)
    try:
        from . import consent
        consent.record_consent(
            tenant_id, contact_ref=chat_id, channel="telegram", purpose="service",
            action="grant", consent_basis="telegram_start",
            wording="Contact tapped the signed Telegram /start deep-link (opt-in to chat).",
            captured_by="contact",
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.webhook start consent failed: %r", type(exc).__name__)
    return out


# ---------------------------------------------------------------------------
# the brain reply (W2) — assemble grounding ctx -> ONE Groq call -> send -> append turn.
# Flag-gated COMM_BRAIN_ENABLED; rate + daily-Groq capped; opt-out/handoff short-circuit (free).
# ---------------------------------------------------------------------------
async def _maybe_reply(tenant_id: str, provider_def_id: str, session_id: str,
                       parsed: Dict[str, str]) -> Dict[str, Any]:
    """Generate + send the brain reply for one inbound message. Returns
    {"replied": bool, "action": str, "status": str}. NEVER raises. The webhook acks 200
    regardless of the outcome here (a draft/send failure is never an error to Telegram)."""
    out: Dict[str, Any] = {"replied": False, "action": "noted", "status": ""}
    if not config.brain_enabled():
        return out
    chat_id = (parsed.get("chat_id") or "").strip()
    incoming = (parsed.get("text") or "").strip()
    if not chat_id or not incoming:
        return out

    # (a) PRE-LLM keyword gate — opt-out / handoff. FREE, ungameable, runs BEFORE any token.
    try:
        from . import brain
        pre = brain.precheck(incoming)
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.webhook brain precheck failed: %r", type(exc).__name__)
        return out
    if pre.short_circuit:
        out["action"] = pre.action
        if pre.action == "opted_out":
            # suppress this contact (best-effort consent artifact) — NO Groq call.
            try:
                from . import consent
                consent.record_consent(
                    tenant_id, contact_ref=chat_id, channel="telegram", purpose="marketing",
                    action="revoke", consent_basis="telegram_stop",
                    wording="Contact sent a STOP/opt-out keyword on Telegram.",
                    captured_by="contact",
                )
            except Exception:  # noqa: BLE001
                pass
        # send the short canned acknowledgement (still bounded by the engine timeout). Keep the
        # terminal action (opted_out / needs_human) — a successful send must not relabel it "replied".
        await _send_reply(tenant_id, provider_def_id, session_id, chat_id, pre.reply, out,
                          keep_action=True)
        return out

    # (b) per-(tenant, chat) flood guard + per-tenant daily Groq ceiling — BEFORE the LLM call.
    try:
        from . import ratelimit
        if not ratelimit.allow_inbound(tenant_id, chat_id):
            out["action"] = "rate_limited"
            return out
        if not ratelimit.allow_groq_call(tenant_id):
            out["action"] = "groq_cap"
            return out
    except Exception:  # noqa: BLE001 — a guard failure must not block (fail-open on the guard only)
        pass

    # (c) max-turn handoff (mirrors WA_MAX_TURNS) + assemble the grounding ctx from the session.
    ctx = _build_ctx(tenant_id, session_id, incoming)
    try:
        from . import brain as _brain
        human_turns = sum(1 for t in (ctx.get("turns") or []) if (t or {}).get("role") != "assistant")
        if human_turns >= _brain.reply_max_turns():
            out["action"] = "max_turns_handoff"
            return out
        plan = _brain.generate_reply(ctx)
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.webhook brain generate failed: %r", type(exc).__name__)
        return out
    reply = (getattr(plan, "text", "") or "").strip()
    if not reply:
        out["action"] = getattr(plan, "action", "draft_failed")
        return out
    await _send_reply(tenant_id, provider_def_id, session_id, chat_id, reply, out)
    return out


def _build_ctx(tenant_id: str, session_id: str, incoming: str) -> Dict[str, Any]:
    """Assemble the brain grounding ctx from the comm_session (post-call seeds + rolling turns)
    + a best-effort cross-call memory recap. Mirrors _wa_reply_text's inputs. NEVER raises."""
    ctx: Dict[str, Any] = {"channel": "telegram", "incoming": incoming, "turns": []}
    try:
        sess = sessions.get_session(tenant_id, session_id) or {}
    except Exception:  # noqa: BLE001
        sess = {}
    ctx["turns"] = sess.get("turns") or []
    ctx["agent_name"] = sess.get("agent_persona") or "Riya"
    ctx["name"] = sess.get("name") or ""
    ctx["call_summary"] = sess.get("call_summary") or ""
    ctx["next_action"] = sess.get("next_action") or ""
    ctx["outcome"] = sess.get("outcome") or ""
    ctx["interest"] = sess.get("interest") or ""
    # campaign brand context is seeded onto the session by the post-call hook when available;
    # we read whatever is present (W1 may leave these empty -> the brain still replies generally).
    ctx["company_name"] = sess.get("company_name") or ""
    ctx["product_name"] = sess.get("product_name") or ""
    ctx["product_summary"] = sess.get("product_summary") or ""
    # cross-call memory recap (tenant-scoped; never raises). The voice earner's memory.py is the
    # source; we read it best-effort by the session's contact_phone if present.
    phone = sess.get("contact_phone") or ""
    if phone:
        ctx["memory_recap"] = _memory_recap(phone, tenant_id, ctx["agent_name"])
    return ctx


def _memory_recap(phone: str, tenant_id: str, agent_name: str) -> str:
    """Best-effort per-person cross-call recap from the voice earner's memory.py (tenant-scoped —
    the P0-LEAK fix: never read the shared legacy flat file without a tenant). Returns "" when
    memory is absent/unreadable. NEVER raises, NEVER imports caller.py/agent.py."""
    try:
        import re
        import memory as _mem  # the voice agent's cross-call store (separate module; not agent.py)
        rec = _mem.load_memory(re.sub(r"[^0-9]", "", phone or ""), tenant_id)
        return (_mem.build_recap(rec, agent_name) or "")[:500]
    except Exception:  # noqa: BLE001
        return ""


async def _send_reply(tenant_id: str, provider_def_id: str, session_id: str, chat_id: str,
                      reply: str, out: Dict[str, Any], *, keep_action: bool = False) -> None:
    """Send one Telegram reply via the engine (per-channel timeout owned there) + append the
    assistant turn to the session. Mutates `out` with the result. NEVER raises.

    `keep_action=True` (the opt-out/handoff canned ack) preserves the terminal action already on
    `out` (opted_out / needs_human) — a successful send must not relabel it "replied"."""
    if not (reply or "").strip():
        return
    try:
        from . import engine
        from .channels.base import SendEnvelope
        from .channels.telegram import CHANNEL as TG_CHANNEL
        env = SendEnvelope(to_ref=chat_id, kind="text", purpose="service", text=reply)
        res = await engine.send(
            tenant_id, env, provider_def_id=provider_def_id, channel=TG_CHANNEL,
            session_id=session_id,
        )
        out["status"] = getattr(res, "status", "")
        out["replied"] = bool(getattr(res, "ok", False))
        if getattr(res, "ok", False):
            if not keep_action:
                out["action"] = "replied"
            try:
                sessions.append_turn(tenant_id, session_id, role="assistant", text_body=reply)
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.webhook send reply failed: %r", type(exc).__name__)


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
    # (3a) BODY-SIZE CAP (W2 cost guard): an oversized body is dropped + acked 200 (so Telegram
    # stops retrying) without parsing/storing/replying. A real Telegram Update is tiny.
    try:
        if len(raw_body or b"") > config.inbound_body_max_bytes():
            return 200, {"ok": True, "handled": False, "error": "body_too_large"}
    except Exception:  # noqa: BLE001
        pass
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
        # NOTE: a media-only message (photo/document/voice with no text/caption) still parses
        # here with text="" (chat_id is present) — it does NOT crash; the brain path below
        # is a clean no-op on empty text (W2 inbound-media: don't-crash + acknowledge).
        return 200, {"ok": True, "handled": False}

    # (4a) /start DEEP-LINK (S5): a signed single-use payload binds the contact chat_id +
    # writes a telegram_start consent row. Best-effort; a bad/forged/replayed link is ignored
    # (logged in the response), the message is still stored + acked below.
    start_info = {"is_start": False, "bound": False, "error": ""}
    try:
        start_info = _maybe_handle_start(tenant_id, provider_def_id, parsed)
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.webhook.handle start failed: %r", type(exc).__name__)

    # (4b) store the inbound turn (RLS GUC bound to tenant_id INSIDE sessions.*; best-effort).
    # The session row is the brain's grounding window; keep its id for the reply path.
    stored = False
    session_id = ""
    try:
        session_id = sessions.get_or_create(
            tenant_id, channel="telegram", external_chat_id=parsed["chat_id"],
            provider_def_id=provider_def_id,
        ) or ""
        if session_id and (parsed.get("text") or "").strip():
            stored = sessions.append_turn(
                tenant_id, session_id, role="user", text_body=parsed["text"]
            )
    except Exception as exc:  # noqa: BLE001 — never raise out of the webhook
        _log.warning("comm.webhook.handle store failed: %r", type(exc).__name__)

    # (4c) THE BRAIN REPLY (W2) — flag-gated (COMM_BRAIN_ENABLED), rate + daily-Groq capped,
    # opt-out/handoff short-circuit (free, pre-LLM). A /start bare command is not replied to.
    reply_info = {"replied": False, "action": "noted", "status": ""}
    try:
        if config.brain_enabled() and not start_info.get("is_start"):
            reply_info = await _maybe_reply(tenant_id, provider_def_id, session_id, parsed)
    except Exception as exc:  # noqa: BLE001 — the reply path must never break the ack
        _log.warning("comm.webhook.handle reply failed: %r", type(exc).__name__)

    # (5) ack fast so Telegram is happy. Report what happened (store/reply/start) for diagnostics.
    body: Dict[str, Any] = {
        "ok": True, "handled": True, "stored": bool(stored),
        "reply": bool(reply_info.get("replied")), "action": reply_info.get("action", "noted"),
    }
    if start_info.get("is_start"):
        body["start"] = {"bound": bool(start_info.get("bound")), "error": start_info.get("error", "")}
    return 200, body
