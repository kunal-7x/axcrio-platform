"""voice_ops.gcal.sync — ASYNC Google Calendar event sync on booking changes (TRACKED).

WHAT THIS FIXES (founder bug 3): when a vendor has connected their calendar, AI/manual bookings
must create a REAL calendar event (lead name/phone/campaign/notes/status); reschedule/cancel must
update/delete the event. The sync must be ASYNC — it NEVER blocks the call (the BookingService
schedules these as background tasks via `_cal_bg`).

DESIGN:
  * `CalendarSync.on_booked / on_rescheduled / on_cancelled(org_id, booking)` are the three hooks
    the BookingService fires (fire-and-forget). Each:
      - mints a fresh access token via GoogleOAuth.refresh (reconnect-on-expiry handled there:
        a revoked token surfaces and the sync no-ops rather than crashing),
      - calls the Calendar v3 REST API (events.insert / patch / delete) over stdlib HTTP in a
        thread (so the network call never blocks the event loop),
      - on insert, returns the new calendar_event_id so the booking row can be updated (the
        update is performed via the injected `persist_event_id` callback / store, dormant-safe).
  * DORMANT-SAFE: with no creds (config.configured False) every hook is a no-op returning
    not_configured. NEVER raises (the call / booking is never affected).

The event body carries lead name, phone, campaign, notes, and the booking status in the
description, exactly as the founder asked. ZERO heavy imports at load (urllib is stdlib; the
oauth/vault deps are local-import-light).
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from typing import Any, Optional

from . import vault
from .config import GCalConfig
from .oauth import GoogleOAuth

log = logging.getLogger("voice_ops.gcal.sync")

_NOT_CONFIGURED = {"status": "not_configured", "reason": "calendar_not_configured"}


def _to_event_body(booking: dict, *, status: str = "") -> dict:
    """Map a booking dict -> a Google Calendar event body. Pure; carries the founder's fields."""
    name = booking.get("name") or "Lead"
    phone = booking.get("phone_display") or booking.get("phone_key") or ""
    campaign = booking.get("campaign_id") or ""
    notes = booking.get("notes") or ""
    st = status or booking.get("status") or ""
    desc_lines = [
        f"Lead: {name}",
        f"Phone: {phone}" if phone else "",
        f"Campaign: {campaign}" if campaign else "",
        f"Status: {st}" if st else "",
        f"Notes: {notes}" if notes else "",
        "Booked via Famit AI.",
    ]
    return {
        "summary": booking.get("title") or "Site Visit",
        "description": "\n".join([ln for ln in desc_lines if ln]),
        "start": {"dateTime": booking.get("slot_start")},
        "end": {"dateTime": booking.get("slot_end") or booking.get("slot_start")},
    }


class CalendarSync:
    """Async calendar fan-out. Construct with a GCalConfig + (optionally) a GoogleOAuth and a
    `persist_event_id(org_id, booking_id, event_id)` callback so a created event id is written
    back onto the booking row. Tests inject a fake `http` callable to avoid real network."""

    def __init__(self, cfg: Optional[GCalConfig] = None, *, oauth: Optional[GoogleOAuth] = None,
                 persist_event_id: Any = None, http: Any = None):
        self.cfg = cfg or GCalConfig.from_env()
        self._oauth = oauth or GoogleOAuth(self.cfg)
        self._persist = persist_event_id      # callable(org_id, booking_id, event_id) | None
        self._http = http                      # test seam: callable(method, url, token, body) -> dict

    # ------------------------------------------------------------ hooks #
    async def on_booked(self, org_id: str, booking: dict) -> dict:
        """Create a calendar event for a fresh booking. Returns {status, event_id} or
        not_configured. NEVER raises."""
        if not self.cfg.configured:
            return dict(_NOT_CONFIGURED)
        tok = await self._access_token(org_id)
        if tok is None:
            return {"status": "skipped", "reason": "no_access_token"}
        cal = tok.get("calendar_id", "primary")
        body = _to_event_body(booking, status=booking.get("status") or "booked")
        url = f"{self.cfg.api_base}/calendars/{urllib.parse.quote(cal)}/events"
        res = await self._call("POST", url, tok["access_token"], body)
        ev_id = (res or {}).get("id", "")
        if ev_id and self._persist is not None and booking.get("id"):
            await self._persist_id(org_id, booking["id"], ev_id)
        return {"status": "ok" if ev_id else "error", "event_id": ev_id}

    async def on_rescheduled(self, org_id: str, booking: dict) -> dict:
        """Patch an existing event to the new slot. If no event id is known, create one."""
        if not self.cfg.configured:
            return dict(_NOT_CONFIGURED)
        ev_id = booking.get("calendar_event_id") or ""
        if not ev_id:
            return await self.on_booked(org_id, booking)
        tok = await self._access_token(org_id)
        if tok is None:
            return {"status": "skipped", "reason": "no_access_token"}
        cal = tok.get("calendar_id", "primary")
        body = _to_event_body(booking, status="rescheduled")
        url = f"{self.cfg.api_base}/calendars/{urllib.parse.quote(cal)}/events/{urllib.parse.quote(ev_id)}"
        res = await self._call("PATCH", url, tok["access_token"], body)
        return {"status": "ok" if res is not None else "error", "event_id": ev_id}

    async def on_cancelled(self, org_id: str, booking: dict) -> dict:
        """Delete the calendar event for a cancelled booking. No-op if no event id is known."""
        if not self.cfg.configured:
            return dict(_NOT_CONFIGURED)
        ev_id = booking.get("calendar_event_id") or ""
        if not ev_id:
            return {"status": "noop", "reason": "no_event_id"}
        tok = await self._access_token(org_id)
        if tok is None:
            return {"status": "skipped", "reason": "no_access_token"}
        cal = tok.get("calendar_id", "primary")
        url = f"{self.cfg.api_base}/calendars/{urllib.parse.quote(cal)}/events/{urllib.parse.quote(ev_id)}"
        res = await self._call("DELETE", url, tok["access_token"], None)
        return {"status": "ok" if res is not None else "error", "event_id": ev_id}

    def status(self, org_id: str = "") -> dict:
        """Redacted snapshot — booleans only (safe for an API). When org_id given, reports whether
        a token row exists (no token material)."""
        out = dict(self.cfg.status())
        if org_id:
            row = vault.read_blob(org_id)
            out["connected"] = bool(row and row.get("status") == "connected")
            out["account_email"] = (row or {}).get("account_email", "")
        return out

    # --------------------------------------------------------- internals #
    async def _access_token(self, org_id: str) -> Optional[dict]:
        """Refresh -> a transient access token dict {access_token, calendar_id}, or None when not
        connected / revoked. Runs the (sync) refresh in a thread so it never blocks the loop."""
        try:
            res = await asyncio.to_thread(self._oauth.refresh, org_id)
        except Exception as exc:  # noqa: BLE001
            log.info("gcal access-token refresh failed: %r", exc)
            return None
        if res.get("status") != "ok" or not res.get("access_token"):
            return None
        return res

    async def _call(self, method: str, url: str, token: str, body: Optional[dict]) -> Optional[dict]:
        """One Calendar v3 REST call. Uses the injected test `http` seam if present; else stdlib
        urllib in a thread (never blocks the loop). Returns the parsed JSON ({} for 204 delete) or
        None on error. NEVER raises."""
        if self._http is not None:
            try:
                return await _maybe_await(self._http(method, url, token, body))
            except Exception as exc:  # noqa: BLE001
                log.info("gcal http (test seam) failed: %r", exc)
                return None
        try:
            return await asyncio.to_thread(self._http_sync, method, url, token, body)
        except Exception as exc:  # noqa: BLE001
            log.info("gcal http call failed %s %s: %r", method, url, exc)
            return None

    @staticmethod
    def _http_sync(method: str, url: str, token: str, body: Optional[dict]) -> Optional[dict]:
        import urllib.request

        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Authorization": f"Bearer {token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec - fixed googleapis host
            raw = resp.read().decode("utf-8") if resp.length != 0 else ""
        return json.loads(raw) if raw.strip() else {}

    async def _persist_id(self, org_id: str, booking_id: str, event_id: str) -> None:
        try:
            r = self._persist(org_id, booking_id, event_id)
            await _maybe_await(r)
        except Exception as exc:  # noqa: BLE001
            log.info("gcal persist_event_id failed (non-fatal): %r", exc)


async def _maybe_await(v):
    if asyncio.iscoroutine(v):
        return await v
    return v
