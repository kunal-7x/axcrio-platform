"""comm.ratelimit — in-process per-tenant guards for the inbound brain (Wave 2).

Spec: communication/COMMUNICATION-MASTER-PLAN.md WAVE 2 ("Per-tenant webhook rate-limit +
body-size cap + daily Groq ceiling BEFORE any LLM call") + §6 (cost guards as acceptance gates,
not "later").

Two cheap, in-process, never-raise guards run BEFORE the brain spends a Groq token:

  * `allow_inbound(tenant_id, chat_id)`  — a sliding 60s window per (tenant, chat). A flood from
    one chat is dropped (the webhook still acks 200 so Telegram stops retrying) WITHOUT calling
    the LLM. Bounds the abuse blast radius to one chat.
  * `allow_groq_call(tenant_id)`         — a per-tenant per-UTC-day counter. Once a tenant hits
    COMM_GROQ_DAILY_CAP brain calls in a day, further inbound messages are stored + acked but get
    NO LLM reply (a runaway journey/abuse can never run up an unbounded Groq bill). Resets at the
    UTC day boundary.

These are PROCESS-LOCAL (a restart resets the counters). That is acceptable for a circuit-breaker
whose job is to cap a runaway within a process; the durable per-tenant budget ledger is Wave 3.
ZERO I/O at import, NEVER raises, no agent.py import. Read the caps at call time (config.*).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, Tuple

from . import config

_LOCK = threading.Lock()

# (tenant, chat) -> a deque of recent inbound timestamps (sliding 60s window).
_INBOUND: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
_INBOUND_CAP_KEYS = 20000        # crude bound on the key space (drop-oldest when exceeded)

# tenant -> {"day": "YYYY-MM-DD", "count": int} — the per-UTC-day Groq-call counter.
_GROQ_DAY: Dict[str, Dict[str, object]] = {}


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def allow_inbound(tenant_id: str, chat_id: str) -> bool:
    """Sliding 60s per-(tenant, chat) rate gate. Returns True if this inbound is within the cap
    (and records it), False if it exceeds COMM_INBOUND_RATE_PER_MIN. NEVER raises.
    A cap <= 0 disables the gate (always True)."""
    cap = config.inbound_rate_per_min()
    if cap <= 0:
        return True
    key = (str(tenant_id or ""), str(chat_id or ""))
    now = time.time()
    try:
        with _LOCK:
            if len(_INBOUND) > _INBOUND_CAP_KEYS:
                # crude space bound: drop ~half the keys (oldest-inserted first).
                for k in list(_INBOUND.keys())[: _INBOUND_CAP_KEYS // 2]:
                    _INBOUND.pop(k, None)
            dq = _INBOUND[key]
            cutoff = now - 60.0
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= cap:
                return False
            dq.append(now)
            return True
    except Exception:  # noqa: BLE001 — a guard must never crash the webhook
        return True


def allow_groq_call(tenant_id: str) -> bool:
    """Per-tenant per-UTC-day Groq-call gate. Returns True if under COMM_GROQ_DAILY_CAP for today
    (and increments the counter), False once the cap is hit. NEVER raises. A cap <= 0 = unlimited."""
    cap = config.groq_daily_cap()
    if cap <= 0:
        return True
    tid = str(tenant_id or "")
    day = _utc_day()
    try:
        with _LOCK:
            rec = _GROQ_DAY.get(tid)
            if not rec or rec.get("day") != day:
                rec = {"day": day, "count": 0}
                _GROQ_DAY[tid] = rec
            count = int(rec.get("count", 0))  # type: ignore[arg-type]
            if count >= cap:
                return False
            rec["count"] = count + 1
            return True
    except Exception:  # noqa: BLE001
        return True


def snapshot(tenant_id: str = "") -> dict:
    """Diagnostic — current counters for a tenant (never a secret). NEVER raises."""
    try:
        with _LOCK:
            rec = _GROQ_DAY.get(str(tenant_id or ""), {})
            return {"groq_day": dict(rec), "inbound_keys": len(_INBOUND)}
    except Exception:  # noqa: BLE001
        return {}
