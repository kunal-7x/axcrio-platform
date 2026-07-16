"""Offline W1 smoke for ads_engine — no app boot, no .env. Run:
    python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_w1 as s; s.main()"
Asserts: import-clean, 6 routes registered, store tenant isolation, dormant-OFF mount yields None.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def _no_caller_import() -> tuple[str, bool]:
    """Assert NO `import caller` / `from caller` in any package source (DI rule)."""
    pkg = Path(__file__).parent
    bad = []
    for p in pkg.glob("*.py"):
        src = p.read_text(encoding="utf-8")
        for ln in src.splitlines():
            s = ln.strip()
            if s.startswith("import caller") or s.startswith("from caller "):
                bad.append(f"{p.name}: {s}")
    return ("no `from caller import` in package", not bad)


def _import_clean() -> tuple[str, bool]:
    try:
        import ads_engine  # noqa: F401
        import ads_engine.config  # noqa: F401
        import ads_engine.store  # noqa: F401
        import ads_engine.vault_adapter  # noqa: F401
        import ads_engine.analytics  # noqa: F401
        import ads_engine.endpoints  # noqa: F401
        return ("package imports clean", True)
    except Exception as e:  # noqa: BLE001
        return (f"package imports clean (FAILED: {e!r})", False)


def _routes_registered() -> tuple[str, bool]:
    import ads_engine.endpoints as ep

    def _rt(*a, **k):
        return True

    def _can(t, action):
        return True

    def _need_auth():
        return ("RESP", 401)

    def _forbidden(msg="x"):
        return ("RESP", 403)

    # FEATURE_ADS need not be on to BUILD the router (only routes self-404 at request time).
    router = ep.build_router(_rt, _can, _need_auth, _forbidden)
    if router is None:
        return ("router builds (FastAPI present)", False)
    want = {
        ("GET", "/ads/health"),
        ("GET", "/ads/campaigns"),
        ("POST", "/ads/campaigns/propose"),
        ("POST", "/ads/campaigns/{plan_id}/approve"),
        ("POST", "/ads/campaigns/{plan_id}/pause"),
        ("POST", "/ads/optimize"),
    }
    got = set()
    for r in router.routes:
        path = getattr(r, "path", "")
        for m in (getattr(r, "methods", None) or set()):
            if m in ("GET", "POST"):
                got.add((m, path))
    missing = want - got
    ok = not missing
    return (f"6 routes registered (missing={sorted(missing)})", ok)


def _tenant_isolation() -> tuple[str, bool]:
    """Tenant A cannot read tenant B's ad_plans via store.py."""
    import ads_engine as pkg
    import ads_engine.store as store

    tmp = Path(tempfile.mkdtemp(prefix="ads_w1_"))

    # Minimal in-memory JSON IO seams (mirror caller _read/_atomic_write_json contract).
    def _read(path: Path, default):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default

    def _atomic_write_json(path: Path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    pkg.wire(_read=_read, _write=lambda p, d: _atomic_write_json(p, d),
             _atomic_write_json=_atomic_write_json, var_dir=tmp)

    # Tenant B writes a campaign.
    store.put_row("t_B", "campaigns", "cmp_B1", {"plan_id": "cmp_B1", "name": "B-secret"})
    # Tenant A writes its own.
    store.put_row("t_A", "campaigns", "cmp_A1", {"plan_id": "cmp_A1", "name": "A-own"})

    a_rows = store.get_collection("t_A", "campaigns")
    a_sees_b = "cmp_B1" in a_rows or any(r.get("name") == "B-secret" for r in a_rows.values())
    a_row_b = store.get_row("t_A", "campaigns", "cmp_B1")  # must be None (cross-tenant)
    a_list = store.list_campaigns("t_A")
    leak = a_sees_b or (a_row_b is not None) or any(c.get("name") == "B-secret" for c in a_list)

    # Tenant-stamp is server-set even if body lies.
    store.put_row("t_A", "campaigns", "cmp_A2", {"plan_id": "cmp_A2", "tenant_id": "t_B"})
    stamped = store.get_row("t_A", "campaigns", "cmp_A2")
    stamp_ok = stamped is not None and stamped.get("tenant_id") == "t_A"

    ok = (not leak) and stamp_ok
    return (f"tenant A cannot read tenant B ad_plans (leak={leak}, stamp_ok={stamp_ok})", ok)


def _seams_is_factory() -> tuple[str, bool]:
    """REGRESSION GUARD (the dark-engine footgun): `ads_engine.seams` MUST stay the callable
    factory function defined in __init__.py. If anyone adds a `seams.py` submodule, the import
    `from . import seams` in endpoints/store/tick/vault_adapter/leads resolves to the MODULE,
    shadows the function, and `_seams_fn()`/`seams()` calls break -> the whole router goes dark.
    This asserts the function is intact AND no seams.py file exists alongside the package."""
    try:
        import ads_engine as pkg
        from pathlib import Path as _P
        ok_callable = callable(getattr(pkg, "seams", None))
        no_submodule = not (_P(pkg.__file__).parent / "seams.py").exists()
        ok = ok_callable and no_submodule
        return (f"seams stays a factory fn (callable={ok_callable}, no seams.py={no_submodule})", ok)
    except Exception as e:  # noqa: BLE001
        return (f"seams stays a factory fn (FAILED: {e!r})", False)


def _router_mounts_no_dupes() -> tuple[str, bool]:
    """Router builds AND mounts into a real FastAPI app with no duplicate (method, path) pairs —
    proving the engine is not dark and the include won't crash the caller mount."""
    try:
        import ads_engine.endpoints as ep
        from fastapi import FastAPI

        def _rt(*a, **k):
            return {"tenant_id": "t1", "is_admin": True}

        router = ep.build_router(_rt, lambda t, a: True,
                                 lambda: ("R", 401), lambda m="x": ("R", 403))
        if router is None:
            return ("router mounts (FastAPI present)", False)
        pairs = []
        for r in router.routes:
            for m in (getattr(r, "methods", None) or set()):
                pairs.append((m, getattr(r, "path", "")))
        dupes = sorted({p for p in pairs if pairs.count(p) > 1})
        FastAPI().include_router(router)  # crashes on a real mount conflict
        return (f"router mounts clean ({len(pairs)} routes, dupes={dupes})", not dupes)
    except Exception as e:  # noqa: BLE001
        return (f"router mounts clean (FAILED: {e!r})", False)


def _dormant_off() -> tuple[str, bool]:
    """FEATURE_ADS OFF -> config.is_enabled() False; the build_router mount path in caller is
    guarded by FEATURE_ADS so the router is never mounted. We assert the config gate is False."""
    os.environ.pop("FEATURE_ADS", None)
    import importlib
    import ads_engine.config as cfg
    importlib.reload(cfg)
    cfg.set_cfg_get(None)
    return ("FEATURE_ADS default OFF => is_enabled() False (dormant)", cfg.is_enabled() is False)


def main() -> int:
    checks = [
        _import_clean(),
        _no_caller_import(),
        _seams_is_factory(),
        _routes_registered(),
        _router_mounts_no_dupes(),
        _tenant_isolation(),
        _dormant_off(),
    ]
    all_ok = True
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        all_ok = all_ok and ok
    print("RESULT:", "ALL PASS" if all_ok else "FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
