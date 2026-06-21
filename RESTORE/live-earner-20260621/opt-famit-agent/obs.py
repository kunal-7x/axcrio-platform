"""obs.py — Famit P0 observability: Prometheus /metrics + structured request logs.

ADDITIVE. Exposes an in-process Prometheus registry with:
  * famit_requests_total{method,route,status}      — request counter
  * famit_request_latency_seconds{method,route}    — latency histogram
  * famit_request_in_progress                      — in-flight gauge
  * famit_call_cost_total{currency}                — REUSES the already-metered
        per-call cost (summed from the existing cost_ledger via a callback into
        caller.py — no new metering, no double counting)
  * famit_build_info{component}                    — static 1 (liveness/version)

If prometheus_client is unavailable the module degrades gracefully: render()
returns a tiny text/plain stub and the middleware becomes a no-op, so /metrics
still answers 200 and nothing breaks.

`route` is the FastAPI route TEMPLATE (e.g. /campaigns/{cid}), not the raw path,
so per-id endpoints don't explode metric cardinality.

Also provides `log_request(...)` — a one-line structured (JSON) access log written
to stderr (picked up by journald), best-effort and never raising.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Callable, Optional

try:
    from prometheus_client import (CollectorRegistry, Counter, Gauge, Histogram,
                                   generate_latest, CONTENT_TYPE_LATEST)
    _PROM = True
except Exception:  # noqa: BLE001
    _PROM = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

# Callback set by caller.py: returns {currency: total_cost_float} from cost_ledger.
_cost_provider: Optional[Callable[[], dict]] = None
_REGISTRY = None
_C_REQ = _H_LAT = _G_INPROG = _G_COST = _G_BUILD = None
_ready = False


def init(cost_provider: Optional[Callable[[], dict]] = None,
         component: str = "famit-caller") -> bool:
    """Build the registry + metrics once. `cost_provider` is an optional callable
    returning {currency: float} summed cost (reusing the existing ledger)."""
    global _cost_provider, _REGISTRY, _C_REQ, _H_LAT, _G_INPROG, _G_COST, _G_BUILD, _ready
    _cost_provider = cost_provider
    if not _PROM:
        _ready = False
        return False
    try:
        _REGISTRY = CollectorRegistry()
        _C_REQ = Counter("famit_requests_total", "HTTP requests",
                         ["method", "route", "status"], registry=_REGISTRY)
        _H_LAT = Histogram("famit_request_latency_seconds", "Request latency (s)",
                           ["method", "route"], registry=_REGISTRY,
                           buckets=(.01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10))
        _G_INPROG = Gauge("famit_request_in_progress", "In-flight requests",
                          registry=_REGISTRY)
        _G_COST = Gauge("famit_call_cost_total",
                        "Cumulative metered call cost (from cost_ledger)",
                        ["currency"], registry=_REGISTRY)
        _G_BUILD = Gauge("famit_build_info", "Static build/liveness info",
                         ["component"], registry=_REGISTRY)
        _G_BUILD.labels(component=component).set(1)
        _ready = True
        return True
    except Exception:  # noqa: BLE001
        _ready = False
        return False


def ready() -> bool:
    return _ready


def inprogress_inc():
    if _ready and _G_INPROG is not None:
        try:
            _G_INPROG.inc()
        except Exception:  # noqa: BLE001
            pass


def inprogress_dec():
    if _ready and _G_INPROG is not None:
        try:
            _G_INPROG.dec()
        except Exception:  # noqa: BLE001
            pass


def observe(method: str, route: str, status: int, latency_s: float):
    """Record one finished request. Best-effort."""
    if not _ready:
        return
    try:
        _C_REQ.labels(method=method, route=route, status=str(status)).inc()
        _H_LAT.labels(method=method, route=route).observe(max(0.0, latency_s))
    except Exception:  # noqa: BLE001
        pass


def _refresh_cost():
    """Pull the latest cumulative cost from the provider into the gauge."""
    if not _ready or _cost_provider is None or _G_COST is None:
        return
    try:
        by_ccy = _cost_provider() or {}
        for ccy, total in by_ccy.items():
            _G_COST.labels(currency=str(ccy or "INR")).set(float(total or 0))
    except Exception:  # noqa: BLE001
        pass


def render() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics endpoint."""
    if not _ready or _REGISTRY is None:
        body = (b"# prometheus_client unavailable; obs stub\n"
                b"famit_up 1\n")
        return body, "text/plain; version=0.0.4; charset=utf-8"
    _refresh_cost()  # cheap; reads the derived ledger summary
    try:
        return generate_latest(_REGISTRY), CONTENT_TYPE_LATEST
    except Exception:  # noqa: BLE001
        return b"famit_up 1\n", "text/plain; version=0.0.4; charset=utf-8"


def log_request(method: str, path: str, route: str, status: int,
                latency_ms: float, tenant: str = "", ip: str = "") -> None:
    """One-line structured access log to stderr (journald). Never raises."""
    try:
        rec = {"t": "req", "method": method, "path": path, "route": route,
               "status": status, "ms": round(latency_ms, 1),
               "tenant": tenant or "", "ip": ip or ""}
        print(json.dumps(rec, ensure_ascii=False), file=sys.stderr, flush=False)
    except Exception:  # noqa: BLE001
        pass
