"""ads_engine.campaign — the standard-campaign builder + the publish/manage lifecycle (W5).

This is PURE orchestration + policy. It turns an approved brief into a published STANDARD Meta v25
campaign (no Advantage+/ASC on v25) or a Google v24 Search/PMax campaign, and owns the
campaign-side business rules. The actual platform HTTP lives in `connectors/meta.py` +
`connectors/google.py`; campaign.py only DECIDES the payload and DISPOSES the lifecycle. It NEVER
touches caller.py / agent.py / run_job / .env (earner-safe; conforms design/campaign.md).

THE FOUR BINDING GUARDS (design/campaign.md + redteam):

  1. SINGLE AUTHORITATIVE HOUSING SETTER (redteam api-version M4): `_apply_housing()` is the ONLY
     place special_ad_categories / special_ad_category_country / age / gender / geo are set. For the
     housing vertical it FORCES special_ad_categories=["HOUSING"] + special_ad_category_country=["IN"]
     and requires `is_property=true`. Illegal age/gender/zip/interest/lookalike targeting is
     impossible BY CONSTRUCTION — the targeting is built from a whitelist (meta.build_geo_radius_*),
     never validated-after-the-fact. The connectors send what campaign.py sets; they hold NO
     conditional HOUSING path.

  2. CPA x50 VIABILITY GATE WITH TEETH (redteam spend C3): monthly_floor = CPA_estimate x
     cpa_multiplier (cpa_multiplier clamped >=50 IN CODE, config.py). A sub-floor housing launch
     (below viability_block_ratio x floor, block_ratio clamped >=0.8 IN CODE) is a HARD BLOCK.
     warn_underfunded plans require an explicit step-up override to launch.

  3. PLATFORM CAPS AT PUBLISH (redteam spend C1): at publish time we set the ad-set daily_budget +
     lifetime cap on Meta, and the CampaignBudget ceiling on Google, so the PLATFORM stops delivery
     at the cap without depending on our poll-and-pause sweep.

  4. LIFECYCLE + IDEMPOTENCY: propose -> pending_approval -> approved -> active(DRY)/paused.
     plan_id idempotency at publish (re-publish of an already-published plan = no duplicate).
     Budget consolidation (one ad set, structural). Learning-phase edit lock.

DI: every dependency is bound once via `bind(...)` (the spine's DI spirit). campaign.py imports
NOTHING heavy at module load (the mount import-guard must never trip). Every public fn takes
`tenant_id` as its FIRST arg (tenant is token-derived by endpoints.py; never read from a body).
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

# Bound once by ads_engine wiring (see bind()). NEVER import caller.py here.
_store: Any = None        # ads_engine.store (tenant-scoped rows)
_config: Any = None       # ads_engine.config (knobs/caps/version pins)
_connectors: Any = None   # ads_engine.connectors (get_connector seam)
_guardrails: Any = None   # ads_engine.guardrails (spend-cap chain + status vocab)


def bind(*, store=None, config=None, connectors=None, guardrails=None) -> None:
    """Bind the injected seams once at mount time. Idempotent; never raises."""
    global _store, _config, _connectors, _guardrails
    if store is not None:
        _store = store
    if config is not None:
        _config = config
    if connectors is not None:
        _connectors = connectors
    if guardrails is not None:
        _guardrails = guardrails


def _cfg():
    if _config is not None:
        return _config
    from . import config as c  # lazy default — keeps module import cheap
    return c


def _st():
    if _store is not None:
        return _store
    from . import store as s
    return s


# ---------------------------------------------------------------------------
# Objective map (brief word -> Meta v25 ODAX outcome enum). Real-estate default = leads.
# CTWA lead-quality loop uses OUTCOME_LEADS w/ a messaging conversion location (redteam M3).
# NO legacy/ASC/AAC objective is emittable.
# ---------------------------------------------------------------------------
_OBJECTIVE_MAP = {
    "leads":      ("OUTCOME_LEADS", "LEAD_GENERATION"),
    "sales":      ("OUTCOME_SALES", "OFFSITE_CONVERSIONS"),
    "traffic":    ("OUTCOME_TRAFFIC", "LINK_CLICKS"),
    "awareness":  ("OUTCOME_AWARENESS", "REACH"),
    "engagement": ("OUTCOME_ENGAGEMENT", "POST_ENGAGEMENT"),
}
_DEFAULT_OBJECTIVE = "leads"

# Status vocabulary (mirrors _lib.ts AdsStatus). guardrails owns the blocked_cap/blocked_funds set.
ST_DRAFT = "draft"
ST_PENDING = "pending_approval"
ST_ACTIVE = "active"
ST_PAUSED = "paused"
ST_DRY_RUN = "dry_run"
ST_BLOCKED_FUNDS = "blocked_insufficient_funds"
ST_NOT_CONFIGURED = "not_configured"
ST_BLOCKED_PUBLISH = "blocked_publish_failed"

# Targeting keys that are ILLEGAL for a HOUSING campaign — must be impossible to reach.
_ILLEGAL_HOUSING_TARGETING_KEYS = frozenset({
    "interests", "flexible_spec", "exclusions", "behaviors", "zips",
    "zip", "postal_codes", "lookalike_spec", "custom_audiences",
    "interested_in", "relationship_statuses", "education_statuses",
    "income", "family_statuses", "work_positions",
})


def _new_plan_id() -> str:
    return "cmp_" + uuid.uuid4().hex[:10]


# ===========================================================================
# 1. SINGLE AUTHORITATIVE HOUSING SETTER (redteam api-version M4).
#    The ONLY place HOUSING fields + protected-class-safe targeting are set.
# ===========================================================================
def _apply_housing(plan: dict, brief: dict) -> dict:
    """Force the HOUSING Special Ad Category + the anti-discrimination targeting whitelist.

    This is the single authoritative setter. For the housing vertical it is MANDATORY:
      * `is_property=true` is REQUIRED on the brief; absent -> ValueError (no silent housing path).
      * special_ad_categories = ["HOUSING"], special_ad_category_country = ["IN"] (India-only).
      * targeting is built from connectors/meta.build_geo_radius_targeting (age 18/65, all genders,
        radius >= floor, NO zip/interests/exclusions/lookalike) — illegal targeting cannot exist.
      * any illegal targeting key the brief tries to smuggle in is RECORDED in `stripped[]` and
        NEVER copied onto the plan.

    Returns the plan, mutated in place. Raises ValueError ONLY for the missing-is_property guard
    (a programmer/compliance error, surfaced to the caller, never published).
    """
    cfg = _cfg()
    # Mandatory property assertion — a HOUSING campaign with no property flag is refused.
    if not bool(brief.get("is_property")):
        raise ValueError("housing campaign requires is_property=true on the brief")

    plan["special_ad_category"] = "HOUSING"
    plan["special_ad_categories"] = ["HOUSING"]
    plan["special_ad_category_country"] = ["IN"]

    # Geo pin is required for a housing campaign (radius around the project, no neighbourhood/ZIP).
    pin = brief.get("geo_pin") or brief.get("pin") or {}
    try:
        lat = float(pin.get("lat", pin.get("latitude")))
        lng = float(pin.get("lng", pin.get("longitude")))
    except (TypeError, ValueError):
        raise ValueError("housing campaign requires a project geo_pin {lat,lng}")

    floor = float(cfg.min_radius_km())
    req_radius = brief.get("radius_km") or brief.get("radius") or floor
    try:
        radius = max(float(req_radius), floor)  # bump UP to floor, never below
    except (TypeError, ValueError):
        radius = floor

    # Build targeting via the connector's SAFE-WHITELIST constructor when available; else inline.
    targeting = _build_housing_targeting(lat=lat, lng=lng, radius_km=radius)

    # Record (transparency) what the brief tried to set that we stripped.
    stripped: list = []
    brief_aud = brief.get("audience") or {}
    for k in _ILLEGAL_HOUSING_TARGETING_KEYS:
        if k in brief_aud or k in brief:
            stripped.append(k)
    for k in ("age_min", "age_max", "genders", "age", "gender"):
        if k in brief_aud:
            stripped.append(k)  # locked demographics — brief values ignored

    plan["targeting"] = targeting
    plan["targeting_stripped"] = sorted(set(stripped))
    # HARD post-condition: assert no illegal key is reachable on the emitted targeting.
    _assert_housing_targeting_legal(targeting)
    return plan


def _build_housing_targeting(*, lat: float, lng: float, radius_km: float) -> dict:
    """Build the HOUSING-safe targeting via meta.build_geo_radius_targeting (the whitelist).
    Falls back to an inline whitelist if the connector class is unavailable (offline build)."""
    try:
        from .connectors.meta import MetaConnector
        # Build with no creds (a pure payload builder; no network).
        return MetaConnector(None).build_geo_radius_targeting(
            latitude=lat, longitude=lng, radius_km=radius_km, country="IN", housing=True)
    except Exception:  # noqa: BLE001 — degrade to an inline whitelist; still legal-by-construction
        return {
            "geo_locations": {
                "custom_locations": [{
                    "latitude": round(float(lat), 6),
                    "longitude": round(float(lng), 6),
                    "radius": float(radius_km),
                    "distance_unit": "kilometer",
                }],
                "location_types": ["home", "recent"],
            },
            "age_min": 18,
            "age_max": 65,
            "genders": [1, 2],
        }


def _assert_housing_targeting_legal(targeting: dict) -> None:
    """Fail-closed: the emitted HOUSING targeting MUST carry age 18/65 + all genders and MUST NOT
    carry any illegal narrowing key. Any violation raises (an illegal plan can never be persisted).
    """
    if not isinstance(targeting, dict):
        raise ValueError("housing targeting must be a dict")
    if targeting.get("age_min") != 18 or targeting.get("age_max") != 65:
        raise ValueError("housing targeting must lock age 18..65 (65+)")
    if sorted(targeting.get("genders") or []) != [1, 2]:
        raise ValueError("housing targeting must include all genders [1,2]")
    for k in _ILLEGAL_HOUSING_TARGETING_KEYS:
        if k in targeting:
            raise ValueError(f"illegal housing targeting key reachable: {k}")
    geo = targeting.get("geo_locations") or {}
    # geo must be radius-only (custom_locations); no zip/region narrowing keys.
    for k in ("zips", "regions", "cities", "neighborhoods"):
        if k in geo:
            raise ValueError(f"illegal housing geo narrowing key: {k}")
    locs = geo.get("custom_locations") or []
    if not locs:
        raise ValueError("housing targeting requires a geo-radius custom_location")


# ===========================================================================
# 2. CPA x50 VIABILITY GATE WITH TEETH (redteam spend C3).
# ===========================================================================
def assess_viability(tenant_id: str, plan: dict) -> dict:
    """Compute the monthly budget floor to exit Meta's learning phase, and verdict the plan.

    monthly_floor = CPA_estimate x cpa_multiplier (scaled to a month). cpa_multiplier is clamped
    >=50 IN CODE (config.cpa_multiplier). A housing launch funded below
    viability_block_ratio x floor (block_ratio clamped >=0.8 IN CODE) is a HARD BLOCK. Anything
    below the floor but above the block ratio is warn_underfunded (needs a step-up override).
    """
    cfg = _cfg()
    cpa_minor = int(plan.get("cpl_max_minor") or 0) or int(cfg.default_cpl_minor())
    cpa_minor = max(1, cpa_minor)
    events = int(cfg.cpa_multiplier())              # >= 50 by code clamp
    block_ratio = float(cfg.viability_block_ratio())  # >= 0.8 by code clamp

    # Floor: ~`events` conversions/week to exit learning, expressed monthly (x30/7).
    weekly_floor = cpa_minor * events
    monthly_floor_minor = int(round(weekly_floor * (30.0 / 7.0)))
    monthly_budget_minor = int(plan.get("budget_daily_minor", 0) or 0) * 30
    shortfall = monthly_floor_minor - monthly_budget_minor

    is_housing = str(plan.get("special_ad_category") or "") == "HOUSING"

    if monthly_budget_minor <= 0:
        verdict, reason = "blocked_underfunded", "No daily budget set."
    elif monthly_budget_minor < monthly_floor_minor * block_ratio:
        # HARD BLOCK: sub-floor launch (especially housing — never a soft warn here).
        verdict = "blocked_underfunded"
        reason = (
            f"Budget ~Rs{monthly_budget_minor // 100}/mo is below the hard floor "
            f"(>={int(monthly_floor_minor * block_ratio) // 100}/mo, "
            f"{int(block_ratio * 100)}% of the Rs{monthly_floor_minor // 100}/mo needed for "
            f"~{events} conversions to exit Meta's learning phase at a "
            f"Rs{cpa_minor // 100} target CPL). Raise budget or CPL.")
    elif shortfall > 0:
        verdict, reason = "warn_underfunded", (
            f"Budget covers fewer than {events} learning conversions/mo; CPL may stay unstable. "
            f"Recommended >= Rs{monthly_floor_minor // 100}/mo. Launch requires an explicit "
            f"step-up override.")
    else:
        verdict, reason = "ok", ""

    return {
        "verdict": verdict,
        "cpa_minor": cpa_minor,
        "events_needed": events,
        "block_ratio": block_ratio,
        "monthly_floor_minor": monthly_floor_minor,
        "monthly_budget_minor": monthly_budget_minor,
        "shortfall_minor": max(0, shortfall),
        "is_housing": is_housing,
        "reason": reason,
    }


# ===========================================================================
# 3. BUDGET CONSOLIDATION (structural) + objective mapping + plan build.
# ===========================================================================
def consolidate_budget(plan: dict) -> dict:
    """Enforce ONE ad set: the plan carries exactly one budget_daily_minor + one targeting block.
    Any multi-audience/geo split in the brief is recorded as an optimizer note, never fragmented
    into many tiny ad sets (don't shatter the learning signal). Structural, not a runtime choice."""
    plan["ad_set_count"] = 1
    notes = plan.get("notes") or []
    if plan.pop("_split_intent", None):
        notes.append("split-test intent folded into one ad set (creative-level test); "
                     "optimizer reads per-ad results")
    plan["notes"] = notes
    return plan


def _map_objective(brief: dict) -> tuple[str, str]:
    raw = str(brief.get("objective") or _DEFAULT_OBJECTIVE).strip().lower()
    # tolerate already-mapped enum form.
    for word, (obj, opt) in _OBJECTIVE_MAP.items():
        if raw == word or raw == obj.lower():
            return obj, opt
    return _OBJECTIVE_MAP[_DEFAULT_OBJECTIVE]


def build_plan(tenant_id: str, brief: dict) -> dict:
    """Build a HOUSING-safe, budget-consolidated CampaignPlan from a brief. HOUSING fields and the
    anti-discrimination targeting are applied BEFORE the plan is returned, so an illegal plan can
    never exist. Raises ValueError on a missing-is_property / missing-pin housing guard."""
    provider = str(brief.get("provider") or "meta").lower()
    objective, optimization_goal = _map_objective(brief)
    ctwa = bool(brief.get("ctwa")) or str(brief.get("destination_type") or "").upper() == "WHATSAPP"

    plan: dict = {
        "name": str(brief.get("name") or "ElevateX Campaign"),
        "provider": provider,
        "objective": objective,
        "optimization_goal": optimization_goal,
        "billing_event": str(brief.get("billing_event") or "IMPRESSIONS"),
        "bid_strategy": str(brief.get("bid_strategy") or "LOWEST_COST_WITHOUT_CAP"),
        "destination_type": "WHATSAPP" if ctwa else str(brief.get("destination_type") or "ON_AD"),
        "budget_daily_minor": int(brief.get("budget_daily_minor", 0) or 0),
        "lifetime_budget_minor": int(brief.get("lifetime_budget_minor", 0) or 0),
        "cpl_max_minor": int(brief.get("cpl_max_minor", 0) or 0),
        "channel_type": str(brief.get("channel_type") or "SEARCH").upper(),  # google
        "promoted_object": brief.get("promoted_object") or {},
        "creatives": list(brief.get("creatives") or []),
        "status": "PAUSED",
    }
    if brief.get("_split_intent"):
        plan["_split_intent"] = True

    # SINGLE authoritative HOUSING setter — the only place targeting/special-ad fields are set.
    _apply_housing(plan, brief)
    consolidate_budget(plan)

    # Caps: a plan ALWAYS carries a daily + lifetime cap (defaults from config caps if unset).
    caps = _cfg().caps()
    plan["daily_cap_minor"] = int(brief.get("daily_cap_minor")
                                  or caps.get("daily_cap_minor", 0)
                                  or plan["budget_daily_minor"])
    plan["lifetime_cap_minor"] = int(brief.get("lifetime_cap_minor")
                                     or caps.get("lifetime_cap_minor", 0)
                                     or 0)
    return plan


# ===========================================================================
# 4. LIFECYCLE: propose -> pending_approval -> approved -> active(DRY)/paused.
# ===========================================================================
def _persist(tenant_id: str, rec: dict) -> dict:
    return _st().put_row(tenant_id, "campaigns", rec["plan_id"], rec)


def propose(tenant_id: str, brief: dict) -> dict:
    """Build a HOUSING-safe plan, run the viability gate, persist a draft (or a blocked record).

    NO spend. Returns {ok, status, plan_id, plan, viability}. A sub-floor housing launch is
    persisted as blocked_insufficient_funds and CANNOT be approved until the budget/CPL is fixed.
    A missing-is_property/pin housing guard returns ok=False with the reason (never persisted live).
    """
    try:
        plan = build_plan(tenant_id, brief)
    except ValueError as exc:
        return {"ok": False, "status": "invalid_request", "plan_id": None,
                "reason": str(exc)}

    viability = assess_viability(tenant_id, plan)
    plan_id = str(brief.get("plan_id") or _new_plan_id())
    now = int(time.time())

    if viability["verdict"] == "blocked_underfunded":
        status = ST_BLOCKED_FUNDS
    else:
        status = ST_DRAFT  # 'ok' or 'warn_underfunded' are both proposable

    rec = {
        "plan_id": plan_id,
        "org_id": tenant_id,
        "tenant_id": tenant_id,
        "provider": plan["provider"],
        "name": plan["name"],
        "objective": plan["objective"],
        "special_ad_category": plan.get("special_ad_category"),
        "special_ad_category_country": plan.get("special_ad_category_country"),
        "plan": plan,
        "status": status,
        "viability": viability,
        "review_status": {"summary": "n/a", "ads": {}},
        "campaign_ref": "",
        "adset_ref": "",
        "budget_ref": "",
        "ad_refs": [],
        "budget_daily_minor": plan["budget_daily_minor"],
        "daily_cap_minor": plan["daily_cap_minor"],
        "lifetime_cap_minor": plan["lifetime_cap_minor"],
        "cpl_max_minor": plan["cpl_max_minor"],
        "caps_set_at_publish": False,
        "learning": {"phase": "none", "started_ts": None,
                     "locked_until_ts": None, "conversions_in_phase": 0},
        "approved_by": None,
        "approved_ts": None,
        "pause_reason": "",
        "created_ts": now,
        "updated_ts": now,
        "engine_version": _cfg().META_API_VERSION,
    }
    _persist(tenant_id, rec)
    return {"ok": True, "status": status, "plan_id": plan_id,
            "plan": plan, "viability": viability}


async def approve(tenant_id: str, plan_id: str, *, step_up: bool = False,
                  actor: str = "system") -> dict:
    """Approve + publish a proposed campaign. SPEND-MUTATING (gated by step-up at the endpoint).

    Guards, in order:
      * record must exist + be in a proposable state (draft/pending/warn).
      * blocked_underfunded -> refused (re-propose to fix); never publishes.
      * warn_underfunded -> requires `step_up=True` (the explicit founder override, redteam C3).
      * IDEMPOTENCY: if already active/dry_run with a campaign_ref, return it — NO duplicate publish.
      * publish via the connector (DRY-RUN-safe); set PLATFORM CAPS AT PUBLISH (redteam C1);
        flip ACTIVE only on a clean publish (or persist dry_run when config.dry_run).
    """
    st = _st()
    cfg = _cfg()
    rec = st.get_row(tenant_id, "campaigns", plan_id)
    if not rec:
        return {"ok": False, "status": "not_found", "plan_id": plan_id,
                "reason": "campaign not found"}

    # ---- IDEMPOTENCY (redteam M5): already published -> no duplicate. ----
    if rec.get("status") in (ST_ACTIVE, ST_DRY_RUN) and rec.get("campaign_ref"):
        return {"ok": True, "status": rec["status"], "plan_id": plan_id,
                "campaign_ref": rec["campaign_ref"], "already": True,
                "spending": rec["status"] == ST_ACTIVE}

    viability = rec.get("viability") or {}
    if viability.get("verdict") == "blocked_underfunded" or rec.get("status") == ST_BLOCKED_FUNDS:
        return {"ok": False, "status": ST_BLOCKED_FUNDS, "plan_id": plan_id,
                "reason": viability.get("reason") or "campaign is under-funded; re-propose to fix"}

    # warn_underfunded requires the explicit step-up override.
    if viability.get("verdict") == "warn_underfunded" and not step_up:
        return {"ok": False, "status": "blocked_not_approved", "plan_id": plan_id,
                "reason": "under-funded plan requires an explicit step-up override to launch",
                "viability": viability}

    plan = rec.get("plan") or {}
    # Defensive: re-assert HOUSING legality before any publish (an illegal plan never ships).
    if str(plan.get("special_ad_category")) == "HOUSING":
        try:
            _assert_housing_targeting_legal(plan.get("targeting") or {})
        except ValueError as exc:
            return {"ok": False, "status": "invalid_request", "plan_id": plan_id,
                    "reason": f"housing legality check failed: {exc}"}

    now = int(time.time())
    rec["status"] = ST_PENDING
    rec["approved_by"] = actor
    rec["approved_ts"] = now
    rec["updated_ts"] = now
    _persist(tenant_id, rec)

    provider = str(rec.get("provider") or "meta").lower()

    # ---- DRY-RUN: full path, synthetic refs, no real spend. ----
    if cfg.dry_run():
        rec["status"] = ST_DRY_RUN
        rec["campaign_ref"] = f"dry_{plan_id}"
        rec["adset_ref"] = f"dry_adset_{plan_id}"
        rec["budget_ref"] = f"dry_budget_{plan_id}"
        rec["caps_set_at_publish"] = True  # caps would be set on the platform at publish
        rec["updated_ts"] = int(time.time())
        _persist(tenant_id, rec)
        return {"ok": True, "status": ST_DRY_RUN, "plan_id": plan_id,
                "campaign_ref": rec["campaign_ref"], "spending": False,
                "caps_set": True}

    # ---- BLINDSPOTS B14: MANAGED-FUNDING PRE-CHECK (live path only). When the vendor funds through
    # OUR gateway (the managed model — a payment_gateway key is connected), a real launch must not
    # publish unless the funded paise balance covers the campaign's monthly budget; a shortfall is a
    # HARD blocked_insufficient_funds. We scope the gate to "a gateway is configured" so the
    # vendor-own-card model (balance lives on Meta, never on us) is NOT falsely blocked. Fail-CLOSED
    # within the managed model: if a connected gateway's balance can't be read it counts as un-funded.
    try:
        from . import budget as _budget
        _managed_funding = bool(_budget.configured_provider(tenant_id))
    except Exception:  # noqa: BLE001
        _budget, _managed_funding = None, False
    if cfg.require_funded() and _managed_funding:
        try:
            required_minor = int((viability.get("monthly_budget_minor")
                                  or (int(rec.get("daily_cap_minor") or plan.get("budget_daily_minor") or 0) * 30)))
            funded_ok = _budget.is_funded(tenant_id, required_minor)
        except Exception:  # noqa: BLE001 — any error => fail-closed (treat as un-funded)
            required_minor, funded_ok = 0, False
        if not funded_ok:
            rec["status"] = ST_BLOCKED_FUNDS
            rec["pause_reason"] = "ad-budget account not funded for this monthly budget"
            rec["updated_ts"] = int(time.time())
            _persist(tenant_id, rec)
            return {"ok": False, "status": ST_BLOCKED_FUNDS, "plan_id": plan_id,
                    "reason": "ad budget not funded — add budget via the payment gateway before launch",
                    "required_minor": required_minor, "spending": False}

    # ---- LIVE publish (connector resolves creds; dormant -> not_configured, no spend). ----
    conn = None
    if _connectors is not None:
        try:
            conn = _connectors.get_connector(tenant_id, provider)
        except Exception:  # noqa: BLE001
            conn = None
    if conn is None:
        rec["status"] = ST_NOT_CONFIGURED
        rec["updated_ts"] = int(time.time())
        _persist(tenant_id, rec)
        return {"ok": False, "status": ST_NOT_CONFIGURED, "plan_id": plan_id,
                "reason": f"{provider} not configured (no vault creds)"}

    if provider == "google":
        result = await _publish_google(tenant_id, conn, rec, plan)
    else:
        result = await _publish_meta(tenant_id, conn, rec, plan)
    return result


async def _publish_meta(tenant_id: str, conn: Any, rec: dict, plan: dict) -> dict:
    """Meta publish: batch create (PAUSED) -> set PLATFORM CAPS at publish -> flip ACTIVE."""
    plan_id = rec["plan_id"]
    housing = str(plan.get("special_ad_category")) == "HOUSING"
    creatives = plan.get("creatives") or []

    res = await conn.publish(plan, creatives, housing=housing)
    if not getattr(res, "ok", False):
        rec["status"] = ST_BLOCKED_PUBLISH
        rec["pause_reason"] = f"publish failed: {getattr(res, 'error', '')}"
        rec["updated_ts"] = int(time.time())
        _persist(tenant_id, rec)
        return {"ok": False, "status": ST_BLOCKED_PUBLISH, "plan_id": plan_id,
                "reason": rec["pause_reason"]}

    refs = _parse_meta_batch(res.data)
    rec["campaign_ref"] = refs.get("campaign", "")
    rec["adset_ref"] = refs.get("adset", "")
    rec["ad_refs"] = refs.get("ads", [])

    # REDTEAM C1 — PLATFORM CAPS AT PUBLISH: set ad-set daily + lifetime budget on Meta.
    caps_set = False
    if rec["adset_ref"]:
        cap_res = await conn.set_caps(
            adset_id=rec["adset_ref"],
            daily_budget_minor=int(rec.get("daily_cap_minor") or plan.get("budget_daily_minor") or 0),
            lifetime_budget_minor=int(rec.get("lifetime_cap_minor") or 0))
        caps_set = bool(getattr(cap_res, "ok", False))
        if not caps_set:
            # fail-closed: leave PAUSED, do NOT flip active without a platform cap in place.
            rec["status"] = ST_BLOCKED_PUBLISH
            rec["pause_reason"] = "platform cap not set; refusing to activate uncapped"
            rec["updated_ts"] = int(time.time())
            _persist(tenant_id, rec)
            return {"ok": False, "status": ST_BLOCKED_PUBLISH, "plan_id": plan_id,
                    "reason": rec["pause_reason"], "campaign_ref": rec["campaign_ref"]}

    # Flip ACTIVE only after cap is in place.
    if rec["campaign_ref"]:
        await conn.set_status(object_id=rec["campaign_ref"], status="ACTIVE")
    now = int(time.time())
    rec["status"] = ST_ACTIVE
    rec["caps_set_at_publish"] = caps_set
    rec["learning"] = {"phase": "learning", "started_ts": now,
                       "locked_until_ts": now + _cfg().learning_lock_days() * 86400,
                       "conversions_in_phase": 0}
    rec["review_status"] = {"summary": "pending",
                            "ads": {a: {"status": "PENDING_REVIEW", "code": None, "ts": now}
                                    for a in rec["ad_refs"]}}
    rec["updated_ts"] = now
    _persist(tenant_id, rec)
    return {"ok": True, "status": ST_ACTIVE, "plan_id": plan_id,
            "campaign_ref": rec["campaign_ref"], "spending": True, "caps_set": caps_set}


async def _publish_google(tenant_id: str, conn: Any, rec: dict, plan: dict) -> dict:
    """Google publish: single atomic mutate (CampaignBudget ceiling is set IN the publish)."""
    plan_id = rec["plan_id"]
    # The CampaignBudget amountMicros is set from daily_cap_minor inside create_campaign -> the
    # platform cap is established AT PUBLISH (redteam C1) within the same atomic mutate.
    gplan = dict(plan)
    gplan["daily_budget_minor"] = int(rec.get("daily_cap_minor")
                                      or plan.get("budget_daily_minor") or 0)
    res = await conn.publish(gplan)
    if not getattr(res, "ok", False):
        rec["status"] = ST_BLOCKED_PUBLISH
        rec["pause_reason"] = f"publish failed: {getattr(res, 'error', '')}"
        rec["updated_ts"] = int(time.time())
        _persist(tenant_id, rec)
        return {"ok": False, "status": ST_BLOCKED_PUBLISH, "plan_id": plan_id,
                "reason": rec["pause_reason"]}

    refs = _parse_google_mutate(res.data)
    rec["campaign_ref"] = refs.get("campaign", "")
    rec["budget_ref"] = refs.get("budget", "")
    now = int(time.time())
    rec["status"] = ST_ACTIVE
    rec["caps_set_at_publish"] = True  # the CampaignBudget ceiling is set in the publish mutate.
    rec["learning"] = {"phase": "learning", "started_ts": now,
                       "locked_until_ts": now + _cfg().learning_lock_days() * 86400,
                       "conversions_in_phase": 0}
    rec["updated_ts"] = now
    _persist(tenant_id, rec)
    return {"ok": True, "status": ST_ACTIVE, "plan_id": plan_id,
            "campaign_ref": rec["campaign_ref"], "spending": True, "caps_set": True}


async def pause(tenant_id: str, plan_id: str, reason: str = "", *,
                actor: str = "system") -> dict:
    """Pause a live campaign. ALWAYS allowed (a pause is not a learning-resetting edit, design §3d).
    Idempotent: pausing an already-paused campaign returns already=True."""
    st = _st()
    rec = st.get_row(tenant_id, "campaigns", plan_id)
    if not rec:
        return {"ok": False, "status": "not_found", "plan_id": plan_id,
                "reason": "campaign not found"}
    if rec.get("status") == ST_PAUSED:
        return {"ok": True, "status": ST_PAUSED, "plan_id": plan_id, "already": True}

    # Best-effort platform pause (DRY-RUN / dormant -> state-only pause; never raises).
    if rec.get("status") == ST_ACTIVE and rec.get("adset_ref") and _connectors is not None:
        try:
            conn = _connectors.get_connector(tenant_id, str(rec.get("provider") or "meta"))
            if conn is not None and rec.get("provider") != "google":
                await conn.set_status(object_id=rec["adset_ref"], status="PAUSED")
        except Exception:  # noqa: BLE001 — pause must never raise into the spine
            pass

    rec["status"] = ST_PAUSED
    rec["pause_reason"] = reason or "paused by operator"
    rec["updated_ts"] = int(time.time())
    _persist(tenant_id, rec)
    return {"ok": True, "status": ST_PAUSED, "plan_id": plan_id, "already": False}


def list_campaigns(tenant_id: str) -> dict:
    """List this tenant's campaigns + the config health block (the FE renders the page from this)."""
    cfg = _cfg()
    campaigns = list(_st().get_collection(tenant_id, "campaigns").values())
    return {"ok": True, "campaigns": campaigns, "config": cfg.health_block()}


# ===========================================================================
# 5. LEARNING-PHASE EDIT LOCK (design §3d). pause is ALWAYS allowed (handled above).
# ===========================================================================
def assert_editable(tenant_id: str, rec: dict, change: dict) -> tuple[bool, str]:
    """May this budget/bid/targeting edit proceed during the learning phase?

    During learning, an edit shifting budget/bid/targeting > learning_edit_pct (~20%) would reset
    Meta's learning — block it. Pause is NOT routed here (always allowed)."""
    cfg = _cfg()
    L = rec.get("learning") or {}
    if L.get("phase") not in ("learning", "learning_limited"):
        return True, ""
    now = time.time()
    locked_until = L.get("locked_until_ts")
    if locked_until and now < locked_until:
        pct = _change_magnitude(rec, change)
        if pct > cfg.learning_edit_pct():
            days_left = round((locked_until - now) / 86400, 1)
            return False, (f"Campaign is in Meta's learning phase ({days_left}d left). A "
                           f"{round(pct * 100)}% change would reset learning (Meta resets on "
                           f">{round(cfg.learning_edit_pct() * 100)}% edits). Make a smaller "
                           f"change or wait.")
    return True, ""


def _change_magnitude(rec: dict, change: dict) -> float:
    """Max relative delta across budget/bid (targeting change counts as a full reset = 1.0)."""
    if change.get("targeting") is not None:
        return 1.0
    worst = 0.0
    for field, cur_key in (("budget_daily_minor", "budget_daily_minor"),
                           ("bid_amount_minor", "bid_amount_minor")):
        if field in change:
            cur = float((rec.get("plan") or {}).get(cur_key, rec.get(cur_key, 0)) or 0)
            new = float(change.get(field) or 0)
            if cur > 0:
                worst = max(worst, abs(new - cur) / cur)
            elif new > 0:
                worst = max(worst, 1.0)
    return worst


# ===========================================================================
# 6. Batch-response parsers (connector returns raw platform JSON; we extract refs).
# ===========================================================================
def _parse_meta_batch(data: Any) -> dict:
    """Parse a Graph batch response -> {campaign, adset, ads:[...]}. Best-effort; never raises.

    A Graph batch returns an ordered list of sub-responses; each has a `body` (JSON string) with an
    `id`. Order matches build_publish_batch: [campaign, adset, (creative, ad)*]."""
    out = {"campaign": "", "adset": "", "ads": []}
    try:
        items = data if isinstance(data, list) else (data or {}).get("data") or []
        ids: list = []
        for it in items:
            body = it.get("body") if isinstance(it, dict) else None
            if isinstance(body, str):
                import json as _json
                try:
                    body = _json.loads(body)
                except Exception:  # noqa: BLE001
                    body = {}
            oid = (body or {}).get("id") if isinstance(body, dict) else None
            ids.append(oid)
        if ids:
            out["campaign"] = ids[0] or ""
        if len(ids) > 1:
            out["adset"] = ids[1] or ""
        # remaining ids alternate creative, ad — collect the ad ids (every 2nd after adset).
        rest = ids[2:]
        out["ads"] = [rest[i] for i in range(1, len(rest), 2) if rest[i]]
    except Exception:  # noqa: BLE001
        pass
    return out


def _parse_google_mutate(data: Any) -> dict:
    """Parse a googleAds:mutate response -> {campaign, budget}. Best-effort; never raises."""
    out = {"campaign": "", "budget": ""}
    try:
        results = (data or {}).get("mutateOperationResponses") or (data or {}).get("results") or []
        for r in results:
            if not isinstance(r, dict):
                continue
            camp = r.get("campaignResult") or {}
            bud = r.get("campaignBudgetResult") or {}
            if camp.get("resourceName"):
                out["campaign"] = camp["resourceName"]
            if bud.get("resourceName"):
                out["budget"] = bud["resourceName"]
    except Exception:  # noqa: BLE001
        pass
    return out
