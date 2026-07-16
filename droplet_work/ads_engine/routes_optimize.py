"""ads_engine.routes_optimize — the CONTINUOUS-LOOP sub-router (V2-W3 parity loop).

A SEPARATE route surface mounted onto the main /ads router by endpoints.build_router via a single
`register(router, deps)` call (so endpoints.py stays minimally edited). Every route reuses the host
router's already-wired auth/RBAC/audit closures (passed in `deps`) — NO new auth code here.

Routes (all under /ads, FEATURE_ADS-gated by the shared `auth` closure):
  POST /ads/events/ingest             -> ingest a pixel/server conversion event (the signal substrate)
  GET  /ads/learning/status           -> learning-phase + do-not-edit status for a campaign (UI)
  GET  /ads/fatigue/status            -> creative-fatigue verdicts + rotation proposals for a campaign
  GET  /ads/audience/proposals        -> autonomous audience-expansion candidates (proposal-only)
  POST /ads/optimize/run              -> operator kick: run ONE continuous-optimization pass (dry-run)

EARNER-SAFE: ingest only writes the append-only event spine (no spend); the optimize/run kick reuses the
SAME propose-only + dry-run + guardrail-gated daemon the tick runs — it adds NO spend authority. Read
routes are pure reads of the derived state. Crash-proof: a registration failure never breaks the mount.
"""

from __future__ import annotations

from typing import Any

from . import ad_events, audience as _aud, continuous, fatigue as _fat, learning_phase, store


def _qp(request: Any, key: str, default: str = "") -> str:
    """Best-effort query-param read (Starlette request.query_params). Degrade-safe."""
    try:
        return str(request.query_params.get(key, default) or default)
    except Exception:  # noqa: BLE001
        return default


def register(router: Any, deps: Any) -> None:
    """Attach the continuous-loop routes to the host /ads router. `deps` carries the host closures:
    json, auth, write_gate, tid, body, audit, forbidden (same bag as routes_autorun)."""
    JSON = deps.json
    auth = deps.auth
    write_gate = deps.write_gate
    tid = deps.tid
    body = deps.body
    audit = deps.audit
    forbidden = deps.forbidden

    # ----------------------------------------------------- EVENTS (signal substrate)
    @router.post("/events/ingest")
    async def events_ingest(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        b = await body(request)
        ev = b.get("event") if isinstance(b.get("event"), dict) else b
        if not isinstance(ev, dict) or not (ev.get("type") or ev.get("event")):
            return forbidden("event {type, ...} required")
        try:
            res = ad_events.ingest_event(tid(t), dict(ev))
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "ingest_failed"}, status_code=200)
        audit(request, t, "ads.events.ingest", "ad_event",
              str((res.get("event") or {}).get("event_id", "")),
              {"type": (res.get("event") or {}).get("type"), "deduped": res.get("deduped")})
        return JSON({"ok": bool(res.get("ingested") or res.get("deduped")), **res})

    # ----------------------------------------------------- LEARNING PHASE (UI status)
    @router.get("/learning/status")
    async def learning_status(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        cid = _qp(request, "campaign_id")
        if not cid:
            return forbidden("campaign_id required")
        try:
            return JSON({"ok": True, "campaign_id": cid, "learning": learning_phase.status(tid(t), cid)})
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "status_error"}, status_code=200)

    # ----------------------------------------------------- CREATIVE FATIGUE
    @router.get("/fatigue/status")
    async def fatigue_status(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        cid = _qp(request, "campaign_id")
        if not cid:
            return forbidden("campaign_id required")
        try:
            row = store.get_row(tid(t), "fatigue_state", cid)
            if not row:
                events = store.get_ad_events(tid(t))
                analysis = _fat.analyze(events, campaign_id=cid)
                moves = _fat.propose_rotation(analysis, campaign_id=cid)
                row = _fat.build_state(cid, analysis, moves)
            return JSON({"ok": True, "campaign_id": cid, "fatigue": row})
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "fatigue_error"}, status_code=200)

    # ----------------------------------------------------- AUDIENCE EXPANSION
    @router.get("/audience/proposals")
    async def audience_proposals(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        cid = _qp(request, "campaign_id")
        if not cid:
            return forbidden("campaign_id required")
        try:
            row = store.get_row(tid(t), "audience_state", cid)
            if not row:
                events = store.get_ad_events(tid(t))
                rec = store.get_row(tid(t), "campaigns", cid) or {}
                brief = rec.get("plan", {}).get("brief", {}) if isinstance(rec.get("plan"), dict) else {}
                seed = brief.get("audience_segments") or brief.get("segments") or []
                discovery = _aud.discover_segments(events, seed, campaign_id=cid)
                moves = _aud.propose_expansion(discovery, campaign_id=cid,
                                               budget_daily_minor=int(brief.get("budget_daily_minor") or 0))
                row = _aud.build_state(cid, seed, discovery, moves)
            return JSON({"ok": True, "campaign_id": cid, "audience": row})
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "audience_error"}, status_code=200)

    # ----------------------------------------------------- OPERATOR KICK (dry-run pass)
    @router.post("/optimize/run")
    async def optimize_run(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        try:
            res = await continuous.optimize_pass([tid(t)])
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "optimize_failed"}, status_code=200)
        audit(request, t, "ads.optimize.run", "optimize_pass", tid(t),
              {"decisions": res.get("decisions"), "tenants": res.get("tenants")})
        return JSON({"ok": True, "result": res})
