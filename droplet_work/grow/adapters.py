"""grow.adapters — DEEP WIRING of the L3 orchestrator to the live voice/WhatsApp infra.

Replaces the orchestrator's dormant channel seams with REAL connections:

  * WhatsApp — a self-contained Meta Cloud-API (Graph) sender, env-cred-gated. Needs ZERO
    caller.py code: with META_WA_TOKEN + META_WA_PHONE_NUMBER_ID + an approved welcome
    template it fires a real WhatsApp the instant a lead is captured.
  * Voice   — the <60s outbound AI call. The dial lives in caller.py (run_job/SIP/LiveKit),
    so caller.py REGISTERS a dial callback here at mount; grow just calls it. Late-binding
    via a process registry so registration can happen AFTER the grow singleton is built.

main-loop capture: the live dial schedules `run_job` on the FastAPI event loop via
run_coroutine_threadsafe; `set_main_loop()` is called from an async request context (auto_lead
/ the ingest endpoint) so the loop is the right one even though scoring runs in a worker thread.

Everything dormant-safe: no creds / no registration => skipped_no_config (records the intent,
fires nothing). stdlib at import; httpx lazy (only on a real send). Never raises."""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from .model import CapturedLead, ChannelResult, ChannelStatus, Journey, normalize_phone

log = logging.getLogger("grow.adapters")

# Process registry: caller.py injects the live dial/send here at mount time.
_REGISTRY: dict = {"whatsapp": None, "voice": None}
_MAIN_LOOP = None


def register_whatsapp_sender(fn: Callable) -> None:
    _REGISTRY["whatsapp"] = fn
    log.info("grow: live WhatsApp sender registered")


def register_voice_caller(fn: Callable) -> None:
    _REGISTRY["voice"] = fn
    log.info("grow: live voice caller registered")


def clear_registrations() -> None:
    """Test helper."""
    _REGISTRY["whatsapp"] = None
    _REGISTRY["voice"] = None


def set_main_loop(loop) -> None:
    """Called from an async request context so the voice dial can schedule run_job on the
    real FastAPI loop (run_coroutine_threadsafe) from the scoring worker thread."""
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def get_main_loop():
    return _MAIN_LOOP


# =========================================================================== #
# Self-contained Meta Cloud-API (Graph) WhatsApp sender — no caller.py needed.
# =========================================================================== #
def _wa_creds() -> "tuple[str, str]":
    tok = (os.getenv("META_WA_TOKEN") or os.getenv("META_WHATSAPP_TOKEN")
           or os.getenv("WHATSAPP_TOKEN") or "").strip()
    pnid = (os.getenv("META_WA_PHONE_NUMBER_ID") or os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
    return tok, pnid


def graph_whatsapp_send(captured: CapturedLead, journey: Journey) -> ChannelResult:
    """Fire an approved welcome TEMPLATE (Meta requires a template to OPEN a conversation
    outside the 24h window). Dormant-safe: missing creds/template/phone -> skipped."""
    tok, pnid = _wa_creds()
    if not tok or not pnid:
        return ChannelResult("whatsapp", ChannelStatus.SKIPPED_NO_CONFIG, reason="no_wa_creds")
    phone = normalize_phone(getattr(captured, "phone", "") or "")
    if not phone:
        return ChannelResult("whatsapp", ChannelStatus.SKIPPED_NO_CONFIG, reason="no_phone")
    template = (os.getenv("GROW_WA_WELCOME_TEMPLATE") or "").strip()
    if not template:
        return ChannelResult("whatsapp", ChannelStatus.SKIPPED_NO_CONFIG, reason="no_template")
    ver = (os.getenv("META_GRAPH_VERSION") or "v21.0").strip()
    lang = (os.getenv("GROW_WA_LANG") or "en").strip()
    try:
        import httpx  # noqa: PLC0415 (lazy — only on a live send)
    except Exception:  # noqa: BLE001
        return ChannelResult("whatsapp", ChannelStatus.FAILED, reason="httpx_unavailable")
    body = {"messaging_product": "whatsapp", "to": phone, "type": "template",
            "template": {"name": template, "language": {"code": lang}}}
    try:
        r = httpx.post(f"https://graph.facebook.com/{ver}/{pnid}/messages",
                       headers={"Authorization": f"Bearer {tok}"}, json=body, timeout=10)
        if r.status_code // 100 == 2:
            mid = ((r.json() or {}).get("messages") or [{}])[0].get("id", "")
            return ChannelResult("whatsapp", ChannelStatus.FIRED, ref=mid or "sent")
        return ChannelResult("whatsapp", ChannelStatus.FAILED, reason=f"meta_{r.status_code}:{r.text[:120]}")
    except Exception as exc:  # noqa: BLE001
        return ChannelResult("whatsapp", ChannelStatus.FAILED, reason=f"err:{exc!r}"[:120])


# =========================================================================== #
# Late-binding live adapters — GrowLoop's default channel seams.
# =========================================================================== #
def _wrap(name: str, fn: Callable, captured: CapturedLead, journey: Journey) -> ChannelResult:
    try:
        r = fn(captured, journey)
        if isinstance(r, ChannelResult):
            return r
        # tolerate a plain ref string / dict from a registered live fn
        if isinstance(r, dict):
            return ChannelResult(name, r.get("status", ChannelStatus.FIRED),
                                 ref=str(r.get("ref", "")), reason=str(r.get("reason", "")))
        return ChannelResult(name, ChannelStatus.FIRED, ref=str(r or ""))
    except Exception as exc:  # noqa: BLE001
        return ChannelResult(name, ChannelStatus.FAILED, reason=f"reg_err:{exc!r}"[:120])


def live_whatsapp_sender(captured: CapturedLead, journey: Journey) -> ChannelResult:
    """Registered live sender first (caller.py's proven _wa_send), else the self-contained
    Graph sender, else dormant."""
    fn = _REGISTRY["whatsapp"]
    if fn is not None:
        return _wrap("whatsapp", fn, captured, journey)
    return graph_whatsapp_send(captured, journey)


def live_voice_caller(captured: CapturedLead, journey: Journey) -> ChannelResult:
    """Registered live dial (caller.py owns run_job/SIP), else dormant."""
    fn = _REGISTRY["voice"]
    if fn is None:
        return ChannelResult("voice", ChannelStatus.SKIPPED_NO_CONFIG,
                             reason="no_voice_caller_registered")
    return _wrap("voice", fn, captured, journey)


def status() -> dict:
    tok, pnid = _wa_creds()
    return {
        "whatsapp_registered": _REGISTRY["whatsapp"] is not None,
        "voice_registered": _REGISTRY["voice"] is not None,
        "graph_wa_creds": bool(tok and pnid),
        "graph_wa_template": bool((os.getenv("GROW_WA_WELCOME_TEMPLATE") or "").strip()),
        "main_loop_bound": _MAIN_LOOP is not None,
    }
