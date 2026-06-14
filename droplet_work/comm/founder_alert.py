"""comm.founder_alert — the HOT-LEAD alert to the founder's own Telegram (Wave 1).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §1.1 ("Founder hot-lead alert -> Telegram:
phone + summary + score + Call-Now URL button"), §8 WAVE 1 (URL-buttons only — NO callback /
firewall in W1; that's the W5 war-room), §5.7 (the founder-alert PII transfer to Telegram is
MINIMIZED by default — "Hot lead, tap to view in panel" + link; full-PII inline only as a
tenant opt-in via COMM_FOUNDER_ALERT_FULL_PII=1).

THE SEAM:
  * `send_hot_lead_alert(tenant_id, snap) -> SendResult` — resolve the founder chat_id (the
    tenant's own configured bot's getUpdates, cached), build a channel-neutral SendEnvelope
    (text + a Call-Now URL button to the panel CRM lead, kind="alert", purpose="service"),
    and dispatch through comm.engine.send (which owns the HARD per-channel asyncio.wait_for
    timeout). Returns the uniform SendResult.

EARNER LAW (this runs ONLY inside a detached asyncio.create_task off _finalize_call):
  * the flag is checked at CALL time (config.founder_alert_enabled()); dormant -> a
    not_configured SendResult with NO network I/O.
  * NEVER raises. Every failure path returns a SendResult.
  * the destination is the tenant's OWN configured founder chat_id (never attacker-suppliable);
    we never accept a chat_id from a request body.
  * idempotency: the engine writes one comm_send_log row keyed on comms:{call_id}:alert, so a
    retried create_task can't double-log (and Telegram-side a duplicate is a benign re-send).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from . import config, engine
from .channels.base import Button, SendEnvelope, SendResult
from .channels.telegram import CHANNEL as TG_CHANNEL

_log = logging.getLogger("comm.founder_alert")


def _full_pii_enabled() -> bool:
    """Tenant opt-in to inline the lead's name/phone/summary in the Telegram alert (§5.7).
    Default OFF — the privacy-minimized default is just "Hot lead, tap to view" + panel link."""
    return (os.environ.get("COMM_FOUNDER_ALERT_FULL_PII") or "").strip().lower() in (
        "1", "true", "yes", "on")


def _panel_base() -> str:
    """The panel base URL for the Call-Now / View-in-panel deep link. Env-overridable;
    defaults to the live panel. Never raises."""
    v = (os.environ.get("PANEL_BASE_URL") or os.environ.get("FRONTEND_URL") or "").strip()
    v = v.rstrip("/")
    return v or "https://panel.famit.in"


def _lead_url(snap: Dict[str, Any]) -> str:
    """A best-effort deep link to the lead in the panel CRM (so the founder taps -> the lead
    profile with the full transcript). Falls back to the CRM index. Never raises."""
    base = _panel_base()
    phone = (snap.get("phone") or "").strip()
    if phone:
        # the CRM resolves a lead by phone; keep it a plain query (no PII beyond the number,
        # which the founder already owns) — URL buttons only, no callback.
        from urllib.parse import quote
        return f"{base}/crm?phone={quote(phone)}"
    return f"{base}/crm"


def build_alert_envelope(snap: Dict[str, Any], *, full_pii: bool | None = None) -> SendEnvelope:
    """Build the channel-neutral SendEnvelope for the founder hot-lead alert.

    PII-minimized by default (§5.7): a single "Hot lead — tap to view in panel" line + the
    score + a Call-Now URL button. With COMM_FOUNDER_ALERT_FULL_PII=1 the name/phone/summary
    are inlined (the tenant's explicit opt-in)."""
    if full_pii is None:
        full_pii = _full_pii_enabled()
    chat_id = (snap.get("founder_chat_id") or "").strip()
    score = snap.get("interest", 0) or 0
    try:
        score = int(score)
    except Exception:  # noqa: BLE001
        score = 0
    name = (snap.get("name") or "").strip() or "Lead"
    phone = (snap.get("phone") or "").strip() or "—"
    summary = (snap.get("summary") or "").strip()
    next_action = (snap.get("next_action") or "").strip()
    url = _lead_url(snap)

    if full_pii:
        lines = [
            f"\U0001F525 Hot lead: {name} ({phone}) — score {score}/100.",
        ]
        if summary:
            lines.append(f"Summary: {summary[:400]}")
        if next_action:
            lines.append(f"Next: {next_action[:200]}")
        lines.append("Tap to open in the panel.")
        text = "\n".join(lines)
    else:
        # privacy-minimized default — no name/phone/summary inline; the panel has the detail.
        text = (f"\U0001F525 Hot lead from a call — score {score}/100. "
                f"Tap to view the lead and full transcript in your panel.")

    return SendEnvelope(
        to_ref=chat_id,
        kind="alert",
        purpose="service",
        text=text,
        buttons=[Button(text="Open in panel", url=url)] if url else [],
        meta={
            "call_id": snap.get("call_id", ""),
            "score": score,
            "campaign_name": snap.get("campaign_name", ""),
        },
    )


async def send_hot_lead_alert(tenant_id: str, snap: Dict[str, Any]) -> SendResult:
    """Send the founder hot-lead alert. Resolves the founder chat_id (cached), builds the
    envelope, dispatches through the engine (per-channel timeout owned there). NEVER raises;
    dormant -> not_configured (no I/O)."""
    try:
        if not config.founder_alert_enabled():
            return SendResult.not_configured(TG_CHANNEL, "founder_alert_disabled")

        # the destination is the TENANT'S OWN configured bot's founder chat_id (cached;
        # derived from getUpdates after the founder tapped Start). Never a request value.
        chat_id = (snap.get("founder_chat_id") or "").strip()
        if not chat_id:
            chat_id = await engine.derive_founder_chat_id(tenant_id, slug="telegram-founder")
        if not chat_id:
            return SendResult.not_configured(TG_CHANNEL, "no_founder_chat_id")
        snap = dict(snap)
        snap["founder_chat_id"] = chat_id

        env = build_alert_envelope(snap)
        # idempotency: one alert per call (a retried create_task reuses this key -> one log row).
        call_id = (snap.get("call_id") or "").strip()
        if call_id:
            env.idempotency_key = f"comms:{call_id}:alert"

        return await engine.send(
            tenant_id, env,
            slug="telegram-founder",
            channel=TG_CHANNEL,
            session_id="",
            outcome=str(snap.get("outcome") or ""),
            priority=True,   # cost guard #6: the founder hot-lead alert takes the token-bucket
                             # priority lane so a journey blast can never delay it.
        )
    except Exception as exc:  # noqa: BLE001 — runs in a detached task; never crash it
        _log.warning("comm.founder_alert.send_hot_lead_alert failed: %r", type(exc).__name__)
        return SendResult.failure(TG_CHANNEL, f"alert_{type(exc).__name__}")


# In-process per-(tenant, UTC-day) de-dupe so a tripped anomaly alerts the founder ONCE per day,
# not on every subsequent send while spend stays elevated.
_ANOMALY_ALERTED: Dict[str, str] = {}


async def maybe_alert_spend_anomaly(tenant_id: str) -> SendResult:
    """COST GUARD #4 (the ALERT half): if cost_guards.check_anomaly trips (today's comm-spend >
    multiplier x the trailing-7-day median, above the floor), send the founder a spend-spike alert
    (priority lane) AT MOST ONCE per UTC day. Returns the SendResult, or a not_configured no-op
    when nothing tripped / the alert is dormant. NEVER raises (detached-task safe).

    The 'throttle' half is the budget ceiling (#2) — a tripped anomaly is the early-warning that
    spend is abnormal BEFORE it hits the hard ceiling."""
    try:
        from . import cost_guards
        from datetime import datetime, timezone
        gd = cost_guards.check_anomaly(tenant_id)
        if not gd.anomaly:
            return SendResult.not_configured(TG_CHANNEL, "no_anomaly")
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if _ANOMALY_ALERTED.get(tenant_id) == day:
            return SendResult.not_configured(TG_CHANNEL, "anomaly_already_alerted")
        if not config.founder_alert_enabled():
            # we still mark it 'detected' so the throttle (#2 ceiling) is the active control.
            _ANOMALY_ALERTED[tenant_id] = day
            return SendResult.not_configured(TG_CHANNEL, "alert_disabled_anomaly_detected")
        chat_id = await engine.derive_founder_chat_id(tenant_id, slug="telegram-founder")
        if not chat_id:
            _ANOMALY_ALERTED[tenant_id] = day
            return SendResult.not_configured(TG_CHANNEL, "no_founder_chat_id")
        d = gd.detail or {}
        today_rupees = (int(d.get("today", 0)) / 100.0)
        med_rupees = (float(d.get("median", 0)) / 100.0)
        text = (f"⚠️ Comm-spend anomaly: today ₹{today_rupees:.2f} is over "
                f"{int(config.anomaly_multiplier())}x your 7-day median (₹{med_rupees:.2f}). "
                f"Spend is being throttled at your daily ceiling. Tap to review.")
        env = SendEnvelope(to_ref=chat_id, kind="alert", purpose="service", text=text,
                           buttons=[Button(text="Review spend", url=f"{_panel_base()}/billing")],
                           meta={"anomaly": True})
        env.idempotency_key = f"comms:anomaly:{tenant_id}:{day}"
        res = await engine.send(tenant_id, env, slug="telegram-founder", channel=TG_CHANNEL,
                                priority=True)
        _ANOMALY_ALERTED[tenant_id] = day
        return res
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.founder_alert.maybe_alert_spend_anomaly failed: %r", type(exc).__name__)
        return SendResult.failure(TG_CHANNEL, f"anomaly_{type(exc).__name__}")
