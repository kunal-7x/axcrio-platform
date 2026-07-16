"""ai_manager.db.engine — the AI-Manager persistence spine (lazy, dormant-safe).

Spec: plans/aim-build/contracts/schema-and-config-contract.md §3 + BUILD_SPEC §J.

Mirror of the live P1 `db.engine` that `grow/store.py` already rides
(`eng.session(tenant_id=..., is_admin=...)`, `eng.available()`, GUCs
`app.tenant_id`/`app.is_admin`). Resolution order (never raises):
  1. an engine injected via set_engine() (tests / reuse the shared P1 engine),
  2. the shared live `db.engine` when importable AND available() (delegate — matches grow),
  3. a PRIVATE sqlalchemy engine bound to config.pg_dsn() when AIM_PG_DSN is set,
  4. None — fully dormant (store falls back to InMemory).

HARD INVARIANTS (GLOBAL INVARIANTS §1, §5):
  * ZERO sqlalchemy at import — every sqlalchemy symbol is imported LAZILY inside a
    function, so this module loads on a box where sqlalchemy is absent.
  * Import does ZERO I/O: no engine built, no DSN read, no connection at module load.
  * ensure_schema() is a LAZY NO-OP unless a DSN is configured (AIM_PG_DSN set) OR the
    shared db.engine is available — so on a key-less box it touches NOTHING (returns
    False) and the live Postgres is never altered.
  * session(tenant_id, is_admin) sets `SET LOCAL app.tenant_id` / `app.is_admin` for the
    txn only (never leaks across pooled connections); blank tenant + is_admin=False is
    fail-closed (the empty GUC yields zero rows under RLS, never silently global).
"""
from __future__ import annotations

import contextlib
import logging
import threading
from typing import Iterator, Optional

log = logging.getLogger("ai_manager.db.engine")

_LOCK = threading.RLock()
_ENGINE = None            # cached PRIVATE sqlalchemy Engine (path 3) | None
_ENGINE_TRIED = False     # latch: don't rebuild a failed private engine every call
_INJECTED = None          # set_engine() override (tests / shared-engine reuse)
_SCHEMA_READY = False      # ensure_schema() idempotency latch


# --------------------------------------------------------------------------- #
# engine resolution
# --------------------------------------------------------------------------- #
def set_engine(engine) -> None:
    """Inject a SQLAlchemy engine (tests, or reuse the shared P1 engine).

    Passing None clears the injection (back to auto-resolution). Never raises."""
    global _INJECTED
    with _LOCK:
        _INJECTED = engine


def _shared_engine_module():
    """The shared live `db.engine` module IFF importable AND available(); else None.

    This is the same delegation grow/store.py uses (`from db import engine`). On the
    local box there is no top-level `db` package, so this returns None (dormant)."""
    try:
        from db import engine as _shared  # type: ignore
    except Exception:  # noqa: BLE001 — absent shared engine -> private/None path
        return None
    try:
        return _shared if _shared.available() else None
    except Exception:  # noqa: BLE001
        return None


def _private_engine():
    """Build (once) a PRIVATE sqlalchemy engine bound to config.pg_dsn(); None when unset.

    sqlalchemy is imported LAZILY here so the module loads without it. The build is
    latched so a failed/absent DSN never re-thrashes create_engine on every call."""
    global _ENGINE, _ENGINE_TRIED
    with _LOCK:
        if _ENGINE is not None:
            return _ENGINE
        if _ENGINE_TRIED:
            return _ENGINE
        _ENGINE_TRIED = True
        try:
            from .. import config  # type: ignore
            dsn = (config.pg_dsn() or "").strip()
        except Exception:  # noqa: BLE001
            dsn = ""
        if not dsn:
            return None
        try:
            from sqlalchemy import create_engine
            _ENGINE = create_engine(dsn, pool_pre_ping=True, future=True)
        except Exception as exc:  # noqa: BLE001 — sqlalchemy absent / bad DSN -> dormant
            log.info("ai_manager.db.engine private engine unavailable: %r", exc)
            _ENGINE = None
        return _ENGINE


def _resolve_engine():
    """Return a usable backend or None (never raises). Order: injected -> shared -> private."""
    with _LOCK:
        if _INJECTED is not None:
            return _INJECTED
    shared = _shared_engine_module()
    if shared is not None:
        return shared
    return _private_engine()


def _is_shared(eng) -> bool:
    """True iff eng is the shared `db.engine` MODULE (it owns session()/available());
    a private/injected sqlalchemy Engine does not have a module-level session()."""
    return eng is not None and hasattr(eng, "session") and hasattr(eng, "available")


# --------------------------------------------------------------------------- #
# availability
# --------------------------------------------------------------------------- #
def available() -> bool:
    """True iff a backend engine is resolvable AND a `SELECT 1` probe succeeds.

    Swallows every exception -> False. The store calls this to choose Pg vs InMemory."""
    eng = _resolve_engine()
    if eng is None:
        return False
    # Shared module: delegate to its own availability probe.
    if _is_shared(eng) and eng is not _INJECTED:
        try:
            return bool(eng.available())
        except Exception:  # noqa: BLE001
            return False
    # Injected shared module also exposes available(); prefer it when present.
    if _is_shared(eng):
        try:
            return bool(eng.available())
        except Exception:  # noqa: BLE001
            return False
    # Private / injected raw Engine: probe with SELECT 1.
    try:
        from sqlalchemy import text
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# session — the RLS-GUC transactional context manager
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def session(tenant_id: str, is_admin: bool = False) -> Iterator:
    """Open a transactional connection with the RLS GUCs set FOR THIS TXN:

        SET LOCAL app.tenant_id = :tenant_id
        SET LOCAL app.is_admin  = '1' if is_admin else '0'

    Yields the connection; commits on clean exit, rolls back on exception. SET LOCAL is
    txn-scoped so the GUC never leaks across pooled connections. A blank tenant_id with
    is_admin=False still sets the (empty) GUC so RLS yields zero rows — never global.

    When the backend is the SHARED db.engine module, delegate to ITS session() (it sets
    the identical GUCs) — this is what grow/store.py does. Private/injected raw Engine:
    open a connection, BEGIN, set the GUCs via SET LOCAL, yield, commit/rollback."""
    eng = _resolve_engine()
    if eng is None:
        raise RuntimeError("ai_manager.db.engine: no backend engine available")

    # Delegate to the shared db.engine module's own context manager (identical GUCs).
    if _is_shared(eng):
        with eng.session(tenant_id=tenant_id or "", is_admin=is_admin) as sess:  # type: ignore
            yield sess
        return

    # Private / injected raw sqlalchemy Engine: own the txn + GUCs here.
    from sqlalchemy import text
    conn = eng.connect()
    txn = conn.begin()
    try:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": tenant_id or ""},
        )
        conn.execute(
            text("SELECT set_config('app.is_admin', :adm, true)"),
            {"adm": "1" if is_admin else "0"},
        )
        yield conn
        txn.commit()
    except Exception:
        try:
            txn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# ensure_schema — lazy, idempotent, NO-OP unless a DSN/shared engine is configured
# --------------------------------------------------------------------------- #
def _read_schema_sql() -> str:
    """Read the sibling schema.sql (the 7-table FORCE-RLS DDL). '' on any failure."""
    try:
        import pathlib
        path = pathlib.Path(__file__).with_name("schema.sql")
        return path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.info("ai_manager.db.engine: cannot read schema.sql: %r", exc)
        return ""


def _dsn_configured() -> bool:
    """True iff AIM_PG_DSN is set (the private-engine gate). Never raises."""
    try:
        from .. import config  # type: ignore
        return bool((config.pg_dsn() or "").strip())
    except Exception:  # noqa: BLE001
        return False


def ensure_schema() -> bool:
    """LAZY, idempotent, NO-OP unless a DSN is configured OR the shared db.engine is up.

    - If AIM_PG_DSN is unset AND the shared db.engine is unavailable: return False
      immediately, touching NOTHING (the live Postgres is untouched when AIM is dormant).
    - Else: run ai_manager/db/schema.sql ONCE (guarded by the _SCHEMA_READY latch) as a
      single script in one autocommit txn (the DO-block + dollar-quoted function need
      script-level execution; do NOT naively split on ';'). Returns True on apply,
      False on no-op/failure. NEVER raises (logs + False)."""
    global _SCHEMA_READY
    with _LOCK:
        if _SCHEMA_READY:
            return True

    # Gate: only act when AIM has an explicitly-configured DSN, or an operator has wired
    # the shared db.engine (available()). Otherwise this is a guaranteed no-op.
    if not _dsn_configured() and _shared_engine_module() is None:
        return False

    eng = _resolve_engine()
    if eng is None:
        return False

    sql = _read_schema_sql()
    if not sql.strip():
        return False

    try:
        if _is_shared(eng):
            # Shared module path: open an admin session and run the script verbatim.
            from sqlalchemy import text
            with eng.session(tenant_id="", is_admin=True) as sess:  # type: ignore
                sess.execute(text(sql))
        else:
            # Private/injected Engine: run the whole DDL script in one txn (DO-block +
            # dollar-quoted function must execute as a script, never statement-split).
            from sqlalchemy import text
            with eng.begin() as conn:
                conn.execute(text(sql))
        with _LOCK:
            _SCHEMA_READY = True
        log.info("ai_manager.db.engine: schema applied (idempotent).")
        return True
    except Exception as exc:  # noqa: BLE001 — DDL failure degrades to no-op (never raises)
        log.warning("ai_manager.db.engine.ensure_schema failed: %r", exc)
        return False
