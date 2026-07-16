"""grow.store — tenant-scoped, FORCE-RLS persistence for scores / signals / journeys.

Same posture as voice_ops.whatsapp.store: a dependency-free thread-safe InMemory backend
(CI + resting build + a fine cache when Postgres is absent) and a lazy `_Pg*Backend` that
rides the P1 `db.engine` spine with RLS GUCs per session — this module imports ZERO
sqlalchemy at load. Every method is TENANT-SCOPED and fail-closed on an empty tenant.
DDL: grow/db/ddl_grow.sql (org_id + admin-GUC RLS, signals append-only-by-policy).
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Optional

from .model import Journey, ScoredLead, SignalEvent

log = logging.getLogger("grow.store")


def _ok(tenant_id: str) -> bool:
    return bool((tenant_id or "").strip())


# =========================================================================== #
# SCORES  (grow_lead_scores : latest score per lead, re-scored on each event)
# =========================================================================== #
class _InMemScores:
    def __init__(self):
        self._rows: dict[tuple[str, str], ScoredLead] = {}
        self._lock = threading.RLock()

    def upsert(self, s: ScoredLead) -> None:
        with self._lock:
            self._rows[(s.tenant_id, s.lead_id)] = s.copy()

    def get(self, tenant_id: str, lead_id: str) -> Optional[ScoredLead]:
        with self._lock:
            r = self._rows.get((tenant_id, lead_id))
            return r.copy() if r else None

    def scan(self, tenant_id: str) -> list[ScoredLead]:
        with self._lock:
            return [s.copy() for (t, _l), s in self._rows.items() if t == tenant_id]


class _PgScores:
    def _engine(self):
        try:
            from db import engine as eng  # type: ignore
            return eng if eng.available() else None
        except Exception:  # noqa: BLE001
            return None

    def _text(self, sql: str):
        from sqlalchemy import text
        return text(sql)

    def upsert(self, s: ScoredLead) -> None:
        eng = self._engine()
        if eng is None:
            return
        try:
            with eng.session(tenant_id=s.tenant_id, is_admin=False) as sess:
                sess.execute(self._text(
                    "INSERT INTO grow_lead_scores (org_id,lead_id,journey_id,principal_ref,"
                    " phone_masked,score,tier,confidence,reasons,features,model,source_platform,"
                    " scored_at) VALUES (:org,:lid,:jid,:pr,:pm,:sc,:ti,:cf,CAST(:rs AS jsonb),"
                    " CAST(:ft AS jsonb),:md,:sp,now()) "
                    "ON CONFLICT (org_id,lead_id) DO UPDATE SET journey_id=:jid,"
                    " principal_ref=:pr,phone_masked=:pm,score=:sc,tier=:ti,confidence=:cf,"
                    " reasons=CAST(:rs AS jsonb),features=CAST(:ft AS jsonb),model=:md,"
                    " source_platform=:sp,scored_at=now()"
                ), {"org": s.tenant_id, "lid": s.lead_id, "jid": s.journey_id,
                    "pr": s.principal_ref, "pm": s.phone_masked, "sc": int(s.score),
                    "ti": s.tier, "cf": float(s.confidence), "rs": json.dumps(s.reasons or []),
                    "ft": json.dumps(s.features or {}), "md": s.model, "sp": s.source_platform})
        except Exception as exc:  # noqa: BLE001
            log.info("grow_lead_scores upsert failed: %r", exc)

    def _row(self, tenant_id: str, r) -> ScoredLead:
        rs, ft = r[7], r[8]
        if isinstance(rs, str):
            try: rs = json.loads(rs)
            except Exception: rs = []
        if isinstance(ft, str):
            try: ft = json.loads(ft)
            except Exception: ft = {}
        return ScoredLead(tenant_id=tenant_id, lead_id=r[0], journey_id=r[1] or "",
                          principal_ref=r[2] or "", phone_masked=r[3] or "", score=int(r[4] or 0),
                          tier=r[5] or "junk", confidence=float(r[6] or 0.0), reasons=rs or [],
                          features=ft or {}, model=r[9] or "heuristic_v1", source_platform=r[10] or "")

    _SEL = ("SELECT lead_id,journey_id,principal_ref,phone_masked,score,tier,confidence,"
            "reasons,features,model,source_platform FROM grow_lead_scores WHERE org_id=:org")

    def get(self, tenant_id: str, lead_id: str) -> Optional[ScoredLead]:
        eng = self._engine()
        if eng is None:
            return None
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                r = s.execute(self._text(self._SEL + " AND lead_id=:lid"),
                              {"org": tenant_id, "lid": lead_id}).fetchone()
                return self._row(tenant_id, r) if r else None
        except Exception as exc:  # noqa: BLE001
            log.info("grow_lead_scores get failed: %r", exc)
            return None

    def scan(self, tenant_id: str) -> list[ScoredLead]:
        eng = self._engine()
        if eng is None:
            return []
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(self._text(self._SEL + " ORDER BY scored_at DESC LIMIT 2000"),
                                 {"org": tenant_id}).fetchall()
                return [self._row(tenant_id, r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.info("grow_lead_scores scan failed: %r", exc)
            return []


class ScoreStore:
    def __init__(self, backend=None):
        self.backend = backend or _InMemScores()

    def upsert(self, s: ScoredLead) -> bool:
        if not _ok(s.tenant_id) or not (s.lead_id or "").strip():
            log.warning("ScoreStore.upsert dropped: missing tenant/lead_id")
            return False
        self.backend.upsert(s)
        return True

    def get(self, tenant_id: str, lead_id: str) -> Optional[ScoredLead]:
        return self.backend.get(tenant_id, lead_id) if _ok(tenant_id) else None

    def list(self, tenant_id: str, *, tier: str = "", min_score: int = 0,
             sales_ready_only: bool = False) -> list[ScoredLead]:
        if not _ok(tenant_id):
            return []
        rows = self.backend.scan(tenant_id)
        if tier:
            rows = [r for r in rows if r.tier == tier]
        if min_score:
            rows = [r for r in rows if r.score >= min_score]
        if sales_ready_only:
            rows = [r for r in rows if r.sales_ready]
        rows.sort(key=lambda r: (r.score, r.scored_at), reverse=True)
        return rows


# =========================================================================== #
# SIGNALS  (grow_signals_log : the CAPI dispatch ledger, append/idempotent-upsert)
# =========================================================================== #
class _InMemSignals:
    def __init__(self):
        self._rows: dict[tuple[str, str], SignalEvent] = {}
        self._lock = threading.RLock()

    def upsert(self, e: SignalEvent) -> None:
        with self._lock:
            self._rows[(e.tenant_id, e.event_id)] = e.copy()

    def get(self, tenant_id: str, event_id: str) -> Optional[SignalEvent]:
        with self._lock:
            e = self._rows.get((tenant_id, event_id))
            return e.copy() if e else None

    def scan(self, tenant_id: str) -> list[SignalEvent]:
        with self._lock:
            return [e.copy() for (t, _e), e in self._rows.items() if t == tenant_id]


class _PgSignals:
    def _engine(self):
        try:
            from db import engine as eng  # type: ignore
            return eng if eng.available() else None
        except Exception:  # noqa: BLE001
            return None

    def _text(self, sql: str):
        from sqlalchemy import text
        return text(sql)

    def upsert(self, e: SignalEvent) -> None:
        eng = self._engine()
        if eng is None:
            return
        try:
            with eng.session(tenant_id=e.tenant_id, is_admin=False) as s:
                s.execute(self._text(
                    "INSERT INTO grow_signals_log (org_id,event_id,journey_id,lead_id,platform,"
                    " endpoint,event_name,value,currency,match_keys,status,emq_estimate,reason,"
                    " dispatched_at) VALUES (:org,:eid,:jid,:lid,:pf,:ep,:en,:val,:cur,"
                    " CAST(:mk AS jsonb),:st,:emq,:rs,now()) "
                    "ON CONFLICT (org_id,event_id) DO UPDATE SET status=:st,reason=:rs,"
                    " value=:val,emq_estimate=:emq,match_keys=CAST(:mk AS jsonb),"
                    " dispatched_at=now()"
                ), {"org": e.tenant_id, "eid": e.event_id, "jid": e.journey_id, "lid": e.lead_id,
                    "pf": e.platform, "ep": e.endpoint, "en": e.event_name, "val": int(e.value),
                    "cur": e.currency, "mk": json.dumps(e.match_keys or []), "st": e.status,
                    "emq": float(e.emq_estimate), "rs": e.reason})
        except Exception as exc:  # noqa: BLE001
            log.info("grow_signals_log upsert failed: %r", exc)

    def _row(self, tenant_id: str, r) -> SignalEvent:
        mk = r[8]
        if isinstance(mk, str):
            try: mk = json.loads(mk)
            except Exception: mk = []
        return SignalEvent(tenant_id=tenant_id, event_id=r[0], journey_id=r[1] or "",
                           lead_id=r[2] or "", platform=r[3] or "meta", endpoint=r[4] or "capi",
                           event_name=r[5] or "Lead", value=int(r[6] or 0), currency=r[7] or "INR",
                           match_keys=mk or [], status=r[9] or "shadow",
                           emq_estimate=float(r[10] or 0.0), reason=r[11] or "")

    _SEL = ("SELECT event_id,journey_id,lead_id,platform,endpoint,event_name,value,currency,"
            "match_keys,status,emq_estimate,reason FROM grow_signals_log WHERE org_id=:org")

    def get(self, tenant_id: str, event_id: str) -> Optional[SignalEvent]:
        eng = self._engine()
        if eng is None:
            return None
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                r = s.execute(self._text(self._SEL + " AND event_id=:eid"),
                              {"org": tenant_id, "eid": event_id}).fetchone()
                return self._row(tenant_id, r) if r else None
        except Exception as exc:  # noqa: BLE001
            log.info("grow_signals_log get failed: %r", exc)
            return None

    def scan(self, tenant_id: str) -> list[SignalEvent]:
        eng = self._engine()
        if eng is None:
            return []
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(self._text(self._SEL + " ORDER BY dispatched_at DESC LIMIT 5000"),
                                 {"org": tenant_id}).fetchall()
                return [self._row(tenant_id, r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.info("grow_signals_log scan failed: %r", exc)
            return []


class SignalStore:
    def __init__(self, backend=None):
        self.backend = backend or _InMemSignals()

    def append(self, e: SignalEvent) -> bool:
        if not _ok(e.tenant_id) or not (e.event_id or "").strip():
            log.warning("SignalStore.append dropped: missing tenant/event_id")
            return False
        self.backend.upsert(e)
        return True

    def get(self, tenant_id: str, event_id: str) -> Optional[SignalEvent]:
        return self.backend.get(tenant_id, event_id) if _ok(tenant_id) else None

    def list(self, tenant_id: str, *, journey_id: str = "") -> list[SignalEvent]:
        if not _ok(tenant_id):
            return []
        rows = self.backend.scan(tenant_id)
        if journey_id:
            rows = [r for r in rows if r.journey_id == journey_id]
        rows.sort(key=lambda r: r.dispatched_at, reverse=True)
        return rows


# =========================================================================== #
# JOURNEYS  (grow_journeys : the correlation spine)
# =========================================================================== #
class _InMemJourneys:
    def __init__(self):
        self._rows: dict[tuple[str, str], Journey] = {}
        self._lock = threading.RLock()

    def upsert(self, j: Journey) -> None:
        with self._lock:
            self._rows[(j.tenant_id, j.journey_id)] = j.copy()

    def get(self, tenant_id: str, journey_id: str) -> Optional[Journey]:
        with self._lock:
            j = self._rows.get((tenant_id, journey_id))
            return j.copy() if j else None

    def scan(self, tenant_id: str) -> list[Journey]:
        with self._lock:
            return [j.copy() for (t, _j), j in self._rows.items() if t == tenant_id]


class _PgJourneys:
    def _engine(self):
        try:
            from db import engine as eng  # type: ignore
            return eng if eng.available() else None
        except Exception:  # noqa: BLE001
            return None

    def _text(self, sql: str):
        from sqlalchemy import text
        return text(sql)

    def upsert(self, j: Journey) -> None:
        eng = self._engine()
        if eng is None:
            return
        try:
            with eng.session(tenant_id=j.tenant_id, is_admin=False) as s:
                s.execute(self._text(
                    "INSERT INTO grow_journeys (org_id,journey_id,principal_ref,phone_masked,"
                    " source_platform,source_ad_id,ctwa_clid,fbclid,gclid,status,first_touch_at,"
                    " updated_at) VALUES (:org,:jid,:pr,:pm,:sp,:ad,:ct,:fb,:gc,:st,now(),now()) "
                    "ON CONFLICT (org_id,journey_id) DO UPDATE SET principal_ref=:pr,"
                    " phone_masked=:pm,source_platform=:sp,source_ad_id=:ad,ctwa_clid=:ct,"
                    " fbclid=:fb,gclid=:gc,status=:st,updated_at=now()"
                ), {"org": j.tenant_id, "jid": j.journey_id, "pr": j.principal_ref,
                    "pm": j.phone_masked, "sp": j.source_platform, "ad": j.source_ad_id,
                    "ct": j.ctwa_clid, "fb": j.fbclid, "gc": j.gclid, "st": j.status})
        except Exception as exc:  # noqa: BLE001
            log.info("grow_journeys upsert failed: %r", exc)

    def _row(self, tenant_id: str, r) -> Journey:
        return Journey(tenant_id=tenant_id, journey_id=r[0], principal_ref=r[1] or "",
                       phone_masked=r[2] or "", source_platform=r[3] or "", source_ad_id=r[4] or "",
                       ctwa_clid=r[5] or "", fbclid=r[6] or "", gclid=r[7] or "", status=r[8] or "open")

    _SEL = ("SELECT journey_id,principal_ref,phone_masked,source_platform,source_ad_id,ctwa_clid,"
            "fbclid,gclid,status FROM grow_journeys WHERE org_id=:org")

    def get(self, tenant_id: str, journey_id: str) -> Optional[Journey]:
        eng = self._engine()
        if eng is None:
            return None
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                r = s.execute(self._text(self._SEL + " AND journey_id=:jid"),
                              {"org": tenant_id, "jid": journey_id}).fetchone()
                return self._row(tenant_id, r) if r else None
        except Exception as exc:  # noqa: BLE001
            log.info("grow_journeys get failed: %r", exc)
            return None

    def scan(self, tenant_id: str) -> list[Journey]:
        eng = self._engine()
        if eng is None:
            return []
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(self._text(self._SEL + " ORDER BY updated_at DESC LIMIT 2000"),
                                 {"org": tenant_id}).fetchall()
                return [self._row(tenant_id, r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.info("grow_journeys scan failed: %r", exc)
            return []


class JourneyStore:
    def __init__(self, backend=None):
        self.backend = backend or _InMemJourneys()

    def upsert(self, j: Journey) -> bool:
        if not _ok(j.tenant_id) or not (j.journey_id or "").strip():
            log.warning("JourneyStore.upsert dropped: missing tenant/journey_id")
            return False
        self.backend.upsert(j)
        return True

    def get(self, tenant_id: str, journey_id: str) -> Optional[Journey]:
        return self.backend.get(tenant_id, journey_id) if _ok(tenant_id) else None

    def list(self, tenant_id: str) -> list[Journey]:
        if not _ok(tenant_id):
            return []
        rows = self.backend.scan(tenant_id)
        rows.sort(key=lambda j: j.updated_at, reverse=True)
        return rows


# =========================================================================== #
# ORCHESTRATIONS  (grow_orchestrations : one speed-to-lead run per journey, W2)
# =========================================================================== #
class _InMemOrch:
    def __init__(self):
        self._rows: dict[tuple[str, str], "Orchestration"] = {}
        self._lock = threading.RLock()

    def upsert(self, o) -> None:
        with self._lock:
            self._rows[(o.tenant_id, o.journey_id)] = o.copy()

    def get(self, tenant_id: str, journey_id: str):
        with self._lock:
            o = self._rows.get((tenant_id, journey_id))
            return o.copy() if o else None

    def scan(self, tenant_id: str) -> list:
        with self._lock:
            return [o.copy() for (t, _j), o in self._rows.items() if t == tenant_id]


class _PgOrch:
    def _engine(self):
        try:
            from db import engine as eng  # type: ignore
            return eng if eng.available() else None
        except Exception:  # noqa: BLE001
            return None

    def _text(self, sql: str):
        from sqlalchemy import text
        return text(sql)

    def upsert(self, o) -> None:
        eng = self._engine()
        if eng is None:
            return
        try:
            import json as _json
            chans = _json.dumps([c.public() for c in o.channels])
            with eng.session(tenant_id=o.tenant_id, is_admin=False) as s:
                s.execute(self._text(
                    "INSERT INTO grow_orchestrations (org_id,journey_id,lead_id,status,"
                    " compliance_decision,compliance_reasons,channels,latency_ms,sla_met,"
                    " completed_at) VALUES (:org,:jid,:lid,:st,:cd,CAST(:cr AS jsonb),"
                    " CAST(:ch AS jsonb),:lat,:sla,now()) "
                    "ON CONFLICT (org_id,journey_id) DO UPDATE SET lead_id=:lid,status=:st,"
                    " compliance_decision=:cd,compliance_reasons=CAST(:cr AS jsonb),"
                    " channels=CAST(:ch AS jsonb),latency_ms=:lat,sla_met=:sla,completed_at=now()"
                ), {"org": o.tenant_id, "jid": o.journey_id, "lid": o.lead_id, "st": o.status,
                    "cd": o.compliance_decision, "cr": _json.dumps(o.compliance_reasons or []),
                    "ch": chans, "lat": int(o.latency_ms), "sla": bool(o.sla_met)})
        except Exception as exc:  # noqa: BLE001
            log.info("grow_orchestrations upsert failed: %r", exc)

    def get(self, tenant_id: str, journey_id: str):
        return None  # reads served from InMemory in W2; Pg read-model added with the dashboard wave

    def scan(self, tenant_id: str) -> list:
        return []


class OrchestrationStore:
    def __init__(self, backend=None):
        self.backend = backend or _InMemOrch()

    def upsert(self, o) -> bool:
        if not _ok(o.tenant_id) or not (o.journey_id or "").strip():
            return False
        self.backend.upsert(o)
        return True

    def get(self, tenant_id: str, journey_id: str):
        return self.backend.get(tenant_id, journey_id) if _ok(tenant_id) else None

    def list(self, tenant_id: str) -> list:
        if not _ok(tenant_id):
            return []
        rows = self.backend.scan(tenant_id)
        rows.sort(key=lambda o: o.completed_at, reverse=True)
        return rows


# =========================================================================== #
# Backend selection — Postgres when the seam flag is on AND db.engine is live
# =========================================================================== #
def make_stores(use_pg: bool = False) -> tuple[ScoreStore, SignalStore, JourneyStore, OrchestrationStore]:
    """Build the four stores. use_pg=True wires the lazy Pg backends (they self-degrade
    to no-op when db.engine is unavailable — never crash)."""
    if use_pg:
        return (ScoreStore(_PgScores()), SignalStore(_PgSignals()), JourneyStore(_PgJourneys()),
                OrchestrationStore(_PgOrch()))
    return ScoreStore(), SignalStore(), JourneyStore(), OrchestrationStore()
