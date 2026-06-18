"""voice_ops.compliance.consent — the consent LEDGER + retention TTL (W26 §4.3 / Tier A #7).

The authoritative, APPEND-ONLY consent record — the legal evidence that we were allowed
to place the call and process the data. Two distinct consents tracked separately
(TCCCPR place-call vs DPDP process-data vs recording), each free/specific/informed/
unambiguous/REVOCABLE, timestamped, per-channel.

FRESHNESS is checked AT DIAL TIME, not at import (the load-bearing rule that stops
"imported a list once" being a durable green light):
  * explicit-transaction consent auto-expires +7 days;
  * inferred consent (existing business relationship) is valid only for the contract
    duration (an explicit expires_at);
  * a revocation writes a NEW row stamped revoked_at (revocable as easily as given).
The gate reads the NEWEST non-revoked, non-expired row for
(tenant, principal, consent_type, scope=campaign).

PII-MIN: the principal is referenced by a salted hash + lead_id, never the raw phone.

Shape mirrors voice_ops: a `ConsentStore` Protocol + a real append-only
`InMemoryConsentStore` (tests + local fallback). A LATER seam wave adds a
`PgConsentStore` against the FORCE-RLS, append-only `consent_ledger` table (DDL in the
seam doc, mirror of ddl_wallet.sql); the engine depends only on the Protocol.

Retention TTL: `expired_principal_refs(now)` lists principals whose data is past the
retention policy — the input to the purge/erasure job (the cascade itself is a separate
sub-system; this module owns the consent + TTL bookkeeping).

PURE: stdlib only; NEVER raises into the gate (a store error on a Tier-A check is
surfaced as a fail-closed signal the engine turns into a block).
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Protocol, runtime_checkable

log = logging.getLogger("voice_ops.compliance.consent")

# consent types
TCCCPR_PLACE_CALL = "tcccpr_place_call"
DPDP_PROCESS_DATA = "dpdp_process_data"
RECORDING = "recording"

# bases
BASIS_EXPLICIT = "explicit"     # auto-expires +7d unless an explicit expires_at given
BASIS_INFERRED = "inferred"     # contract-duration; needs an explicit expires_at
BASIS_LEGITIMATE = "legitimate_use"


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


@dataclass
class ConsentRow:
    """One append-only consent record (mirror of a consent_ledger row)."""
    tenant_id: str
    data_principal_ref: str            # salted hash of phone / lead_id (PII-min)
    consent_type: str
    basis: str
    channel: str = "import"            # web_form|ivr_dtmf|verbal_oncall|whatsapp|import
    scope: str = ""                    # campaign_id / purpose
    granted_at: Optional[_dt.datetime] = None
    expires_at: Optional[_dt.datetime] = None
    revoked_at: Optional[_dt.datetime] = None
    evidence_ref: str = ""
    created_at: Optional[_dt.datetime] = None

    def active_at(self, now: _dt.datetime) -> bool:
        """Active = not revoked AND (no expiry OR expiry in the future) AND granted."""
        if self.revoked_at is not None:
            return False
        if self.granted_at is not None and self.granted_at > now:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return True


@runtime_checkable
class ConsentStore(Protocol):
    """Append-only consent store contract."""
    def append(self, row: ConsentRow) -> ConsentRow: ...
    def rows_for(self, tenant_id: str, principal_ref: str, consent_type: str,
                 scope: str) -> List[ConsentRow]: ...
    def all_rows(self, tenant_id: str) -> List[ConsentRow]: ...


class InMemoryConsentStore:
    """Thread-safe append-only ConsentStore. Faithful to the legal semantics: rows are
    never mutated; a revocation/refresh is a NEW row; reads return rows newest-first."""

    def __init__(self):
        self._rows: List[ConsentRow] = []
        self._lock = threading.Lock()

    def append(self, row: ConsentRow) -> ConsentRow:
        t = (row.tenant_id or "").strip()
        if not t:
            raise ValueError("consent.append: empty tenant_id (fail-closed)")
        stamped = replace(row, created_at=row.created_at or _now(),
                          granted_at=row.granted_at or _now())
        with self._lock:
            self._rows.append(stamped)
        return replace(stamped)

    @staticmethod
    def _scope_matches(query_scope: str, row_scope: str) -> bool:
        """Scope match for a consent query (fail-closed, no widening):
          * a GLOBAL grant (row_scope == "") satisfies ANY query (true blanket consent);
          * a query for a SPECIFIC campaign is satisfied by an exact-scope grant;
          * an EMPTY query (query_scope == "") is satisfied ONLY by a global grant —
            it must NOT collapse onto a grant scoped to some *specific other* campaign
            (that was the scope-collapse hole: a no-id campaign inheriting campaign A's
            consent). The engine should pass a real campaign scope; an empty query only
            ever rides true global consent."""
        q = (query_scope or "")
        rs = (row_scope or "")
        if rs == "":
            return True              # global grant satisfies anything
        return q == rs               # specific grant: exact campaign match only

    def rows_for(self, tenant_id: str, principal_ref: str, consent_type: str,
                 scope: str) -> List[ConsentRow]:
        t = (tenant_id or "").strip()
        if not t:
            raise ValueError("consent.rows_for: empty tenant_id (fail-closed)")
        with self._lock:
            out = [replace(r) for r in self._rows
                   if r.tenant_id == t and r.data_principal_ref == principal_ref
                   and r.consent_type == consent_type
                   and self._scope_matches(scope, r.scope)]
        out.sort(key=lambda r: (r.created_at or _now()), reverse=True)
        return out

    def all_rows(self, tenant_id: str) -> List[ConsentRow]:
        t = (tenant_id or "").strip()
        if not t:
            raise ValueError("consent.all_rows: empty tenant_id (fail-closed)")
        with self._lock:
            return [replace(r) for r in self._rows if r.tenant_id == t]


@dataclass(frozen=True)
class ConsentVerdict:
    fresh: bool
    reason: str
    basis: str = ""
    expires_at: Optional[str] = None


class ConsentLedger:
    """Tenant-scoped consent ledger facade. Construct once:
    `ConsentLedger(store, explicit_days=7)`."""

    def __init__(self, store: Optional[ConsentStore] = None, *, explicit_days: int = 7,
                 now_fn: Optional[Callable[[], _dt.datetime]] = None):
        self.store = store or InMemoryConsentStore()
        self.explicit_days = max(1, int(explicit_days))
        self._now = now_fn or _now

    # ------------------------------------------------------------- writes #
    def grant(self, tenant_id: str, principal_ref: str, consent_type: str, *,
              basis: str = BASIS_EXPLICIT, channel: str = "import", scope: str = "",
              evidence_ref: str = "", expires_at: Optional[_dt.datetime] = None) -> ConsentRow:
        """Record a consent grant. For an EXPLICIT basis with no explicit expiry we
        auto-stamp +explicit_days (the 7-day rule). NEVER silently durable: an inferred
        basis with no expiry is recorded but the gate treats missing-expiry-inferred as
        weak (see is_fresh)."""
        now = self._now()
        exp = expires_at
        if exp is None and basis == BASIS_EXPLICIT:
            exp = now + _dt.timedelta(days=self.explicit_days)
        return self.store.append(ConsentRow(
            tenant_id=tenant_id, data_principal_ref=principal_ref, consent_type=consent_type,
            basis=basis, channel=channel, scope=scope, evidence_ref=evidence_ref,
            granted_at=now, expires_at=exp,
        ))

    def revoke(self, tenant_id: str, principal_ref: str, consent_type: str, *,
               scope: str = "", channel: str = "verbal_oncall") -> ConsentRow:
        """Record a revocation (a NEW row stamped revoked_at). Honoured on the next dial."""
        now = self._now()
        return self.store.append(ConsentRow(
            tenant_id=tenant_id, data_principal_ref=principal_ref, consent_type=consent_type,
            basis=BASIS_EXPLICIT, channel=channel, scope=scope,
            granted_at=now, revoked_at=now,
        ))

    # ------------------------------------------------------------- reads #
    def is_fresh(self, tenant_id: str, principal_ref: str, *,
                 consent_type: str = TCCCPR_PLACE_CALL, scope: str = "") -> ConsentVerdict:
        """Dial-time freshness check: the NEWEST row for (tenant, principal, type, scope)
        that is not revoked and not expired. A revocation that is the newest row wins
        (no fresh consent). NEVER raises -> on a store error returns NOT fresh (the
        engine fail-closes the dial)."""
        try:
            rows = self.store.rows_for(tenant_id, principal_ref, consent_type, scope)
        except Exception as exc:  # noqa: BLE001
            log.info("consent.is_fresh store error (treated as not-fresh): %r", exc)
            return ConsentVerdict(False, "consent_store_error")
        if not rows:
            return ConsentVerdict(False, "no_consent_on_record")
        newest = rows[0]
        if newest.revoked_at is not None:
            return ConsentVerdict(False, "consent_revoked", basis=newest.basis)
        now = self._now()
        # an inferred consent with NO expiry is weak — treat as not-fresh (must be
        # backed by a contract-end expires_at), per W26 §4.3 "import is not durable".
        if newest.basis == BASIS_INFERRED and newest.expires_at is None:
            return ConsentVerdict(False, "inferred_consent_without_contract_expiry",
                                  basis=newest.basis)
        if not newest.active_at(now):
            return ConsentVerdict(False, "consent_expired", basis=newest.basis,
                                  expires_at=newest.expires_at.isoformat() if newest.expires_at else None)
        return ConsentVerdict(True, "consent_fresh", basis=newest.basis,
                              expires_at=newest.expires_at.isoformat() if newest.expires_at else None)

    # --------------------------------------------------- retention TTL #
    def expired_principal_refs(self, tenant_id: str, *, ttl_days: int,
                               now: Optional[_dt.datetime] = None) -> List[str]:
        """Principals whose NEWEST consent is older than the retention TTL — the input to
        the purge/erasure job. (The cascade delete is a separate sub-system; this is the
        bookkeeping that drives it.) NEVER raises -> [] on error."""
        ref = now or self._now()
        horizon = ref - _dt.timedelta(days=max(1, int(ttl_days)))
        try:
            rows = self.store.all_rows(tenant_id)
        except Exception as exc:  # noqa: BLE001
            log.info("consent.expired_principal_refs error: %r", exc)
            return []
        newest_by_principal: Dict[str, _dt.datetime] = {}
        for r in rows:
            ts = r.created_at or r.granted_at
            if ts is None:
                continue
            cur = newest_by_principal.get(r.data_principal_ref)
            if cur is None or ts > cur:
                newest_by_principal[r.data_principal_ref] = ts
        return [p for p, ts in newest_by_principal.items() if ts < horizon]
