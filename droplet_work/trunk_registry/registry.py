"""trunk_registry.registry — THE choke-point: get_trunk(tenant, purpose) (T2).

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.3 (outbound selection: get_trunk(tenant,
'outbound') resolves ST_<id> + DID; never raises) + §3 RED-TEAM B1 (the campaign-eligibility
gate is enforced IN THE CHOKE-POINT, on the DB-derived `is_campaign_eligible` column, NOT in
prose/UI — unbypassable) + §2.5 (reputation-aware selection; skip quarantined/circuit-open) +
§5 T2 acceptance ("B1 gate returns NOT-eligible for unregistered").

THE CONSUMER CONTRACT (the strangler seam the caller.py dial loop consumes at T5):

    tc = registry.get_trunk(tenant_id, purpose="campaign")   # never raises
    if tc.ok:
        sip_trunk_id = tc.livekit_trunk_id    # the ST_<id> for CreateSIPParticipantRequest
        sip_number   = tc.did                 # the rotated caller-ID
        # ... LiveKit dial via tc.livekit_trunk_id + tc.did ...
    else:
        ... tc.reason == 'registry_disabled' | 'not_configured' | 'no_eligible_trunk'
        ... the dial loop falls back to the LEGACY `TRUNK` env (byte-identical) ...

RESOLUTION (never raises — a problem yields ok=False, the dial loop uses legacy):
  1. flag OFF -> ok=False, reason='registry_disabled' (resting byte-identical).
  2. PG down -> ok=False, reason='not_configured'.
  3. list enabled, non-quarantined OUTBOUND trunks for the tenant (RLS: own + `_global`),
     priority asc. For purpose='campaign', RED-TEAM B1: filter to is_campaign_eligible=true at
     the STORE layer (the DB-derived column) — a non-140 / DLT-unregistered trunk is NEVER
     returned for a campaign, even one a tenant flipped is_enabled on via a direct write.
  4. walk the chain; SKIP a circuit-open trunk (health) and a trunk with no DID; pick the DID via
     rotation (reputation-aware). The FIRST usable trunk+DID wins.
  5. no usable trunk -> ok=False, reason='no_eligible_trunk' | 'not_configured'.

The B1 gate is applied TWICE on purpose (defense in depth): the store filter
(campaign_eligible_only) AND an explicit per-trunk re-check here, so even a store change can't
silently leak a non-eligible trunk into a campaign dial.

EARNER-SAFE: imports store / rotation / health / config only — NEVER agent.py, NEVER dials,
NEVER does network I/O itself (the dial loop owns the LiveKit call).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import config, health, rotation, store
from .schema import Purpose, SipTrunk

_log = logging.getLogger("trunk_registry.registry")


@dataclass
class TrunkChoice:
    """What get_trunk resolved. `ok` is the ONLY thing the dial loop branches on. On ok=False the
    dial loop falls back to the legacy `TRUNK` env (the strangler)."""
    ok: bool
    reason: str = ""
    purpose: str = ""
    tenant_id: str = ""
    trunk: Optional[SipTrunk] = None
    livekit_trunk_id: str = ""    # the ST_<id> for CreateSIPParticipantRequest
    did: str = ""                 # the rotated caller-ID
    tried: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (f"TrunkChoice(ok={self.ok}, reason={self.reason!r}, "
                f"slug={(self.trunk.slug if self.trunk else None)!r}, "
                f"lk={self.livekit_trunk_id!r}, did={self.did!r})")


def _not_ok(purpose: str, tenant_id: str, reason: str, tried: List[str]) -> TrunkChoice:
    return TrunkChoice(ok=False, reason=reason, purpose=purpose, tenant_id=tenant_id, tried=tried)


def _purpose_str(purpose) -> str:
    return purpose.value if isinstance(purpose, Purpose) else str(purpose or "campaign")


def _is_campaign_eligible(trunk: SipTrunk) -> bool:
    """The B1 gate, re-checked in code (defense in depth on top of the store filter). A trunk is
    campaign-eligible ONLY if the DB-derived column says so. We TRUST the DB-derived value
    (it is GENERATED ALWAYS AS (is_140_series AND dlt_status='registered')); we never recompute
    it from user-settable inputs here (that would re-introduce the bypass the column closes)."""
    return bool(getattr(trunk, "is_campaign_eligible", False))


def get_trunk(
    tenant_id: str,
    purpose: str = "campaign",
    *,
    routing_hint: Optional[str] = None,
    avoid_dids: Optional[List[str]] = None,
    now_fn: Optional[Callable[[], float]] = None,
) -> TrunkChoice:
    """Resolve the trunk + DID for (tenant_id, purpose). NEVER raises.

      * tenant_id    : ALWAYS the token-derived tenant (RLS returns own + `_global` only).
      * purpose      : 'campaign' (REQUIRES campaign-eligibility — B1) | 'test' | 'manual' |
                       'inbound'. test/manual are a single founder dial (not auto-dialed) so they
                       may use the non-140 Vobiz `_global` trunk for a real ring.
      * routing_hint : a trunk SLUG to try first (a consumer's explicit pick).
      * avoid_dids   : DIDs to skip in rotation (reputation-aware — never feed a known-bad DID).

    Resolution: routing_hint slug first, then priority asc; skip circuit-open / no-DID trunks; the
    first usable trunk+DID wins."""
    tried: List[str] = []
    pstr = _purpose_str(purpose)

    # 1) flag OFF -> dormant; dial loop uses legacy TRUNK env (resting byte-identical).
    if not config.is_enabled():
        return _not_ok(pstr, tenant_id, "registry_disabled", tried)

    # 2) PG down -> not_configured (dial loop falls back).
    if not store.available():
        return _not_ok(pstr, tenant_id, "not_configured", tried)

    nowf = now_fn or __import__("time").time
    want_campaign = (pstr == Purpose.CAMPAIGN.value)
    direction = Purpose.INBOUND.value if pstr == Purpose.INBOUND.value else "outbound"

    # 3) candidate chain — enabled, non-quarantined, RLS-scoped, priority asc. For a CAMPAIGN, the
    #    store filters to is_campaign_eligible=true (RED-TEAM B1 — the DB-derived gate, unbypassable).
    candidates: List[SipTrunk] = store.list_trunks(
        tenant_id, direction=direction, enabled_only=True,
        campaign_eligible_only=want_campaign, exclude_quarantined=True)

    if routing_hint:
        hinted = [t for t in candidates if t.slug == routing_hint]
        rest = [t for t in candidates if t.slug != routing_hint]
        candidates = hinted + rest

    if not candidates:
        return _not_ok(pstr, tenant_id, "no_eligible_trunk" if want_campaign else "not_configured",
                       tried)

    # 4) walk the chain; B1 re-check + circuit + DID selection.
    last_reason = "not_configured"
    for t in candidates:
        tried.append(t.slug)
        # RED-TEAM B1 defense-in-depth: a campaign dial RE-VERIFIES eligibility per trunk even
        # after the store filter — a non-eligible trunk is NEVER campaign-dialed.
        if want_campaign and not _is_campaign_eligible(t):
            last_reason = "not_campaign_eligible"
            continue
        tid = t.id or ""
        if tid and health.trunk_is_degraded(tenant_id, tid, now_fn=nowf):
            last_reason = "circuit_open"
            continue
        did = rotation.pick_did(t, avoid=avoid_dids)
        if not did:
            last_reason = "no_did"
            continue
        lk_id = (t.livekit_trunk_id or "").strip()
        if not lk_id:
            # a trunk with no synced LiveKit trunk id cannot be dialed (needs livekit_sync first).
            last_reason = "no_livekit_trunk"
            continue
        return TrunkChoice(ok=True, reason="ok", purpose=pstr, tenant_id=tenant_id, trunk=t,
                           livekit_trunk_id=lk_id, did=did, tried=tried)

    return _not_ok(pstr, tenant_id, last_reason, tried)


def resolve_status(tenant_id: str, purpose: str = "campaign") -> dict:
    """A non-secret diagnostic for the /telephony UI/health: which trunks serve `purpose` for
    this tenant + each one's eligibility/circuit/quarantine state. Never reveals a credential."""
    pstr = _purpose_str(purpose)
    out = {"enabled": config.is_enabled(), "purpose": pstr, "trunks": []}
    if not config.is_enabled() or not store.available():
        return out
    direction = Purpose.INBOUND.value if pstr == Purpose.INBOUND.value else "outbound"
    for t in store.list_trunks(tenant_id, direction=direction):
        out["trunks"].append({
            "slug": t.slug,
            "display_name": t.display_name,
            "priority": t.priority,
            "is_enabled": t.is_enabled,
            "is_campaign_eligible": _is_campaign_eligible(t),
            "is_quarantined": t.is_quarantined(),
            "did_pool_size": len(t.dids),
            "circuit": health.trunk_health_snapshot(tenant_id, t.id or ""),
        })
    return out
