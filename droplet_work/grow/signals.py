"""grow.signals — ★ THE FLAGSHIP: the Revenue-Truth Signal Loop (GROWTH-OS §11).

The moat. Platforms optimize toward the events you feed them; almost every SMB feeds
them junk ("Lead submitted"). We own the GROUND TRUTH — the voice-call outcome + the
WhatsApp conversation + the booking + the sale — and convert it into Conversions API
events with **value = lead-quality score**, so Meta/Google's ML literally hunts for
people who *answer calls and buy*, not people who fill forms. (ElevateX §5 / deck §9.)

This module:
  * builds the per-journey event ladder (Lead → QualifiedLead → Schedule → Attended →
    Purchase), idempotent via `event_id = sha256(journey_id|step)` (browser/server dedup);
  * attaches max matching keys (UNSALTED capi_hash of normalized ph/em/fn/ln + raw
    fbc/fbclid/gclid/ctwa_clid), raw PII NEVER persisted — only the key TYPES land in the
    ledger;
  * estimates EMQ (match quality 0-10) from key coverage so the dashboard can warn before
    a low-quality upload;
  * runs in SHADOW MODE by default — logs the exact would-send payload to the dispatch
    ledger and POSTs nothing — until real CAPI creds + GROW_SIGNALS_LIVE=1 are set. This
    is the ElevateX "build CAPI in Phase 1, even crudely" done safely.

stdlib at import; httpx imported lazily ONLY on a live POST. Never raises into the loop.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .config import GrowConfig
from .model import (Journey, ScoredLead, SignalEvent, SignalStatus, capi_hash,
                    normalize_email, normalize_name, normalize_phone)

log = logging.getLogger("grow.signals")


class SignalDispatcher:
    """Construct with a GrowConfig + a SignalStore (for dedup + the ledger).
    `emit(...)` is the single entry point used by the loop."""

    def __init__(self, config: Optional[GrowConfig] = None, store=None):
        self.cfg = config or GrowConfig()
        self.store = store     # grow.store.SignalStore (optional; dedup degrades to off)

    # ----------------------------------------------------------------- public #
    def emit(self, journey: Journey, scored: Optional[ScoredLead], step: str, *,
             value: Optional[int] = None, raw_phone: str = "", raw_email: str = "",
             raw_name: str = "", currency: str = "INR") -> SignalEvent:
        """Build + dispatch (or shadow-log) one ladder event. Idempotent per
        (journey, step). Never raises — returns a SignalEvent describing what happened."""
        try:
            return self._emit(journey, scored, step, value, raw_phone, raw_email,
                              raw_name, currency)
        except Exception as exc:  # noqa: BLE001
            log.info("grow.signals.emit failed: %r", exc)
            return SignalEvent(
                tenant_id=getattr(journey, "tenant_id", ""), event_id="",
                journey_id=getattr(journey, "journey_id", ""),
                event_name=step, status=SignalStatus.FAILED, reason=f"emit_error:{exc!r}"[:200])

    def should_emit_qualified(self, scored: Optional[ScoredLead]) -> bool:
        """The QualifiedLead gate (§11.1): score >= hot_threshold OR a sales-ready tier."""
        if scored is None:
            return False
        return scored.score >= self.cfg.hot_threshold or scored.sales_ready

    # ----------------------------------------------------------------- core #
    def _emit(self, journey: Journey, scored: Optional[ScoredLead], step: str,
              value: Optional[int], raw_phone: str, raw_email: str, raw_name: str,
              currency: str) -> SignalEvent:
        tenant_id = journey.tenant_id
        event_id = self._event_id(journey.journey_id, step)

        # idempotency: if we've already dispatched this (journey, step), don't double-fire
        if self.store is not None:
            try:
                prior = self.store.get(tenant_id, event_id)
            except Exception:  # noqa: BLE001
                prior = None
            if prior is not None and prior.status in (SignalStatus.SENT, SignalStatus.ACKED,
                                                      SignalStatus.SHADOW):
                ev = prior.copy()
                ev.status = SignalStatus.DEDUPED
                ev.reason = "already_dispatched"
                return ev

        # value: ladder Lead/QualifiedLead carry the lead-quality score; deeper carry money
        if value is None:
            value = int(scored.score) if scored is not None else 0

        user_data, key_types = self._user_data(journey, raw_phone, raw_email, raw_name)
        emq = self._emq(key_types)
        platform = "meta"  # Meta is the Phase-1 platform; Google EC is a later step
        action_source = self._action_source(journey)

        ev = SignalEvent(
            tenant_id=tenant_id, event_id=event_id, journey_id=journey.journey_id,
            lead_id=(scored.lead_id if scored else ""), platform=platform, endpoint="capi",
            event_name=step, value=int(value), currency=currency,
            match_keys=key_types, emq_estimate=emq)

        payload = self._meta_payload(ev, user_data, action_source)

        # ---- dispatch decision ----
        if not self.cfg.meta_live:
            ev.status = SignalStatus.SHADOW
            ev.reason = ("shadow_mode" if self.cfg.shadow_mode else "meta_creds_absent")
            log.info("grow.signals SHADOW %s value=%s emq=%.1f keys=%s payload=%s",
                     step, value, emq, key_types, _redact(payload))
        else:
            ok, reason = self._post_meta(payload)
            ev.status = SignalStatus.ACKED if ok else SignalStatus.FAILED
            ev.reason = reason

        if self.store is not None:
            try:
                self.store.append(ev)
            except Exception as exc:  # noqa: BLE001
                log.info("grow.signals ledger append failed: %r", exc)
        return ev

    # ----------------------------------------------------------------- helpers #
    @staticmethod
    def _event_id(journey_id: str, step: str) -> str:
        return capi_hash(f"{journey_id}|{step}")

    @staticmethod
    def _action_source(journey: Journey) -> str:
        if journey.ctwa_clid:
            return "business_messaging"   # CTWA path (§11.2) — keyed on ctwa_clid
        if journey.fbclid:
            return "website"
        return "system_generated"         # server-side qualified-lead (phone-call truth)

    def _user_data(self, journey: Journey, raw_phone: str, raw_email: str,
                   raw_name: str) -> tuple[dict, list]:
        """Build CAPI user_data with max matching keys. capi_hash is UNSALTED (so Meta can
        match); raw values are consumed here and never persisted. Returns (user_data,
        list-of-key-types-present)."""
        ud: dict = {}
        keys: list[str] = []
        ph = normalize_phone(raw_phone)
        if ph:
            ud["ph"] = [capi_hash(ph)]
            keys.append("ph")
        em = normalize_email(raw_email)
        if em:
            ud["em"] = [capi_hash(em)]
            keys.append("em")
        nm = normalize_name(raw_name)
        if nm:
            parts = nm.split(" ", 1)
            ud["fn"] = [capi_hash(parts[0])]
            keys.append("fn")
            if len(parts) > 1:
                ud["ln"] = [capi_hash(parts[1])]
                keys.append("ln")
        # click identifiers travel UN-hashed
        if journey.ctwa_clid:
            ud["ctwa_clid"] = journey.ctwa_clid
            keys.append("ctwa_clid")
        if journey.fbclid:
            ud["fbc"] = journey.fbclid if journey.fbclid.startswith("fb.") else f"fb.1.{int(time.time())}.{journey.fbclid}"
            keys.append("fbc")
        # external_id = our salted principal_ref (a stable, privacy-clean id we can reuse)
        if journey.principal_ref:
            ud["external_id"] = [journey.principal_ref]
            keys.append("external_id")
        return ud, keys

    @staticmethod
    def _emq(key_types: list) -> float:
        """EMQ proxy 0-10 from key coverage (real EMQ comes back from Meta post-send).
        Target ≥8 on the optimization event (§11.3)."""
        w = {"ph": 3.0, "em": 2.0, "fbc": 2.0, "ctwa_clid": 2.0, "fn": 0.7, "ln": 0.7,
             "external_id": 1.0}
        return round(min(10.0, sum(w.get(k, 0.0) for k in key_types)), 2)

    def _meta_payload(self, ev: SignalEvent, user_data: dict, action_source: str) -> dict:
        data = {
            "event_name": ev.event_name,
            "event_time": int(time.time()),
            "event_id": ev.event_id,                  # browser/server dedup ≥90% (§11.3)
            "action_source": action_source,
            "user_data": user_data,
            "custom_data": {"value": ev.value, "currency": ev.currency,
                            "lead_event_source": "Haptica Grow", "event_source": "crm"},
        }
        body = {"data": [data]}
        if self.cfg.meta_capi_test_event_code:
            body["test_event_code"] = self.cfg.meta_capi_test_event_code
        return body

    def _post_meta(self, payload: dict) -> tuple[bool, str]:
        """Live POST to the Meta CAPI. Lazy httpx import; fail-closed (never raises)."""
        try:
            import httpx  # noqa: PLC0415  (lazy — only on a live send)
        except Exception:  # noqa: BLE001
            return False, "httpx_unavailable"
        url = (f"https://graph.facebook.com/{self.cfg.meta_graph_version}"
               f"/{self.cfg.meta_pixel_id}/events")
        try:
            r = httpx.post(url, params={"access_token": self.cfg.meta_capi_token},
                           json=payload, timeout=self.cfg.dispatch_timeout_s)
            if r.status_code // 100 == 2:
                got = (r.json() or {}).get("events_received")
                return True, f"events_received={got}"
            return False, f"meta_{r.status_code}:{r.text[:160]}"
        except Exception as exc:  # noqa: BLE001
            return False, f"post_error:{exc!r}"[:200]

    # ----------------------------------------------------------------- health #
    def health(self, tenant_id: str) -> dict:
        """The per-tenant Signal Health card (§11.3): EMQ, dedup, ladder coverage,
        click-id coverage, shadow/live split. Optimizer should downgrade autonomy when
        this is red (honesty rule)."""
        rows: list[SignalEvent] = []
        if self.store is not None:
            try:
                rows = self.store.list(tenant_id)
            except Exception:  # noqa: BLE001
                rows = []
        total = len(rows)
        by_status: dict = {}
        ladder: dict = {}
        emq_vals = []
        with_click = 0
        for r in rows:
            by_status[r.status] = by_status.get(r.status, 0) + 1
            ladder[r.event_name] = ladder.get(r.event_name, 0) + 1
            if r.emq_estimate:
                emq_vals.append(r.emq_estimate)
            if any(k in r.match_keys for k in ("ctwa_clid", "fbc")):
                with_click += 1
        deduped = by_status.get(SignalStatus.DEDUPED, 0)
        live = by_status.get(SignalStatus.SENT, 0) + by_status.get(SignalStatus.ACKED, 0)
        unique = max(0, total - deduped)
        return {
            "total": total, "unique": unique, "by_status": by_status,
            "ladder_coverage": ladder,
            "avg_emq_estimate": round(sum(emq_vals) / len(emq_vals), 2) if emq_vals else 0.0,
            "dedup_rate": round(deduped / total, 4) if total else 0.0,
            "click_id_coverage": round(with_click / unique, 4) if unique else 0.0,
            "live_dispatched": live,
            "shadow_dispatched": by_status.get(SignalStatus.SHADOW, 0),
            "failed": by_status.get(SignalStatus.FAILED, 0),
            "mode": "live" if self.cfg.meta_live else "shadow",
        }


def _redact(payload: dict) -> dict:
    """Log-safe view: drop the hashed user_data values, keep the key names only."""
    try:
        d = dict(payload.get("data", [{}])[0])
        ud = d.get("user_data", {})
        d["user_data"] = {k: ("<hash>" if isinstance(v, list) else "<id>") for k, v in ud.items()}
        return {"data": [d], "test_event_code": payload.get("test_event_code", "")}
    except Exception:  # noqa: BLE001
        return {"redacted": True}
