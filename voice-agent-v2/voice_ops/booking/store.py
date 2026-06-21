"""voice_ops.booking.store — the TRACKED, droplet-free wrapper over the booking engine.

THE PATH RULE this satisfies: the real booking schema + atomic-claim core lives in
`droplet_work/booking/core.py`, which is GITIGNORED (kept as local scratch). The tracked
deliverable must NOT *rely on* gitignored code being importable as a package — so this module
NEVER does `from booking import core` or `import droplet_work.booking`. Instead it loads the
single file `droplet_work/booking/core.py` LAZILY at call time via importlib (the exact same
trick `voice_kernel/tests/conftest.load_legacy_prompt_module` uses for prompt.py), and degrades
to a benign "not_configured" when the file (or its Postgres spine) is absent.

Result:
  * `import voice_ops.booking` pulls ZERO droplet_work / sqlalchemy / livekit at module load.
  * On the live box (where droplet_work/booking/core.py + the P1 db spine exist) the wrapper
    drives the REAL atomic-claim engine — no double-book, immutable audit, RLS isolation — all
    inherited from core.py unchanged.
  * In CI / on a host without the gitignored code, every method returns
    {"status":"not_configured"} and NEVER raises — tests inject a fake engine instead.

The wrapper adds NOTHING to the DB semantics; it is a thin, tenant-scoped, fail-closed facade so
the service layer (and the AI tool) talk to ONE stable surface regardless of where the engine is.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("voice_ops.booking.store")

_NOT_CONFIGURED = {"status": "not_configured", "reason": "booking_engine_unavailable"}

# Resolve the repo root from this file: voice_ops/booking/store.py -> parents[2] == repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORE_PATH = _REPO_ROOT / "droplet_work" / "booking" / "core.py"

# One cached module handle, guarded so concurrent calls don't double-load.
_lock = threading.Lock()
_core_mod: Any = None
_core_tried = False


def _load_core() -> Any:
    """Lazily load droplet_work/booking/core.py as an isolated module. Returns the module or
    None (file absent, or it failed to import its own deps). NEVER raises.

    core.py imports `from . import config, identity, models` — relative imports that require a
    real `booking` package on sys.path. We register a lightweight package alias so those relative
    imports resolve to the sibling files, WITHOUT importing droplet_work as a package (which is
    gitignored and not a package) and WITHOUT touching agent.py.
    """
    global _core_mod, _core_tried
    if _core_mod is not None:
        return _core_mod
    with _lock:
        if _core_mod is not None:
            return _core_mod
        if _core_tried:
            return None
        _core_tried = True
        if not _CORE_PATH.exists():
            log.info("booking core absent at %s — store dormant (not_configured)", _CORE_PATH)
            return None
        try:
            pkg_dir = _CORE_PATH.parent
            pkg_name = "_vops_booking_engine"
            # Register a synthetic package whose __path__ is the gitignored booking dir, so the
            # relative imports inside core.py (`from . import config, identity, models`) resolve.
            if pkg_name not in sys.modules:
                import types
                pkg = types.ModuleType(pkg_name)
                pkg.__path__ = [str(pkg_dir)]  # type: ignore[attr-defined]
                sys.modules[pkg_name] = pkg
            mod_name = f"{pkg_name}.core"
            if mod_name in sys.modules:
                _core_mod = sys.modules[mod_name]
                return _core_mod
            spec = importlib.util.spec_from_file_location(mod_name, str(_CORE_PATH))
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            _core_mod = mod
            return _core_mod
        except Exception as exc:  # noqa: BLE001
            log.info("booking core load failed (store dormant): %r", exc)
            _core_mod = None
            return None


def reset_engine_cache() -> None:
    """Test hook: drop the cached engine handle so a fresh fake/real can be injected."""
    global _core_mod, _core_tried
    with _lock:
        _core_mod = None
        _core_tried = False


# An injectable engine for tests (so we never need the gitignored file or Postgres in CI).
_injected_engine: Any = None


def set_engine_for_tests(engine: Any) -> None:
    """Inject a fake engine object exposing the core.py surface (book/reschedule/cancel/
    mark_completed/get_booking/list_bookings/list_events). Pass None to clear."""
    global _injected_engine
    _injected_engine = engine


def _engine() -> Any:
    """The active booking engine: the injected fake (tests) else the lazily-loaded real core."""
    if _injected_engine is not None:
        return _injected_engine
    return _load_core()


def available() -> bool:
    """True only when a booking engine (real core or injected fake) is resolvable."""
    return _engine() is not None


# --------------------------------------------------------------------------- #
# Thin tenant-scoped facade. Each method fail-closes on empty org_id (never a
# cross-tenant / rootless call) and degrades to not_configured when dormant.
# --------------------------------------------------------------------------- #
def _require_org(org_id: str) -> Optional[dict]:
    if not (org_id or "").strip():
        return {"status": "error", "reason": "empty_org_id"}
    return None


def book(org_id: str, resource_id: str, phone: str, *, slot_start: Any, slot_end: Any = None,
         name: str = "", title: str = "", notes: str = "", source: str = "",
         campaign_id: str = "", is_admin: bool = False) -> dict:
    bad = _require_org(org_id)
    if bad:
        return bad
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        return eng.book(org_id, resource_id, phone, slot_start=slot_start, slot_end=slot_end,
                        name=name, title=title, notes=notes, source=source,
                        campaign_id=campaign_id, is_admin=is_admin)
    except Exception as exc:  # noqa: BLE001
        log.info("store.book failed: %r", exc)
        return {"ok": False, "status": "error", "reason": "engine_error", "detail": repr(exc)[:160]}


def reschedule(org_id: str, booking_id: str, *, new_slot_start: Any, new_slot_end: Any = None,
               is_admin: bool = False) -> dict:
    bad = _require_org(org_id)
    if bad:
        return bad
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        return eng.reschedule(org_id, booking_id, new_slot_start=new_slot_start,
                              new_slot_end=new_slot_end, is_admin=is_admin)
    except Exception as exc:  # noqa: BLE001
        log.info("store.reschedule failed: %r", exc)
        return {"ok": False, "status": "error", "reason": "engine_error", "detail": repr(exc)[:160]}


def cancel(org_id: str, booking_id: str, *, reason: str = "", is_admin: bool = False) -> dict:
    bad = _require_org(org_id)
    if bad:
        return bad
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        return eng.cancel(org_id, booking_id, reason=reason, is_admin=is_admin)
    except Exception as exc:  # noqa: BLE001
        log.info("store.cancel failed: %r", exc)
        return {"ok": False, "status": "error", "reason": "engine_error", "detail": repr(exc)[:160]}


def mark_completed(org_id: str, booking_id: str, *, is_admin: bool = False) -> dict:
    bad = _require_org(org_id)
    if bad:
        return bad
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        return eng.mark_completed(org_id, booking_id, is_admin=is_admin)
    except Exception as exc:  # noqa: BLE001
        log.info("store.mark_completed failed: %r", exc)
        return {"ok": False, "status": "error", "reason": "engine_error", "detail": repr(exc)[:160]}


def get_booking(org_id: str, booking_id: str, *, is_admin: bool = False) -> dict:
    bad = _require_org(org_id)
    if bad:
        return bad
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        return eng.get_booking(org_id, booking_id, is_admin=is_admin)
    except Exception as exc:  # noqa: BLE001
        log.info("store.get_booking failed: %r", exc)
        return {"status": "error", "reason": "engine_error", "detail": repr(exc)[:160]}


def list_bookings(org_id: str, *, contact_id: str = "", status: str = "", limit: int = 100,
                  is_admin: bool = False) -> dict:
    bad = _require_org(org_id)
    if bad:
        return bad
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        return eng.list_bookings(org_id, contact_id=contact_id, status=status, limit=limit,
                                 is_admin=is_admin)
    except Exception as exc:  # noqa: BLE001
        log.info("store.list_bookings failed: %r", exc)
        return {"status": "error", "reason": "engine_error", "detail": repr(exc)[:160]}


def list_events(org_id: str, booking_id: str, *, limit: int = 200, is_admin: bool = False) -> dict:
    bad = _require_org(org_id)
    if bad:
        return bad
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        return eng.list_events(org_id, booking_id, limit=limit, is_admin=is_admin)
    except Exception as exc:  # noqa: BLE001
        log.info("store.list_events failed: %r", exc)
        return {"status": "error", "reason": "engine_error", "detail": repr(exc)[:160]}
