"""
auto_lead — real-time multi-source lead ingestion + automation for Haptica.

Connect sources (website / custom webhooks, Zapier/Make, Meta & Google lead ads,
WhatsApp, email inbox, Apollo) → monitor in real time → auto-import every lead →
validate / dedupe → route into Haptica's leads pipeline (so Riya can call them).

Public surface is build_router (the house build_router pattern). Import-guarded +
dormant-safe so a missing dep can't break startup.
"""

from .router import build_router

__all__ = ["build_router"]
