"""comm.cost_guards — the durable per-tenant cost guards (Wave 3, guards #2/#3/#4/#5).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §6 (the 6 cost guards as ACCEPTANCE GATES):

  #2 BUDGET CEILING      — per-tenant daily comm-spend ceiling (comm_daily_budget_minor, default
                           ₹500/day). Over budget -> metered channels return 'blocked_budget';
                           free channels (Telegram) still flow; the founder is alerted.
  #3 FREQUENCY CAP       — per-(contact, channel) per-UTC-day send cap. Stops a journey bug from
                           spamming + billing one contact.
  #4 SPEND-ANOMALY       — today's spend > N x the trailing-7-day median (and above a paise floor)
                           -> the founder is alerted + auto-throttle. (The alert/throttle wiring is
                           the engine's; this module is the DETECTOR.)
  #5 DELIVERABILITY STATE — per-(identity, channel) reachability. A Telegram 403 flips state='dead'
                           so the router never re-attempts (or bills) a known-dead destination.

Backed by communication/db/ddl_comm_cost.sql (3 FORCE-RLS tables). EVERY function:
  * runs inside db.engine.session(tenant_id=..., is_admin=False) -> the GUC binds rows to the
    tenant (cross-tenant impossible at the DB layer),
  * is PERMISSIVE-ON-FAULT: PG down / table missing -> the guard returns 'allow' (a guard must
    NEVER block a send because its bookkeeping is unavailable — the dial loop's detached task
    must always make progress),
  * NEVER raises, does ZERO I/O at import, imports NO agent.py.

Money is INTEGER paise end to end (matches wallet.py / comm_send_log.cost_minor).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from . import config

_log = logging.getLogger("comm.cost_guards")


# ============================================================================
# datastore plumbing (mirrors send_log._engine / wallet._engine degrade contract)
# ============================================================================
def _engine():
    try:
        from db import engine  # type: ignore
        return engine
    except Exception:  # noqa: BLE001
        return None


def available() -> bool:
    eng = _engine()
    try:
        return bool(eng and eng.available())
    except Exception:  # noqa: BLE001
        return False


def _text(sql: str):
    from sqlalchemy import text
    return text(sql)


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class GuardDecision:
    """The verdict of a precheck. `allow` is the only field a caller branches on; `block_status`
    is the comm_send_log status to record when blocked (blocked_budget | blocked_frequency |
    blocked_dead). `anomaly` flags a spend spike (a non-blocking signal -> founder alert)."""
    allow: bool = True
    block_status: str = ""
    reason: str = ""
    anomaly: bool = False
    detail: dict = None  # type: ignore[assignment]


# ============================================================================
# #5 DELIVERABILITY STATE — per-(tenant, contact, channel) reachability.
# ============================================================================
def get_deliverability(tenant_id: str, contact_ref: str, channel: str = "telegram") -> str:
    """Return the reachability state for THIS (tenant, contact, channel): 'ok' | 'dead' |
    'suppressed'. Unknown/absent -> 'ok' (default reachable). PG down -> 'ok' (permissive).
    NEVER raises."""
    if not available() or not tenant_id or not contact_ref:
        return "ok"
    eng = _engine()
    try:
        with eng.session(tenant_id=tenant_id, is_admin=False) as s:
            row = s.execute(_text(
                "SELECT state FROM comm_deliverability "
                "WHERE tenant_id=:t AND contact_ref=:c AND channel=:ch"
            ), {"t": tenant_id, "c": contact_ref, "ch": channel}).fetchone()
            return str(row[0]) if row and row[0] else "ok"
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.cost_guards.get_deliverability degraded: %r", type(exc).__name__)
        return "ok"


def is_dead(tenant_id: str, contact_ref: str, channel: str = "telegram") -> bool:
    """True iff this destination is known dead/suppressed (the router must skip it). Permissive
    on fault (-> False = not dead = allow)."""
    return get_deliverability(tenant_id, contact_ref, channel) in ("dead", "suppressed")


def mark_deliverability(tenant_id: str, contact_ref: str, channel: str, state: str,
                        reason: str = "") -> bool:
    """Upsert the (tenant, contact, channel) reachability state. A Telegram 403 -> state='dead'.
    A successful send -> state='ok' (revive a previously-dead chat that re-enabled the bot).
    Idempotent upsert; bumps fail_count on a non-ok state. NEVER raises; returns True on write."""
    if not available() or not tenant_id or not contact_ref:
        return False
    eng = _engine()
    inc = 0 if state == "ok" else 1
    try:
        with eng.session(tenant_id=tenant_id, is_admin=False) as s:
            s.execute(_text(
                "INSERT INTO comm_deliverability "
                "  (tenant_id, contact_ref, channel, state, reason, fail_count, last_event_at, updated_at) "
                "VALUES (:t,:c,:ch,:st,:rs,:inc, now(), now()) "
                "ON CONFLICT (tenant_id, contact_ref, channel) DO UPDATE SET "
                "  state=EXCLUDED.state, reason=EXCLUDED.reason, "
                "  fail_count=comm_deliverability.fail_count + :inc, "
                "  last_event_at=now(), updated_at=now()"
            ), {"t": tenant_id, "c": contact_ref, "ch": channel, "st": state,
                "rs": (reason or "")[:160], "inc": inc})
            return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.cost_guards.mark_deliverability degraded: %r", type(exc).__name__)
        return False


def classify_failure(error_code: str) -> str:
    """Map a SendResult.error_code to a deliverability state transition, or '' for 'no change'.
    A Telegram 403 (bot blocked / chat not found / user is deactivated) -> 'dead'. Transient
    network/timeout errors do NOT flip state (the contact may still be reachable)."""
    ec = (error_code or "").lower()
    if "http_403" in ec or "forbidden" in ec or "bot was blocked" in ec or "chat not found" in ec \
            or "user is deactivated" in ec:
        return "dead"
    return ""


# ============================================================================
# #3 FREQUENCY CAP — per-(tenant, contact, channel, UTC day) send count.
# ============================================================================
def freq_count_today(tenant_id: str, contact_ref: str, channel: str = "telegram") -> int:
    """Current send count to THIS contact on THIS channel today (UTC). 0 on fault. NEVER raises."""
    if not available() or not tenant_id or not contact_ref:
        return 0
    eng = _engine()
    try:
        with eng.session(tenant_id=tenant_id, is_admin=False) as s:
            row = s.execute(_text(
                "SELECT sent_count FROM comm_freq_counter "
                "WHERE tenant_id=:t AND contact_ref=:c AND channel=:ch AND day=CAST(:d AS date)"
            ), {"t": tenant_id, "c": contact_ref, "ch": channel, "d": _utc_day()}).fetchone()
            return int(row[0]) if row and row[0] is not None else 0
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.cost_guards.freq_count_today degraded: %r", type(exc).__name__)
        return 0


def check_frequency(tenant_id: str, contact_ref: str, channel: str = "telegram") -> GuardDecision:
    """Per-contact frequency PRECHECK (does NOT increment — call bump_frequency on an actual send).
    Blocks when today's count for this contact >= the cap. Permissive on fault. NEVER raises."""
    cap = config.freq_cap_per_contact_day()
    if cap <= 0 or not contact_ref:
        return GuardDecision(allow=True, reason="freq_off")
    used = freq_count_today(tenant_id, contact_ref, channel)
    if used >= cap:
        return GuardDecision(allow=False, block_status="blocked_frequency",
                             reason=f"freq_cap_{used}/{cap}", detail={"used": used, "cap": cap})
    return GuardDecision(allow=True, reason="freq_ok", detail={"used": used, "cap": cap})


def bump_frequency(tenant_id: str, contact_ref: str, channel: str = "telegram", n: int = 1) -> bool:
    """Atomically increment the (tenant, contact, channel, day) send counter. Called AFTER an
    actual contact-facing send. Idempotent-by-day upsert. NEVER raises; returns True on write."""
    if not available() or not tenant_id or not contact_ref:
        return False
    eng = _engine()
    try:
        with eng.session(tenant_id=tenant_id, is_admin=False) as s:
            s.execute(_text(
                "INSERT INTO comm_freq_counter (tenant_id, contact_ref, channel, day, sent_count, updated_at) "
                "VALUES (:t,:c,:ch,CAST(:d AS date),:n, now()) "
                "ON CONFLICT (tenant_id, contact_ref, channel, day) DO UPDATE SET "
                "  sent_count=comm_freq_counter.sent_count + :n, updated_at=now()"
            ), {"t": tenant_id, "c": contact_ref, "ch": channel, "d": _utc_day(), "n": int(n)})
            return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.cost_guards.bump_frequency degraded: %r", type(exc).__name__)
        return False


# ============================================================================
# #2 BUDGET CEILING + #4 SPEND-ANOMALY — per-(tenant, channel, UTC day) spend.
# ============================================================================
def spend_today_minor(tenant_id: str, channel: str = "") -> int:
    """Today's (UTC) total comm-spend in paise. channel='' -> SUM across all channels (the
    per-tenant ceiling is tenant-wide). 0 on fault. NEVER raises."""
    if not available() or not tenant_id:
        return 0
    eng = _engine()
    try:
        with eng.session(tenant_id=tenant_id, is_admin=False) as s:
            if channel:
                row = s.execute(_text(
                    "SELECT COALESCE(SUM(spend_minor),0) FROM comm_daily_spend "
                    "WHERE tenant_id=:t AND channel=:ch AND day=CAST(:d AS date)"
                ), {"t": tenant_id, "ch": channel, "d": _utc_day()}).fetchone()
            else:
                row = s.execute(_text(
                    "SELECT COALESCE(SUM(spend_minor),0) FROM comm_daily_spend "
                    "WHERE tenant_id=:t AND day=CAST(:d AS date)"
                ), {"t": tenant_id, "d": _utc_day()}).fetchone()
            return int(row[0]) if row and row[0] is not None else 0
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.cost_guards.spend_today_minor degraded: %r", type(exc).__name__)
        return 0


def check_budget(tenant_id: str, est_cost_minor: int) -> GuardDecision:
    """Per-tenant daily budget PRECHECK. A FREE send (est<=0, e.g. Telegram) ALWAYS flows — the
    ceiling only gates *metered* channels (plan §6: 'free channels flow'). A paid send is blocked
    when today's spend + this estimate would exceed the cap. Permissive on fault. NEVER raises."""
    est = int(est_cost_minor or 0)
    if est <= 0:
        return GuardDecision(allow=True, reason="free_send")   # free channels never blocked
    cap = config.daily_budget_minor()
    if cap <= 0:
        return GuardDecision(allow=True, reason="budget_off")
    spent = spend_today_minor(tenant_id)
    if spent + est > cap:
        return GuardDecision(allow=False, block_status="blocked_budget",
                             reason=f"budget_{spent}+{est}>{cap}",
                             detail={"spent": spent, "est": est, "cap": cap})
    return GuardDecision(allow=True, reason="budget_ok",
                         detail={"spent": spent, "est": est, "cap": cap})


def record_spend(tenant_id: str, channel: str, cost_minor: int) -> bool:
    """Add `cost_minor` paise to the (tenant, channel, UTC day) running spend (called AFTER a
    settled send). Always bumps send_count (even at cost 0) so the daily series is dense for the
    anomaly median. Idempotent-by-day upsert. NEVER raises; returns True on write."""
    if not available() or not tenant_id:
        return False
    eng = _engine()
    cost = max(0, int(cost_minor or 0))
    try:
        with eng.session(tenant_id=tenant_id, is_admin=False) as s:
            s.execute(_text(
                "INSERT INTO comm_daily_spend (tenant_id, channel, day, spend_minor, send_count, updated_at) "
                "VALUES (:t,:ch,CAST(:d AS date),:amt,1, now()) "
                "ON CONFLICT (tenant_id, channel, day) DO UPDATE SET "
                "  spend_minor=comm_daily_spend.spend_minor + :amt, "
                "  send_count=comm_daily_spend.send_count + 1, updated_at=now()"
            ), {"t": tenant_id, "ch": channel, "d": _utc_day(), "amt": cost})
            return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.cost_guards.record_spend degraded: %r", type(exc).__name__)
        return False


def _trailing_daily_spend(tenant_id: str, days: int = 7) -> list:
    """The per-day total spend (paise) for the previous `days` UTC days (EXCLUDING today), oldest
    first. Days with no row count as 0. Used for the anomaly median. [] on fault. NEVER raises."""
    if not available() or not tenant_id:
        return []
    eng = _engine()
    try:
        with eng.session(tenant_id=tenant_id, is_admin=False) as s:
            rows = s.execute(_text(
                "SELECT day, COALESCE(SUM(spend_minor),0) FROM comm_daily_spend "
                "WHERE tenant_id=:t AND day < CAST(:today AS date) "
                "  AND day >= CAST(:today AS date) - :n "
                "GROUP BY day ORDER BY day ASC"
            ), {"t": tenant_id, "today": _utc_day(), "n": int(days)}).fetchall()
            by_day = {str(r[0]): int(r[1]) for r in rows}
        # Densify: every one of the last `days` days, missing -> 0.
        from datetime import date, timedelta
        today = datetime.now(timezone.utc).date()
        series = []
        for i in range(days, 0, -1):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            series.append(by_day.get(d, 0))
        return series
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.cost_guards._trailing_daily_spend degraded: %r", type(exc).__name__)
        return []


def _median(xs: list) -> float:
    ys = sorted(int(x) for x in xs)
    if not ys:
        return 0.0
    n = len(ys)
    mid = n // 2
    if n % 2:
        return float(ys[mid])
    return (ys[mid - 1] + ys[mid]) / 2.0


def check_anomaly(tenant_id: str) -> GuardDecision:
    """SPEND-ANOMALY detector (non-blocking signal). Trips when today's spend exceeds BOTH the
    paise floor AND multiplier x the trailing-7-day median. (median 0 -> any spend above the floor
    trips, since a tenant who has never spent suddenly spending IS the anomaly.) Permissive on
    fault (no PG -> never trips). NEVER raises. Returns GuardDecision(allow=True, anomaly=bool)."""
    mult = config.anomaly_multiplier()
    floor = config.anomaly_floor_minor()
    if mult <= 0:
        return GuardDecision(allow=True, anomaly=False, reason="anomaly_off")
    today = spend_today_minor(tenant_id)
    if today < floor:
        return GuardDecision(allow=True, anomaly=False, reason="below_floor",
                             detail={"today": today, "floor": floor})
    series = _trailing_daily_spend(tenant_id, days=7)
    med = _median(series)
    threshold = med * mult
    tripped = today > threshold and today >= floor
    return GuardDecision(allow=True, anomaly=bool(tripped),
                         reason=("anomaly" if tripped else "normal"),
                         detail={"today": today, "median": med, "mult": mult, "threshold": threshold})


# ============================================================================
# the composite precheck the engine calls BEFORE a send (cheap, ordered, permissive).
# ============================================================================
def precheck_send(tenant_id: str, contact_ref: str, channel: str, est_cost_minor: int) -> GuardDecision:
    """Run the blocking guards in cheap-to-expensive order; the FIRST block wins. Order:
       (a) deliverability — a known-dead chat (free, one indexed read);
       (b) frequency cap  — per-contact daily count;
       (c) budget ceiling — only for metered (est>0) sends; free sends always pass.
    Returns the first blocking GuardDecision, else allow. Permissive on fault. NEVER raises.
    NOTE: this does NOT mutate counters — bump_frequency / record_spend run AFTER a real send."""
    if not config.cost_guards_enabled():
        return GuardDecision(allow=True, reason="guards_off")
    try:
        if contact_ref and is_dead(tenant_id, contact_ref, channel):
            return GuardDecision(allow=False, block_status="blocked_dead",
                                 reason="deliverability_dead")
        fd = check_frequency(tenant_id, contact_ref, channel)
        if not fd.allow:
            return fd
        bd = check_budget(tenant_id, est_cost_minor)
        if not bd.allow:
            return bd
        return GuardDecision(allow=True, reason="ok")
    except Exception as exc:  # noqa: BLE001 — a guard must never block/crash on its own fault
        _log.warning("comm.cost_guards.precheck_send degraded: %r", type(exc).__name__)
        return GuardDecision(allow=True, reason="degraded_allow")
