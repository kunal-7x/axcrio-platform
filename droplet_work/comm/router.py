"""comm.router — the token-deriving build_router the orchestrator (caller.py) mounts.

Thin re-export of comm.endpoints.build_router, so the caller.py mount line reads uniformly with
the other modules (`from comm.router import build_router`, the funnels/workflow/whatsapp_builder
shape). All the route logic + the fail-closed webhook live in comm.endpoints.

build_router(resolve_tenant, can, need_auth, forbidden, *, require_super_admin=None,
             firewall=None, audit=None) -> APIRouter | None  (None when FastAPI is absent).
"""
from __future__ import annotations

from .endpoints import build_router  # noqa: F401

__all__ = ["build_router"]
