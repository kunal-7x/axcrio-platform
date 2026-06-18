"""voice_ops.reporting — the real-time reporting / analytics data layer (W14).

THE FOUNDER PAIN this fixes ("nothing updates in real time"): dashboards, CRM and
analytics are STALE after a call because every read walks a flat in-memory JSON
list with a 30s poll. W14 replaces poll-stale-rows with a PUSH read-model:

    every meaningful call moment emits ONE W8 Event  ->  a SinkConsumer (separate
    process) materializes a per-tenant FactCall read-model  ->  a query API
    aggregates that read-model for ANY date range, recalculated per range, with
    drill-down + funnels + agent/source/follow-up analytics + a daily timeline.

This package is TRACKED + DISJOINT + earner-safe:
  * ZERO import of droplet_work / agent.py / caller.py at module load — a PG
    backend is injected lazily (mirrors voice_ops/booking/store.py), default is a
    dependency-free in-memory store so CI + the resting build never need Postgres.
  * Reuses the W8 EventBus + taxonomy (voice_kernel.events) for ingest and the
    canonical UTC-store / vendor-tz-render timestamp layer (timeutil) so the
    "shows 1 day ago for a call just now" off-by-one cannot happen.
  * Reuses the W7 lead Lifecycle (hot/warm/cold/dead) — the read-model carries the
    lifecycle the memory FSM derived; reporting never re-invents classification.

Public surface:
  - DateRange / resolve_range  — presets (today/yesterday/7d/30d/this-month/
    prev-month) + custom, vendor-tz aware, half-open [from,to) UTC windows.
  - FactCall                   — the canonical per-call read-model row.
  - ReportingStore             — tenant-scoped read-model store (injectable backend).
  - ReportingService           — the query API (aggregate any range + drill-down).
  - build_consumer_handler     — turns W8 events into FactCall upserts.
  - ReportingConfig            — knobs (vendor tz, flag, backend selection).
"""
from __future__ import annotations

from .config import ReportingConfig
from .daterange import DateRange, RANGE_PRESETS, resolve_range
from .model import (
    FUNNEL_STAGES,
    CallStatus,
    FactCall,
    LeadStatus,
    funnel_index,
)
from .store import ReportingStore, InMemoryReportingBackend
from . import aggregate
from .aggregate import (
    aggregate as aggregate_report,
    build_funnel,
    daily_timeline,
    drill,
)
from .service import ReportingService
from .consumer import build_consumer_handler, fact_from_event, EventReducer

__all__ = [
    "ReportingConfig",
    "DateRange",
    "RANGE_PRESETS",
    "resolve_range",
    "FUNNEL_STAGES",
    "CallStatus",
    "LeadStatus",
    "FactCall",
    "funnel_index",
    "ReportingStore",
    "InMemoryReportingBackend",
    "aggregate",
    "aggregate_report",
    "build_funnel",
    "daily_timeline",
    "drill",
    "ReportingService",
    "build_consumer_handler",
    "fact_from_event",
    "EventReducer",
]
