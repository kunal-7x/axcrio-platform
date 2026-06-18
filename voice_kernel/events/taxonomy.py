"""voice_kernel.events.taxonomy — the typed event taxonomy (W8).

ONE canonical name per meaningful action, so dashboard / CRM / analytics /
AI-Manager / reports all react from a SINGLE source of truth instead of polling.
This is the founder's whole "nothing updates in real time" fix: every box-mutating
moment in a call's life emits exactly one named Event.

The frozen wire contract is `voice_kernel.contracts.Event`
(name, call_id, tenant_id, ts_iso, payload). This module does NOT subclass or
widen it — it gives:
  - `EventName`: a str-Enum of the allowed names (the closed taxonomy);
  - small typed FACTORIES that stamp `ts_iso` canonically (UTC) and build a
    minimal, PII-light `payload`, returning a plain frozen `Event`.

Factories never raise on bad/missing optional fields — an event must never be the
thing that breaks a call (LEARNINGS §4). They DO require `call_id`/`tenant_id`
(routing keys) and let the Event itself stay a dumb frozen record.

Naming rule: past-tense snake_case facts ("call_ended", "recording_ready"),
never imperative commands — events are facts that already happened.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from ..contracts import Event
from .timeutil import now_utc_iso


class EventName(str, Enum):
    """The closed taxonomy. Adding a sink requires NO change here; adding a new
    fact type is the only reason to extend this enum (keep it append-only)."""

    # --- call lifecycle ---------------------------------------------------- #
    CALL_STARTED = "call_started"        # dial placed / inbound ring picked up
    CALL_CONNECTED = "call_connected"    # media established, conversation live
    CALL_ENDED = "call_ended"            # normal hangup (either side)
    CALL_FAILED = "call_failed"          # no-answer / busy / SIP error / crash

    # --- post-call artifacts ---------------------------------------------- #
    RECORDING_READY = "recording_ready"  # egress stored, presigned url available
    TRANSCRIPT_READY = "transcript_ready"  # full turn transcript persisted
    SUMMARY_READY = "summary_ready"      # LLM summary / lead-memory finalized

    # --- lead lifecycle (mirrors packet.Lifecycle) ------------------------ #
    LEAD_HOT = "lead_hot"
    LEAD_WARM = "lead_warm"
    LEAD_COLD = "lead_cold"
    LEAD_DEAD = "lead_dead"

    # --- downstream business actions -------------------------------------- #
    CALLBACK_SCHEDULED = "callback_scheduled"   # commitment extracted -> retry
    SITE_VISIT_BOOKED = "site_visit_booked"     # appointment booked
    HANDOFF_REQUESTED = "handoff_requested"     # hot/high-ticket -> human
    HANDOFF_DONE = "handoff_done"               # human accepted / completed
    WHATSAPP_SENT = "whatsapp_sent"             # follow-up message dispatched

    # --- ops / reliability ------------------------------------------------ #
    PROVIDER_FAILED = "provider_failed"  # stt/llm/tts/sip provider error (routing)
    DAILY_REPORT = "daily_report"        # scheduled rollup ready

    # --- real-time config (W13) ------------------------------------------- #
    CONFIG_CHANGED = "config_changed"        # a tenant's config doc changed (version bumped)
    PROVIDER_KEY_ADDED = "provider_key_added"    # a new API key joined the rotation pool
    PROVIDER_KEY_REVOKED = "provider_key_revoked"  # a key was removed/disabled
    KEY_POOL_EXHAUSTED = "key_pool_exhausted"    # a provider's pool has NO healthy key (LOUD)


# Lifecycle string -> lead event name (the memory layer hands us a Lifecycle).
_LIFECYCLE_TO_EVENT = {
    "hot": EventName.LEAD_HOT,
    "warm": EventName.LEAD_WARM,
    "cold": EventName.LEAD_COLD,
    "dead": EventName.LEAD_DEAD,
}


def _clean(payload: Optional[dict]) -> dict:
    """Drop None values so payloads stay minimal; never include falsy-by-mistake
    keys with a None. Keeps the wire small and the consumers simple."""
    if not payload:
        return {}
    return {k: v for k, v in payload.items() if v is not None}


def make_event(
    name: EventName | str,
    call_id: str,
    tenant_id: str,
    payload: Optional[dict] = None,
    ts_iso: Optional[str] = None,
) -> Event:
    """The single generic factory. Stamps `ts_iso` canonically (UTC, Z-suffixed)
    when not supplied; coerces an EventName enum to its value; never raises on a
    None payload. Routing keys (`call_id`, `tenant_id`) are coerced to str so a
    None can't silently become the literal 'None' stream key — empty stays empty
    and the bus drops it (fail-closed, never cross-tenant).

    A `ts_iso` carried INSIDE the payload (e.g. forwarded via a factory's
    `**extra`) is treated as the canonical event timestamp, NOT a payload field —
    so `call_started(..., ts_iso=...)` pins the timestamp (load-bearing for stable
    idempotency ids) instead of stamping a fresh 'now' and burying the value."""
    nm = name.value if isinstance(name, EventName) else str(name)
    body = dict(payload or {})
    ts_in_payload = body.pop("ts_iso", None)
    return Event(
        name=nm,
        call_id="" if call_id is None else str(call_id),
        tenant_id="" if tenant_id is None else str(tenant_id),
        ts_iso=ts_iso or ts_in_payload or now_utc_iso(),
        payload=_clean(body),
    )


# --------------------------------------------------------------------------- #
# Ergonomic, self-documenting factories for the founder's full list. Each
# returns a plain frozen Event; payloads are minimal + PII-light (phones are
# expected to be masked by the caller, mirroring the erasure-audit pattern).
# --------------------------------------------------------------------------- #
def call_started(call_id: str, tenant_id: str, direction: str = "outbound", **extra) -> Event:
    return make_event(EventName.CALL_STARTED, call_id, tenant_id, {"direction": direction, **extra})


def call_connected(call_id: str, tenant_id: str, **extra) -> Event:
    return make_event(EventName.CALL_CONNECTED, call_id, tenant_id, {**extra})


def call_ended(call_id: str, tenant_id: str, duration_s: Optional[int] = None, **extra) -> Event:
    return make_event(EventName.CALL_ENDED, call_id, tenant_id, {"duration_s": duration_s, **extra})


def call_failed(call_id: str, tenant_id: str, reason: str = "", **extra) -> Event:
    return make_event(EventName.CALL_FAILED, call_id, tenant_id, {"reason": reason, **extra})


def recording_ready(call_id: str, tenant_id: str, url: str = "", duration_s: Optional[int] = None, **extra) -> Event:
    return make_event(EventName.RECORDING_READY, call_id, tenant_id, {"url": url, "duration_s": duration_s, **extra})


def transcript_ready(call_id: str, tenant_id: str, turns: Optional[int] = None, **extra) -> Event:
    return make_event(EventName.TRANSCRIPT_READY, call_id, tenant_id, {"turns": turns, **extra})


def summary_ready(call_id: str, tenant_id: str, lifecycle: str = "", conversion_prob: Optional[float] = None, **extra) -> Event:
    return make_event(
        EventName.SUMMARY_READY, call_id, tenant_id,
        {"lifecycle": lifecycle or None, "conversion_prob": conversion_prob, **extra},
    )


def lead_classified(call_id: str, tenant_id: str, lifecycle: str, conversion_prob: Optional[float] = None, **extra) -> Event:
    """Map a Lifecycle value to its lead_* event. Unknown -> LEAD_COLD (safe
    floor; never silently dropped)."""
    name = _LIFECYCLE_TO_EVENT.get((lifecycle or "").lower(), EventName.LEAD_COLD)
    return make_event(name, call_id, tenant_id, {"conversion_prob": conversion_prob, **extra})


def callback_scheduled(call_id: str, tenant_id: str, preferred_ts: str = "", **extra) -> Event:
    return make_event(EventName.CALLBACK_SCHEDULED, call_id, tenant_id, {"preferred_ts": preferred_ts or None, **extra})


def site_visit_booked(call_id: str, tenant_id: str, slot_ts: str = "", **extra) -> Event:
    return make_event(EventName.SITE_VISIT_BOOKED, call_id, tenant_id, {"slot_ts": slot_ts or None, **extra})


def handoff_requested(call_id: str, tenant_id: str, reason: str = "", **extra) -> Event:
    return make_event(EventName.HANDOFF_REQUESTED, call_id, tenant_id, {"reason": reason or None, **extra})


def handoff_done(call_id: str, tenant_id: str, agent: str = "", **extra) -> Event:
    return make_event(EventName.HANDOFF_DONE, call_id, tenant_id, {"agent": agent or None, **extra})


def whatsapp_sent(call_id: str, tenant_id: str, template: str = "", **extra) -> Event:
    return make_event(EventName.WHATSAPP_SENT, call_id, tenant_id, {"template": template or None, **extra})


def provider_failed(call_id: str, tenant_id: str, provider: str = "", code: Optional[int] = None, **extra) -> Event:
    return make_event(EventName.PROVIDER_FAILED, call_id, tenant_id, {"provider": provider or None, "code": code, **extra})


def config_changed(tenant_id: str, namespace: str = "", version: Optional[int] = None,
                   updated_by: str = "", **extra) -> Event:
    """A tenant's config doc changed (vendor profile / provider keys / retention). Carries the new
    `version` so a consumer can drop a stale cache without refetching the whole blob. Tenant-scoped,
    not call-scoped: call_id = the namespace so the stream id stays meaningful + dedup is per
    (tenant, namespace, version)."""
    return make_event(
        EventName.CONFIG_CHANGED, f"config:{namespace or 'all'}", tenant_id,
        {"namespace": namespace or None, "version": version, "updated_by": updated_by or None, **extra},
    )


def provider_key_added(tenant_id: str, provider: str = "", fingerprint: str = "", **extra) -> Event:
    """A new API key joined the rotation pool (fingerprint only — NEVER the secret)."""
    return make_event(
        EventName.PROVIDER_KEY_ADDED, f"key:{provider or '?'}", tenant_id,
        {"provider": provider or None, "fingerprint": fingerprint or None, **extra},
    )


def provider_key_revoked(tenant_id: str, provider: str = "", fingerprint: str = "", **extra) -> Event:
    return make_event(
        EventName.PROVIDER_KEY_REVOKED, f"key:{provider or '?'}", tenant_id,
        {"provider": provider or None, "fingerprint": fingerprint or None, **extra},
    )


def key_pool_exhausted(tenant_id: str, provider: str = "", **extra) -> Event:
    """A provider's pool has NO healthy key — the LOUD operational alarm the founder asked for."""
    return make_event(
        EventName.KEY_POOL_EXHAUSTED, f"pool:{provider or '?'}", tenant_id,
        {"provider": provider or None, **extra},
    )


def daily_report(tenant_id: str, report_date: str = "", **extra) -> Event:
    """Tenant-scoped, not call-scoped: call_id is the report date so the stream
    ID stays meaningful and the dedup key is STABLE per (tenant, day).

    For that stability to hold, the idempotency id must NOT depend on the wall
    clock — so we PIN ts_iso to midnight of the report date (`{rd}T00:00:00Z`)
    rather than letting make_event stamp a fresh 'now'. Two report rollups for the
    same (tenant, day) therefore collapse to one event (re-run / double-trigger
    safe); a different day or extra-payload still differs. (W8 FIX-NOW 3.)"""
    rd = report_date or now_utc_iso()[:10]
    return make_event(
        EventName.DAILY_REPORT, f"report:{rd}", tenant_id,
        {"report_date": rd, **extra}, ts_iso=f"{rd}T00:00:00Z",
    )
