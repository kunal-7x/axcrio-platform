"""ElevateX ads_engine — the thin ad-platform connector router (FEATURE_ADS, default OFF).

W1 SKELETON. This package is a *mounted router + service modules* that lights up the
EXISTING /ads UI (`famit-panel/app/ads/page.tsx` + `_lib.ts`). It REBUILDS NOTHING in
the live earner: the voice pipeline (agent.py + the dial loop + the LiveKit triple +
the scheduler loop) is BYTE-UNTOUCHED. The lead->call path is enqueue-only via an
injected closure (not wired in W1).

HARD RULES (binding — every module obeys):
  * Import must be CHEAP + CRASH-PROOF: a broken/half-built package can NEVER trip the
    caller.py mount import-guard and crash startup. So `__init__` imports NOTHING heavy
    at module load; the only heavy work happens inside `wire(...)` / `build_router(...)`,
    both called lazily by caller.py at mount time and both swallowed by the mount guard.
  * NO `from caller import ...` ANYWHERE in this package. caller.py is the live earner
    and importing it would create a cycle + drag the whole app in. EVERY seam ads_engine
    needs (store IO, tenant resolution, RBAC, audit, jobs, registry) is INJECTED via
    `wire(...)` — dependency injection, the same spirit as provider_registry.build_router.
    A module-level smoke asserts no `import caller` slips in.

The package is a singleton wired ONCE at mount time. `wire(...)` stashes the injected
seams on the module-level `_SEAMS` object; `store`, `analytics`, `endpoints`, etc. read
their dependencies from there (never from a global import).
"""

from __future__ import annotations

__version__ = "0.1.0-w1"

# ---------------------------------------------------------------------------
# Injected-seams container. Populated by wire(...). Everything the package needs
# from the host app (caller.py) lives here — NOTHING is imported from caller.
# ---------------------------------------------------------------------------


class _Seams:
    """Holds every dependency caller.py injects. Plain attribute bag (cheap, no deps).

    Attributes (all optional until wire() runs; modules degrade-to-dormant if a
    required seam is absent):
      read              callable(path, default) -> data         (caller._read)
      write             callable(path, data) -> None            (caller._write)
      atomic_write_json callable(path, data) -> None            (caller._atomic_write_json)
      awrite            async callable(path, data) -> None       (caller._awrite)  [optional]
      var_dir           pathlib.Path                            (caller.VAR root)
      resolve_tenant    callable(request) -> tenant|None        (token-derived identity)
      can               callable(tenant, action) -> bool        (RBAC)
      need_auth         callable() -> Response(401)
      forbidden         callable(msg) -> Response(403)
      require_object    callable(tenant, obj, not_found=) -> Response|None  (BOLA guard)
      audit             callable(request, tenant, action, obj_type, obj_id, meta=) (best-effort)
      require_super_admin callable(request) -> tenant|Response  (excludes legacy-pw)
      auth_method       callable(request) -> 'jwt'|'legacy_pw'|'hmac'|'none'  (M2 gate)
      firewall          module (consume_reveal_step_up / mint_reveal_step_up)  [step-up]
      jobs              dict  (the live JOBS map — enqueue-only mirror; NOT mutated in W1)
      run_job           async callable(job_id)  (the earner dial entry; enqueue-only)
      tenant_by_id      callable(tenant_id) -> tenant|None
      active_calls      dict  (live ACTIVE_CALLS map; read-only)
      registry          module  (provider_registry — get_provider seam for creds)
      get_provider      callable(tenant_id, capability, get_key=) -> ProviderClient|None
    """

    __slots__ = (
        "read", "write", "atomic_write_json", "awrite", "var_dir",
        "resolve_tenant", "can", "need_auth", "forbidden", "require_object",
        "audit", "require_super_admin", "auth_method", "firewall",
        "jobs", "run_job", "tenant_by_id", "active_calls",
        "registry", "get_provider", "wired",
    )

    def __init__(self) -> None:
        for name in self.__slots__:
            setattr(self, name, None)
        self.wired = False


# Module-level singleton seams container. Read by every other module.
_SEAMS = _Seams()


def wire(
    *,
    _read=None,
    _write=None,
    _atomic_write_json=None,
    _awrite=None,
    var_dir=None,
    resolve_tenant=None,
    can=None,
    need_auth=None,
    _forbidden=None,
    require_object=None,
    audit=None,
    require_super_admin=None,
    auth_method=None,
    firewall=None,
    JOBS=None,
    run_job=None,
    _tenant_by_id=None,
    ACTIVE_CALLS=None,
    registry=None,
    get_provider=None,
):
    """DI entrypoint. caller.py calls this ONCE at mount time, passing every seam.

    Idempotent + crash-proof: a missing seam just leaves the attribute None (the
    consuming module degrades to dormant / fail-closed). Returns the seams object so
    the mount can assert it wired. NEVER raises — a wiring error must not crash startup.
    """
    try:
        _SEAMS.read = _read
        _SEAMS.write = _write
        _SEAMS.atomic_write_json = _atomic_write_json
        _SEAMS.awrite = _awrite
        _SEAMS.var_dir = var_dir
        _SEAMS.resolve_tenant = resolve_tenant
        _SEAMS.can = can
        _SEAMS.need_auth = need_auth
        _SEAMS.forbidden = _forbidden
        _SEAMS.require_object = require_object
        _SEAMS.audit = audit
        _SEAMS.require_super_admin = require_super_admin
        _SEAMS.auth_method = auth_method
        _SEAMS.firewall = firewall
        _SEAMS.jobs = JOBS
        _SEAMS.run_job = run_job
        _SEAMS.tenant_by_id = _tenant_by_id
        _SEAMS.active_calls = ACTIVE_CALLS
        _SEAMS.registry = registry
        _SEAMS.get_provider = get_provider
        _SEAMS.wired = True
    except Exception:  # noqa: BLE001 — wiring must never crash the live spine
        _SEAMS.wired = False
    return _SEAMS


def seams() -> "_Seams":
    """Accessor for the wired seams (used by store/analytics/endpoints)."""
    return _SEAMS
