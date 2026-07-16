"""ads_engine.orchestrator — the AUTONOMY LOOP (BLINDSPOTS B9 + B6/B10).

THE "ADD ONE KEY → IT RUNS" UNIT. Turns a tenant's {connected ad key + funded budget + project
brief} into a SELF-RUNNING pipeline that chains, one phase per tick:

    propose-campaign → generate-creative (or use an uploaded asset) → moderation →
    CPA×50 viability → (guarded) launch → [lead → 60s call → CAPI/DataManager feedback]

EARNER-SAFE INVARIANTS (mirrors tick.py's contract — this module is driven BY the tick):
  * OPT-IN, DOUBLE-GATED. The orchestrator never runs unless BOTH the global flag
    `config.autorun_enabled()` (ADS_AUTORUN, default OFF) AND the per-tenant opt-in
    (`autorun_config.enabled`) are set. Enabling FEATURE_ADS alone does NOT start an autonomous loop.
  * DRY-RUN BY DEFAULT. Every spend/dial-mutating step runs through the SAME gated seams as the
    manual path: campaign.approve honours `config.dry_run()` (synthetic refs, no spend); the
    lead→call enqueue stays dry-run until the 140-series flag; feedback emit is offline until creds
    exist. The orchestrator adds NO new spend authority — it only sequences existing gated calls.
  * LAUNCH PARKS AT A HUMAN CHECKPOINT. Unless `config.autorun_autolaunch()` (ADS_AUTORUN_AUTOLAUNCH,
    default OFF) the state machine drives everything UP TO launch and stops at `launch_pending`,
    leaving approve+step-up as the human gate (BLINDSPOTS B9/B11).
  * NEVER RAISES into the tick. `tick_pass` swallows + logs every per-tenant failure; one tenant's
    error never aborts the others; the cursor is best-effort persisted so a crash resumes cleanly.
  * BOUNDED. One phase advance per tenant per tick — no unbounded fan-out inside a single pass.

NO `from caller import ...` — only the package's own injected seams (store/config/vault_adapter).
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from . import (ad_events as _ad_events, campaign, config, creative as _creative,
               feedback, leads, store, vault_adapter)

# ---------------------------------------------------------------------------
# Phase machine. Each phase advances by exactly ONE step per tick.
# ---------------------------------------------------------------------------
PH_IDLE = "idle"                 # awaiting preconditions (key + budget + brief)
PH_PROPOSING = "proposing"       # build_plan + viability + persist draft
PH_CREATIVE = "creating_creative"  # submit a creative job (or adopt an uploaded asset)
PH_MODERATING = "moderating"     # advance the job through generate→compose→moderate
PH_VIABILITY = "viability"       # re-confirm CPA×50 viability before launch
PH_LAUNCH_PENDING = "launch_pending"  # viable + moderated; parked for human step-up (or autolaunch)
PH_LAUNCHED = "launched"         # approve() succeeded (dry_run or live)
PH_BLOCKED = "blocked"           # a hard stop (under-funded / illegal / moderation-blocked)
PH_DONE = "done"                 # terminal success for this brief cycle

_CONFIG_ROW = "config"           # the single per-tenant row id in `autorun_config`
_STATE_ROW = "state"             # the single per-tenant row id in `autorun_state`

# Bound the moderation poll so a stuck creative job can never spin the cursor forever.
_MAX_MODERATE_TICKS = 8


def _log(msg: str, *, level: str = "info") -> None:
    try:
        import logging as _lg
        getattr(_lg.getLogger("ads_engine.orchestrator"), level, _lg.getLogger("ads_engine.orchestrator").info)(msg)
    except Exception:  # noqa: BLE001
        pass


def _now() -> int:
    return int(time.time())


# ===========================================================================
# Media-engine asset bridge (BLINDSPOTS B6). A store-backed gallery so a media-engine
# asset can be MIRRORED in and then bridged into a moderated ad variant — offline, no
# external gallery service required. get_asset/mirror_asset are the exact interface
# CreativeService.import_upload / _mirror_to_gallery expect.
# ===========================================================================
class StoreAssetBridge:
    """Tenant-scoped asset bridge backed by the `media_assets` store collection."""

    def get_asset(self, tenant_id: str, asset_id: str) -> Optional[dict]:
        try:
            return store.get_row(tenant_id, "media_assets", str(asset_id))
        except Exception:  # noqa: BLE001
            return None

    def mirror_asset(self, tenant_id: str, asset: dict) -> dict:
        try:
            aid = str((asset or {}).get("variant_id") or (asset or {}).get("asset_id")
                      or ("ma_" + uuid.uuid4().hex[:10]))
            row = dict(asset or {})
            row["asset_id"] = aid
            return store.put_row(tenant_id, "media_assets", aid, row)
        except Exception:  # noqa: BLE001
            return {}


def register_media_asset(tenant_id: str, asset: dict) -> dict:
    """Mirror a media-engine asset into the backend gallery so it can be bridged into an ad
    variant. Used by the media-engine→ads bridge route and the offline chain test."""
    return StoreAssetBridge().mirror_asset(tenant_id, asset)


# ===========================================================================
# Creative service factory (mirrors endpoints._creative_service but WITH the asset bridge so
# the standalone-generate + media-engine-bridge paths work without touching creative.py).
# ===========================================================================
def make_creative_service(*, with_bridge: bool = True) -> "_creative.CreativeService":
    def _resolve_def_id(tenant_id: str, model_id: str) -> str:
        try:
            return vault_adapter.resolve_provider_def_id(
                tenant_id, named_provider="creative_gen", slug=str(model_id or "")) or ""
        except Exception:  # noqa: BLE001
            return ""

    return _creative.CreativeService(
        get_secret_json=vault_adapter.get_secret_json,
        resolve_def_id=_resolve_def_id,
        asset_bridge=StoreAssetBridge() if with_bridge else None,
    )


# ===========================================================================
# Opt-in config + state cursor (per tenant).
# ===========================================================================
def get_config(tenant_id: str) -> dict:
    try:
        row = store.get_row(tenant_id, "autorun_config", _CONFIG_ROW)
    except Exception:  # noqa: BLE001
        row = None
    return row if isinstance(row, dict) else {}


def get_state(tenant_id: str) -> dict:
    try:
        row = store.get_row(tenant_id, "autorun_state", _STATE_ROW)
    except Exception:  # noqa: BLE001
        row = None
    if not isinstance(row, dict) or not row:
        return {"phase": PH_IDLE, "plan_id": "", "job_id": "", "variant_ids": [],
                "moderate_ticks": 0, "blocked_reason": "", "history": [], "updated_ts": 0}
    return row


def _save_state(tenant_id: str, state: dict) -> dict:
    state["updated_ts"] = _now()
    try:
        return store.put_row(tenant_id, "autorun_state", _STATE_ROW, state)
    except Exception:  # noqa: BLE001
        return state


def _transition(state: dict, phase: str, *, note: str = "") -> dict:
    prev = state.get("phase")
    state["phase"] = phase
    hist = state.get("history") or []
    hist.append({"from": prev, "to": phase, "note": note, "ts": _now()})
    state["history"] = hist[-40:]  # bounded
    return state


def enable(tenant_id: str, brief: dict, *, autopilot_launch: bool = False,
           uploaded_asset_id: str = "", actor: str = "system") -> dict:
    """Opt a tenant into the autonomy loop with a project brief. Resets the state cursor to idle."""
    cfg = {
        "enabled": True,
        "brief": dict(brief or {}),
        "autopilot_launch": bool(autopilot_launch),
        "uploaded_asset_id": str(uploaded_asset_id or ""),
        "actor": str(actor or "system"),
        "updated_ts": _now(),
    }
    try:
        store.put_row(tenant_id, "autorun_config", _CONFIG_ROW, cfg)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "config_write_failed", "detail": type(exc).__name__}
    _save_state(tenant_id, {"phase": PH_IDLE, "plan_id": "", "job_id": "", "variant_ids": [],
                            "moderate_ticks": 0, "blocked_reason": "", "history": []})
    return {"ok": True, "enabled": True, "config": cfg, "state": get_state(tenant_id)}


def disable(tenant_id: str) -> dict:
    cfg = get_config(tenant_id)
    cfg["enabled"] = False
    cfg["updated_ts"] = _now()
    try:
        store.put_row(tenant_id, "autorun_config", _CONFIG_ROW, cfg)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "enabled": False}


def status(tenant_id: str) -> dict:
    cfg = get_config(tenant_id)
    state = get_state(tenant_id)
    ok, reason, details = check_preconditions(tenant_id, cfg)
    return {"ok": True, "enabled": bool(cfg.get("enabled")),
            "autopilot_launch": bool(cfg.get("autopilot_launch")),
            "preconditions_ok": ok, "preconditions_reason": reason,
            "preconditions": details, "phase": state.get("phase"),
            "plan_id": state.get("plan_id"), "job_id": state.get("job_id"),
            "variant_ids": state.get("variant_ids") or [],
            "blocked_reason": state.get("blocked_reason"),
            "global_autorun": config.autorun_enabled(),
            "autolaunch_flag": config.autorun_autolaunch(),
            "dry_run": config.dry_run(), "history": state.get("history") or []}


# ===========================================================================
# Preconditions — the "ONE key + budget + brief" gate.
# ===========================================================================
def _has_connected_key(tenant_id: str) -> bool:
    try:
        statuses = vault_adapter.list_status(tenant_id) or {}
    except Exception:  # noqa: BLE001
        return False
    # Any ad-platform channel configured is enough to start (creative can still degrade to
    # not_configured per-model — that is handled downstream, fail-soft).
    return any(str(statuses.get(ch)) == "configured" for ch in ("meta", "google"))


def _has_funded_budget(tenant_id: str, brief: dict) -> bool:
    # Funded = a positive paise balance in the ad-budget account OR a brief that names a daily budget
    # (the vendor-own-card model funds on the platform, not on us — a named budget is the intent).
    try:
        acct = store.get_budget_account(tenant_id) or {}
        if int(acct.get("balance_minor", 0) or 0) > 0:
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        return int((brief or {}).get("budget_daily_minor", 0) or 0) > 0
    except Exception:  # noqa: BLE001
        return False


def check_preconditions(tenant_id: str, cfg: Optional[dict] = None) -> tuple[bool, str, dict]:
    cfg = cfg if cfg is not None else get_config(tenant_id)
    brief = cfg.get("brief") if isinstance(cfg.get("brief"), dict) else {}
    has_key = _has_connected_key(tenant_id)
    has_budget = _has_funded_budget(tenant_id, brief)
    has_brief = bool(brief)
    details = {"connected_key": has_key, "funded_budget": has_budget, "has_brief": has_brief}
    if not has_brief:
        return False, "no_brief", details
    if not has_key:
        return False, "no_connected_key", details
    if not has_budget:
        return False, "no_funded_budget", details
    return True, "", details


# ===========================================================================
# The per-tenant single-step advance (the state machine).
# ===========================================================================
async def advance(tenant_id: str, *, creative_service: Any = None,
                  now_ts: Optional[int] = None) -> dict:
    """Advance ONE tenant's autonomy cursor by exactly ONE phase. Never raises. Returns a summary.

    Each call performs at most one meaningful step so a single tick can never run the whole pipeline
    in a burst — the machine walks one phase per tick, fully auditable, fully gated.
    """
    now = int(now_ts if now_ts is not None else _now())
    cfg = get_config(tenant_id)
    if not cfg.get("enabled"):
        return {"phase": "disabled", "advanced": False}

    ok, reason, _details = check_preconditions(tenant_id, cfg)
    state = get_state(tenant_id)
    phase = state.get("phase") or PH_IDLE
    brief = cfg.get("brief") if isinstance(cfg.get("brief"), dict) else {}
    svc = creative_service or make_creative_service()

    try:
        # ---- IDLE: wait for preconditions, then start proposing. ----
        if phase in (PH_IDLE, PH_DONE, PH_BLOCKED):
            if not ok:
                return {"phase": phase, "advanced": False, "reason": reason}
            # Only (re)start from idle; done/blocked are terminal until re-enabled.
            if phase != PH_IDLE:
                return {"phase": phase, "advanced": False, "reason": "terminal"}
            _transition(state, PH_PROPOSING, note="preconditions met")
            _save_state(tenant_id, state)
            return {"phase": PH_PROPOSING, "advanced": True}

        # ---- PROPOSING: build_plan + viability + persist draft. ----
        if phase == PH_PROPOSING:
            result = campaign.propose(tenant_id, dict(brief))
            if not result.get("ok"):
                state["blocked_reason"] = result.get("reason") or result.get("status") or "propose_failed"
                _transition(state, PH_BLOCKED, note=f"propose: {state['blocked_reason']}")
                _save_state(tenant_id, state)
                return {"phase": PH_BLOCKED, "advanced": True, "reason": state["blocked_reason"]}
            state["plan_id"] = result.get("plan_id") or ""
            if result.get("status") == campaign.ST_BLOCKED_FUNDS:
                state["blocked_reason"] = "blocked_insufficient_funds"
                _transition(state, PH_BLOCKED, note="viability blocked underfunded")
                _save_state(tenant_id, state)
                return {"phase": PH_BLOCKED, "advanced": True, "reason": "blocked_insufficient_funds"}
            _transition(state, PH_CREATIVE, note=f"plan {state['plan_id']}")
            _save_state(tenant_id, state)
            return {"phase": PH_CREATIVE, "advanced": True, "plan_id": state["plan_id"]}

        # ---- CREATIVE: adopt an uploaded asset if the vendor gave one, else generate. ----
        if phase == PH_CREATIVE:
            plan_id = state.get("plan_id") or ""
            asset_id = str(cfg.get("uploaded_asset_id") or "")
            if asset_id:
                variant = svc.import_upload(tenant_id, plan_id, asset_id, brief=dict(brief))
                vid = variant.get("variant_id") or ""
                if vid:
                    state["variant_ids"] = list(set((state.get("variant_ids") or []) + [vid]))
                # an uploaded asset is moderated inline by import_upload -> skip the poll.
                state["moderate_ticks"] = 0
                _transition(state, PH_VIABILITY, note=f"adopted upload {asset_id}")
                _save_state(tenant_id, state)
                return {"phase": PH_VIABILITY, "advanced": True, "via": "upload"}
            job = svc.submit(tenant_id, plan_id, dict(brief))
            state["job_id"] = job.get("job_id") or ""
            state["moderate_ticks"] = 0
            _transition(state, PH_MODERATING, note=f"job {state['job_id']}")
            _save_state(tenant_id, state)
            return {"phase": PH_MODERATING, "advanced": True, "job_id": state["job_id"]}

        # ---- MODERATING: walk the creative job one stage; when ready, go to viability. ----
        if phase == PH_MODERATING:
            job = svc.get_job(tenant_id, state.get("job_id") or "")
            if not job:
                state["blocked_reason"] = "creative_job_lost"
                _transition(state, PH_BLOCKED, note="job missing")
                _save_state(tenant_id, state)
                return {"phase": PH_BLOCKED, "advanced": True}
            state["moderate_ticks"] = int(state.get("moderate_ticks", 0)) + 1
            if job.get("state") not in ("ready", "failed"):
                await svc.advance(tenant_id, job)
            job = svc.get_job(tenant_id, state.get("job_id") or "") or job
            if job.get("state") == "ready":
                vids = list(job.get("variant_ids") or [])
                state["variant_ids"] = list(set((state.get("variant_ids") or []) + vids))
                _transition(state, PH_VIABILITY, note="creative ready")
                _save_state(tenant_id, state)
                return {"phase": PH_VIABILITY, "advanced": True, "variants": len(vids)}
            if job.get("state") == "failed" or state["moderate_ticks"] >= _MAX_MODERATE_TICKS:
                state["blocked_reason"] = "creative_failed_or_timed_out"
                _transition(state, PH_BLOCKED, note=f"creative {job.get('state')}")
                _save_state(tenant_id, state)
                return {"phase": PH_BLOCKED, "advanced": True}
            _save_state(tenant_id, state)
            return {"phase": PH_MODERATING, "advanced": True, "job_state": job.get("state")}

        # ---- VIABILITY: confirm at least one moderated-approved variant + CPA×50 viability. ----
        if phase == PH_VIABILITY:
            plan_id = state.get("plan_id") or ""
            variants = svc.get_variants(tenant_id, plan_id)
            approved = [v for v in variants
                        if v.get("moderation_status") == _creative.MOD_APPROVED]
            if not approved:
                # nothing publishable — no approved creative (RERA/Housing/broken-text gate).
                blocked = [v for v in variants if v.get("moderation_status") == _creative.MOD_BLOCKED]
                state["blocked_reason"] = ("creative_moderation_blocked" if blocked
                                           else "no_approved_creative")
                _transition(state, PH_BLOCKED, note=state["blocked_reason"])
                _save_state(tenant_id, state)
                return {"phase": PH_BLOCKED, "advanced": True, "reason": state["blocked_reason"]}
            rec = store.get_row(tenant_id, "campaigns", plan_id) or {}
            viability = rec.get("viability") or {}
            if viability.get("verdict") == "blocked_underfunded":
                state["blocked_reason"] = "blocked_insufficient_funds"
                _transition(state, PH_BLOCKED, note="viability blocked")
                _save_state(tenant_id, state)
                return {"phase": PH_BLOCKED, "advanced": True}
            _transition(state, PH_LAUNCH_PENDING, note=f"{len(approved)} approved variant(s)")
            _save_state(tenant_id, state)
            return {"phase": PH_LAUNCH_PENDING, "advanced": True, "approved": len(approved)}

        # ---- LAUNCH_PENDING: human checkpoint, unless autopilot. ----
        if phase == PH_LAUNCH_PENDING:
            if not config.autorun_autolaunch() or not cfg.get("autopilot_launch"):
                # Park here: the operator approves via the step-up endpoint. Not an error.
                return {"phase": PH_LAUNCH_PENDING, "advanced": False,
                        "reason": "awaiting_human_step_up"}
            # Auto-pilot: the orchestrator itself approves. In DRY-RUN this is a synthetic-ref
            # persist (no spend). step_up=True authorizes a warn_underfunded plan launch.
            result = await campaign.approve(tenant_id, state.get("plan_id") or "",
                                            step_up=True, actor="orchestrator:autopilot")
            if result.get("ok"):
                _transition(state, PH_LAUNCHED,
                            note=f"launched status={result.get('status')} spending={result.get('spending')}")
                _save_state(tenant_id, state)
                return {"phase": PH_LAUNCHED, "advanced": True, "launch": result}
            state["blocked_reason"] = result.get("reason") or result.get("status") or "launch_failed"
            _transition(state, PH_BLOCKED, note=f"launch: {state['blocked_reason']}")
            _save_state(tenant_id, state)
            return {"phase": PH_BLOCKED, "advanced": True, "reason": state["blocked_reason"]}

        # ---- LAUNCHED: terminal success for this cycle. ----
        if phase == PH_LAUNCHED:
            _transition(state, PH_DONE, note="cycle complete")
            _save_state(tenant_id, state)
            return {"phase": PH_DONE, "advanced": True}

    except Exception as exc:  # noqa: BLE001 — a per-tenant advance NEVER raises into the tick
        _log(f"advance failed for tenant {tenant_id} in phase {phase}: {exc!r}", level="warning")
        return {"phase": phase, "advanced": False, "error": type(exc).__name__}

    return {"phase": phase, "advanced": False}


# ===========================================================================
# The tick pass — called by ads_engine.tick (throttled). Bounded + crash-proof.
# ===========================================================================
async def tick_pass(*, now_ts: Optional[int] = None,
                    creative_service: Any = None) -> dict:
    """Advance every opt-in tenant's autonomy cursor by ONE phase. Driven by the detached tick.

    Globally gated by `config.autorun_enabled()` so an un-flagged deploy never auto-runs. Per-tenant
    isolated: one tenant's failure never aborts the others. Returns a small summary for smoke tests.
    """
    summary = {"tenants": 0, "advanced": 0, "ran": False}
    if not config.autorun_enabled():
        return summary
    summary["ran"] = True
    try:
        tids = store.list_tenant_ids("autorun_config")
    except Exception as exc:  # noqa: BLE001
        _log(f"tick_pass: tenant enumeration failed: {exc!r}", level="warning")
        return summary
    svc = creative_service or make_creative_service()
    for tid in (tids or []):
        try:
            cfg = get_config(tid)
            if not cfg.get("enabled"):
                continue
            summary["tenants"] += 1
            res = await advance(tid, creative_service=svc, now_ts=now_ts)
            if res.get("advanced"):
                summary["advanced"] += 1
        except Exception as exc:  # noqa: BLE001 — per-tenant isolation
            _log(f"tick_pass: tenant {tid} advance failed: {exc!r}", level="warning")
            continue
    return summary


# ===========================================================================
# Standalone creative (BLINDSPOTS B10) — "type a brief → get ad variants" with NO pre-existing plan.
# ===========================================================================
def ensure_draft_plan(tenant_id: str, brief: dict) -> dict:
    """Mint a draft campaign plan from a brief so creative can be generated BEFORE a full campaign
    exists. Reuses campaign.propose (build_plan + viability + persist). Falls back to a minimal
    draft row if propose rejects the brief (so a bare creative brief still gets a plan_id)."""
    try:
        result = campaign.propose(tenant_id, dict(brief or {}))
        if result.get("ok") and result.get("plan_id"):
            return {"ok": True, "plan_id": result["plan_id"], "status": result.get("status"),
                    "viability": result.get("viability"), "synthetic": False}
        reason = result.get("reason") or result.get("status")
    except Exception as exc:  # noqa: BLE001
        reason = type(exc).__name__
    # Fallback: a minimal draft so a standalone creative is never blocked by a thin brief.
    plan_id = "draft_" + uuid.uuid4().hex[:12]
    now = _now()
    rec = {
        "plan_id": plan_id, "org_id": tenant_id, "tenant_id": tenant_id,
        "provider": str((brief or {}).get("provider") or "meta"),
        "name": str((brief or {}).get("name") or "Standalone creative draft"),
        "objective": str((brief or {}).get("objective") or "OUTCOME_LEADS"),
        "plan": {"draft": True, "brief": dict(brief or {})},
        "status": campaign.ST_DRAFT, "viability": {"verdict": "draft", "reason": reason},
        "standalone_creative": True, "created_ts": now, "updated_ts": now,
    }
    try:
        store.put_row(tenant_id, "campaigns", plan_id, rec)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "plan_id": plan_id, "status": campaign.ST_DRAFT,
            "synthetic": True, "reason": reason}


def standalone_generate(tenant_id: str, brief: dict, *, kinds: Optional[list] = None,
                        sizes: Optional[list] = None,
                        creative_service: Any = None) -> dict:
    """Decoupled generate: type a brief → get a creative job WITHOUT a pre-existing campaign.
    Auto-creates a draft plan, then submits the creative job (moderation runs in the job pipeline)."""
    draft = ensure_draft_plan(tenant_id, dict(brief or {}))
    plan_id = draft["plan_id"]
    svc = creative_service or make_creative_service()
    job = svc.submit(tenant_id, plan_id, dict(brief or {}), kinds=kinds, sizes=sizes)
    return {"ok": True, "plan_id": plan_id, "draft": draft, "job": job}


def bridge_media_asset(tenant_id: str, asset_id: str, *, brief: Optional[dict] = None,
                       plan_id: str = "", creative_service: Any = None) -> dict:
    """Bridge a media-engine asset (already mirrored into the `media_assets` gallery) into a
    moderated ad variant (BLINDSPOTS B6). Auto-creates a draft plan when none is supplied so the
    asset can enter the ad moderation gate without a campaign first."""
    b = dict(brief or {})
    if not plan_id:
        plan_id = ensure_draft_plan(tenant_id, b)["plan_id"]
    svc = creative_service or make_creative_service()
    variant = svc.import_upload(tenant_id, plan_id, str(asset_id), brief=b)
    return {"ok": variant.get("ok", True) is not False, "plan_id": plan_id, "variant": variant}


# ===========================================================================
# CLOSE THE LOOP (V2-W6) — translate a live 60s-call verdict into the ad_events spine, so the
# continuous optimizer learns on CONVERSATIONS (qualified/hot/booked) not clicks. This is the
# differentiator made real end-to-end: a qualified call tells Meta to find ten more like it.
# EARNER-SAFE: append-only, dry-run-safe (ingest stamps nothing on the box / spends nothing),
# no caller.py/agent.py touch — the verdict arrives via the same gated telephony seam. Never raises.
# ===========================================================================
# Call-verdict -> the strongest ad_events QUALITY rung it escalates (the real-buyer label CAPI wants).
_VERDICT_QUALITY = {
    "lead_qualified": _ad_events.EV_LEAD_QUALIFIED,
    "qualified": _ad_events.EV_LEAD_QUALIFIED,
    "warm": _ad_events.EV_LEAD_QUALIFIED,      # warm/investor/end_user clear the qualified bar (feedback parity)
    "investor": _ad_events.EV_LEAD_QUALIFIED,
    "end_user": _ad_events.EV_LEAD_QUALIFIED,
    "hot": _ad_events.EV_HOT,
    "site_visit": _ad_events.EV_SITE_VISIT_BOOKED,
    "site_visit_booked": _ad_events.EV_SITE_VISIT_BOOKED,
    "visited": _ad_events.EV_SITE_VISIT_BOOKED,
    "booked": _ad_events.EV_BOOKING,
    "booking": _ad_events.EV_BOOKING,
}
# CRM-true milestone beats the call score (booked > visited > qualified) — strongest-signal-wins.
_CRM_QUALITY = {
    "booked": _ad_events.EV_BOOKING,
    "visited": _ad_events.EV_SITE_VISIT_BOOKED,
    "qualified": _ad_events.EV_LEAD_QUALIFIED,
}
# Verdicts that mean the dial never reached a human -> no connection => no signal at all.
# NOTE: `not_qualified` / `junk` are NOT here — those mean the call CONNECTED (you learned the lead
# is bad by talking to them), so they emit call_connected (real engagement) but no quality rung.
_VERDICT_NOT_CONNECTED = frozenset({
    "not_connected", "no_answer", "no_response", "failed", "busy", "unreachable",
    "rejected", "voicemail", "disconnected", "abandoned",
})


def _norm_lc(s: Any) -> str:
    return str(s or "").strip().lower().replace("-", "_").replace(" ", "_")


def _resolve_ad_ref(lead: dict) -> dict:
    """Pull the ad/variant/source-campaign attribution a call lead carries (raw_fields/source_ref),
    so the emitted ad_events bind back to the exact creative + the source voice campaign."""
    rf = lead.get("raw_fields") if isinstance(lead.get("raw_fields"), dict) else {}
    sr = lead.get("source_ref") if isinstance(lead.get("source_ref"), dict) else {}
    ad_id = str(lead.get("ad_id") or rf.get("ad_id") or sr.get("ad_id")
                or lead.get("variant_id") or rf.get("variant_id") or sr.get("variant_id") or "")
    variant_id = str(lead.get("variant_id") or rf.get("variant_id") or sr.get("variant_id") or ad_id or "")
    scid = str(lead.get("source_campaign_id") or rf.get("source_campaign_id")
               or sr.get("source_campaign_id") or lead.get("campaign_id") or "")
    plat = _norm_lc(lead.get("platform") or rf.get("platform") or sr.get("platform")) or "meta"
    return {"ad_id": ad_id, "variant_id": variant_id, "source_campaign_id": scid, "platform": plat}


def emit_call_signal(tenant_id: str, lead: dict, verdict: Optional[str] = None, *,
                     now_epoch: Optional[float] = None) -> dict:
    """Fold a live 60s-call outcome into the ad_events conversion spine (the closed loop).

    Emits `call_connected` for any reached lead (a dense engagement proxy) AND the strongest quality
    rung the call/CRM produced (lead_qualified / hot / site_visit_booked / booking) — the real-buyer
    label the bandit rewards and `feedback`/`same_day_capi_drain` escalate to Meta same-day. A
    not_qualified / not-connected verdict emits NO positive signal (negative-by-absence, the honest
    negative). Idempotent (ad_events.ingest_event dedupes on event_id); append-only; NEVER raises."""
    out: dict = {"emitted": []}
    try:
        if not tenant_id or not isinstance(lead, dict):
            return out
        v = _norm_lc(verdict or lead.get("score"))
        crm = _norm_lc(lead.get("crm_outcome"))
        ref = _resolve_ad_ref(lead)
        ts = float(now_epoch if now_epoch is not None else time.time())
        base = {
            "lead_id": str(lead.get("lead_id") or ""),
            "ad_id": ref["ad_id"], "variant_id": ref["variant_id"],
            "source_campaign_id": ref["source_campaign_id"], "campaign_id": ref["source_campaign_id"],
            "platform": ref["platform"], "ts": ts,
            "sentiment": _norm_lc(lead.get("sentiment")),
            "value_minor": int(lead.get("value_minor") or 0),
            "phone": lead.get("phone"), "email": lead.get("email"), "name": lead.get("name"),
            "source_ref": lead.get("source_ref") if isinstance(lead.get("source_ref"), dict) else {},
        }
        # 1) Did the dial reach the lead? -> call_connected (a strong engagement proxy the optimizer counts).
        if v and v not in _VERDICT_NOT_CONNECTED:
            res = _ad_events.ingest_event(
                tenant_id, {**base, "type": _ad_events.EV_CALL_CONNECTED}, now_ts=ts)
            if res.get("ingested") or res.get("deduped"):
                out["emitted"].append(_ad_events.EV_CALL_CONNECTED)
        # 2) The strongest quality rung (CRM milestone beats call score) -> the real-buyer label.
        rung = _CRM_QUALITY.get(crm) or _VERDICT_QUALITY.get(v)
        if rung:
            res = _ad_events.ingest_event(tenant_id, {**base, "type": rung}, now_ts=ts)
            if res.get("ingested") or res.get("deduped"):
                out["emitted"].append(rung)
        return out
    except Exception as exc:  # noqa: BLE001 — the loop-closer never raises into the chain
        _log(f"emit_call_signal failed for tenant {tenant_id}: {exc!r}", level="warning")
        return out


async def process_post_launch_lead(tenant_id: str, raw_lead: dict, *,
                                   source: str = "ad", channel: str = "voice",
                                   event: Optional[str] = None,
                                   now_epoch: Optional[float] = None) -> dict:
    """The back half of the autonomy chain: a captured lead → (60s) call enqueue → quality feedback.

    EARNER-SAFE: `leads.ingest` runs the fail-closed compliance pre-dial gate and the call enqueue
    stays DRY-RUN until the 140-series flag (no real dial fires here). `feedback.emit_quality` is
    offline until CAPI/Data-Manager creds exist (negative-by-absence for junk leads). This is the
    SAME gated path the inbound webhook uses — the orchestrator only sequences it, adds no authority.

    CLOSING THE LOOP (V2-W6): the live call verdict (`event`) is ALSO folded into the ad_events spine
    via `emit_call_signal`, so the continuous optimizer learns on CONVERSATIONS (qualified/hot/booked),
    not clicks, and the same-day CAPI drain escalates the real-buyer label to Meta. `feedback.emit_quality`
    still fires the same-day CAPI signal directly (idempotent on event_id) — both paths converge.
    Returns {lead, feedback, events}. Never raises."""
    out: dict = {"lead": None, "feedback": None, "events": None}
    try:
        lead = leads.ingest(tenant_id, source, dict(raw_lead or {}),
                            channel=channel, now_epoch=now_epoch)
        out["lead"] = lead
        if not isinstance(lead, dict) or lead.get("status", "").startswith("blocked"):
            return out  # gated out (no consent / DND / cooloff) — never feed a signal.
        out["feedback"] = await feedback.emit_quality(tenant_id, lead, event=event,
                                                      now_epoch=now_epoch)
        # Fold the call outcome into the conversion-signal spine (optimize on conversations, not clicks).
        out["events"] = emit_call_signal(tenant_id, lead, event, now_epoch=now_epoch)
    except Exception as exc:  # noqa: BLE001 — the chain back-half never raises into a caller
        _log(f"process_post_launch_lead failed for tenant {tenant_id}: {exc!r}", level="warning")
    return out


__all__ = [
    "enable", "disable", "status", "advance", "tick_pass", "check_preconditions",
    "process_post_launch_lead", "emit_call_signal",
    "get_config", "get_state", "make_creative_service", "register_media_asset",
    "standalone_generate", "bridge_media_asset", "ensure_draft_plan", "StoreAssetBridge",
    "PH_IDLE", "PH_PROPOSING", "PH_CREATIVE", "PH_MODERATING", "PH_VIABILITY",
    "PH_LAUNCH_PENDING", "PH_LAUNCHED", "PH_BLOCKED", "PH_DONE",
]
