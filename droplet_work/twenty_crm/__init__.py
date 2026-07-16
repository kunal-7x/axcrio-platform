"""
twenty_crm — Haptica ↔ Twenty CRM integration (server-side proxy + value bridge).

Deeply integrates Twenty (https://twenty.com) as Haptica's relational sales-CRM
engine WITHOUT an iframe: the panel renders native Haptica UI over a normalized
``/twenty/*`` contract served here, while the workspace API key stays server-side.

Public surface is ``build_router`` (the house build_router pattern). Import-guarded
and dormant-safe so a missing dep or an unconnected tenant never breaks startup.
"""

from .router import build_router

__all__ = ["build_router"]
