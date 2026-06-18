"""voice_kernel.events.serde — Event <-> Redis-stream-field (de)serialization.

Redis stream entries are flat field->value maps. We encode the whole Event into a
SMALL fixed set of fields, with the variable `payload` JSON-encoded into ONE
field (RESEARCH-DECISIONS §8) so nested dicts survive and the field set never
explodes. Decode is the exact inverse, tolerant of a missing/garbage payload
(a poison entry must be parseable enough to route to the DLQ, never crash the
consumer loop).

Idempotency key (`iid`): the producer-stamped, consumer-deduped identity of a
logical event. We derive it as `name:call_id:digest8(ts_iso+payload)` so the SAME
logical fact emitted twice (retry, double-call) collapses to one, while two
genuinely-different facts on the same call never collide.
"""
from __future__ import annotations

import hashlib
import json

from ..contracts import Event


def idempotency_id(event: Event) -> str:
    """Stable per-logical-event id. Deterministic for the same content, so a
    re-emit of the identical event dedupes; sorted-keys JSON makes it
    order-independent."""
    body = json.dumps(event.payload or {}, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha1(f"{event.ts_iso}|{body}".encode("utf-8")).hexdigest()[:8]
    return f"{event.name}:{event.call_id}:{digest}"


def encode(event: Event) -> dict:
    """Event -> flat str->str field map for XADD. `payload` is one JSON field."""
    return {
        "name": event.name,
        "call_id": event.call_id,
        "tenant_id": event.tenant_id,
        "ts_iso": event.ts_iso,
        "iid": idempotency_id(event),
        "payload": json.dumps(event.payload or {}, separators=(",", ":"), default=str),
    }


def decode(fields: dict) -> Event:
    """Flat field map (str OR bytes keys/values, depending on redis decode mode)
    -> Event. Tolerant: a bad/missing payload decodes to {} rather than raising,
    so a poison entry still yields a routable Event for the DLQ."""
    f = _normalize(fields)
    raw = f.get("payload", "") or ""
    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {"_raw": payload}
    except Exception:
        payload = {"_undecodable": raw}
    return Event(
        name=f.get("name", ""),
        call_id=f.get("call_id", ""),
        tenant_id=f.get("tenant_id", ""),
        ts_iso=f.get("ts_iso", ""),
        payload=payload,
    )


def decoded_iid(fields: dict) -> str:
    """Read the producer-stamped iid straight off the stream fields (no re-hash),
    so consumer-side dedup matches the producer key exactly."""
    return _normalize(fields).get("iid", "")


def _normalize(fields: dict) -> dict:
    """Coerce bytes keys/values to str (redis-py returns bytes unless the client
    is created with decode_responses=True). Idempotent for str maps."""
    out = {}
    for k, v in (fields or {}).items():
        kk = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
        vv = v.decode() if isinstance(v, (bytes, bytearray)) else v
        out[kk] = vv
    return out
