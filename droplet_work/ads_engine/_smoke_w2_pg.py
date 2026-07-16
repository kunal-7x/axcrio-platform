"""Offline W2 smoke — ads_engine.store against the Postgres FORCE-RLS backend.

PRECONDITION (the harness sets these): ADS_PG_DSN points at a Postgres connection as a
NOSUPERUSER/NOBYPASSRLS role (so FORCE RLS binds — a superuser would BYPASS RLS and the
isolation proof would be meaningless), and db/ddl_ads_engine.sql is applied. Run:
    ADS_STORE_BACKEND=postgres ADS_PG_DSN=... python -c \
      "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_w2_pg as s; s.main()"

Asserts:
  * apiCompatible — the SAME store.py accessors behave identically on PG: collection put/get/
    delete, cas + VersionConflict, per-tenant append/get + replace, budget credit/debit/ledger,
    page-map link/conflict/unlink, tenant-scoped get_row None for cross-tenant.
  * rlsEnforced — INFRASTRUCTURAL isolation: tenant A cannot read tenant B rows; a FORGED raw
    insert of a tenant_id='B' row while the connection GUC is tenant A is BLOCKED by the RLS
    WITH CHECK policy (not by app code); a forged BODY tenant_id is server-stamped to A.
"""

from __future__ import annotations

import sys


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def _reset_for_test():
    """Truncate the W2 tables so the smoke is repeatable (admin GUC to bypass RLS for cleanup)."""
    from ads_engine import store_pg
    eng = store_pg._engine()
    with eng.session("", is_admin=True) as conn:
        conn.execute("TRUNCATE ads_rows, ads_tenant_rows, ads_page_tenant_map")


def main() -> int:
    if "droplet_work" not in ",".join(sys.path):
        sys.path.insert(0, "droplet_work")

    import os
    os.environ["ADS_STORE_BACKEND"] = "postgres"

    from ads_engine import store
    store._reset_backend()

    # Confirm we actually resolved the PG backend (not the json fallback).
    backend = store._pg()
    _assert(backend is not None and getattr(backend, "name", "") == "postgres",
            "backend resolves to postgres (ADS_STORE_BACKEND=postgres)")

    _reset_for_test()

    A, B = "t_A", "t_B"

    # ---- apiCompatible: collection put/get/delete ----
    store.put_row(B, "campaigns", "cmp_B1", {"plan_id": "cmp_B1", "name": "B-secret"})
    store.put_row(A, "campaigns", "cmp_A1", {"plan_id": "cmp_A1", "name": "A-own"})
    a_rows = store.get_collection(A, "campaigns")
    _assert(set(a_rows.keys()) == {"cmp_A1"}, "get_collection returns ONLY tenant A's rows")
    _assert(a_rows["cmp_A1"].get("tenant_id") == A, "stored row carries server-stamped tenant_id")

    # ---- rlsEnforced: cross-tenant reads are empty ----
    _assert(store.get_row(A, "campaigns", "cmp_B1") is None,
            "rls: tenant A get_row of B's row => None")
    leak = any(c.get("name") == "B-secret" for c in store.list_campaigns(A))
    _assert(not leak, "rls: tenant A list_campaigns never sees B-secret")

    # ---- rlsEnforced: forged BODY tenant_id is server-stamped to A ----
    store.put_row(A, "campaigns", "cmp_A2", {"plan_id": "cmp_A2", "tenant_id": B})
    stamped = store.get_row(A, "campaigns", "cmp_A2")
    _assert(stamped is not None and stamped.get("tenant_id") == A,
            "rls: a forged body tenant_id is overwritten to the caller's tenant")

    # ---- rlsEnforced: a FORGED RAW insert of a B row under A's GUC is DB-BLOCKED ----
    from ads_engine import store_pg
    eng = store_pg._engine()
    forged_blocked = False
    try:
        with eng.session(A, is_admin=False) as conn:
            conn.execute(
                "INSERT INTO ads_rows (tenant_id, collection, row_id, data, version) "
                "VALUES (%s, %s, %s, %s, %s)",
                (B, "campaigns", "forged_raw", store_pg._json({"x": 1}), 0),
            )
        forged_blocked = False
    except Exception:  # RLS WITH CHECK violation (row-level security policy)
        forged_blocked = True
    _assert(forged_blocked, "rls: a raw INSERT of tenant B while GUC=A is blocked by WITH CHECK")
    # and it left no row visible to B either
    _assert(store.get_row(B, "campaigns", "forged_raw") is None,
            "rls: the blocked forged insert created no B row")

    # ---- apiCompatible: delete is tenant-scoped ----
    _assert(store.delete_row(A, "campaigns", "cmp_A2") is True, "delete_row removes own row")
    _assert(store.delete_row(A, "campaigns", "cmp_B1") is False,
            "delete_row of a cross-tenant row is a no-op (RLS-invisible)")

    # ---- apiCompatible: CAS + VersionConflict ----
    r0 = store.cas_row(A, "bandit_state", "cmp_A1", None, {"arm": "v1"})
    _assert(int(r0.get("version", 0)) == 1, "cas: first write bumps version to 1")
    r1 = store.cas_row(A, "bandit_state", "cmp_A1", 1, {"arm": "v2", "version": 1})
    _assert(int(r1.get("version", 0)) == 2, "cas: second write at expected v=1 bumps to 2")
    conflict = False
    try:
        store.cas_row(A, "bandit_state", "cmp_A1", 1, {"arm": "v3", "version": 1})  # stale expected
    except store.VersionConflict:
        conflict = True
    _assert(conflict, "cas: a stale expected_version raises VersionConflict")

    # ---- apiCompatible: per-tenant append / get / cross-tenant isolation ----
    store.append_tenant_row(A, "leads_ads", {"lead": "A1"})
    store.append_tenant_row(A, "leads_ads", {"lead": "A2"})
    store.append_tenant_row(B, "leads_ads", {"lead": "B1"})
    a_leads = store.get_tenant_file(A, "leads_ads")
    _assert([r.get("lead") for r in a_leads] == ["A1", "A2"],
            "per-tenant get returns own rows in append order")
    b_leads = store.get_tenant_file(B, "leads_ads")
    _assert([r.get("lead") for r in b_leads] == ["B1"], "per-tenant file isolated across tenants")
    store.put_tenant_file(A, "leads_ads", [{"lead": "A_only"}])  # replace
    _assert([r.get("lead") for r in store.get_tenant_file(A, "leads_ads")] == ["A_only"],
            "put_tenant_file replaces the tenant's list (idempotent re-migrate)")

    # ---- apiCompatible: budget credit/debit/ledger (paise, floored at zero) ----
    store.credit_budget(A, 500000, ref={"intent_id": "i1"})
    _assert(store.get_budget_account(A)["balance_minor"] == 500000, "budget: credit raises balance")
    store.debit_budget(A, 300000, ref={"campaign_id": "c1"})
    _assert(store.get_budget_account(A)["balance_minor"] == 200000, "budget: debit draws down")
    store.debit_budget(A, 999999, ref={"campaign_id": "c1"})
    _assert(store.get_budget_account(A)["balance_minor"] == 0, "budget: debit floored at zero")
    led = store.get_budget_ledger(A, 50)
    _assert(len(led) == 3, f"budget: append-only ledger has 3 rows (got {len(led)})")
    _assert(store.get_budget_account(B)["balance_minor"] == 0, "budget: tenant B balance isolated at 0")

    # ---- apiCompatible: page-map link / conflict / unlink ----
    store.link_page_to_tenant(A, "page_123", actor="ownerA")
    _assert(store.get_tenant_for_page("page_123") == A, "page-map: resolves the owning tenant")
    conflict = False
    try:
        store.link_page_to_tenant(B, "page_123", actor="hijackB")
    except store.PageOwnershipConflict:
        conflict = True
    _assert(conflict, "page-map: a second tenant claiming the page => PageOwnershipConflict")
    _assert(store.unlink_page(B, "page_123") is False, "page-map: a non-owner cannot unlink")
    _assert(store.unlink_page(A, "page_123") is True, "page-map: the owner can unlink")
    _assert(store.get_tenant_for_page("page_123") is None, "page-map: unmapped after unlink (fail-closed)")

    # ---- apiCompatible: list_tenant_ids (privileged sweep) sees both tenants ----
    tids = set(store.list_tenant_ids("campaigns"))
    _assert(A in tids, "list_tenant_ids enumerates tenants with rows (privileged sweep)")

    print("\nALL ads_engine W2 Postgres-RLS smoke assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
