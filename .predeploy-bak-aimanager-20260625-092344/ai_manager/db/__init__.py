"""ai_manager.db — the AI-Manager persistence package (engine + schema).

Spec: BUILD_SPEC §J + schema-and-config-contract §3. This package owns:
  * engine.py  — session(GUC) / available() / ensure_schema(lazy no-op) / set_engine.
  * schema.sql — the 7 FORCE-RLS ai_manager_* tables + audit immutability trigger.

Importing this package does ZERO I/O and NEVER raises: `engine` is guard-imported so a
half-built tree (or an absent sqlalchemy) still lets `import ai_manager.db` succeed.
`store.py` rides the SHARED `from db import engine` for its Pg path (like grow/store.py)
and may fall back to THIS `engine` for ensure_schema() + a private-DSN engine; both are
lazy and degrade to the InMemory store when no backend is resolvable.
"""
from __future__ import annotations

try:  # guard-import: a broken engine submodule must not break `import ai_manager.db`.
    from . import engine  # noqa: F401
except Exception:  # noqa: BLE001 — degrade to dormant; the store stays InMemory.
    engine = None  # type: ignore

__all__ = ["engine"]
