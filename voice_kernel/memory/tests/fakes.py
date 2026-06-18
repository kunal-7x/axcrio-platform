"""Fake async session that SIMULATES Postgres RLS on the lead_memory tables.

We do NOT spin up Postgres in CI. Instead this fake honors the EXACT RLS
contract the real DDL enforces: every statement runs under a tenant GUC set by
`asession(tenant_id=...)`, and the policy is `is_admin OR tenant_id = GUC`. The
fake stores rows in a dict and applies that predicate to SELECT/INSERT/UPDATE/
DELETE — so a cross-tenant read returns nothing and a forged-tenant INSERT is
rejected, exactly as FORCE-RLS would. This proves the SERVICE's contract
(GUC-scoped, empty-on-cross-tenant, WITH-CHECK rejects a forged write) without a
live box.
"""
from __future__ import annotations

import re
from typing import Any


class _Result:
    def __init__(self, rows: list[dict], rowcount: int = 0):
        self._rows = rows
        self.rowcount = rowcount

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class FakeRLSSession:
    """One transaction. Knows the current GUC tenant (set by asession). Enforces
    the FORCE-RLS predicate on every statement against a shared store."""

    def __init__(self, store: dict, guc_tenant: str, is_admin: bool):
        self.store = store  # {(tenant, phone): row dict}, plus store["_history"] list
        self.guc_tenant = guc_tenant
        self.is_admin = is_admin

    def _visible(self, tenant: str) -> bool:
        return self.is_admin or (tenant == self.guc_tenant)

    async def execute(self, stmt: Any, params: dict | None = None):
        sql = str(getattr(stmt, "text", stmt)).strip()
        params = params or {}
        low = sql.lower()

        if low.startswith("select"):
            t, p = params.get("t"), params.get("p")
            rows = []
            key = (t, p)
            row = self.store.get(key)
            # RLS: only rows whose tenant matches the GUC (or admin) are visible.
            if row and self._visible(row["tenant_id"]):
                rows = [dict(row)]
            return _Result(rows)

        if low.startswith("insert into lead_memory_summary"):
            t = params.get("t")
            # WITH CHECK: a forged cross-tenant write is rejected.
            if not self._visible(t):
                raise PermissionError("RLS WITH CHECK: forged tenant_id on summary insert")
            self.store.setdefault("_history", []).append(dict(params))
            return _Result([], rowcount=1)

        if low.startswith("insert into lead_memory"):
            t, p = params.get("t"), params.get("p")
            if not self._visible(t):
                raise PermissionError("RLS WITH CHECK: forged tenant_id on lead_memory insert")
            key = (t, p)
            existing = self.store.get(key)
            call_count = (existing["call_count"] + 1) if existing else 1
            self.store[key] = {
                "tenant_id": t, "lead_phone": p,
                "name": params.get("name", ""),
                "lifecycle": params.get("lc", "new"),
                "last_call_summary": params.get("sum", ""),
                "open_commitments": params.get("oc", "[]"),
                "preferred_callback_ts": params.get("cb", ""),
                "do_not_mention": params.get("dnm", "[]"),
                "conversion_prob": params.get("prob", 0),
                "call_count": call_count,
            }
            return _Result([], rowcount=1)

        if low.startswith("delete from lead_memory_summary"):
            hist = self.store.get("_history", [])
            before = len(hist)
            # per-lead deletes scope by lead_phone; whole-tenant deletes do not.
            # (The erasure SQL leads with `tenant_id = :t`, so detect the phone
            # predicate by the lead_phone token, not a fixed "where lead_phone".)
            if "lead_phone" in low:
                p = params.get("p")
                self.store["_history"] = [
                    h for h in hist
                    if not (h.get("p") == p and self._visible(h.get("t", "")))
                ]
            else:  # whole-tenant
                self.store["_history"] = [
                    h for h in hist if not self._visible(h.get("t", ""))
                ]
            return _Result([], rowcount=before - len(self.store.get("_history", [])))

        if low.startswith("delete from lead_memory"):
            removed = 0
            for key in list(self.store.keys()):
                if key == "_history":
                    continue
                t, p = key
                if not self._visible(t):
                    continue  # RLS: cannot touch another tenant's row
                if "lead_phone" in low and p != params.get("p"):
                    continue
                self.store.pop(key, None)
                removed += 1
            return _Result([], rowcount=removed)

        return _Result([])


class fake_asession_factory:
    """Drop-in for db.engine.asession bound to a shared store. Usage:
        svc = LeadMemoryService(asession=fake_asession_factory(store))
    Each `async with factory(tenant_id=..., is_admin=...) as s:` yields a
    FakeRLSSession scoped to that GUC tenant."""

    def __init__(self, store: dict | None = None):
        self.store = store if store is not None else {}

    def __call__(self, tenant_id: str = "", is_admin: bool = False):
        outer = self

        class _Ctx:
            async def __aenter__(self_inner):
                return FakeRLSSession(outer.store, (tenant_id or "").strip(), is_admin)

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()
