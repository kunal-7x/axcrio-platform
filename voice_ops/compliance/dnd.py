"""voice_ops.compliance.dnd — DND / NCPR scrub-before-dial (W26 Tier A #3 / §4.2).

The mandatory pre-dial gate: every number is checked against TWO layers before it may
be queued —
  (1) the NCPR national register (the DND list), cached in `dnd_cache` with a <=30-day
      freshness duty (a stale row is a MISS -> re-scrub before dial); and
  (2) the local per-tenant suppression list (the existing on-call "say stop / press 9"
      opt-outs — caller.py `_suppressed_set` / suppression.json).
A hit on EITHER layer blocks the dial (unless a fresh EXPLICIT consent row overrides
NCPR for opted-in categories — that override is resolved by the consent engine, not here).

PII-MINIMISATION: no raw phone number is stored at rest — only a salted SHA-256 hash
(the `dnd_cache.number_hash` PK). The scrub itself is via the operator/DLT DND-scrub API
per access provider; the cache makes the dial-time check O(1) while honouring the refresh
duty. On a cache MISS the gate is FAIL-CLOSED: block-and-requeue rather than dial an
un-scrubbed number (design/W26 §3.3).

Shape mirrors the rest of voice_ops: a `DndStore` Protocol + a real, dependency-free
`InMemoryDndStore` (tests + local fallback). A LATER seam wave adds a `PgDndStore` against
the FORCE-RLS `dnd_cache` table; the engine depends only on the Protocol. Tenant-scoped,
fail-closed on empty tenant.

PURE: stdlib only; NO droplet_work / asyncpg; NEVER raises into the gate (a store error
during a Tier-A check -> the engine treats it as fail-closed block).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import re
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Protocol, runtime_checkable

log = logging.getLogger("voice_ops.compliance.dnd")

CATEGORY_ALL = "all"
_DIGITS = re.compile(r"\D+")


def normalize_e164(number: str) -> str:
    """Best-effort E.164 normalisation for hashing (India-default +91)."""
    d = _DIGITS.sub("", number or "")
    if not d:
        return ""
    if d.startswith("0091"):
        d = d[4:]
    elif d.startswith("0") and len(d) == 11:
        d = d[1:]
    if len(d) == 10 and d[0] in "6789":
        d = "91" + d
    return "+" + d if not d.startswith("+") else d


def number_hash(number: str, salt: str = "") -> str:
    """Salted SHA-256 of the normalised number — the only representation stored at rest
    (no raw PII). Stable per (number, salt)."""
    norm = normalize_e164(number)
    return hashlib.sha256(f"{salt}|{norm}".encode("utf-8")).hexdigest()


@dataclass
class DndRecord:
    number_hash: str
    category: str = CATEGORY_ALL
    listed: bool = False
    refreshed_at: Optional[_dt.datetime] = None


@runtime_checkable
class DndStore(Protocol):
    """NCPR cache + local suppression contract. InMemory test impl + a future
    PgDndStore (FORCE-RLS dnd_cache) both satisfy this."""

    def get(self, number_hash: str, category: str) -> Optional[DndRecord]: ...
    def put(self, rec: DndRecord) -> None: ...
    def add_suppression(self, tenant_id: str, number_hash: str) -> None: ...
    def is_suppressed(self, tenant_id: str, number_hash: str) -> bool: ...


class InMemoryDndStore:
    """Thread-safe, dependency-free DndStore. NCPR cache keyed by (hash, category) +
    a per-tenant suppression set keyed by (tenant, hash)."""

    def __init__(self):
        self._ncpr: Dict[str, DndRecord] = {}             # "hash::category" -> record
        self._suppress: Dict[str, set] = {}               # tenant -> {hash}
        self._lock = threading.Lock()

    def get(self, number_hash: str, category: str) -> Optional[DndRecord]:
        with self._lock:
            return self._ncpr.get(f"{number_hash}::{category}")

    def put(self, rec: DndRecord) -> None:
        with self._lock:
            self._ncpr[f"{rec.number_hash}::{rec.category}"] = rec

    def add_suppression(self, tenant_id: str, number_hash: str) -> None:
        t = (tenant_id or "").strip()
        if not t:
            return
        with self._lock:
            self._suppress.setdefault(t, set()).add(number_hash)

    def is_suppressed(self, tenant_id: str, number_hash: str) -> bool:
        t = (tenant_id or "").strip()
        if not t:
            return False
        with self._lock:
            return number_hash in self._suppress.get(t, set())


@dataclass(frozen=True)
class ScrubResult:
    """The DND verdict. `block` True => do not dial. `reason` carries the layer."""
    block: bool
    reason: str
    layer: str = ""                 # 'ncpr' | 'suppression' | 'cache_miss' | 'clear'
    needs_rescrub: bool = False     # True on a stale/missing NCPR cache row


class DndScrubber:
    """Tenant-scoped scrub-before-dial. Construct once: `DndScrubber(store, salt, refresh_days)`.
    Fail-CLOSED: a cache miss (no fresh NCPR row) blocks-and-requeues (`needs_rescrub`)."""

    def __init__(self, store: Optional[DndStore] = None, *, salt: str = "",
                 refresh_days: int = 30, now_fn: Optional[Callable[[], _dt.datetime]] = None):
        self.store = store or InMemoryDndStore()
        self.salt = salt
        self.refresh_days = max(1, int(refresh_days))
        self._now = now_fn or (lambda: _dt.datetime.now(_dt.timezone.utc))

    def _fresh(self, rec: DndRecord) -> bool:
        if rec.refreshed_at is None:
            return False
        ref = rec.refreshed_at
        if getattr(ref, "tzinfo", None) is None:
            ref = ref.replace(tzinfo=_dt.timezone.utc)
        return (self._now() - ref) <= _dt.timedelta(days=self.refresh_days)

    def scrub(self, tenant_id: str, number: str, *, category: str = CATEGORY_ALL) -> ScrubResult:
        """Check both layers. Order: local suppression (cheap, tenant opt-out is absolute)
        then NCPR cache (fresh? listed?). A stale/missing NCPR row -> block + needs_rescrub
        (fail-closed). NEVER raises."""
        t = (tenant_id or "").strip()
        if not t:
            return ScrubResult(True, "empty_tenant_fail_closed", "fail_closed")
        h = number_hash(number, self.salt)

        # Layer 2: local per-tenant suppression (on-call opt-out) — absolute block.
        try:
            if self.store.is_suppressed(t, h):
                return ScrubResult(True, "lead_on_local_suppression_list", "suppression")
        except Exception as exc:  # noqa: BLE001 — fail-closed on a Tier-A check error
            log.info("dnd suppression check failed (fail-closed): %r", exc)
            return ScrubResult(True, "suppression_check_error_fail_closed", "fail_closed")

        # Layer 1: NCPR national register cache.
        try:
            rec = self.store.get(h, category) or self.store.get(h, CATEGORY_ALL)
        except Exception as exc:  # noqa: BLE001
            log.info("dnd ncpr check failed (fail-closed): %r", exc)
            return ScrubResult(True, "ncpr_check_error_fail_closed", "fail_closed")

        if rec is None or not self._fresh(rec):
            # cache miss / stale -> must re-scrub before dialing (fail-closed).
            return ScrubResult(True, "ncpr_cache_miss_or_stale_rescrub_required",
                               "cache_miss", needs_rescrub=True)
        if rec.listed:
            return ScrubResult(True, "number_on_ncpr_dnd_register", "ncpr")
        return ScrubResult(False, "clear", "clear")

    # ---- mutations used by the on-call opt-out path + the scrub-refresh job ----
    def record_optout(self, tenant_id: str, number: str) -> None:
        """On-call "stop calling me" -> immediate local suppression (honoured next dial)."""
        t = (tenant_id or "").strip()
        if not t:
            return
        self.store.add_suppression(t, number_hash(number, self.salt))

    def cache_ncpr(self, number: str, *, listed: bool, category: str = CATEGORY_ALL) -> None:
        """Write a fresh NCPR scrub result into the cache (called by the scrub-refresh job
        after hitting the operator DND-scrub API)."""
        self.store.put(DndRecord(number_hash=number_hash(number, self.salt),
                                 category=category, listed=bool(listed),
                                 refreshed_at=self._now()))
