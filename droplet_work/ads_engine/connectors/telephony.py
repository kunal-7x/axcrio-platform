"""ads_engine.connectors.telephony — hand an ad-sourced lead to the EXISTING voice pipeline.

Design: vault-connectors.md §6 + INTERCONNECT_MAP.md §ENQUEUE. This connector is a thin ADAPTER.
It does the ONE earner-safe thing: given an ad lead (and ONLY after compliance.py has passed), it
BUILDS the `JOBS` row in the exact shape the live dispatcher writes at caller.py:5754-5768 (with
`force_window=True` for an ad-lead instant dial) and returns it to the INJECTED enqueue closure.

WHAT THIS FILE NEVER DOES (binding earner-safety, ARCH_SKELETON f.1/f.2 + INTERCONNECT §5.2):
  * It NEVER dials. No socket, no SIP, no LiveKit, no `run_job`.
  * It NEVER imports caller / agent.py / the LiveKit triple. `agent.py` stays byte-identical.
  * It NEVER mutates the live JOBS map. leads.py (not this file) does
    `JOBS[job_id] = build_call_job(...)` + `asyncio.create_task(run_job(job_id))`. This module
    only owns the ROW SHAPE + an optional enqueue helper that defers to an injected closure.

The JOBS row is a 1:1 mirror of caller.py:5754-5768 (verified on disk 2026-06-25):
    JOBS[job_id] = {
        "state": "queued", "campaign_id": cid, "tenant_id": tenant_id,
        "concurrency": conc, "hourly_cap": ..., "daily_cap": ...,
        "force_window": <bool>,
        "leads": [{"name", "num", "status":"queued", "room":"", "launched_at":0.0, "attempt":0}],
    }

OPEN FORK #1 (vault-connectors.md §10 + research §1/§7): India TCCCPR makes promotional voice
originate on a 140-series CLI through a registered telemarketer (a plain 10-digit promo call is now
a violation). The default backend is the live LiveKit/SIP trunk (byte-untouched). An optional
Exotel-AgentStream 140-series promo path is a STUB here, OFF by default behind config.TELEPHONY_BACKEND
— it changes only the descriptor shape, never the live dial path, and is not wired in this wave.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

_log = logging.getLogger("ads_engine.connectors.telephony")

# Backends (OPEN FORK #1). Default = the live trunk; "exotel" is an off-by-default 140-series stub.
BACKEND_LIVEKIT = "livekit"
BACKEND_EXOTEL = "exotel"

# Conservative per-job caps for an instant single-lead ad dial (clamped like caller.py:5752).
_DEFAULT_CONCURRENCY = 1
_DEFAULT_HOURLY_CAP = 1
_DEFAULT_DAILY_CAP = 1
_MAX_CONCURRENCY = 20  # the same hard ceiling caller.py clamps to.


def _lead_name(lead: dict) -> str:
    """The lead's display name, tolerating the lead/leads_ads field drift. '' when absent."""
    for k in ("name", "full_name", "lead_name"):
        v = (lead or {}).get(k)
        if v:
            return str(v).strip()
    return ""


def _lead_num(lead: dict) -> str:
    """The lead's phone number, tolerating num/phone/number drift. '' when absent (=> rejected)."""
    for k in ("num", "phone", "number", "msisdn", "phone_number"):
        v = (lead or {}).get(k)
        if v:
            return str(v).strip()
    return ""


def build_call_job(
    tenant_id: str,
    campaign_id: str,
    lead: dict,
    *,
    concurrency: int = _DEFAULT_CONCURRENCY,
    hourly_cap: int = _DEFAULT_HOURLY_CAP,
    daily_cap: int = _DEFAULT_DAILY_CAP,
    force_window: bool = True,
    backend: str = BACKEND_LIVEKIT,
) -> dict:
    """Build the JOBS row for ONE ad lead — the exact caller.py:5754-5768 shape. Pure (no IO/no dial).

    `force_window=True` is the ad-lead "dial now" semantic (the :5763 field) — an ad lead clicked
    intent NOW, so run_job skips the out-of-window idle. Caps are clamped to the same ceilings the
    live dispatcher uses. Raises ValueError on a lead with no usable number (fail-LOUD here, because
    a numberless job would silently never dial — better to reject at build time than enqueue a dud).

    The returned dict is byte-compatible with what `run_job` consumes; leads.py assigns it into JOBS.
    """
    tid = str(tenant_id or "").strip()
    cid = str(campaign_id or "").strip()
    if not tid:
        raise ValueError("telephony.build_call_job: empty tenant_id")
    num = _lead_num(lead or {})
    if not num:
        raise ValueError("telephony.build_call_job: lead has no phone number")

    conc = max(1, min(int(concurrency), _MAX_CONCURRENCY))
    job: dict = {
        "state": "queued",
        "campaign_id": cid,
        "tenant_id": tid,
        "concurrency": conc,
        "hourly_cap": max(1, int(hourly_cap)),
        "daily_cap": max(1, int(daily_cap)),
        # ad-lead instant dial: mirrors the caller.py:5763 force_window field.
        "force_window": bool(force_window),
        "leads": [{
            "name": _lead_name(lead or {}),
            "num": num,
            "status": "queued",
            "room": "",
            "launched_at": 0.0,
            "attempt": 0,
        }],
    }

    # OPEN FORK #1 — Exotel 140-series promo-CLI STUB (off by default). When explicitly selected we
    # ATTACH a non-default descriptor; we do NOT alter the live row shape and do NOT dial. leads.py
    # ignores this field on the LiveKit path; an Exotel adapter (not built this wave) would read it.
    if str(backend or BACKEND_LIVEKIT).strip().lower() == BACKEND_EXOTEL:
        job["telephony_backend"] = BACKEND_EXOTEL
        job["promo_cli_series"] = "140"  # TCCCPR promotional-voice CLI series (research §1/§5)

    return job


class TelephonyConnector:
    """The hand-off adapter. Builds the JOBS row + defers the actual enqueue to an INJECTED closure.

    Deliberately NOT a BaseConnector subclass: telephony makes NO outbound HTTP from ads_engine — the
    dial path is the live LiveKit/SIP pipeline this connector never touches. It exists so
    `connectors.get_connector(tenant, "telephony")` can return a uniform object, and so leads.py has
    one place to build the row.

    `enqueue` is the injected closure leads.py provides (it wraps `JOBS[jid]=row` +
    `create_task(run_job(jid))`). This class NEVER holds JOBS / run_job itself.
    """

    channel = "telephony"

    def __init__(
        self,
        creds: Any = None,
        *,
        version: str = "",
        http: Any = None,
        enqueue: Optional[Callable[[str, str, dict], Any]] = None,
        backend: str = "",
        **kw: Any,
    ) -> None:
        self.creds = creds
        self.version = version
        # `http` is accepted for a uniform constructor signature but UNUSED — telephony never calls out.
        self._enqueue = enqueue
        # backend default comes from config.TELEPHONY_BACKEND when present; else the live trunk.
        self._backend = (str(backend).strip().lower() or self._cfg_backend())

    @staticmethod
    def _cfg_backend() -> str:
        """Resolve the configured telephony backend (config.TELEPHONY_BACKEND), default 'livekit'."""
        try:
            from .. import config
            val = config.cfg("TELEPHONY_BACKEND", BACKEND_LIVEKIT)
        except Exception:  # noqa: BLE001 — degrade-never-raise -> live trunk
            return BACKEND_LIVEKIT
        v = (str(val).strip().lower() or BACKEND_LIVEKIT)
        return v if v in (BACKEND_LIVEKIT, BACKEND_EXOTEL) else BACKEND_LIVEKIT

    def build_call_job(self, tenant_id: str, campaign_id: str, lead: dict, **kw: Any) -> dict:
        """Instance wrapper around the module-level builder, pinning the connector's backend."""
        kw.setdefault("backend", self._backend)
        return build_call_job(tenant_id, campaign_id, lead, **kw)

    def hand_off(self, tenant_id: str, campaign_id: str, lead: dict, **kw: Any) -> dict:
        """Build the row and hand it to the injected enqueue closure. Returns a NON-secret receipt.

        This is the ONLY place ads_engine "triggers" a call, and it does so EXCLUSIVELY through the
        injected closure — never JOBS/run_job directly. If no enqueue is wired, the row is built and
        returned with handed_off=False (dormant) so the caller can see it without anything dialing.
        Never raises into the spine on an enqueue error (it is swallowed + surfaced as handed_off
        False) — but a malformed lead still raises from build_call_job (fail-loud at build time).
        """
        job = self.build_call_job(tenant_id, campaign_id, lead, **kw)
        handed = False
        if self._enqueue is not None:
            try:
                self._enqueue(str(tenant_id or "").strip(), str(campaign_id or "").strip(), job)
                handed = True
            except Exception as exc:  # noqa: BLE001 — enqueue failure must not crash the spine
                _log.warning("ads_engine.connectors.telephony enqueue failed: %r",
                             type(exc).__name__)
                handed = False
        return {
            "ok": handed,
            "handed_off": handed,
            "backend": self._backend,
            "force_window": bool(job.get("force_window")),
            "lead_count": len(job.get("leads") or []),
            "campaign_id": job.get("campaign_id", ""),
        }
