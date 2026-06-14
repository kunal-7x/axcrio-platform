"""trunk_registry.livekit_sync — build/sync a LiveKit-SIP trunk + dispatch-rule from a row (T2, NEW).

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.3 (LiveKit-SIP wiring — drives the SAME LiveKit
the agent dials, NO container restart; multi-trunk is NATIVE) + §3 red-team D (DELETE refuses an
env/`_global`/AIM trunk; default soft-disable) + §8 (this is the genuinely-NEW glue).

WHAT IT DOES (pure config-builders + an injectable LiveKit Server-API client):
  * `build_outbound_trunk_request(trunk, sip_password)` -> the request OBJECT for
    CreateSIPOutboundTrunk (host/transport/numbers/auth), built from a registry SipTrunk row.
  * `build_inbound_trunk_request(trunk)` + `build_dispatch_rule_request(trunk, tenant_id)` -> the
    inbound trunk + a dispatch rule carrying `metadata:{tenant_id}` (multi-tenant DID->agent
    routing).
  * `create_outbound_trunk(...)` / `create_inbound_trunk(...)` / `create_dispatch_rule(...)` /
    `delete_trunk(...)` — call the LiveKit Server API through an INJECTED async client (the SAME
    `api.LiveKitAPI` caller.py:2829 already constructs). Adding/removing a trunk OBJECT via the
    API needs NO container restart — LiveKit-SIP multi-trunk is native.

EARNER-SAFETY (non-negotiable):
  * NEVER imports agent.py. NEVER constructs its own LiveKit client at import — the client is
    INJECTED by the caller (T3/T5), so importing this module is pure + does ZERO network I/O.
  * The LiveKit SDK (`livekit.api`) is imported LAZILY inside the builders, and its absence is
    tolerated (the builders fall back to a plain dict the test/inspector can assert on). So this
    module imports cleanly on a build box with no LiveKit SDK.
  * RED-TEAM D — `delete_trunk` REFUSES to delete the env-protected live trunk id
    (LIVEKIT_SIP_TRUNK_ID) or any id flagged `protected_ids`; the registry default for 'remove'
    is a soft-disable of the DB row, not a LiveKit delete. A genuine hard-delete is PIN-gated +
    audited at the endpoint layer (T3); this module is the last-line refusal.

This module is dormant until T3 mounts it AND the flag is ON — flag-OFF nothing calls it.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, List, Optional

from .schema import Encryption, SipTrunk, Transport

_log = logging.getLogger("trunk_registry.livekit_sync")


# The env var caller.py reads for the LIVE outbound trunk id (the one the earner dials). A
# LiveKit-delete of THIS id would kill the live trunk -> always refused (red-team D).
_ENV_PROTECTED_TRUNK = "LIVEKIT_SIP_TRUNK_ID"


def _lk_api():
    """Lazily import the LiveKit Server-API request/enum module. Returns the module or None
    (absent on a build box). NEVER raises at import time — the builders degrade to plain dicts."""
    try:
        from livekit import api  # type: ignore
        return api
    except Exception:  # noqa: BLE001
        return None


def _transport_enum(api, trunk: SipTrunk):
    """Map our transport string to the LiveKit SIPTransport enum (or the raw string if absent)."""
    t = trunk.transport.value if isinstance(trunk.transport, Transport) else str(trunk.transport or "udp")
    if api is None:
        return t
    try:
        return {
            "udp": api.SIPTransport.SIP_TRANSPORT_UDP,
            "tcp": api.SIPTransport.SIP_TRANSPORT_TCP,
            "tls": api.SIPTransport.SIP_TRANSPORT_TLS,
        }.get(t, api.SIPTransport.SIP_TRANSPORT_UDP)
    except Exception:  # noqa: BLE001
        return t


def _address(trunk: SipTrunk) -> str:
    """`host:port` (LiveKit's SIPOutboundTrunkInfo.address). Port omitted when default 5060."""
    host = (trunk.sip_host or "").strip()
    port = int(trunk.sip_port or 5060)
    return f"{host}:{port}" if port and port != 5060 else host


# ---------------------------------------------------------------------------
# Request BUILDERS (pure; no I/O). Return the LiveKit request object, or a plain dict mirror
# when the SDK is absent (the offline test asserts on the dict shape).
# ---------------------------------------------------------------------------
def build_outbound_trunk_request(trunk: SipTrunk, sip_password: str = "") -> Any:
    """Build a CreateSIPOutboundTrunkRequest from a registry row + the decrypted SIP password.
    The password is passed transiently (never logged/stored here). With the SDK absent, returns
    a dict mirror (no password echoed — masked) for offline assertion."""
    api = _lk_api()
    numbers: List[str] = trunk.dids or ([trunk.caller_id] if trunk.caller_id else [])
    name = trunk.display_name or trunk.slug or "trunk"
    if api is None:
        return {
            "_kind": "outbound_trunk", "name": name, "address": _address(trunk),
            "transport": (trunk.transport.value if isinstance(trunk.transport, Transport)
                          else str(trunk.transport)),
            "numbers": numbers, "auth_username": trunk.auth_username or "",
            "auth_password_present": bool(sip_password),
        }
    try:
        info = api.SIPOutboundTrunkInfo(
            name=name,
            address=_address(trunk),
            transport=_transport_enum(api, trunk),
            numbers=numbers,
            auth_username=trunk.auth_username or "",
            auth_password=sip_password or "",
        )
        return api.CreateSIPOutboundTrunkRequest(trunk=info)
    except Exception as exc:  # noqa: BLE001 — degrade to the dict mirror (never raise)
        _log.warning("build_outbound_trunk_request fell back to dict: %r", type(exc).__name__)
        return {"_kind": "outbound_trunk", "name": name, "address": _address(trunk),
                "numbers": numbers, "auth_username": trunk.auth_username or "",
                "auth_password_present": bool(sip_password)}


def build_inbound_trunk_request(trunk: SipTrunk) -> Any:
    """Build a CreateSIPInboundTrunkRequest from a registry row (the inbound DID + allowlist)."""
    api = _lk_api()
    name = trunk.display_name or trunk.slug or "inbound"
    numbers: List[str] = trunk.dids or ([trunk.caller_id] if trunk.caller_id else [])
    allowed = list(trunk.allowed_addresses or [])
    if api is None:
        return {"_kind": "inbound_trunk", "name": name, "numbers": numbers,
                "allowed_addresses": allowed}
    try:
        info = api.SIPInboundTrunkInfo(name=name, numbers=numbers, allowed_addresses=allowed)
        return api.CreateSIPInboundTrunkRequest(trunk=info)
    except Exception as exc:  # noqa: BLE001
        _log.warning("build_inbound_trunk_request fell back to dict: %r", type(exc).__name__)
        return {"_kind": "inbound_trunk", "name": name, "numbers": numbers,
                "allowed_addresses": allowed}


def build_dispatch_rule_request(trunk: SipTrunk, tenant_id: str, *, agent_name: str = "",
                                room_prefix: str = "inbound-") -> Any:
    """Build a CreateSIPDispatchRuleRequest carrying `metadata:{tenant_id}` so an inbound DID
    routes to the right tenant's agent (multi-tenant DID->agent routing, §2.3). With the SDK
    absent, returns the dict mirror."""
    api = _lk_api()
    import json as _json
    metadata = _json.dumps({"tenant_id": tenant_id, "trunk_slug": trunk.slug})
    trunk_ids = [trunk.livekit_trunk_id] if trunk.livekit_trunk_id else []
    if api is None:
        return {"_kind": "dispatch_rule", "tenant_id": tenant_id, "trunk_ids": trunk_ids,
                "room_prefix": room_prefix, "metadata": metadata, "agent_name": agent_name}
    try:
        rule = api.SIPDispatchRule(
            dispatch_rule_individual=api.SIPDispatchRuleIndividual(room_prefix=room_prefix))
        req = api.CreateSIPDispatchRuleRequest(rule=rule, trunk_ids=trunk_ids, metadata=metadata)
        return req
    except Exception as exc:  # noqa: BLE001
        _log.warning("build_dispatch_rule_request fell back to dict: %r", type(exc).__name__)
        return {"_kind": "dispatch_rule", "tenant_id": tenant_id, "trunk_ids": trunk_ids,
                "room_prefix": room_prefix, "metadata": metadata, "agent_name": agent_name}


# ---------------------------------------------------------------------------
# API CALLS — go through an INJECTED async LiveKit client (the SAME api.LiveKitAPI caller.py
# uses). NO container restart (multi-trunk is native). These are thin + never import agent.py.
# ---------------------------------------------------------------------------
@dataclass
class SyncResult:
    ok: bool
    livekit_trunk_id: str = ""
    reason: str = ""
    raw: Any = None


async def create_outbound_trunk(lk, trunk: SipTrunk, sip_password: str = "") -> SyncResult:
    """Create the LiveKit-SIP OUTBOUND trunk for a registry row via the injected client `lk`
    (which exposes `.sip.create_sip_outbound_trunk`). Returns the new `ST_<id>` to store in
    `livekit_trunk_id`. NEVER raises -> SyncResult(ok=False, reason=...)."""
    req = build_outbound_trunk_request(trunk, sip_password)
    try:
        resp = await lk.sip.create_sip_outbound_trunk(req)
        st_id = (getattr(resp, "sip_trunk_id", "") or getattr(resp, "id", "") or "").strip()
        return SyncResult(ok=bool(st_id), livekit_trunk_id=st_id, raw=resp)
    except Exception as exc:  # noqa: BLE001
        return SyncResult(ok=False, reason=f"create_outbound_failed:{type(exc).__name__}")


async def create_inbound_trunk(lk, trunk: SipTrunk) -> SyncResult:
    req = build_inbound_trunk_request(trunk)
    try:
        resp = await lk.sip.create_sip_inbound_trunk(req)
        st_id = (getattr(resp, "sip_trunk_id", "") or getattr(resp, "id", "") or "").strip()
        return SyncResult(ok=bool(st_id), livekit_trunk_id=st_id, raw=resp)
    except Exception as exc:  # noqa: BLE001
        return SyncResult(ok=False, reason=f"create_inbound_failed:{type(exc).__name__}")


async def create_dispatch_rule(lk, trunk: SipTrunk, tenant_id: str, **kw) -> SyncResult:
    req = build_dispatch_rule_request(trunk, tenant_id, **kw)
    try:
        resp = await lk.sip.create_sip_dispatch_rule(req)
        rule_id = (getattr(resp, "sip_dispatch_rule_id", "") or getattr(resp, "id", "") or "").strip()
        return SyncResult(ok=bool(rule_id), livekit_trunk_id=rule_id, raw=resp)
    except Exception as exc:  # noqa: BLE001
        return SyncResult(ok=False, reason=f"create_dispatch_failed:{type(exc).__name__}")


def is_protected_trunk_id(livekit_trunk_id: str, *, protected_ids: Optional[List[str]] = None) -> bool:
    """RED-TEAM D — True iff this LiveKit trunk id MUST NOT be LiveKit-deleted: the env-bound live
    outbound trunk (LIVEKIT_SIP_TRUNK_ID) or any explicitly-protected id (the AIM inbound trunk).
    The registry default for 'remove' is a DB soft-disable; this is the last-line refusal."""
    lk_id = (livekit_trunk_id or "").strip()
    if not lk_id:
        return True  # an empty id is never safe to act on
    env_id = (os.environ.get(_ENV_PROTECTED_TRUNK) or "").strip()
    if env_id and lk_id == env_id:
        return True
    if protected_ids and lk_id in {str(p).strip() for p in protected_ids if p}:
        return True
    return False


async def delete_trunk(lk, livekit_trunk_id: str, *, protected_ids: Optional[List[str]] = None,
                       force_protected: bool = False) -> SyncResult:
    """Delete a LiveKit-SIP trunk OBJECT. REFUSES (red-team D) the env-protected live trunk / any
    protected id unless `force_protected=True` (which the endpoint sets ONLY after a PIN step-up +
    audit). The package DEFAULT path never deletes — it soft-disables the DB row. NEVER raises."""
    if is_protected_trunk_id(livekit_trunk_id, protected_ids=protected_ids) and not force_protected:
        return SyncResult(ok=False, livekit_trunk_id=livekit_trunk_id,
                          reason="refused_protected_live_trunk")
    try:
        resp = await lk.sip.delete_sip_trunk(_delete_req(livekit_trunk_id))
        return SyncResult(ok=True, livekit_trunk_id=livekit_trunk_id, raw=resp)
    except Exception as exc:  # noqa: BLE001
        return SyncResult(ok=False, livekit_trunk_id=livekit_trunk_id,
                          reason=f"delete_failed:{type(exc).__name__}")


def _delete_req(livekit_trunk_id: str):
    api = _lk_api()
    if api is None:
        return {"_kind": "delete_trunk", "sip_trunk_id": livekit_trunk_id}
    try:
        return api.DeleteSIPTrunkRequest(sip_trunk_id=livekit_trunk_id)
    except Exception:  # noqa: BLE001
        return {"_kind": "delete_trunk", "sip_trunk_id": livekit_trunk_id}
