"""voice_kernel.memory.service — LeadMemoryService: the MemoryService impl.

Implements the FROZEN `MemoryService` Protocol (contracts.py:211-218):
    async load(tenant_id, lead_phone) -> LeadMemory
    async persist(tenant_id, lead_phone, summary: LeadMemory) -> None

HOT / WARM / COLD split:
  * HOT  — the assembled LeadMemory already in the ContextPacket (no I/O; not
           this module's concern — it lives in the packet).
  * WARM — `load()`: ONE indexed PK read at dial, served through a
           tenant-namespaced cache; on miss -> empty LeadMemory() (NEW), never
           raises. RLS supplies the tenant predicate (GUC), with a redundant
           explicit `tenant_id` WHERE as defense-in-depth.
  * COLD — `persist()`: UPSERT the head row + append the history leg, in ONE txn
           under the same GUC; write-side sanitize on every stored string; cache
           refreshed. Also `extract_and_persist()` ties extraction.py +
           lifecycle.py + cards.py into a single post-call call.

Tenant scoping is FAIL-CLOSED: a blank tenant_id raises (S3) — a memory op with
no tenant is a bug, not a wildcard. The tenant_id is the server-stamped
KernelSession.tenant_id routed by the kernel (kernel.py:148).

Reuses the box's `db.engine.asession(tenant_id, is_admin=False)` VERBATIM (the
proven RLS context manager). The import is lazy/injectable so this module imports
with NO DB present and tests run against a fake session. Imports NOTHING from
droplet_work.agent.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Optional, Sequence

from ..packet import Lifecycle, LeadMemory
from .hygiene import sanitize
from ..tokens import clamp_chars
from .cache import LeadMemoryCache
from .cards import LeadCard, build_summary_card
from .extraction import extract_rules, extract_with_llm, prob_for

log = logging.getLogger("voice_kernel.memory")

# clamp_chars appends a 1-char ellipsis when it truncates, so to keep the STORED
# value within the DB CHECK (<= 300) we clamp to 299 — a truncated summary is then
# at most 299 + "…" = 300 chars. The prompt L4 cap is 300; this never exceeds it.
_SUMMARY_CHARS = 299

def _load_box_asession():
    """LAZY import of the box's RLS `asession` — done ONLY on first use when no
    session was injected. Importing this module must pull ZERO droplet modules
    (the voice_kernel isolation guarantee + EARNER LAW), so the import lives here,
    not at module top. Returns None if the box DB layer is absent (OFF/CI)."""
    try:  # pragma: no cover - exercised only on the live box
        from droplet_work.db.engine import asession as _a  # type: ignore
        return _a
    except Exception:  # pragma: no cover
        return None


def _coerce_tuple(val: Any) -> tuple[str, ...]:
    """JSONB -> tuple[str,...]. Accepts a list, a JSON string, or None."""
    if val is None:
        return ()
    if isinstance(val, (list, tuple)):
        return tuple(str(x) for x in val)
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return tuple(str(x) for x in parsed)
        except Exception:
            return (val,) if val else ()
    return ()


def _coerce_lifecycle(val: Any) -> Lifecycle:
    try:
        return Lifecycle(str(val or "new").lower())
    except ValueError:
        return Lifecycle.NEW


def _row_to_memory(row: Any) -> LeadMemory:
    """Map a DB row (mapping or attr-object) to the FROZEN LeadMemory."""
    def g(key: str, default: Any = "") -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        return getattr(row, key, default)

    return LeadMemory(
        name=str(g("name", "") or ""),
        lifecycle=_coerce_lifecycle(g("lifecycle", "new")),
        last_call_summary=clamp_chars(str(g("last_call_summary", "") or ""), _SUMMARY_CHARS),
        open_commitments=_coerce_tuple(g("open_commitments", [])),
        preferred_callback_ts=str(g("preferred_callback_ts", "") or ""),
        do_not_mention=_coerce_tuple(g("do_not_mention", [])),
    )


class LeadMemoryService:
    """The FROZEN MemoryService Protocol impl (async, PG/RLS). Registered via
    `build_kernel(cfg, memory=LeadMemoryService())`."""

    # sentinel so we can tell "no session injected, resolve from the box lazily"
    # apart from "explicitly injected None" (tests pass a fake; the live box uses
    # the lazy box loader). Importing this module pulls ZERO droplet modules.
    _UNSET = object()

    def __init__(
        self,
        asession: Optional[Callable[..., Any]] = _UNSET,
        cache: Optional[LeadMemoryCache] = None,
    ):
        # injectable session factory (the box's RLS asession). If not supplied,
        # resolve it LAZILY from the box on first use (None on CI / OFF). This
        # keeps module import droplet-free (isolation guarantee).
        self._asession_injected = asession is not self._UNSET
        self._asession = asession if self._asession_injected else None
        self._asession_resolved = self._asession_injected
        # NB: an empty LeadMemoryCache is FALSY (len==0), so `cache or ...` would
        # silently swap in a fresh cache and drop the caller's. Use an explicit
        # None check so an injected (empty) cache is honoured.
        self.cache = cache if cache is not None else LeadMemoryCache()

    def _session(self):
        """Resolve the asession factory, importing the box layer LAZILY the first
        time it is needed (only when nothing was injected)."""
        if not self._asession_resolved:
            self._asession = _load_box_asession()
            self._asession_resolved = True
        return self._asession

    # ----------------------------------------------------------- fail-closed #
    @staticmethod
    def _require_tenant(tenant_id: str) -> str:
        t = (tenant_id or "").strip()
        if not t:
            # S3: a memory read/write with no tenant is a bug, not a wildcard.
            raise ValueError("MemoryService requires a non-blank tenant_id (fail-closed)")
        return t

    # ------------------------------------------------------------ WARM: load #
    async def load(self, tenant_id: str, lead_phone: str) -> LeadMemory:
        """ONE PK read at dial, RLS-scoped. Cache-first. Empty-on-miss (NEW),
        never raises a not-found. A blank tenant_id is fail-closed (raises)."""
        tenant_id = self._require_tenant(tenant_id)
        phone = (lead_phone or "").strip()

        cached = self.cache.get(tenant_id, phone)
        if cached is not None:
            return cached

        sess = self._session()
        if sess is None:
            return LeadMemory()  # no DB wired (OFF path / test default) -> empty NEW

        from sqlalchemy import text

        # RLS supplies the tenant predicate via the GUC; the explicit tenant_id in
        # the WHERE is a redundant defense-in-depth seatbelt (S1).
        sql = text(
            "SELECT name, lifecycle, last_call_summary, open_commitments, "
            "preferred_callback_ts, do_not_mention "
            "FROM lead_memory WHERE tenant_id = :t AND lead_phone = :p"
        )
        try:
            async with sess(tenant_id=tenant_id, is_admin=False) as s:
                res = await s.execute(sql, {"t": tenant_id, "p": phone})
                row = res.mappings().first() if hasattr(res, "mappings") else res.first()
        except Exception as exc:
            log.warning("LeadMemoryService.load failed, degrading to empty: %r", exc)
            return LeadMemory()

        mem = _row_to_memory(row) if row else LeadMemory()
        self.cache.put(tenant_id, phone, mem)
        return mem

    # --------------------------------------------------------- COLD: persist #
    async def persist(self, tenant_id: str, lead_phone: str, summary: LeadMemory) -> None:
        """UPSERT the head row + append the history leg, in ONE txn under the
        tenant GUC. Write-side sanitize on every stored string. Cache refreshed.
        `summary` is an ALREADY-RECONCILED LeadMemory (reconciliation happens in
        extraction.extract_*). Blank tenant_id is fail-closed."""
        tenant_id = self._require_tenant(tenant_id)
        phone = (lead_phone or "").strip()

        clean = self._sanitize_memory(summary)
        prob = prob_for(summary)  # internal score derived during extraction (0 if none)

        sess = self._session()
        if sess is None:
            # No DB wired (test default / OFF): keep the cache hot so continuity
            # still works in-process, but there is nothing to persist durably.
            self.cache.put(tenant_id, phone, clean)
            return

        from sqlalchemy import text

        upsert = text(
            "INSERT INTO lead_memory "
            "(tenant_id, lead_phone, name, lifecycle, last_call_summary, "
            " open_commitments, preferred_callback_ts, do_not_mention, "
            " conversion_prob, call_count, updated_at) "
            "VALUES (:t, :p, :name, :lc, :sum, "
            " CAST(:oc AS jsonb), :cb, CAST(:dnm AS jsonb), :prob, 1, now()) "
            "ON CONFLICT (tenant_id, lead_phone) DO UPDATE SET "
            " name = EXCLUDED.name, lifecycle = EXCLUDED.lifecycle, "
            " last_call_summary = EXCLUDED.last_call_summary, "
            " open_commitments = EXCLUDED.open_commitments, "
            " preferred_callback_ts = EXCLUDED.preferred_callback_ts, "
            " do_not_mention = EXCLUDED.do_not_mention, "
            " conversion_prob = EXCLUDED.conversion_prob, "
            " call_count = lead_memory.call_count + 1, updated_at = now()"
        )
        history = text(
            "INSERT INTO lead_memory_summary "
            "(tenant_id, lead_phone, summary, lifecycle_at_write, conversion_prob) "
            "VALUES (:t, :p, :sum, :lc, :prob)"
        )
        params = {
            "t": tenant_id, "p": phone,
            "name": clean.name, "lc": clean.lifecycle.value,
            "sum": clean.last_call_summary,
            "oc": json.dumps(list(clean.open_commitments)),
            "cb": clean.preferred_callback_ts,
            "dnm": json.dumps(list(clean.do_not_mention)),
            "prob": prob,
        }
        try:
            async with sess(tenant_id=tenant_id, is_admin=False) as s:
                await s.execute(upsert, params)
                await s.execute(history, {
                    "t": tenant_id, "p": phone, "sum": clean.last_call_summary,
                    "lc": clean.lifecycle.value, "prob": prob,
                })
        except Exception as exc:
            log.warning("LeadMemoryService.persist failed (non-fatal, COLD): %r", exc)
            return
        self.cache.put(tenant_id, phone, clean)

    # ------------------------------------------------ COLD: extract+persist #
    async def extract_and_persist(
        self,
        *,
        tenant_id: str,
        lead_phone: str,
        turns: Sequence[dict],
        raw_summary: str = "",
        name: str = "",
        llm: Optional[Callable[[str], Awaitable[str]]] = None,
    ) -> LeadMemory:
        """The one-call COLD post-call entry: load prior -> extract salient facts
        (rules, or LLM-assisted) -> persist the reconciled LeadMemory. Returns the
        stored memory (for the summary card). Never raises into the call
        lifecycle. This is what the LATER `_finalize_call` seam invokes."""
        tenant_id = self._require_tenant(tenant_id)
        prior = await self.load(tenant_id, lead_phone)
        if llm is not None:
            mem = await extract_with_llm(
                turns=turns, prior=prior, raw_summary=raw_summary, name=name, llm=llm
            )
        else:
            mem = extract_rules(turns=turns, prior=prior, raw_summary=raw_summary, name=name)
        await self.persist(tenant_id, lead_phone, mem)
        return mem

    def summary_card(self, mem: LeadMemory, conversion_prob: int = 0) -> LeadCard:
        """Build the AI summary card the panel renders (pure)."""
        return build_summary_card(mem, conversion_prob=conversion_prob)

    # ------------------------------------------------------------- internals #
    @staticmethod
    def _sanitize_memory(mem: LeadMemory) -> LeadMemory:
        """Write-side sanitize (S4): NFKC + zero-width strip + fence defang on
        every stored string, summary re-clamped to 300. A poisoned prior call
        cannot smuggle an invisible fence-breakout into the store."""
        from dataclasses import replace

        return replace(
            mem,
            name=sanitize(mem.name),
            last_call_summary=clamp_chars(sanitize(mem.last_call_summary), _SUMMARY_CHARS),
            open_commitments=tuple(sanitize(c) for c in mem.open_commitments),
            preferred_callback_ts=sanitize(mem.preferred_callback_ts),
            do_not_mention=tuple(sanitize(d) for d in mem.do_not_mention),
        )
