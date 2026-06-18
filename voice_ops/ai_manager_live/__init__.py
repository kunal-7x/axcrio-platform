"""voice_ops.ai_manager_live — the AI-Manager LIVE-data adapter + command center (W14).

THE FOUNDER PAIN this fixes (#2): "the AI Manager fetches WRONG details." Today the
manager answers operational questions by making loopback HTTP calls that walk the
same stale flat-file in-memory list the dashboard does. W14 points it at the W14
reporting layer instead, so it reads the EXACT same live aggregates the dashboard
shows — it can NEVER diverge into a stale separate cache.

It delivers three things on top of the reporting layer:
  1. `LiveAdapter` — answers operational questions ("how many calls today",
     "connect rate this week", "campaign X performance", "show hot leads") straight
     from `ReportingService` (LIVE numbers, range-aware, drill-down-aware).
  2. `parse_command` — a tiny deterministic natural-language command parser
     ("send today's report", "show hot leads", "campaign X performance",
     "yesterday's numbers") -> a structured `Command`. No LLM needed for the common
     verbs (deterministic + cheap + drift-free); an LLM can be layered later for
     the long tail.
  3. `DailySummary` — the end-of-day executive summary generator (totals + hot-lead
     names + short AI summaries + next actions, founder pain #4) and a
     WhatsApp-ready `deliver()` to the tenant's registered number — DORMANT until WA
     creds are wired (returns a queued/not_configured envelope, never sends blind).

Earner-safe + disjoint: imports ONLY voice_ops.reporting + voice_kernel (+ a lazy,
injected WhatsApp sender). ZERO droplet_work / agent.py / caller.py import.
"""
from __future__ import annotations

from .config import AIManagerLiveConfig
from .commands import Command, CommandKind, parse_command
from .adapter import LiveAdapter
from .summary import DailySummary, build_daily_summary
from .delivery import ReportDelivery, NullWhatsAppSender
from .service import AIManagerLiveService

__all__ = [
    "AIManagerLiveConfig",
    "Command",
    "CommandKind",
    "parse_command",
    "LiveAdapter",
    "DailySummary",
    "build_daily_summary",
    "ReportDelivery",
    "NullWhatsAppSender",
    "AIManagerLiveService",
]
