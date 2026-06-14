"""comm.post_call — the post-call orchestration off caller.py:_finalize_call (Wave 1).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §2.3 (the earner-safe post-call seam),
§1.1 (founder hot-lead alert + post-call auto-summary to the contact), §5.3 (the post-call
auto-message records a consent artifact BEFORE the first contact-facing send), §8 WAVE 1.

THE TWO PUBLIC SEAMS (what caller.py:_finalize_call uses):

  1. `snapshot(rec, tr, camp_fields, *, tenant_id, call_id) -> dict`
     A PURE-SYNCHRONOUS dict copy of ONLY the fields the detached sends need. It holds NO
     reference to the live `rec` / `tr` / `it` objects the dial loop keeps mutating, NO open
     files, NO db handles — just str/int primitives. This is THE earner-safety contract: the
     caller.py hook calls this synchronously on the hot path (cheap dict reads, no I/O), THEN
     create_task's `run(...)` on the immutable snapshot. The reads here DUPLICATE the field
     reads in caller.py (`_wa_draft_followup_text` etc.) by design — we do NOT refactor the
     live earner's helper (additive-and-isolated beats DRY when the shared code is the earner).

  2. `run(snap) -> dict`   (async; the body of the detached task)
     Orchestrates up to two fire-and-forget sends, each through comm.engine.send which owns the
     HARD per-channel asyncio.wait_for timeout:
       (a) HOT-LEAD ALERT to the founder's Telegram   (gated FEATURE_TELEGRAM_FOUNDER_ALERT)
       (b) post-call AUTO-SUMMARY to the contact       (gated FEATURE_TELEGRAM_FOLLOWUP)
     A consent artifact is written (best-effort, append-only) BEFORE the contact send (§5.3).
     NEVER raises (it runs detached; an unhandled exception would be an orphaned task warning).

EARNER LAW: this module is imported by caller.py but its `run` only ever executes inside
asyncio.create_task — NEVER awaited on the dial loop. Every flag is read at call time; all OFF
=> `run` returns immediately with NO network I/O. It imports NO agent.py.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

_log = logging.getLogger("comm.post_call")

# The hot-lead score gate — mirrors caller.py's existing `_score >= 70` lead.qualified branch
# (the same threshold that already fires notify_handoff_team). Kept here so the comm alert
# fires on EXACTLY the same definition of "hot" the earner already uses.
HOT_LEAD_MIN_SCORE = 70


# ---------------------------------------------------------------------------
# (1) the synchronous snapshot — pure dict copy, NO live-object references.
# ---------------------------------------------------------------------------
def snapshot(
    rec: Optional[dict],
    tr: Optional[dict],
    camp_fields: Optional[dict],
    *,
    tenant_id: str,
    call_id: str = "",
) -> Dict[str, Any]:
    """Build the immutable post-call snapshot SYNCHRONOUSLY (no I/O, no live refs).

    Called on the hot path in _finalize_call; must be cheap + total. Every value is a plain
    primitive copied out of the dicts — the returned snapshot shares NO mutable object with
    the live `rec` / `tr` / `camp_fields` (we read scalars, and `str(...)`/`int(...)` them)."""
    rec = rec or {}
    tr = tr or {}
    cf = camp_fields or {}

    def _i(v: Any) -> int:
        try:
            return int(v or 0)
        except Exception:  # noqa: BLE001
            return 0

    score = _i(rec.get("interest", 0)) or _i(tr.get("interest", 0))
    return {
        "tenant_id": str(tenant_id or ""),
        "call_id": str(call_id or rec.get("id") or ""),
        # contact / lead identity
        "phone": str(rec.get("phone", "") or ""),
        "name": str(rec.get("name", "") or ""),
        # call result
        "outcome": str(rec.get("outcome", "") or ""),
        "interest": score,
        "duration_s": _i(rec.get("duration_s", 0)),
        "room": str(rec.get("room", "") or ""),
        "campaign_name": str(rec.get("campaign_name", "") or ""),
        # transcript-derived (duplicate of _wa_draft_followup_text reads — NOT a refactor)
        "summary": str(tr.get("summary", "") or ""),
        "next_action": str(tr.get("next_action", "") or ""),
        # campaign brand context (duplicate reads)
        "company_name": str(cf.get("company_name", "") or ""),
        "product_name": str(cf.get("product_name", "") or ""),
        "agent_name": str(cf.get("agent_name", "Riya") or "Riya"),
        "lead_source": str(cf.get("lead_source", "") or rec.get("lead_source", "") or ""),
        # the contact's Telegram chat_id IF a prior /start deep-link bound it (W2+). In W1 this
        # is normally empty -> the auto-summary has no deliverable Telegram destination and is a
        # clean no-op (the founder alert is the W1-proven real-reach). Never blocks either way.
        "contact_chat_id": str(rec.get("telegram_chat_id", "") or tr.get("telegram_chat_id", "") or ""),
        # the founder chat_id is resolved lazily in the task (cached getUpdates), not here.
    }


# ---------------------------------------------------------------------------
# helpers — the hot-lead gate + the contact auto-summary text.
# ---------------------------------------------------------------------------
def is_hot_lead(snap: Dict[str, Any]) -> bool:
    """The SAME 'hot' definition caller.py already uses for notify_handoff_team:
    a real (non-opt-out) call with interest score >= 70."""
    if (snap.get("outcome") or "").strip() == "opt_out":
        return False
    try:
        return int(snap.get("interest", 0) or 0) >= HOT_LEAD_MIN_SCORE
    except Exception:  # noqa: BLE001
        return False


def _draft_summary_text(snap: Dict[str, Any]) -> str:
    """The contact-facing post-call auto-summary. ONE optional Groq call (reusing the box's
    _groq_chat is a caller.py concern; here in the comm package we keep it dependency-free and
    deterministic so the module imports clean offline). A short, warm Hinglish recap + one next
    step, mirroring _wa_draft_followup_text's intent WITHOUT importing the earner helper."""
    agent = (snap.get("agent_name") or "Riya").strip() or "Riya"
    company = (snap.get("company_name") or "").strip()
    product = (snap.get("product_name") or "").strip()
    name = (snap.get("name") or "").strip() or "ji"
    summary = (snap.get("summary") or "").strip()
    next_action = (snap.get("next_action") or "").strip()

    greet = f"Hi {name}, this is {agent}" + (f" from {company}" if company else "") + "."
    body = ""
    if summary:
        body = f" Thanks for the call — quick recap: {summary[:300]}"
    elif product:
        body = f" Thanks for the call about {product}."
    else:
        body = " Thanks for taking the call."
    step = ""
    if next_action:
        step = f" Next step: {next_action[:160]}."
    tail = " Reply here if you have any questions."
    return (greet + body + step + tail).strip()


# ---------------------------------------------------------------------------
# (2) the detached task body — alert + auto-summary, each engine-timeout-bounded.
# ---------------------------------------------------------------------------
async def run(snap: Dict[str, Any]) -> Dict[str, Any]:
    """The body of the detached post-call task. NEVER awaited on the dial loop (caller.py
    create_task's it). Orchestrates the founder alert + the contact auto-summary, each via
    comm.engine.send (per-channel timeout owned there). NEVER raises."""
    out: Dict[str, Any] = {"alert": "skip", "summary": "skip"}
    try:
        from . import config  # call-time flag reads
        if not config.comm_enabled():
            return out
        tenant_id = (snap.get("tenant_id") or "").strip()
        if not tenant_id:
            return out

        # (a) FOUNDER HOT-LEAD ALERT — only for a hot lead, only when the flag is on.
        if config.founder_alert_enabled() and is_hot_lead(snap):
            try:
                from . import founder_alert
                res = await founder_alert.send_hot_lead_alert(tenant_id, snap)
                out["alert"] = getattr(res, "status", "sent" if getattr(res, "ok", False) else "failed")
            except Exception as exc:  # noqa: BLE001
                _log.warning("comm.post_call founder alert failed: %r", type(exc).__name__)
                out["alert"] = "error"

        # (b) POST-CALL AUTO-SUMMARY to the contact — only when the flag is on AND a deliverable
        # Telegram destination exists (the contact previously /start-ed the bot; W2+). In W1 this
        # is normally a clean no-op (no contact chat_id) — never an error, never a block.
        if config.followup_enabled():
            contact_chat = (snap.get("contact_chat_id") or "").strip()
            if not contact_chat:
                out["summary"] = "no_destination"
            elif (snap.get("outcome") or "").strip() == "opt_out":
                out["summary"] = "suppressed_optout"
            else:
                # §5.3 — record the service-implicit consent artifact BEFORE the contact send.
                try:
                    from . import consent
                    consent.record_consent(
                        tenant_id,
                        contact_ref=contact_chat,
                        channel="telegram",
                        purpose="service",
                        action="grant",
                        lead_source=snap.get("lead_source", ""),
                        wording="Post-call summary auto-sent to the contact after the phone call.",
                        captured_by="system",
                        call_id=snap.get("call_id", ""),
                    )
                except Exception as exc:  # noqa: BLE001
                    _log.warning("comm.post_call consent write failed: %r", type(exc).__name__)
                try:
                    from . import engine
                    from .channels.base import SendEnvelope
                    from .channels.telegram import CHANNEL as TG_CHANNEL
                    call_id = (snap.get("call_id") or "").strip()
                    env = SendEnvelope(
                        to_ref=contact_chat,
                        kind="summary",
                        purpose="service",
                        text=_draft_summary_text(snap),
                        idempotency_key=(f"comms:{call_id}:summary" if call_id else ""),
                        meta={"call_id": call_id},
                    )
                    res = await engine.send(
                        tenant_id, env, slug="telegram-founder",
                        channel=TG_CHANNEL, outcome=str(snap.get("outcome") or ""))
                    out["summary"] = getattr(res, "status",
                                             "sent" if getattr(res, "ok", False) else "failed")
                except Exception as exc:  # noqa: BLE001
                    _log.warning("comm.post_call summary send failed: %r", type(exc).__name__)
                    out["summary"] = "error"
        return out
    except Exception as exc:  # noqa: BLE001 — detached task; never propagate
        _log.warning("comm.post_call.run failed: %r", type(exc).__name__)
        return out
