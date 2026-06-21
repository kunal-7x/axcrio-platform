"""entitlements.py — FOUNDATION CONTROL LAYER engine (CL-B1 / plan C0+C1).

The home-grown entitlement engine: the single source of truth for "what mode is feature X for tenant T".
Spec: design/control-datamodel.md §2 (resolution algorithm) + CONTROL_LAYER_EXECUTION_PLAN.md §2.

DESIGN POSTURE (mirrors crm/core.py + wallet.py — the proven F2/F4/crm precedents):
  * IMPORT-SAFE DEGRADE: if db.engine is unavailable, available() -> False and every tenant-row read
    returns empty -> resolution falls back to the global default (all 'on') -> live site untouched.
  * Lazy ensure_schema() applies db/ddl_control.sql idempotently as the app role (is_admin GUC).
  * The CATALOG (feature_registry) + PLANS are seeded from var/control/{registry,plans}.json — the
    source of truth that works even BEFORE the PG cutover. Tenant-scoped rows (overrides, status) read
    from PG when available (RLS-scoped via db.engine.session). This is the json|dual|pg strangler shape.
  * NOT registered in the store.py JSON-mirror seam (it's a PG-native control table set, like contacts /
    wallet_accounts). Catalog truth = the seed JSON; tenant truth = PG (or all-default when PG absent).

RESOLUTION (most-specific-wins, FAIL-CLOSED):
  status gate ▸ per-vendor override ▸ plan entitlement ▸ global default ▸ parent rolldown tightens ▸
  unknown/garbage ▸ hidden.  is_core is a floor that survives all of it (never hidden — anti-lockout).

OpenFeature-style FACADE at the bottom (get_provider / set_provider) so the store is swappable later
(to flagd / Flagsmith) without touching a single call-site in caller.py — the OSS-research verdict.

RESTING STATE: with every tenant on the default plan + empty overrides + status='active', resolve_modes
returns 'on' for EVERY key -> behavior byte-identical to today (T17). Ships behind CONTROL_ENABLED.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("entitlements")

# ── paths / constants ──────────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHEMA_PATH = os.path.join(_DIR, "db", "ddl_control.sql")
_REGISTRY_JSON = os.path.join(_DIR, "var", "control", "registry.json")
_PLANS_JSON = os.path.join(_DIR, "var", "control", "plans.json")

MODES = ("on", "hidden", "locked")
_STRICT = {"on": 0, "locked": 1, "hidden": 2}   # rolldown strictness: hidden > locked > on
_STATUS_GATED = ("suspended", "disabled", "expired")

# HTTP codes the enforcement choke-point (C3) raises; defined here so the engine is the single source.
HIDDEN_CODE = 404
LOCKED_CODE = 402

# ── module state ───────────────────────────────────────────────────────────
_schema_ready: Optional[bool] = None
_registry_cache: Optional[dict] = None          # { key -> meta }
_plans_cache: Optional[dict] = None              # { plan_id -> {entitlements, limits, is_default, ...} }
_lock = threading.RLock()

# per-tenant resolved-mode cache, keyed by (tenant_id, ent_version). Invalidated by a version bump.
_resolve_cache: dict[tuple[str, int], dict[str, str]] = {}


# ════════════════════════════════════════════════════════════════════════
# init / availability  (mirrors crm/core.py + wallet.py)
# ════════════════════════════════════════════════════════════════════════
def init(config: Any = None) -> bool:
    """Optional wiring hook (called from caller.py after store.init). Loads the catalog/plans seed +
    best-effort applies the schema. Returns True if PG is reachable. NEVER raises."""
    try:
        load_registry()
        load_plans()
    except Exception as exc:  # noqa: BLE001
        logger.warning("entitlements seed load failed (degrade): %r", exc)
    try:
        ensure_schema()
    except Exception:  # noqa: BLE001
        pass
    return available()


def _engine():
    try:
        from db import engine  # type: ignore
        return engine
    except Exception:  # noqa: BLE001
        return None


def available() -> bool:
    eng = _engine()
    try:
        return bool(eng and eng.available())
    except Exception:  # noqa: BLE001
        return False


def status() -> dict:
    reg = None
    try:
        reg = len(load_registry())
    except Exception:  # noqa: BLE001
        pass
    return {
        "pg_available": available(),
        "schema_ready": bool(_schema_ready),
        "registry_keys": reg,
        "plans": list((load_plans() or {}).keys()),
        "resolve_cache_size": len(_resolve_cache),
        "provider": _PROVIDER.__class__.__name__ if _PROVIDER else None,
    }


def ensure_schema() -> bool:
    """Apply db/ddl_control.sql idempotently as the app role. NEVER raises -> False (degrade)."""
    global _schema_ready
    if _schema_ready:
        return True
    if not available():
        return False
    eng = _engine()
    try:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as fh:
            ddl = fh.read()
        with eng.session(tenant_id="", is_admin=True) as s:  # type: ignore
            s.connection().exec_driver_sql(ddl)
        _schema_ready = True
        logger.info("control schema ensured")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("entitlements.ensure_schema failed (degrade): %r", exc)
        _schema_ready = False
        return False


# ════════════════════════════════════════════════════════════════════════
# CATALOG + PLANS — loaded from the seed JSON (source of truth, works pre-PG)
# ════════════════════════════════════════════════════════════════════════
def load_registry() -> dict[str, dict]:
    """{ key -> {parent_key, default_mode, is_core, kind, label, nav_href, api_prefixes, min_role} }.
    Cached. PG feature_registry can later override the seed (drift sync), but seed JSON is canonical."""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache
    with _lock:
        if _registry_cache is not None:
            return _registry_cache
        out: dict[str, dict] = {}
        try:
            with open(_REGISTRY_JSON, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            for r in doc.get("features", []):
                k = r["key"]
                out[k] = {
                    "key": k,
                    "kind": r.get("kind", "page"),
                    "parent_key": r.get("parent_key"),
                    "label": r.get("label", ""),
                    "nav_href": r.get("nav_href"),
                    "api_prefixes": list(r.get("api_prefixes") or []),
                    "default_mode": r.get("default_mode", "on"),
                    "min_role": r.get("min_role"),
                    "is_core": bool(r.get("is_core", False)),
                    "sort_order": r.get("sort_order", 0),
                }
        except Exception as exc:  # noqa: BLE001
            logger.error("load_registry failed: %r", exc)
            out = {}
        _registry_cache = out
        return out


def load_plans() -> dict[str, dict]:
    """{ plan_id -> {name, is_default, entitlements:{key:mode}, limits:{key:int}} }. Cached."""
    global _plans_cache
    if _plans_cache is not None:
        return _plans_cache
    with _lock:
        if _plans_cache is not None:
            return _plans_cache
        out: dict[str, dict] = {}
        try:
            with open(_PLANS_JSON, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            for p in doc.get("plans", []):
                out[p["plan_id"]] = {
                    "plan_id": p["plan_id"],
                    "name": p.get("name", ""),
                    "is_default": bool(p.get("is_default", False)),
                    "entitlements": dict(p.get("entitlements") or {}),
                    "limits": dict(p.get("limits") or {}),
                }
        except Exception as exc:  # noqa: BLE001
            logger.error("load_plans failed: %r", exc)
            out = {}
        _plans_cache = out
        return out


def default_plan_id() -> Optional[str]:
    for pid, p in load_plans().items():
        if p.get("is_default"):
            return pid
    plans = load_plans()
    return next(iter(plans), None)


def reload_seed() -> None:
    """Drop the catalog/plan caches so a hot edit of the seed JSON (or an /admin write) is picked up."""
    global _registry_cache, _plans_cache
    with _lock:
        _registry_cache = None
        _plans_cache = None
        _resolve_cache.clear()


# ════════════════════════════════════════════════════════════════════════
# TENANT-SCOPED reads (PG via db.engine.session; empty/default when PG absent)
# ════════════════════════════════════════════════════════════════════════
def load_status(tenant_id: str) -> dict:
    """tenant_status row for the tenant (admin GUC read). Defaults to active/default-plan/v1 if absent —
    this is what makes a brand-new tenant (or a PG-down box) resting byte-identical."""
    default = {"status": "active", "plan_id": default_plan_id(), "ent_version": 1}
    if not available() or not tenant_id:
        return default
    eng = _engine()
    try:
        from sqlalchemy import text
        ensure_schema()
        with eng.session(tenant_id="", is_admin=True) as s:  # type: ignore  # admin GUC: read any tenant
            row = s.execute(text(
                "SELECT status, plan_id, ent_version FROM tenant_status WHERE tenant_id = :t"
            ), {"t": tenant_id}).fetchone()
        if not row:
            return default
        return {
            "status": row[0] or "active",
            "plan_id": row[1] or default_plan_id(),
            "ent_version": int(row[2] or 1),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("load_status(%s) failed (degrade to active): %r", tenant_id, exc)
        return default


def load_overrides(tenant_id: str) -> dict[str, str]:
    """{ feature_key -> mode } per-vendor overrides for the tenant (admin GUC read). {} when absent."""
    if not available() or not tenant_id:
        return {}
    eng = _engine()
    try:
        from sqlalchemy import text
        ensure_schema()
        with eng.session(tenant_id="", is_admin=True) as s:  # type: ignore
            rows = s.execute(text(
                "SELECT feature_key, mode FROM tenant_entitlements WHERE tenant_id = :t"
            ), {"t": tenant_id}).fetchall()
        return {r[0]: r[1] for r in rows if r[1] in MODES}
    except Exception as exc:  # noqa: BLE001
        logger.warning("load_overrides(%s) failed (degrade to none): %r", tenant_id, exc)
        return {}


def load_plan_entitlements(plan_id: Optional[str]) -> dict[str, str]:
    """{ feature_key -> mode } for a plan. Seed JSON is canonical; PG plan_entitlements override later."""
    if not plan_id:
        return {}
    p = load_plans().get(plan_id)
    if not p:
        return {}
    return {k: m for k, m in p.get("entitlements", {}).items() if m in MODES}


def load_plan_limits(plan_id: Optional[str]) -> dict[str, int]:
    if not plan_id:
        return {}
    p = load_plans().get(plan_id)
    return dict(p.get("limits", {})) if p else {}


def load_tenant_limit_overrides(tenant_id: str) -> dict[str, int]:
    """Per-tenant cap overrides. Today these live in the JSON tenant store (caller POST /tenants/{id}/
    limits); the control layer surfaces them but does not own a new table for them. {} here = inherit
    the plan limits. A later unit wires the tenant-store read; resting state = plan limits only."""
    return {}


# ════════════════════════════════════════════════════════════════════════
# THE RESOLUTION ALGORITHM (datamodel §2 — deterministic, most-specific-wins, FAIL-CLOSED)
# ════════════════════════════════════════════════════════════════════════
def resolve_modes(tenant_id: str) -> dict[str, str]:
    """Effective mode of EVERY registry key for a tenant. Cached by (tenant_id, ent_version)."""
    registry = load_registry()
    if not registry:
        return {}

    status_row = load_status(tenant_id)
    version = int(status_row.get("ent_version", 1) or 1)

    ck = (tenant_id or "", version)
    cached = _resolve_cache.get(ck)
    if cached is not None:
        return cached

    status = status_row.get("status", "active")
    plan_id = status_row.get("plan_id") or default_plan_id()
    plan_ent = load_plan_entitlements(plan_id)
    overrides = load_overrides(tenant_id)

    eff: dict[str, str] = {}

    # ── PASS A: per-key, most-specific-wins ────────────────────────────────
    for key, meta in registry.items():
        is_core = meta["is_core"]

        # (1) STATUS GATE — suspended/disabled/expired = everything HIDDEN except is_core.
        if status in _STATUS_GATED:
            eff[key] = "on" if is_core else "hidden"
            continue

        # (2) per-vendor override ▸ (3) plan ▸ (4) global default
        m = overrides.get(key)
        if m is None:
            m = plan_ent.get(key)
        if m is None:
            m = meta["default_mode"]
        # (5) garbage/unknown value → FAIL-CLOSED
        if m not in MODES:
            m = "hidden"

        # CORE FLOOR — a core feature can never be hidden (anti-lockout); demote hidden→on.
        # (LOCK on a core feature is still allowed: billing visible-but-locked is acceptable.)
        if is_core and m == "hidden":
            m = "on"

        eff[key] = m

    # ── PASS B: PARENT ROLLDOWN (strictest ancestor wins; hidden > locked > on) ──
    for key, meta in registry.items():
        strictest = eff[key]
        anc = meta["parent_key"]
        # guard against pathological cycles in the seed
        seen = 0
        while anc is not None and anc in registry and seen < 64:
            if _STRICT[eff[anc]] > _STRICT[strictest]:
                strictest = eff[anc]
            anc = registry[anc]["parent_key"]
            seen += 1
        # is_core never rolled-down to hidden (kept reachable, matching the status gate).
        if meta["is_core"] and strictest == "hidden":
            strictest = eff[key] if eff[key] != "hidden" else "on"
        eff[key] = strictest

    _resolve_cache[ck] = eff
    return eff


def mode_for(tenant_id: str, feature_key: str) -> str:
    """Effective mode of one feature. A key NOT in the registry is UNGOVERNED → FAIL-CLOSED to hidden."""
    return resolve_modes(tenant_id).get(feature_key, "hidden")


def assert_access(tenant_id: str, feature_key: str) -> None:
    """The enforcement primitive the C3 choke-point calls. hidden→404, locked→402, on→pass.
    Raises fastapi.HTTPException when available; else a plain ValueError carrying the code (smoke-safe)."""
    m = mode_for(tenant_id, feature_key)
    if m == "on":
        return
    if m == "locked":
        _raise(LOCKED_CODE, {"error": "locked", "feature": feature_key, "upgrade": True})
    # hidden OR anything unexpected → fail-closed 404 (no existence leak)
    _raise(HIDDEN_CODE, {"error": "not_found"})


def _raise(code: int, detail: Any) -> None:
    try:
        from fastapi import HTTPException  # type: ignore
        raise HTTPException(status_code=code, detail=detail)
    except ImportError:
        err = ValueError(f"entitlement_block:{code}:{detail}")
        err.status_code = code  # type: ignore[attr-defined]
        err.detail = detail     # type: ignore[attr-defined]
        raise err


def effective_limits(tenant_id: str) -> dict:
    """plan_limits for the tenant's plan, with any per-tenant cap override layered on top.
    Used by the run-loop / wallet gate (a later unit consumes this)."""
    status_row = load_status(tenant_id)
    plan_id = status_row.get("plan_id") or default_plan_id()
    base = load_plan_limits(plan_id)
    return {**base, **load_tenant_limit_overrides(tenant_id)}


# ── path → feature_key resolution (longest-prefix-wins) — used by the C3 choke-point ──
_SHARED_PATH_MAP = {
    # intentionally-shared routes that naive prefix matching would mis-assign (explore §D.6).
    "/leads/hot": "command.dashboard",          # hot-leads widget on the dashboard, not the Leads page
    "/stats": "command.dashboard",
    "/status": "command.dashboard",
}


def feature_key_for_path(path: str) -> Optional[str]:
    """Map an API path to its governing feature_key via api_prefixes (LONGEST-prefix-wins), with an
    explicit map for the few deliberately-shared routes. Returns None for an ungoverned (legacy) path
    → the choke-point passes it through (a CI registry-drift guard closes that gap later)."""
    if not path:
        return None
    p = path.split("?", 1)[0].rstrip("/") or "/"
    # exact shared-route map first
    if p in _SHARED_PATH_MAP:
        return _SHARED_PATH_MAP[p]
    best_key = None
    best_len = -1
    for key, meta in load_registry().items():
        for pref in meta["api_prefixes"]:
            pr = pref.rstrip("/")
            if not pr:
                continue
            if p == pr or p.startswith(pr + "/"):
                if len(pr) > best_len:
                    best_len = len(pr)
                    best_key = key
    return best_key


# ── cache / version control (C4 hooks; CL-B1 ships the bump primitive) ──
def bump_version(tenant_id: str) -> int:
    """Increment a tenant's ent_version (any control write calls this) → invalidates the resolve cache
    → next /me/entitlements + next API request see the new modes. Returns the new version.
    Degrades to a pure in-proc cache clear when PG is absent."""
    invalidate(tenant_id)
    if not available() or not tenant_id:
        return 1
    eng = _engine()
    try:
        from sqlalchemy import text
        ensure_schema()
        with eng.session(tenant_id="", is_admin=True) as s:  # type: ignore
            row = s.execute(text(
                "INSERT INTO tenant_status (tenant_id, ent_version) VALUES (:t, 2) "
                "ON CONFLICT (tenant_id) DO UPDATE SET ent_version = tenant_status.ent_version + 1, "
                "updated_at = now() RETURNING ent_version"
            ), {"t": tenant_id}).fetchone()
        return int(row[0]) if row else 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("bump_version(%s) failed: %r", tenant_id, exc)
        return 1


def invalidate(tenant_id: Optional[str] = None) -> None:
    """Drop the resolved-mode cache for one tenant (all versions) or everything."""
    with _lock:
        if tenant_id is None:
            _resolve_cache.clear()
            return
        for k in [k for k in _resolve_cache if k[0] == tenant_id]:
            _resolve_cache.pop(k, None)


def entitlements_payload(tenant_id: str) -> dict:
    """The /me/entitlements response body (vendor-facing, core read). {modes, status, plan, version}."""
    st = load_status(tenant_id)
    return {
        "modes": resolve_modes(tenant_id),
        "status": st.get("status", "active"),
        "plan": st.get("plan_id"),
        "version": int(st.get("ent_version", 1) or 1),
    }


# ════════════════════════════════════════════════════════════════════════
# CONTROL WRITES (CL-B3 / plan C2) — admin-only mutations of the tenant-scoped control rows.
# Each write: applies the PG change under the admin GUC (engine.session(is_admin=True)), then
# bump_version() (invalidates the resolve cache -> /me/entitlements + the API choke-point see the new
# mode immediately), and mirrors a fast read-copy into entitlement_audit. The IMMUTABLE source of truth
# is the PG `events` leg via audit.record(channel='control') — caller.py writes that; this mirror is a
# convenience projection for the Audit page (spec §1.5). All writes return {ok, before, after} so the
# caller can audit old->new. NEVER raises (degrades to ok:False when PG is down) so a control write can
# never 500 the admin plane.
# ════════════════════════════════════════════════════════════════════════
def _exec_admin(sql: str, params: dict | None = None, fetch: bool = False):
    """Run one statement under the admin GUC (is_admin -> RLS sees/writes any tenant). Returns rows when
    fetch=True, else the rowcount. Raises on failure (callers wrap)."""
    eng = _engine()
    from sqlalchemy import text
    ensure_schema()
    with eng.session(tenant_id="", is_admin=True) as s:  # type: ignore
        res = s.execute(text(sql), params or {})
        if fetch:
            return res.fetchall()
        return res.rowcount


def _mirror_audit(actor_user: str, actor_tenant: str, action: str, *, target_tenant: str | None = None,
                  feature_key: str | None = None, old_value: str | None = None,
                  new_value: str | None = None, reason: str = "", ip: str = "") -> None:
    """Append a row to the entitlement_audit read-mirror. Best-effort; the events leg is the truth."""
    try:
        _exec_admin(
            "INSERT INTO entitlement_audit (actor_user, actor_tenant, action, target_tenant, "
            "feature_key, old_value, new_value, reason, ip) VALUES (:au,:at,:ac,:tt,:fk,:ov,:nv,:rs,:ip)",
            {"au": actor_user or "", "at": actor_tenant or "", "ac": action, "tt": target_tenant,
             "fk": feature_key, "ov": old_value, "nv": new_value, "rs": reason or "", "ip": ip or ""},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("entitlement_audit mirror failed (events leg is truth): %r", exc)


def set_override(tenant_id: str, feature_key: str, mode: str, set_by: str = "", reason: str = "") -> dict:
    """Per-vendor override (HIDE/LOCK/ON). Upserts tenant_entitlements + bumps the version. The mode is
    validated against MODES (fail-closed: an invalid mode is rejected, not silently stored)."""
    if mode not in MODES:
        return {"ok": False, "reason": f"mode must be one of {MODES}"}
    if feature_key not in load_registry():
        return {"ok": False, "reason": "unknown feature_key"}
    before = load_overrides(tenant_id).get(feature_key)
    if not available():
        return {"ok": False, "reason": "control store unavailable"}
    try:
        _exec_admin(
            "INSERT INTO tenant_entitlements (tenant_id, feature_key, mode, set_by, reason) "
            "VALUES (:t,:k,:m,:b,:r) ON CONFLICT (tenant_id, feature_key) DO UPDATE SET "
            "mode = EXCLUDED.mode, set_by = EXCLUDED.set_by, set_at = now(), reason = EXCLUDED.reason",
            {"t": tenant_id, "k": feature_key, "m": mode, "b": set_by, "r": reason},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("set_override failed: %r", exc)
        return {"ok": False, "reason": "write failed"}
    ver = bump_version(tenant_id)
    return {"ok": True, "before": before, "after": mode, "version": ver}


def clear_override(tenant_id: str, feature_key: str, set_by: str = "") -> dict:
    """Delete a per-vendor override (revert to plan/global) + bump the version."""
    before = load_overrides(tenant_id).get(feature_key)
    if not available():
        return {"ok": False, "reason": "control store unavailable"}
    try:
        _exec_admin("DELETE FROM tenant_entitlements WHERE tenant_id = :t AND feature_key = :k",
                    {"t": tenant_id, "k": feature_key})
    except Exception as exc:  # noqa: BLE001
        logger.error("clear_override failed: %r", exc)
        return {"ok": False, "reason": "write failed"}
    ver = bump_version(tenant_id)
    return {"ok": True, "before": before, "after": None, "version": ver}


def set_status(tenant_id: str, status: str, *, reason: str = "", updated_by: str = "",
               trial_ends_at: str | None = None) -> dict:
    """Set the vendor lifecycle status (active/trial/suspended/disabled/expired). Upserts tenant_status
    (preserving plan_id) + bumps the version. Suspended/disabled flips the status FLOOR in resolve_modes
    so every non-core feature hides for that tenant. DATA IS NEVER DELETED — this is a flag flip only."""
    valid = ("active", "trial", "suspended", "disabled", "expired")
    if status not in valid:
        return {"ok": False, "reason": f"status must be one of {valid}"}
    before = load_status(tenant_id).get("status", "active")
    if not available():
        return {"ok": False, "reason": "control store unavailable"}
    try:
        _exec_admin(
            "INSERT INTO tenant_status (tenant_id, status, plan_id, suspended_reason, trial_ends_at, "
            "updated_by, updated_at) VALUES (:t,:s,:p,:r,:te,:u, now()) "
            "ON CONFLICT (tenant_id) DO UPDATE SET status = EXCLUDED.status, "
            "suspended_reason = EXCLUDED.suspended_reason, trial_ends_at = EXCLUDED.trial_ends_at, "
            "updated_by = EXCLUDED.updated_by, updated_at = now()",
            {"t": tenant_id, "s": status, "p": (load_status(tenant_id).get("plan_id") or default_plan_id()),
             "r": (reason or "") if status in _STATUS_GATED else "",
             "te": trial_ends_at, "u": updated_by},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("set_status failed: %r", exc)
        return {"ok": False, "reason": "write failed"}
    ver = bump_version(tenant_id)
    return {"ok": True, "before": before, "after": status, "version": ver}


def set_plan(tenant_id: str, plan_id: str, *, updated_by: str = "") -> dict:
    """Assign a plan to a vendor. Upserts tenant_status.plan_id (preserving status) + bumps the version."""
    if plan_id not in load_plans():
        return {"ok": False, "reason": "unknown plan_id"}
    before = load_status(tenant_id).get("plan_id")
    if not available():
        return {"ok": False, "reason": "control store unavailable"}
    try:
        _exec_admin(
            "INSERT INTO tenant_status (tenant_id, status, plan_id, updated_by, updated_at) "
            "VALUES (:t, :s, :p, :u, now()) ON CONFLICT (tenant_id) DO UPDATE SET "
            "plan_id = EXCLUDED.plan_id, updated_by = EXCLUDED.updated_by, updated_at = now()",
            {"t": tenant_id, "s": load_status(tenant_id).get("status", "active"),
             "p": plan_id, "u": updated_by},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("set_plan failed: %r", exc)
        return {"ok": False, "reason": "write failed"}
    ver = bump_version(tenant_id)
    return {"ok": True, "before": before, "after": plan_id, "version": ver}


def set_global_flag(feature_key: str, mode: str, *, set_by: str = "") -> dict:
    """Set the GLOBAL default_mode of a feature (the baseline for EVERY vendor). Writes feature_registry
    (PG, when present) + updates the in-proc catalog cache + bumps EVERY tenant's version (global change).
    The seed JSON stays canonical for the catalog SHAPE; this overrides the default_mode at runtime."""
    if mode not in MODES:
        return {"ok": False, "reason": f"mode must be one of {MODES}"}
    reg = load_registry()
    if feature_key not in reg:
        return {"ok": False, "reason": "unknown feature_key"}
    if reg[feature_key].get("is_core") and mode == "hidden":
        return {"ok": False, "reason": "cannot hide a core feature (anti-lockout)"}
    before = reg[feature_key].get("default_mode")
    # update the in-proc catalog so resolution reflects it immediately even pre-PG.
    with _lock:
        reg[feature_key]["default_mode"] = mode
    if available():
        try:
            _exec_admin("UPDATE feature_registry SET default_mode = :m WHERE key = :k",
                        {"m": mode, "k": feature_key})
        except Exception as exc:  # noqa: BLE001
            logger.warning("set_global_flag PG write failed (in-proc applied): %r", exc)
    # a global default change can affect every tenant -> drop ALL resolve caches.
    invalidate(None)
    return {"ok": True, "before": before, "after": mode}


def resolved_with_provenance(tenant_id: str) -> list[dict]:
    """The per-vendor permissions view: for EVERY registry key, the effective mode + WHERE it came from
    (override > plan > global). Powers the Vendor Workspace Permissions tab (provenance pill)."""
    registry = load_registry()
    st = load_status(tenant_id)
    plan_id = st.get("plan_id") or default_plan_id()
    plan_ent = load_plan_entitlements(plan_id)
    overrides = load_overrides(tenant_id)
    eff = resolve_modes(tenant_id)
    status_gated = st.get("status", "active") in _STATUS_GATED
    out: list[dict] = []
    for key, meta in registry.items():
        if key in overrides:
            prov = "override"
        elif key in plan_ent:
            prov = "plan"
        else:
            prov = "global"
        if status_gated and not meta.get("is_core"):
            prov = "status"
        out.append({
            "key": key, "kind": meta.get("kind"), "parent_key": meta.get("parent_key"),
            "label": meta.get("label", ""), "nav_href": meta.get("nav_href"),
            "is_core": bool(meta.get("is_core")), "sort_order": meta.get("sort_order", 0),
            "default_mode": meta.get("default_mode"),
            "override": overrides.get(key), "plan_mode": plan_ent.get(key),
            "effective": eff.get(key, "hidden"), "provenance": prov,
        })
    out.sort(key=lambda r: (r["sort_order"], r["key"]))
    return out


def vendor_detail(tenant_id: str) -> dict:
    """Full control profile for a vendor: status, plan, version, resolved entitlement map + provenance,
    effective limits. Usage/health/wallet are joined in caller.py (it owns those stores)."""
    st = load_status(tenant_id)
    return {
        "tenant_id": tenant_id,
        "status": st.get("status", "active"),
        "plan": st.get("plan_id") or default_plan_id(),
        "version": int(st.get("ent_version", 1) or 1),
        "entitlements": resolved_with_provenance(tenant_id),
        "limits": effective_limits(tenant_id),
    }


def registry_tree() -> list[dict]:
    """The full feature_registry catalog (for /admin/features). Sorted by sort_order then key."""
    rows = list(load_registry().values())
    rows.sort(key=lambda r: (r.get("sort_order", 0), r["key"]))
    return rows


def plans_detail() -> list[dict]:
    """All plans + their entitlements + limits (for /admin/plans)."""
    out = []
    for pid, p in load_plans().items():
        out.append({
            "plan_id": pid, "name": p.get("name", ""), "is_default": bool(p.get("is_default")),
            "entitlements": dict(p.get("entitlements") or {}), "limits": dict(p.get("limits") or {}),
        })
    out.sort(key=lambda r: (not r["is_default"], r["plan_id"]))
    return out


# ════════════════════════════════════════════════════════════════════════
# OpenFeature-STYLE FACADE — swap-safety insurance (OSS-research verdict).
# Standardizes the call-site so the backing store can later be replaced (flagd/Flagsmith) WITHOUT
# editing any caller.py. The default provider IS this module's engine.
# ════════════════════════════════════════════════════════════════════════
class EntitlementProvider:
    """Provider contract. A future flagd/Flagsmith adapter implements the same two methods."""

    name = "local"

    def resolve(self, tenant_id: str, feature_key: str) -> str:
        return mode_for(tenant_id, feature_key)

    def resolve_all(self, tenant_id: str) -> dict[str, str]:
        return resolve_modes(tenant_id)


_PROVIDER: EntitlementProvider = EntitlementProvider()


def set_provider(provider: EntitlementProvider) -> None:
    global _PROVIDER
    _PROVIDER = provider


def get_provider() -> EntitlementProvider:
    return _PROVIDER


def evaluate(tenant_id: str, feature_key: str) -> str:
    """OpenFeature-style facade entrypoint: caller.py calls THIS, not mode_for directly, so the
    backing engine is swappable. Identical result to mode_for through the default provider."""
    try:
        return _PROVIDER.resolve(tenant_id, feature_key)
    except Exception as exc:  # noqa: BLE001 — FAIL-CLOSED on a provider error
        logger.error("provider.resolve failed (fail-closed hidden): %r", exc)
        return "hidden"
