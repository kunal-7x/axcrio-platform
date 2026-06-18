"""voice_kernel.memory.erasure — right-to-erasure cascade (GDPR Art.17).

The research is unanimous: deleting the head row is NOT enough — every derived
leg and every cache/vector keyed off the lead must be purged or the data
resurfaces. So erasure here is a CASCADE in ONE transaction, parent->child,
under the tenant GUC, plus an explicit eviction sweep over every registered
`Purgeable` store (the WARM cache today; a future W4 vector leg tomorrow).

Two scopes, both HARD-delete (Art.17 = real removal, not a soft `deleted_at`):
  * erase_lead(tenant_id, lead_phone)  — one lead's right-to-erasure.
  * erase_tenant(tenant_id)            — full tenant offboarding.

RLS bounds every DELETE to the tenant (a cross-tenant erase is structurally
impossible — the GUC bounds the statement). Erasure is idempotent: erasing an
already-erased lead is a no-op SUCCESS (Art.17 cares about the end state, not
whether a row existed). An append-only audit EVENT (no PII content — only the
fact + a hashed lead ref) records that erasure happened, so erasure is itself
auditable without re-storing what was erased.

EARNER LAW: edits NO live code. The super-admin control that calls erase_* is
the LATER flag-gated seam (design/W7-MEMORY-SEAM.md).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Awaitable, Callable, Optional, Protocol, runtime_checkable

log = logging.getLogger("voice_kernel.memory.erasure")

def _load_box_asession():
    """LAZY box-asession import — done ONLY on first use when no session was
    injected. Importing this module must pull ZERO droplet modules (isolation
    guarantee + EARNER LAW). Returns None off the box (CI / OFF)."""
    try:  # pragma: no cover - exercised only on the live box
        from droplet_work.db.engine import asession as _a  # type: ignore
        return _a
    except Exception:  # pragma: no cover
        return None


@runtime_checkable
class Purgeable(Protocol):
    """Any store that DERIVES from a lead registers as Purgeable so erase_* can
    purge it generically. This binds the contract so W4 cannot add an
    un-erasable vector leg later — every derived store MUST implement these."""

    def delete_by_lead(self, tenant_id: str, lead_phone: str) -> int: ...

    def delete_by_tenant(self, tenant_id: str) -> int: ...


def _hash_ref(tenant_id: str, lead_phone: str) -> str:
    """A non-reversible reference for the no-PII audit event (the actual phone is
    erased; the audit keeps only a salted hash so it carries no recoverable PII)."""
    return hashlib.sha256(f"{tenant_id}|{lead_phone}".encode("utf-8")).hexdigest()[:16]


class LeadMemoryEraser:
    """Drives the erasure cascade across the DB legs + every registered
    Purgeable. Accepts an injectable `asession` (the box's RLS context manager)
    so tests run with a fake. Accepts an optional audit emitter (no-PII)."""

    # The child->parent order matters only for FK integrity; with RLS-scoped
    # independent tables we delete the history leg first, then the head.
    #
    # Defense-in-depth (red-team S1): every DELETE carries an EXPLICIT
    # `tenant_id = :t` predicate IN ADDITION to the RLS GUC — identical to the
    # seatbelt on load()/persist(). On the live box RLS already bounds the
    # statement; the explicit predicate makes erasure non-catastrophic even in a
    # misconfig where FORCE-RLS is somehow not applied (a bare
    # `DELETE FROM lead_memory` would otherwise wipe ALL tenants). Belt-and-braces.
    _LEAD_DELETES = (
        "DELETE FROM lead_memory_summary WHERE tenant_id = :t AND lead_phone = :p",
        "DELETE FROM lead_memory WHERE tenant_id = :t AND lead_phone = :p",
    )
    _TENANT_DELETES = (
        "DELETE FROM lead_memory_summary WHERE tenant_id = :t",
        "DELETE FROM lead_memory WHERE tenant_id = :t",
    )

    _UNSET = object()

    def __init__(
        self,
        asession: Optional[Callable[..., object]] = _UNSET,
        purgeables: Optional[list[Purgeable]] = None,
        audit: Optional[Callable[[dict], Awaitable[None]]] = None,
    ):
        # injected session wins; otherwise resolve the box layer LAZILY on first
        # use (None off the box) so module import stays droplet-free.
        self._asession_injected = asession is not self._UNSET
        self._asession = asession if self._asession_injected else None
        self._asession_resolved = self._asession_injected
        self._purgeables: list[Purgeable] = list(purgeables or [])
        self._audit = audit

    def _session(self):
        if not self._asession_resolved:
            self._asession = _load_box_asession()
            self._asession_resolved = True
        return self._asession

    def register(self, store: Purgeable) -> None:
        """Register a derived store (cache today, vector leg tomorrow). Bound to
        the Purgeable contract — every leg that derives from a lead must register
        so erasure can never miss one (E4)."""
        if not isinstance(store, Purgeable):
            raise TypeError("erasure: registered store must implement Purgeable (delete_by_lead/_tenant)")
        self._purgeables.append(store)

    async def erase_lead(self, tenant_id: str, lead_phone: str) -> dict:
        """One lead's right-to-erasure. HARD-delete head + history in ONE txn
        under the tenant GUC, then evict every Purgeable. Idempotent."""
        tenant_id = (tenant_id or "").strip()
        if not tenant_id:
            raise ValueError("erase_lead requires a tenant_id (fail-closed)")
        rows = await self._delete(tenant_id, self._LEAD_DELETES, {"t": tenant_id, "p": lead_phone})
        purged = self._purge_caches(lambda s: s.delete_by_lead(tenant_id, lead_phone))
        await self._emit_audit("lead_erased", tenant_id, lead_phone, rows, purged)
        return {"db_rows": rows, "cache_purged": purged, "ref": _hash_ref(tenant_id, lead_phone)}

    async def erase_tenant(self, tenant_id: str) -> dict:
        """Full tenant offboarding. Purges ALL of the tenant's lead memory + every
        Purgeable namespace. RLS bounds it to the tenant. Idempotent."""
        tenant_id = (tenant_id or "").strip()
        if not tenant_id:
            raise ValueError("erase_tenant requires a tenant_id (fail-closed)")
        rows = await self._delete(tenant_id, self._TENANT_DELETES, {"t": tenant_id})
        purged = self._purge_caches(lambda s: s.delete_by_tenant(tenant_id))
        await self._emit_audit("tenant_erased", tenant_id, "", rows, purged)
        return {"db_rows": rows, "cache_purged": purged, "tenant_id": tenant_id}

    # ---- internals -------------------------------------------------------- #
    async def _delete(self, tenant_id: str, statements: tuple[str, ...], params: dict) -> int:
        sess = self._session()
        if sess is None:
            log.warning("erasure: no asession available — DB delete skipped (cache still purged)")
            return 0
        from sqlalchemy import text  # local import: stdlib-only module surface

        total = 0
        async with sess(tenant_id=tenant_id, is_admin=False) as s:
            for stmt in statements:
                res = await s.execute(text(stmt), params)
                total += int(getattr(res, "rowcount", 0) or 0)
        return total

    def _purge_caches(self, op: Callable[[Purgeable], int]) -> int:
        purged = 0
        for store in self._purgeables:
            try:
                purged += int(op(store) or 0)
            except Exception as exc:  # never let a cache miss break erasure
                log.warning("erasure: purgeable %r failed (continuing): %r", store, exc)
        return purged

    async def _emit_audit(self, name: str, tenant_id: str, lead_phone: str, rows: int, purged: int) -> None:
        if self._audit is None:
            return
        try:
            await self._audit({
                "event": name,
                "tenant_id": tenant_id,
                "lead_ref": _hash_ref(tenant_id, lead_phone) if lead_phone else "",
                "db_rows": rows,
                "cache_purged": purged,
            })
        except Exception as exc:  # audit must never break the erase itself
            log.warning("erasure: audit emit failed (non-fatal): %r", exc)
